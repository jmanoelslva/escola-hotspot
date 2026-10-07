"""Senhas temporárias para visitantes.

Cada visitante é um usuário do hotspot com comentário
"painel-visitante até AAAA-MM-DD HH:MM | descrição" e um agendamento no
próprio MikroTik (/system scheduler) que, na hora marcada, desconecta, apaga o
cookie, remove o usuário e se apaga. Funciona mesmo com o painel fechado.
"""

import re
import secrets
from datetime import datetime, timedelta

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

USUARIOS = "/ip/hotspot/user"
ATIVOS = "/ip/hotspot/active"
COOKIES = "/ip/hotspot/cookie"
AGENDAMENTOS = "/system/scheduler"

PREFIXO = "painel-visitante"
PREFIXO_AGENDAMENTO = "painel-visitante-"
MAX_QUANTIDADE = 50
MAX_DIAS = 30

_COMENTARIO = re.compile(r"^painel-visitante até (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: \| (.*))?$")
_MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def validade(minutos: int | None, ate_fim_do_dia: bool, agora: datetime | None = None) -> datetime:
    agora = (agora or datetime.now()).replace(second=0, microsecond=0)
    if ate_fim_do_dia:
        return agora.replace(hour=23, minute=59)
    if not minutos or minutos < 15 or minutos > MAX_DIAS * 24 * 60:
        raise util.ErroDados(f"Validade entre 15 minutos e {MAX_DIAS} dias.")
    return agora + timedelta(minutes=minutos)


def comentario(ate: datetime, descricao: str) -> str:
    texto = f"{PREFIXO} até {ate:%Y-%m-%d %H:%M}"
    descricao = " ".join((descricao or "").split())[:80]
    return f"{texto} | {descricao}" if descricao else texto


def ler_comentario(texto: str) -> tuple[datetime | None, str]:
    m = _COMENTARIO.match(texto or "")
    if not m:
        return None, ""
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M"), m.group(2) or ""


def _nome_novo(existentes: set[str]) -> str:
    """visita1, visita2...: o menor número livre (fácil de ditar e digitar)."""
    numero = 1
    while f"visita{numero}" in existentes:
        numero += 1
    return f"visita{numero}"


def _senha_nova() -> str:
    """6 números: no celular é só trocar uma vez para o teclado numérico."""
    return "".join(secrets.choice("0123456789") for _ in range(6))


def _script_expirar(nome: str) -> str:
    # Nomes visitaN só têm letras e números: seguros dentro das aspas.
    return (f':do {{ /ip hotspot active remove [find user="{nome}"] }} on-error={{}}; '
            f':do {{ /ip hotspot cookie remove [find user="{nome}"] }} on-error={{}}; '
            f':do {{ /ip hotspot user remove [find name="{nome}"] }} on-error={{}}; '
            f'/system scheduler remove [find name="{PREFIXO_AGENDAMENTO}{nome}"]')


def agendar_uma_vez(mk: Mikrotik, corpo: dict, quando: datetime) -> None:
    """Agendador que roda uma vez em `quando` (o próprio on-event deve se apagar)."""
    corpo = {"policy": "read,write,test", **corpo, "start-time": f"{quando:%H:%M:%S}", "interval": "0s"}
    # RouterOS 7.10+ aceita a data AAAA-MM-DD; versões antigas usam mmm/dd/aaaa.
    try:
        mk.criar(AGENDAMENTOS, {**corpo, "start-date": f"{quando:%Y-%m-%d}"})
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        mk.criar(AGENDAMENTOS, {**corpo, "start-date": f"{_MESES[quando.month - 1]}/{quando:%d/%Y}"})


def _agendar(mk: Mikrotik, nome: str, ate: datetime) -> None:
    agendar_uma_vez(mk, {
        "name": f"{PREFIXO_AGENDAMENTO}{nome}",
        "on-event": _script_expirar(nome),
        "comment": f"Painel do Hotspot: remove o visitante {nome}",
    }, ate)


