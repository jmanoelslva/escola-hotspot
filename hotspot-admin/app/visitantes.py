"""Senhas temporárias para visitantes.

Cada visitante é um usuário do hotspot com comentário
"painel-visitante por 120 min [prazo AAAA-MM-DD HH:MM] [lote AAAAMMDDHHMMSS] | descrição"
(ou "por fim do dia"). O lote junta os cartões criados de uma vez (a data e
hora da criação). O tempo só começa no primeiro acesso. Com prazo, o cartão já
nasce com o agendamento "painel-visitante-<nome>" (comentário "...prazo...")
marcado para o prazo: se ninguém usar até lá, ele some. O vigia (script +
agendador "painel-visitantes", a cada 30 s no próprio MikroTik) vê quem entrou
pela primeira vez e troca o agendamento do prazo (ou cria um) pelo do tempo de
uso, que no fim desconecta, apaga o cookie, remove o usuário e se apaga.
Funciona mesmo com o painel fechado.

Cartões antigos ("painel-visitante até AAAA-MM-DD HH:MM") continuam valendo
até a data marcada, com o agendamento criado junto com eles.
"""

import re
import secrets
import unicodedata
from datetime import datetime, timedelta

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

USUARIOS = "/ip/hotspot/user"
ATIVOS = "/ip/hotspot/active"
COOKIES = "/ip/hotspot/cookie"
AGENDAMENTOS = "/system/scheduler"
SCRIPTS = "/system/script"

PREFIXO = "painel-visitante"
PREFIXO_AGENDAMENTO = "painel-visitante-"
VIGIA = "painel-visitantes"  # sem o "-" do PREFIXO_AGENDAMENTO: não é confundido com um visitante
MAX_QUANTIDADE = 200
MAX_DIAS = 30
FIM_DO_DIA = "fim do dia"

_COMENTARIO = re.compile(r"^painel-visitante até (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: \| (.*))?$")
_COMENTARIO_POR = re.compile(
    r"^painel-visitante por (\d+ min|fim do dia)(?: prazo (\d{4}-\d{2}-\d{2} \d{2}:\d{2}))?(?: lote (\d{14}))?(?: \| (.*))?$")
_MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
COMENTARIO_PRAZO = "Painel do Hotspot: prazo para o primeiro acesso de "
MAX_PRAZO_DIAS = 365

# Roda no MikroTik a cada 30 s. "painel-visitante por " tem 21 letras. Se já há um
# agendamento com o nome do visitante, só segue quando ele é o do prazo (não usado ainda).
# Só nomes com letras minúsculas e números (os que o painel cria): um nome com aspas,
# feito fora do painel, não entra no on-event.
SCRIPT_VIGIA = r''':foreach u in=[/ip hotspot user find where comment~"^painel-visitante por " && !(name~"[^a-z0-9]")] do={
    :local nome [/ip hotspot user get $u name]
    :local tarefa ("painel-visitante-" . $nome)
    :local antigo [/system scheduler find where name=$tarefa]
    :local livre ([:len $antigo] = 0)
    :if (!$livre) do={ :set livre ([/system scheduler get [:pick $antigo 0] comment] ~ "^Painel do Hotspot: prazo") }
    :if ($livre) do={
        :if (([:len [/ip hotspot active find where user=$nome]] > 0) || ([/ip hotspot user get $u uptime] > 0s)) do={
            /system scheduler remove [find where name=$tarefa]
            :local c [/ip hotspot user get $u comment]
            :local dur 1m
            :if ([:pick $c 21 31] = "fim do dia") do={
                :set dur ([:totime "23:59:00"] - [/system clock get time])
                :if ($dur < 1m) do={ :set dur 1m }
            } else={
                :set dur [:totime ([:tonum [:pick $c 21 [:find $c " min"]]] * 60)]
            }
            /system scheduler add name=$tarefa interval=$dur start-date=[/system clock get date] start-time=[/system clock get time] policy=read,write,test comment=("Painel do Hotspot: remove o visitante " . $nome) on-event=(":do { /ip hotspot active remove [find user=\"" . $nome . "\"] } on-error={}; :do { /ip hotspot cookie remove [find user=\"" . $nome . "\"] } on-error={}; :do { /ip hotspot user remove [find name=\"" . $nome . "\"] } on-error={}; /system scheduler remove [find name=\"" . $tarefa . "\"]")
            :log info ("painel-visitantes: " . $nome . " entrou pela primeira vez, sai em " . $dur)
        }
    }
}
'''


def duracao(minutos: int | None, ate_fim_do_dia: bool) -> int | None:
    """Minutos de uso a partir do primeiro acesso; None = até 23:59 do dia do primeiro acesso."""
    if ate_fim_do_dia:
        return None
    if not minutos or minutos < 15 or minutos > MAX_DIAS * 24 * 60:
        raise util.ErroDados(f"Validade entre 15 minutos e {MAX_DIAS} dias.")
    return minutos


def texto_duracao(minutos: int | None) -> str:
    if minutos is None:
        return "até o fim do dia"
    if minutos % 1440 == 0:
        return f"{minutos // 1440} dia" + ("s" if minutos > 1440 else "")
    if minutos % 60 == 0:
        return f"{minutos // 60} hora" + ("s" if minutos > 60 else "")
    return f"{minutos} minutos"


def validar_prazo(prazo: datetime | None, agora: datetime | None = None) -> datetime | None:
    """Prazo opcional para o primeiro acesso: no futuro e até 1 ano."""
    if prazo is None:
        return None
    agora = agora or datetime.now()
    prazo = prazo.replace(second=0, microsecond=0, tzinfo=None)
    if prazo <= agora:
        raise util.ErroDados("O prazo para usar o cartão precisa estar no futuro.")
    if prazo > agora + timedelta(days=MAX_PRAZO_DIAS):
        raise util.ErroDados("O prazo para usar o cartão pode ser de até 1 ano.")
    return prazo


def comentario(minutos: int | None, descricao: str, prazo: datetime | None = None, lote: str = "") -> str:
    texto = f"{PREFIXO} por {FIM_DO_DIA if minutos is None else f'{minutos} min'}"
    if prazo:
        texto += f" prazo {prazo:%Y-%m-%d %H:%M}"
    if lote:
        texto += f" lote {lote}"
    descricao = " ".join((descricao or "").split())[:80]
    return f"{texto} | {descricao}" if descricao else texto


def ler_comentario(texto: str) -> tuple[datetime | None, str]:
    """Cartão antigo, com data marcada: (validade, descrição); senão (None, "")."""
    m = _COMENTARIO.match(texto or "")
    if not m:
        return None, ""
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M"), m.group(2) or ""


def ler_duracao(texto: str) -> tuple[bool, int | None, datetime | None, str, str]:
    """Cartão novo: (True, minutos ou None = fim do dia, prazo ou None, lote, descrição);
    senão (False, None, None, "", "")."""
    m = _COMENTARIO_POR.match(texto or "")
    if not m:
        return False, None, None, "", ""
    minutos = None if m.group(1) == FIM_DO_DIA else int(m.group(1).split()[0])
    prazo = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M") if m.group(2) else None
    return True, minutos, prazo, m.group(3) or "", m.group(4) or ""


def criado_em(lote: str) -> str:
    """Lote "20261107003015" -> "2026-11-07T00:30:15"."""
    try:
        return f"{datetime.strptime(lote, '%Y%m%d%H%M%S'):%Y-%m-%dT%H:%M:%S}"
    except ValueError:
        return ""


def comentario_reservado(texto: str) -> bool:
    """Comentário que faria um usuário comum ser tratado (e apagado) como visitante."""
    return (texto or "").strip().lower().startswith(PREFIXO)


def eh_visitante(texto: str) -> bool:
    return ler_comentario(texto)[0] is not None or ler_duracao(texto)[0]