def criar(mk: Mikrotik, quantidade: int, ate: datetime, perfil: str, descricao: str) -> list[dict]:
    if quantidade < 1 or quantidade > MAX_QUANTIDADE:
        raise util.ErroDados(f"Quantidade entre 1 e {MAX_QUANTIDADE}.")
    if ate <= datetime.now():
        raise util.ErroDados("A validade precisa terminar no futuro.")
    existentes = {u.get("name", "") for u in mk.listar(USUARIOS)}
    texto = comentario(ate, descricao)
    criados = []
    for _ in range(quantidade):
        nome = _nome_novo(existentes)
        existentes.add(nome)
        senha = _senha_nova()
        corpo = {"name": nome, "password": senha, "comment": texto}
        if perfil:
            corpo["profile"] = perfil
        mk.criar(USUARIOS, corpo)
        try:
            _agendar(mk, nome, ate)
        except ErroMikrotik:
            # Sem o agendamento o visitante não expiraria: desfaz este usuário.
            for u in mk.listar(USUARIOS, {"name": nome}):
                mk.remover(USUARIOS, u[".id"])
            raise
        criados.append({"usuario": nome, "senha": senha, "ate": f"{ate:%Y-%m-%dT%H:%M}", "descricao": descricao.strip()})
    return criados


def listar(mk: Mikrotik) -> list[dict]:
    agendados = {a.get("name", "")[len(PREFIXO_AGENDAMENTO):] for a in mk.listar(AGENDAMENTOS)
                 if a.get("name", "").startswith(PREFIXO_AGENDAMENTO)}
    conectados = {a.get("user", "") for a in mk.listar(ATIVOS)}
    agora = datetime.now()
    lista = []
    for u in mk.listar(USUARIOS):
        ate, descricao = ler_comentario(u.get("comment", ""))
        if ate is None:
            continue
        nome = u.get("name", "")
        lista.append({
            "id": u.get(".id"),
            "usuario": nome,
            "senha": u.get("password", ""),
            "perfil": u.get("profile", ""),
            "descricao": descricao,
            "ate": f"{ate:%Y-%m-%dT%H:%M}",
            "expirado": ate <= agora,
            "agendado": nome in agendados,
            "conectado": nome in conectados,
        })
    return sorted(lista, key=lambda v: (v["ate"], v["usuario"]))


def encerrar_varios(mk: Mikrotik, ids: list[str] | None) -> dict:
    """Encerra os visitantes indicados (None = todos), lendo cada tabela uma vez só."""
    usuarios = [u for u in mk.listar(USUARIOS) if ler_comentario(u.get("comment", ""))[0] is not None]
    if ids is not None:
        pedidos = set(ids)
        usuarios = [u for u in usuarios if u.get(".id") in pedidos]
    nomes = {u.get("name", "") for u in usuarios}
    if not nomes:
        return {"encerrados": [], "erros": []}
    ativos = mk.listar(ATIVOS)
    cookies = mk.listar(COOKIES)
    agendamentos = mk.listar(AGENDAMENTOS)
    encerrados, erros = [], []
    for usuario in usuarios:
        nome = usuario.get("name", "")
        try:
            for ativo in ativos:
                if ativo.get("user") == nome:
                    mk.remover(ATIVOS, ativo[".id"])
            for cookie in cookies:
                if cookie.get("user") == nome:
                    mk.remover(COOKIES, cookie[".id"])
            mk.remover(USUARIOS, usuario[".id"])
            for agendamento in agendamentos:
                if agendamento.get("name") == f"{PREFIXO_AGENDAMENTO}{nome}":
                    mk.remover(AGENDAMENTOS, agendamento[".id"])
            encerrados.append(nome)
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            erros.append(f"{nome}: {erro.mensagem}")
    return {"encerrados": encerrados, "erros": erros}


def encerrar(mk: Mikrotik, item_id: str) -> str:
    usuario = mk.obter(USUARIOS, item_id)
    nome = usuario.get("name", "")
    if ler_comentario(usuario.get("comment", ""))[0] is None:
        raise util.ErroDados("Esse usuário não é um visitante criado pelo painel.")
    for ativo in mk.listar(ATIVOS):
        if ativo.get("user") == nome:
            mk.remover(ATIVOS, ativo[".id"])
    for cookie in mk.listar(COOKIES):
        if cookie.get("user") == nome:
            mk.remover(COOKIES, cookie[".id"])
    mk.remover(USUARIOS, item_id)
    for agendamento in mk.listar(AGENDAMENTOS):
        if agendamento.get("name") == f"{PREFIXO_AGENDAMENTO}{nome}":
            mk.remover(AGENDAMENTOS, agendamento[".id"])
    return nome