def _data_hora(texto: str) -> datetime | None:
    """next-run do agendador: "2026-11-07 14:30:00" (7.10+) ou "nov/07/2026 14:30:00"."""
    try:
        data, hora = (texto or "").split(" ", 1)
        if "/" in data:
            mes, dia, ano = data.split("/")
            data = f"{ano}-{_MESES.index(mes.lower()) + 1:02d}-{dia}"
        return datetime.strptime(f"{data} {hora[:8]}", "%Y-%m-%d %H:%M:%S")
    except (ValueError, IndexError):
        return None


def garantir_vigia(mk: Mikrotik) -> None:
    """Cria ou atualiza o script e o agendador que começam a contar o tempo no primeiro acesso."""
    script = next(iter(mk.listar(SCRIPTS, {"name": VIGIA})), None)
    if not script:
        mk.criar(SCRIPTS, {"name": VIGIA, "source": SCRIPT_VIGIA, "policy": "read,write,test",
                           "comment": "Painel do Hotspot: tempo dos visitantes a partir do primeiro acesso"})
    elif script.get("source") != SCRIPT_VIGIA:
        mk.alterar(SCRIPTS, script[".id"], {"source": SCRIPT_VIGIA})
    agendador = next(iter(mk.listar(AGENDAMENTOS, {"name": VIGIA})), None)
    if not agendador:
        mk.criar(AGENDAMENTOS, {"name": VIGIA, "interval": "30s", "start-time": "startup", "policy": "read,write,test",
                                "on-event": f"/system script run {VIGIA}",
                                "comment": "Painel do Hotspot: tempo dos visitantes a partir do primeiro acesso"})
    elif util.sim(agendador.get("disabled")):
        mk.alterar(AGENDAMENTOS, agendador[".id"], {"disabled": "false"})


PREFIXO_PADRAO = "visita"
MAX_PREFIXO = 10


def prefixo_nome(texto: str) -> str:
    """"Reunião de Pais" -> "reuniaodep": só letras minúsculas sem acento, até 10; vazio = "visita"."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    letras = re.sub(r"[^a-z]", "", sem_acento.lower())[:MAX_PREFIXO]
    return letras or PREFIXO_PADRAO


def _nome_novo(existentes: set[str], prefixo: str) -> str:
    """pais1, pais2...: o menor número livre com esse nome (fácil de ditar e digitar)."""
    numero = 1
    while f"{prefixo}{numero}" in existentes:
        numero += 1
    return f"{prefixo}{numero}"


def _senha_nova() -> str:
    """6 números: no celular é só trocar uma vez para o teclado numérico."""
    return "".join(secrets.choice("0123456789") for _ in range(6))


def _script_expirar(nome: str) -> str:
    # Nomes como pais3 só têm letras e números: seguros dentro das aspas.
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


def _agendar_prazo(mk: Mikrotik, nome: str, prazo: datetime) -> None:
    agendar_uma_vez(mk, {
        "name": f"{PREFIXO_AGENDAMENTO}{nome}",
        "on-event": _script_expirar(nome),
        "comment": f"{COMENTARIO_PRAZO}{nome}",
    }, prazo)


def criar(mk: Mikrotik, quantidade: int, minutos: int | None, perfil: str, descricao: str, nome: str = "",
          prazo: datetime | None = None) -> list[dict]:
    """minutos: tempo de uso a partir do primeiro acesso (None = até 23:59 daquele dia);
    prazo: se ninguém usar até essa hora, o cartão some (None = guardado sem prazo)."""
    if quantidade < 1 or quantidade > MAX_QUANTIDADE:
        raise util.ErroDados(f"Quantidade entre 1 e {MAX_QUANTIDADE}.")
    prazo = validar_prazo(prazo)
    garantir_vigia(mk)  # sem o vigia o tempo nunca começaria a contar
    usuarios = mk.listar(USUARIOS)
    existentes = {u.get("name", "") for u in usuarios}
    # Lote = hora da criação; duas criações no mesmo segundo não podem cair no mesmo lote.
    lotes = {ler_duracao(u.get("comment", ""))[3] for u in usuarios}
    quando = datetime.now()
    while f"{quando:%Y%m%d%H%M%S}" in lotes:
        quando += timedelta(seconds=1)
    lote = f"{quando:%Y%m%d%H%M%S}"
    texto = comentario(minutos, descricao, prazo, lote)
    prefixo = prefixo_nome(nome)
    criados = []
    for _ in range(quantidade):
        usuario = _nome_novo(existentes, prefixo)
        existentes.add(usuario)
        senha = _senha_nova()
        corpo = {"name": usuario, "password": senha, "comment": texto}
        if perfil:
            corpo["profile"] = perfil
        mk.criar(USUARIOS, corpo)
        if prazo:
            try:
                _agendar_prazo(mk, usuario, prazo)
            except ErroMikrotik:
                # Sem o agendamento o prazo não valeria: desfaz este usuário.
                for u in mk.listar(USUARIOS, {"name": usuario}):
                    mk.remover(USUARIOS, u[".id"])
                raise
        criados.append({"usuario": usuario, "senha": senha, "duracao": texto_duracao(minutos),
                        "prazo": f"{prazo:%Y-%m-%dT%H:%M}" if prazo else "", "ate": "",
                        "aguardando": True, "lote": lote, "criado_em": criado_em(lote),
                        "descricao": " ".join((descricao or "").split())[:80]})
    return criados


def listar(mk: Mikrotik) -> list[dict]:
    agendamentos = {a.get("name", "")[len(PREFIXO_AGENDAMENTO):]: a for a in mk.listar(AGENDAMENTOS)
                    if a.get("name", "").startswith(PREFIXO_AGENDAMENTO)}
    vigia = next((a for a in mk.listar(AGENDAMENTOS, {"name": VIGIA}) if not util.sim(a.get("disabled"))), None)
    conectados = {a.get("user", "") for a in mk.listar(ATIVOS)}
    agora = datetime.now()
    lista = []
    for u in mk.listar(USUARIOS):
        comentario_usuario = u.get("comment", "")
        nome = u.get("name", "")
        tarefa = agendamentos.get(nome)
        ate, descricao = ler_comentario(comentario_usuario)
        novo, minutos, prazo, lote, descricao_nova = ler_duracao(comentario_usuario)
        if ate is not None:  # cartão antigo, com data marcada desde a criação
            item = {"ate": f"{ate:%Y-%m-%dT%H:%M}", "duracao": "", "prazo": "", "aguardando": False,
                    "lote": "", "criado_em": "",
                    "expirado": ate <= agora, "agendado": tarefa is not None}
        elif novo:
            descricao = descricao_nova
            em_uso = tarefa is not None and not tarefa.get("comment", "").startswith(COMENTARIO_PRAZO)
            fim = _data_hora(tarefa.get("next-run", "")) if em_uso else None
            item = {"ate": f"{fim:%Y-%m-%dT%H:%M}" if fim else "", "duracao": texto_duracao(minutos),
                    "prazo": f"{prazo:%Y-%m-%dT%H:%M}" if prazo else "", "aguardando": not em_uso,
                    "lote": lote, "criado_em": criado_em(lote),
                    "expirado": (fim is not None and fim <= agora) or (not em_uso and prazo is not None and prazo <= agora),
                    # Aguardando: precisa do vigia (e do agendamento do prazo, se houver).
                    "agendado": em_uso or (vigia is not None and (prazo is None or tarefa is not None))}
        else:
            continue
        lista.append({
            "id": u.get(".id"),
            "usuario": nome,
            "senha": u.get("password", ""),
            "perfil": u.get("profile", ""),
            "descricao": descricao,
            **item,
            "conectado": nome in conectados,
        })
    return sorted(lista, key=lambda v: util.chave_natural(v["usuario"]))


def encerrar_varios(mk: Mikrotik, ids: list[str] | None) -> dict:
    """Encerra os visitantes indicados (None = todos), lendo cada tabela uma vez só."""
    usuarios = [u for u in mk.listar(USUARIOS) if eh_visitante(u.get("comment", ""))]
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
    if not eh_visitante(usuario.get("comment", "")):
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
