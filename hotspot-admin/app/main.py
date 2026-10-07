"""Painel web do hotspot MikroTik: usuários, conectados, bypass/bloqueio e importação."""

import io
import json
import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Literal

from fastapi import Depends, FastAPI, File, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import administradores, ajustes, aps, backup, controle, historico, importacao, qrcodes, rede, rede_alunos, sistema, util, visitantes
from .config import APP_VERSION, PASTA_PROJETO, config
from .mikrotik import EnderecoMikrotik, ErroAutenticacao, ErroConexao, ErroMikrotik, Mikrotik
from .sessoes import LimiteLogin, Sessao, Sessoes

USUARIOS = "/ip/hotspot/user"
PERFIS = "/ip/hotspot/user/profile"
ATIVOS = "/ip/hotspot/active"
BINDINGS = "/ip/hotspot/ip-binding"
HOSTS = "/ip/hotspot/host"
SERVIDORES = "/ip/hotspot"
LEASES = "/ip/dhcp-server/lease"
ARQUIVOS = "/file"
PERFIS_HOTSPOT = "/ip/hotspot/profile"
COOKIES_HOTSPOT = "/ip/hotspot/cookie"

COOKIE = "painel_hotspot"
MAC_VAZIO = "00:00:00:00:00:00"
ARQUIVO_MAX_BYTES = 5 * 1024 * 1024

PASTA_STATIC = PASTA_PROJETO / "static"

# Registro de quem fez o quê (dados/acoes.log), além do log do próprio MikroTik.
config.pasta_dados.mkdir(parents=True, exist_ok=True)
log_acoes = logging.getLogger("painel.acoes")
if not log_acoes.handlers:
    _arquivo = RotatingFileHandler(config.pasta_dados / "acoes.log", maxBytes=2_000_000,
                                   backupCount=5, encoding="utf-8")
    _arquivo.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log_acoes.addHandler(_arquivo)
    log_acoes.setLevel(logging.INFO)

app = FastAPI(title="Painel do Hotspot", version=APP_VERSION, docs_url=None, redoc_url=None, openapi_url=None)
app.state.sessoes = Sessoes(config.sessao_minutos)
app.state.limite_login = LimiteLogin()
app.state.transport = None  # os testes trocam por um MikroTik falso
app.state.endereco = EnderecoMikrotik(ajustes.endereco_mikrotik(config.pasta_dados, config), config.mikrotik_verificar_tls)
app.state.atualizacao = sistema.VerificadorAtualizacao()


# ---------------------------------------------------------------- infraestrutura

@app.middleware("http")
async def cabecalhos(request: Request, call_next):
    caminho = request.url.path
    # Pedidos que alteram algo precisam do cabeçalho X-Painel: outro site não
    # consegue mandá-lo sem uma pré-verificação CORS, que este servidor não aceita.
    if caminho.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-painel") != "1":
            return JSONResponse({"erro": "Requisição recusada."}, status_code=403)
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if caminho.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.exception_handler(ErroMikrotik)
async def erro_mikrotik(request: Request, erro: ErroMikrotik):
    resposta = JSONResponse({"erro": erro.mensagem}, status_code=erro.status)
    if isinstance(erro, ErroConexao):
        app.state.endereco.esquecer()  # na próxima, testa HTTPS/HTTP de novo
    if isinstance(erro, ErroAutenticacao) and request.url.path != "/api/login":
        # A senha mudou no MikroTik ou o usuário foi removido: encerra a sessão.
        app.state.sessoes.encerrar(request.cookies.get(COOKIE))
        resposta.delete_cookie(COOKIE)
    return resposta


@app.exception_handler(util.ErroDados)
async def erro_dados(_: Request, erro: util.ErroDados):
    return JSONResponse({"erro": str(erro)}, status_code=400)


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "?"


def sessao_atual(request: Request) -> Sessao:
    sessao = app.state.sessoes.obter(request.cookies.get(COOKIE))
    if sessao is None:
        raise ErroMikrotik("Sessão encerrada. Entre novamente.", 401)
    return sessao


def conectar(usuario: str, senha: str) -> Mikrotik:
    return Mikrotik(app.state.endereco.url(), usuario, senha, config.mikrotik_verificar_tls,
                    config.mikrotik_timeout, transport=app.state.transport)


def tipo_conexao() -> str:
    try:
        return "HTTPS" if app.state.endereco.url().startswith("https://") else "HTTP"
    except ErroMikrotik:
        return ""


def mikrotik(sessao: Sessao = Depends(sessao_atual)):
    with conectar(sessao.usuario, sessao.senha) as mk:
        yield mk


def registrar(sessao: Sessao, acao: str) -> None:
    log_acoes.info("%s %s", sessao.usuario, acao)


# ---------------------------------------------------------------- conversões

def _usuario(item: dict) -> dict:
    mac = item.get("mac-address", "")
    return {
        "id": item.get(".id"),
        "nome": item.get("name", ""),
        "senha": item.get("password", ""),
        "perfil": item.get("profile", ""),
        "comentario": item.get("comment", ""),
        "limite_tempo": "" if item.get("limit-uptime") in (None, "0s", "0") else item.get("limit-uptime"),
        "mac": "" if mac in ("", MAC_VAZIO) else mac,
        "desativado": util.sim(item.get("disabled")),
        "uptime": item.get("uptime", ""),
        "bytes_in": util.inteiro(item.get("bytes-in")),
        "bytes_out": util.inteiro(item.get("bytes-out")),
    }


def _ativo(item: dict) -> dict:
    return {
        "id": item.get(".id"),
        "usuario": item.get("user", ""),
        "ip": item.get("address", ""),
        "mac": item.get("mac-address", ""),
        "uptime": item.get("uptime", ""),
        "restante": item.get("session-time-left", ""),
        "bytes_in": util.inteiro(item.get("bytes-in")),
        "bytes_out": util.inteiro(item.get("bytes-out")),
        "login_por": item.get("login-by", ""),
        "comentario": item.get("comment", ""),
    }


def _dispositivo(item: dict) -> dict:
    return {
        "id": item.get(".id"),
        "tipo": item.get("type", "regular"),
        "mac": item.get("mac-address", ""),
        "ip": item.get("address", ""),
        "servidor": item.get("server", "all"),
        "comentario": item.get("comment", ""),
        "desativado": util.sim(item.get("disabled")),
    }


def _nomes_existentes(mk: Mikrotik) -> set[str]:
    return {u.get("name", "") for u in mk.listar(USUARIOS)}


def _perfis(mk: Mikrotik) -> set[str]:
    return {p.get("name", "") for p in mk.listar(PERFIS)}


# ---------------------------------------------------------------- modelos

class Login(BaseModel):
    usuario: str = Field(max_length=64)
    senha: str = Field(max_length=128)


class NovoUsuario(BaseModel):
    nome: str = Field(max_length=64)
    senha: str = Field(max_length=64)
    perfil: str = Field(default="", max_length=64)
    comentario: str = Field(default="", max_length=200)
    limite_tempo: str = Field(default="", max_length=20)
    mac: str = Field(default="", max_length=20)


class AlterarUsuario(BaseModel):
    nome: str | None = Field(default=None, max_length=64)
    senha: str | None = Field(default=None, max_length=64)
    perfil: str | None = Field(default=None, max_length=64)
    comentario: str | None = Field(default=None, max_length=200)
    limite_tempo: str | None = Field(default=None, max_length=20)
    mac: str | None = Field(default=None, max_length=20)
    desativado: bool | None = None


class Ids(BaseModel):
    ids: list[str] = Field(max_length=2000)


class NovoDispositivo(BaseModel):
    tipo: Literal["bypassed", "blocked"]
    mac: str = Field(max_length=20)
    ip: str = Field(default="", max_length=15)
    comentario: str = Field(default="", max_length=200)
    servidor: str = Field(default="all", max_length=64)


class AlterarDispositivo(BaseModel):
    tipo: Literal["bypassed", "blocked"] | None = None
    mac: str | None = Field(default=None, max_length=20)
    ip: str | None = Field(default=None, max_length=15)
    comentario: str | None = Field(default=None, max_length=200)
    desativado: bool | None = None


class ItemImportacao(BaseModel):
    usuario: str = Field(max_length=64)
    senha: str = Field(max_length=64)
    comentario: str = Field(default="", max_length=200)
    perfil: str = Field(default="", max_length=64)


class Importar(BaseModel):
    perfil: str = Field(default="", max_length=64)
    linhas: list[ItemImportacao] = Field(max_length=importacao.MAX_LINHAS)


class Lote(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=2000)
    acao: Literal["ativar", "desativar", "perfil"]
    perfil: str = Field(default="", max_length=64)


class DadosPerfil(BaseModel):
    nome: str | None = Field(default=None, max_length=32)
    download_mbps: float | None = None
    envio_mbps: float | None = None
    aparelhos: int | None = None
    tempo_sessao: str | None = Field(default=None, max_length=20)


class DadosHorario(BaseModel):
    ativo: bool
    inicio: str = Field(default="07:00", max_length=5)
    fim: str = Field(default="17:00", max_length=5)
    dias: list[str] = Field(default_factory=list, max_length=7)


class NovoBloqueio(BaseModel):
    dominio: str = Field(max_length=300)
    motivo: str = Field(default="", max_length=100)


class Dominio(BaseModel):
    dominio: str = Field(default="", max_length=200)


class NovosVisitantes(BaseModel):
    quantidade: int = Field(ge=1, le=visitantes.MAX_QUANTIDADE)
    minutos: int | None = Field(default=None, ge=0, le=visitantes.MAX_DIAS * 24 * 60)
    ate_fim_do_dia: bool = False
    perfil: str = Field(default="", max_length=64)
    descricao: str = Field(default="", max_length=80)
    nome: str = Field(default="", max_length=40)


class EncerrarVisitantes(BaseModel):
    todos: bool = False
    ids: list[str] = Field(default_factory=list, max_length=500)


class Wifi(BaseModel):
    ssid: str = Field(default="", max_length=32)
    seguranca: Literal["aberta", "wpa"] = "aberta"
    senha: str = Field(default="", max_length=63)


class Ligar(BaseModel):
    ativo: bool


class NovoAdministrador(BaseModel):
    nome: str = Field(max_length=64)
    senha: str = Field(max_length=64)
    grupo: str = Field(default=administradores.GRUPO_PAINEL, max_length=64)
    comentario: str = Field(default="", max_length=100)


class AlterarAdministrador(BaseModel):
    senha: str | None = Field(default=None, max_length=64)
    grupo: str | None = Field(default=None, max_length=64)
    comentario: str | None = Field(default=None, max_length=100)
    desativado: bool | None = None


class DadosAP(BaseModel):
    nome: str = Field(max_length=60)
    ip: str = Field(max_length=15)


class DadosEscola(BaseModel):
    nome: str = Field(max_length=200)
    cidade: str = Field(default="", max_length=200)


class ConexaoMikrotik(BaseModel):
    ip: str = Field(default="", max_length=253)
    porta: int | None = None


class LiberarAlunos(BaseModel):
    minutos: int


class JanelaAlunos(BaseModel):
    inicio: str = Field(max_length=5)
    fim: str = Field(max_length=5)
    dias: list[int] = Field(default_factory=list, max_length=7)


class ConfigAlunos(BaseModel):
    interface: str = Field(max_length=64)
    janelas: list[JanelaAlunos] = Field(default_factory=list, max_length=rede_alunos.MAX_JANELAS)


class ModoAlunos(BaseModel):
    modo: Literal["horario", "aberta", "fechada"]


class Aviso(BaseModel):
    texto: str = Field(default="", max_length=500)


class NomeBackup(BaseModel):
    nome: str = Field(max_length=60)


def _id_valido(item_id: str) -> str:
    # IDs do RouterOS têm a forma *1A; nada além disso vai para a URL.
    if not (item_id.startswith("*") and item_id[1:].isalnum() and len(item_id) <= 12):
        raise util.ErroDados("Identificador inválido.")
    return item_id


# ---------------------------------------------------------------- sessão

@app.post("/api/login")
def login(dados: Login, request: Request, response: Response):
    ip = ip_cliente(request)
    if app.state.limite_login.bloqueado(ip):
        raise ErroMikrotik("Muitas tentativas erradas. Aguarde 15 minutos.", 429)
    usuario = dados.usuario.strip()
    if not usuario or not dados.senha:
        raise util.ErroDados("Informe usuário e senha.")
    try:
        with conectar(usuario, dados.senha) as mk:
            identidade = mk.identidade()
            mk.listar(PERFIS)  # confere se o usuário pode ler o hotspot
    except ErroAutenticacao:
        app.state.limite_login.errou(ip)
        log_acoes.info("%s login recusado (ip %s)", usuario, ip)
        raise
    app.state.limite_login.acertou(ip)
    token = app.state.sessoes.criar(usuario, dados.senha, identidade)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
    log_acoes.info("%s entrou (ip %s)", usuario, ip)
    _backup_do_dia(usuario, dados.senha)
    return {"usuario": usuario, "identidade": identidade, "conexao": tipo_conexao()}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    app.state.sessoes.encerrar(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/sessao")
def sessao(s: Sessao = Depends(sessao_atual)):
    return {"usuario": s.usuario, "identidade": s.identidade, "conexao": tipo_conexao()}


@app.get("/api/info")
def info():
    escola = ajustes.escola(config.pasta_dados, config)
    return {"escola": escola["nome"], "cidade": escola["cidade"], "versao": APP_VERSION}


# ---------------------------------------------------------------- usuários

@app.get("/api/perfis")
def perfis(mk: Mikrotik = Depends(mikrotik)):
    return sorted(_perfis(mk))


@app.get("/api/servidores")
def servidores(mk: Mikrotik = Depends(mikrotik)):
    return sorted(s.get("name", "") for s in mk.listar(SERVIDORES))


@app.get("/api/usuarios")
def listar_usuarios(mk: Mikrotik = Depends(mikrotik)):
    return sorted((_usuario(u) for u in _usuarios_comuns(mk)), key=lambda u: util.chave_natural(u["nome"]))


def _usuarios_comuns(mk: Mikrotik) -> list[dict]:
    """Usuários do hotspot sem os visitantes (que têm a própria tela) e sem os do sistema."""
    return [u for u in mk.listar(USUARIOS)
            if not util.sim(u.get("default")) and u.get("name") != "default-trial"
            and visitantes.ler_comentario(u.get("comment", ""))[0] is None]


@app.post("/api/usuarios")
def criar_usuario(dados: NovoUsuario, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    corpo = {
        "name": util.validar_usuario(dados.nome),
        "password": util.validar_senha(dados.senha),
        "comment": dados.comentario.strip(),
    }
    if dados.perfil:
        corpo["profile"] = dados.perfil
    tempo = util.validar_tempo(dados.limite_tempo)
    if tempo:
        corpo["limit-uptime"] = tempo
    if dados.mac.strip():
        corpo["mac-address"] = util.normalizar_mac(dados.mac)
    criado = mk.criar(USUARIOS, corpo)
    registrar(s, f"criou usuário {corpo['name']}")
    return _usuario(criado or corpo)


@app.patch("/api/usuarios/{item_id}")
def alterar_usuario(item_id: str, dados: AlterarUsuario, mk: Mikrotik = Depends(mikrotik),
                    s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    corpo: dict[str, str] = {}
    if dados.nome is not None:
        corpo["name"] = util.validar_usuario(dados.nome)
    if dados.senha:
        corpo["password"] = util.validar_senha(dados.senha)
    if dados.perfil:
        corpo["profile"] = dados.perfil
    if dados.comentario is not None:
        corpo["comment"] = dados.comentario.strip()
    if dados.limite_tempo is not None:
        corpo["limit-uptime"] = util.validar_tempo(dados.limite_tempo) or "0s"
    if dados.mac is not None:
        corpo["mac-address"] = util.normalizar_mac(dados.mac) if dados.mac.strip() else MAC_VAZIO
    if dados.desativado is not None:
        corpo["disabled"] = "true" if dados.desativado else "false"
    if not corpo:
        raise util.ErroDados("Nada para alterar.")
    atual = mk.obter(USUARIOS, item_id)
    alterado = mk.alterar(USUARIOS, item_id, corpo)
    campos = ", ".join("senha" if c == "password" else c for c in corpo)
    registrar(s, f"alterou usuário {atual.get('name')} ({campos})")
    return _usuario(alterado or {**atual, **corpo})


@app.delete("/api/usuarios/{item_id}")
def remover_usuario(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    atual = mk.obter(USUARIOS, item_id)
    mk.remover(USUARIOS, item_id)
    registrar(s, f"excluiu usuário {atual.get('name')}")
    return {"ok": True}


@app.post("/api/usuarios/excluir")
def remover_varios(dados: Ids, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    nomes = {u.get(".id"): u.get("name") for u in mk.listar(USUARIOS)}
    removidos, erros = 0, []
    for item_id in dados.ids:
        _id_valido(item_id)
        try:
            mk.remover(USUARIOS, item_id)
            removidos += 1
            registrar(s, f"excluiu usuário {nomes.get(item_id, item_id)}")
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            erros.append(f"{nomes.get(item_id, item_id)}: {erro.mensagem}")
    return {"removidos": removidos, "erros": erros}


# ---------------------------------------------------------------- conectados

@app.get("/api/conectados")
def conectados(mk: Mikrotik = Depends(mikrotik)):
    return sorted((_ativo(a) for a in mk.listar(ATIVOS)), key=lambda a: a["usuario"].lower())


@app.delete("/api/conectados/{item_id}")
def desconectar(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    atual = mk.obter(ATIVOS, item_id)
    # Primeiro o cookie (login automático do perfil com login-by=cookie): sem
    # isso o aparelho entraria sozinho de novo logo depois de desconectado.
    cookies = _remover_cookies(mk, atual.get("mac-address", ""), atual.get("user", ""))
    mk.remover(ATIVOS, item_id)
    registrar(s, f"desconectou {atual.get('user')} ({atual.get('mac-address')})"
                 + (f" e apagou {cookies} cookie(s)" if cookies else ""))
    return {"ok": True, "cookies": cookies}


def _remover_cookies(mk: Mikrotik, mac: str, usuario: str) -> int:
    """Apaga os cookies do hotspot deste aparelho (pelo MAC; sem MAC, pelo usuário)."""
    removidos = 0
    for cookie in mk.listar(COOKIES_HOTSPOT):
        mesmo_aparelho = mac and cookie.get("mac-address", "").upper() == mac.upper()
        mesmo_usuario = not mac and usuario and cookie.get("user") == usuario
        if mesmo_aparelho or mesmo_usuario:
            mk.remover(COOKIES_HOTSPOT, cookie[".id"])
            removidos += 1
    return removidos


# ---------------------------------------------------------------- bypass e bloqueio

@app.get("/api/dispositivos")
def dispositivos(mk: Mikrotik = Depends(mikrotik)):
    itens = [_dispositivo(b) for b in mk.listar(BINDINGS)]
    return sorted(itens, key=lambda d: (d["tipo"], d["comentario"].lower(), d["mac"]))


@app.get("/api/aparelhos")
def aparelhos(mk: Mikrotik = Depends(mikrotik)):
    """Aparelhos vistos agora no hotspot, com o nome que mandaram ao DHCP (ajuda a achar a TV)."""
    nomes: dict[str, str] = {}
    try:
        for lease in mk.listar(LEASES):
            mac = lease.get("mac-address", "").upper()
            nome = lease.get("comment") or lease.get("host-name") or ""
            if mac and nome:
                nomes[mac] = nome
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        pass  # sem DHCP no roteador ou sem permissão: segue sem os nomes
    resultado = []
    for host in mk.listar(HOSTS):
        mac = host.get("mac-address", "").upper()
        resultado.append({
            "mac": mac,
            "ip": host.get("address", ""),
            "nome": nomes.get(mac, ""),
            "autorizado": util.sim(host.get("authorized")),
            "bypass": util.sim(host.get("bypassed")),
        })
    return sorted(resultado, key=lambda h: (h["nome"] == "", h["nome"].lower(), h["ip"]))


@app.get("/api/rede")
def ver_rede(mk: Mikrotik = Depends(mikrotik)):
    """Todos os aparelhos: no hotspot (com ou sem login) e no DHCP de qualquer rede."""
    return rede.todos(mk)


@app.post("/api/dispositivos")
def criar_dispositivo(dados: NovoDispositivo, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    corpo = {
        "type": dados.tipo,
        "mac-address": util.normalizar_mac(dados.mac),
        "comment": dados.comentario.strip(),
        "server": dados.servidor or "all",
    }
    ip = util.validar_ip(dados.ip)
    if ip:
        corpo["address"] = ip
    criado = mk.criar(BINDINGS, corpo)
    registrar(s, f"cadastrou {dados.tipo} {corpo['mac-address']} ({corpo['comment']})")
    return _dispositivo(criado or corpo)


@app.patch("/api/dispositivos/{item_id}")
def alterar_dispositivo(item_id: str, dados: AlterarDispositivo, mk: Mikrotik = Depends(mikrotik),
                        s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    corpo: dict[str, str] = {}
    if dados.tipo is not None:
        corpo["type"] = dados.tipo
    if dados.mac is not None:
        corpo["mac-address"] = util.normalizar_mac(dados.mac)
    if dados.ip is not None:
        corpo["address"] = util.validar_ip(dados.ip) or "0.0.0.0"
    if dados.comentario is not None:
        corpo["comment"] = dados.comentario.strip()
    if dados.desativado is not None:
        corpo["disabled"] = "true" if dados.desativado else "false"
    if not corpo:
        raise util.ErroDados("Nada para alterar.")
    atual = mk.obter(BINDINGS, item_id)
    alterado = mk.alterar(BINDINGS, item_id, corpo)
    registrar(s, f"alterou aparelho {atual.get('mac-address')} ({', '.join(corpo)})")
    return _dispositivo(alterado or {**atual, **corpo})


@app.delete("/api/dispositivos/{item_id}")
def remover_dispositivo(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    atual = mk.obter(BINDINGS, item_id)
    mk.remover(BINDINGS, item_id)
    registrar(s, f"removeu aparelho {atual.get('mac-address')} ({atual.get('comment', '')})")
    return {"ok": True}


# ---------------------------------------------------------------- importação

@app.post("/api/importar/previa")
def previa_importacao(arquivo: UploadFile = File(...), s: Sessao = Depends(sessao_atual)):
    conteudo = arquivo.file.read(ARQUIVO_MAX_BYTES + 1)
    if len(conteudo) > ARQUIVO_MAX_BYTES:
        raise util.ErroDados("Arquivo grande demais (máximo de 5 MB).")
    linhas = importacao.ler_planilha(arquivo.filename or "", conteudo)
    with conectar(s.usuario, s.senha) as mk:
        importacao.conferir(linhas, _nomes_existentes(mk), _perfis(mk))
    return {"linhas": [l.para_dict() for l in linhas]}


@app.post("/api/importar")
def importar(dados: Importar, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    resultado = []
    criados = 0
    for item in dados.linhas:
        corpo = {"comment": item.comentario.strip()}
        try:
            corpo["name"] = util.validar_usuario(item.usuario)
            corpo["password"] = util.validar_senha(item.senha)
        except util.ErroDados as erro:
            resultado.append({"usuario": item.usuario, "ok": False, "erro": str(erro)})
            continue
        perfil = item.perfil or dados.perfil
        if perfil:
            corpo["profile"] = perfil
        try:
            mk.criar(USUARIOS, corpo)
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            resultado.append({"usuario": item.usuario, "ok": False, "erro": erro.mensagem})
            continue
        criados += 1
        resultado.append({"usuario": item.usuario, "ok": True, "erro": ""})
    registrar(s, f"importou {criados} usuário(s) de planilha")
    return {"criados": criados, "resultado": resultado}


# ---------------------------------------------------------------- ações em lote, senha e exportação

@app.post("/api/usuarios/lote")
def lote_usuarios(dados: Lote, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    if dados.acao == "perfil":
        if dados.perfil not in _perfis(mk):
            raise util.ErroDados("Escolha um perfil que exista no MikroTik.")
        corpo = {"profile": dados.perfil}
        descricao = f"perfil {dados.perfil}"
    else:
        corpo = {"disabled": "true" if dados.acao == "desativar" else "false"}
        descricao = "desativou" if dados.acao == "desativar" else "ativou"
    nomes = {u.get(".id"): u.get("name") for u in mk.listar(USUARIOS)}
    alterados, erros = 0, []
    for item_id in dados.ids:
        _id_valido(item_id)
        try:
            mk.alterar(USUARIOS, item_id, corpo)
            alterados += 1
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            erros.append(f"{nomes.get(item_id, item_id)}: {erro.mensagem}")
    registrar(s, f"lote ({descricao}) em {alterados} usuário(s)")
    return {"alterados": alterados, "erros": erros}


@app.post("/api/usuarios/{item_id}/nova-senha")
def nova_senha(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    atual = mk.obter(USUARIOS, item_id)
    senha = util.gerar_senha()
    mk.alterar(USUARIOS, item_id, {"password": senha})
    registrar(s, f"gerou senha nova para {atual.get('name')}")
    return _usuario({**atual, "password": senha})


@app.get("/api/usuarios/exportar")
def exportar_usuarios(senhas: bool = False, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    usuarios = listar_usuarios(mk)
    livro = Workbook()
    folha = livro.active
    folha.title = "Usuários"
    titulos = (["Usuário"] + (["Senha"] if senhas else [])
               + ["Nome", "Turma", "Perfil", "Limite de tempo", "Situação", "Enviados (MB)", "Recebidos (MB)"])
    folha.append(titulos)
    for celula in folha[1]:
        celula.font = Font(bold=True)
    for u in usuarios:
        nome, turma = util.separar_turma(u["comentario"])
        folha.append([u["nome"]] + ([u["senha"]] if senhas else []) + [
            nome, turma, u["perfil"], u["limite_tempo"], "Desativado" if u["desativado"] else "Ativo",
            round(u["bytes_in"] / 1048576, 1), round(u["bytes_out"] / 1048576, 1)])
    for coluna, largura in zip("ABCDEFGHIJ", (18, 12, 30, 12, 14, 14, 12, 14, 14, 14)):
        folha.column_dimensions[coluna].width = largura
    saida = io.BytesIO()
    livro.save(saida)
    registrar(s, "exportou a lista de usuários" + (" com senhas" if senhas else ""))
    nome = f"usuarios-hotspot-{datetime.now():%Y-%m-%d}.xlsx"
    return Response(saida.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# ---------------------------------------------------------------- perfis e horário

def _perfil_por_id(mk: Mikrotik, item_id: str) -> dict:
    _id_valido(item_id)
    return mk.obter(controle.PERFIS, item_id)


@app.get("/api/perfis/detalhes")
def perfis_detalhes(mk: Mikrotik = Depends(mikrotik)):
    horarios = controle.ler_horarios(mk.listar(controle.FILTROS))
    usuarios = mk.listar(USUARIOS)
    lista = []
    for p in mk.listar(controle.PERFIS):
        item = controle.perfil_para_json(p, horarios)
        item["usuarios"] = sum(1 for u in usuarios if u.get("profile", "default") == item["nome"]
                               and not util.sim(u.get("default")) and u.get("name") != "default-trial")
        lista.append(item)
    return sorted(lista, key=lambda p: (not p["padrao"], p["nome"].lower()))


@app.post("/api/perfis")
def criar_perfil(dados: DadosPerfil, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    if not dados.nome:
        raise util.ErroDados("Informe o nome do perfil.")
    corpo = controle.montar_perfil(dados.nome, dados.download_mbps or 0, dados.envio_mbps or 0,
                                   dados.aparelhos if dados.aparelhos is not None else 1, dados.tempo_sessao or "")
    if corpo["name"] in _perfis(mk):
        raise util.ErroDados("Já existe um perfil com esse nome.")
    if not corpo.get("rate-limit"):
        corpo.pop("rate-limit", None)
    # Perfil novo herda os scripts de login/saída do padrão (IPv6 do mikrotik-redes.rsc).
    padrao = next((p for p in mk.listar(controle.PERFIS) if p.get("default") == "true" or p.get("name") == "default"), {})
    for campo in ("on-login", "on-logout"):
        if padrao.get(campo):
            corpo[campo] = padrao[campo]
    mk.criar(controle.PERFIS, corpo)
    registrar(s, f"criou perfil {corpo['name']}")
    return {"ok": True}


@app.patch("/api/perfis/{item_id}")
def alterar_perfil(item_id: str, dados: DadosPerfil, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    atual = _perfil_por_id(mk, item_id)
    nome = dados.nome if dados.nome is not None and dados.nome != atual.get("name") else None
    if nome is not None and (util.sim(atual.get("default")) or atual.get("name") == "default"):
        raise util.ErroDados("O perfil default não pode ser renomeado.")
    if nome is not None and controle.ler_horarios(mk.listar(controle.FILTROS)).get(atual.get("name", "")):
        raise util.ErroDados("Desligue o horário deste perfil antes de renomear.")
    if nome is not None and any(u.get("profile") == atual.get("name") for u in mk.listar(USUARIOS)):
        raise util.ErroDados("Há usuários com este perfil; para renomear, crie um perfil novo e mude os usuários.")
    corpo = controle.montar_perfil(nome, dados.download_mbps, dados.envio_mbps, dados.aparelhos, dados.tempo_sessao)
    if not corpo:
        raise util.ErroDados("Nada para alterar.")
    mk.alterar(controle.PERFIS, item_id, corpo)
    campos = ", ".join(corpo)
    registrar(s, f"alterou perfil {atual.get('name')} ({campos})")
    return {"ok": True}


@app.delete("/api/perfis/{item_id}")
def remover_perfil(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    atual = _perfil_por_id(mk, item_id)
    nome = atual.get("name", "")
    if util.sim(atual.get("default")) or nome == "default":
        raise util.ErroDados("O perfil default não pode ser excluído.")
    em_uso = sum(1 for u in mk.listar(USUARIOS) if u.get("profile") == nome)
    if em_uso:
        raise util.ErroDados(f"Há {em_uso} usuário(s) com este perfil. Mude o perfil deles antes de excluir.")
    controle.aplicar_horario(mk, atual, None)
    mk.remover(controle.PERFIS, item_id)
    registrar(s, f"excluiu perfil {nome}")
    return {"ok": True}


@app.put("/api/perfis/{item_id}/horario")
def horario_perfil(item_id: str, dados: DadosHorario, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    atual = _perfil_por_id(mk, item_id)
    horario = controle.validar_horario(dados.inicio, dados.fim, dados.dias) if dados.ativo else None
    controle.aplicar_horario(mk, atual, horario)
    registrar(s, f"horário do perfil {atual.get('name')}: " + (horario.texto() if horario else "livre"))
    return {"ok": True}


# ---------------------------------------------------------------- sites bloqueados

def _bloqueio_do_painel(mk: Mikrotik, item_id: str) -> dict:
    _id_valido(item_id)
    atual = mk.obter(controle.DNS_ESTATICO, item_id)
    if not atual.get("comment", "").startswith(controle.PREFIXO_BLOQUEIO):
        raise util.ErroDados("Esse registro de DNS não foi criado pelo painel.")
    return atual


@app.get("/api/bloqueios")
def bloqueios(mk: Mikrotik = Depends(mikrotik)):
    itens = [controle.bloqueio_para_json(b) for b in mk.listar(controle.DNS_ESTATICO)
             if b.get("comment", "").startswith(controle.PREFIXO_BLOQUEIO)]
    return sorted(itens, key=lambda b: b["dominio"])


@app.post("/api/bloqueios")
def criar_bloqueio(dados: NovoBloqueio, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    dominio = controle.normalizar_dominio(dados.dominio)
    if any(b.get("name") == dominio for b in mk.listar(controle.DNS_ESTATICO)):
        raise util.ErroDados("Esse site já está bloqueado.")
    controle.criar_bloqueio(mk, dominio, dados.motivo)
    registrar(s, f"bloqueou o site {dominio}")
    return {"ok": True, "dominio": dominio}


@app.patch("/api/bloqueios/{item_id}")
def alternar_bloqueio(item_id: str, dados: AlterarDispositivo, mk: Mikrotik = Depends(mikrotik),
                      s: Sessao = Depends(sessao_atual)):
    if dados.desativado is None:
        raise util.ErroDados("Nada para alterar.")
    atual = _bloqueio_do_painel(mk, item_id)
    mk.alterar(controle.DNS_ESTATICO, item_id, {"disabled": "true" if dados.desativado else "false"})
    registrar(s, f"{'pausou' if dados.desativado else 'reativou'} o bloqueio de {atual.get('name')}")
    return {"ok": True}


@app.delete("/api/bloqueios/{item_id}")
def remover_bloqueio(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    atual = _bloqueio_do_painel(mk, item_id)
    mk.remover(controle.DNS_ESTATICO, item_id)
    registrar(s, f"desbloqueou o site {atual.get('name')}")
    return {"ok": True}


@app.get("/api/forcar-dns")
def ver_forcar_dns(mk: Mikrotik = Depends(mikrotik)):
    return controle.estado_forcar_dns(mk)


@app.put("/api/forcar-dns")
def mudar_forcar_dns(dados: Ligar, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    controle.aplicar_forcar_dns(mk, dados.ativo)
    registrar(s, "ligou o forçar DNS do roteador" if dados.ativo else "desligou o forçar DNS do roteador")
    return controle.estado_forcar_dns(mk)


@app.get("/api/hotspot/perfis")
def ver_perfis_servidor(mk: Mikrotik = Depends(mikrotik)):
    return controle.perfis_servidor(mk)


@app.patch("/api/hotspot/perfis/{item_id}")
def mudar_dominio(item_id: str, dados: Dominio, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    dominio, aviso_dominio = controle.validar_dominio_hotspot(dados.dominio)
    atual = mk.obter(controle.PERFIS_SERVIDOR, item_id)
    mk.alterar(controle.PERFIS_SERVIDOR, item_id, {"dns-name": dominio})
    registrar(s, f"mudou o endereço do hotspot no perfil {atual.get('name')}: "
                 f"{atual.get('dns-name') or '(IP)'} -> {dominio or '(IP)'}")
    return {"dominio": dominio, "aviso": aviso_dominio}


@app.get("/api/configuracoes/wifi")
def ver_wifi(_: Sessao = Depends(sessao_atual)):
    return {**qrcodes.ler_wifi(config.pasta_dados), "qr": qrcodes.qr_wifi(config.pasta_dados)}


@app.put("/api/configuracoes/wifi")
def gravar_wifi(dados: Wifi, s: Sessao = Depends(sessao_atual)):
    gravado = qrcodes.gravar_wifi(config.pasta_dados, dados.ssid, dados.seguranca, dados.senha)
    registrar(s, f"alterou a rede Wi-Fi dos QR codes: {gravado['ssid'] or '(nenhuma)'} ({gravado['seguranca']})")
    return {**gravado, "qr": qrcodes.qr_wifi(config.pasta_dados)}


# ---------------------------------------------------------------- configurações: escola e MikroTik

@app.get("/api/configuracoes/escola")
def ver_escola(_: Sessao = Depends(sessao_atual)):
    return ajustes.escola(config.pasta_dados, config)


def publicar_escola(mk: Mikrotik) -> str:
    """Grava escola-info.js na pasta do hotspot (nome, cidade e link de troca de senha).
    Devolve "" se deu certo ou a mensagem do erro (o painel não deixa de salvar por isso)."""
    escola = ajustes.escola(config.pasta_dados, config)
    info = {"nome": escola["nome"], "cidade": escola["cidade"], "senha": ajustes.ler(config.pasta_dados).get("senha_url", "")}
    try:
        _gravar_arquivo(mk, f"{_pasta_hotspot(mk)}/escola-info.js", f"var ESCOLA_INFO = {json.dumps(info)};\n")
        return ""
    except ErroAutenticacao:
        raise
    except ErroMikrotik as erro:
        return erro.mensagem


@app.put("/api/configuracoes/escola")
def gravar_escola(dados: DadosEscola, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    ajustes.gravar_escola(config.pasta_dados, dados.nome, dados.cidade)
    escola = ajustes.escola(config.pasta_dados, config)
    erro = publicar_escola(mk)
    registrar(s, f"alterou o nome da escola para \"{escola['nome']}\" ({escola['cidade'] or 'sem cidade'})")
    return {**escola, "aviso_hotspot": f"Não foi possível gravar o nome nas páginas do hotspot: {erro}" if erro else ""}


@app.post("/api/configuracoes/logo")
def gravar_logo(arquivo: UploadFile = File(...), s: Sessao = Depends(sessao_atual)):
    ajustes.gravar_logo(config.pasta_dados, arquivo.file.read(ajustes.LOGO_MAX_BYTES + 1))
    registrar(s, "trocou o logotipo da escola")
    return ajustes.escola(config.pasta_dados, config)


@app.delete("/api/configuracoes/logo")
def remover_logo(s: Sessao = Depends(sessao_atual)):
    ajustes.remover_logo(config.pasta_dados)
    registrar(s, "voltou ao logotipo padrão")
    return ajustes.escola(config.pasta_dados, config)


def _estado_conexao() -> dict:
    endereco = ajustes.endereco_mikrotik(config.pasta_dados, config)
    ip, porta = ajustes.separar_endereco(endereco)
    try:
        em_uso = app.state.endereco.url()
    except ErroMikrotik:
        em_uso = ""
    return {"ip": ip, "porta": porta, "padrao": ajustes.IP_PADRAO, "em_uso": em_uso, "conexao": tipo_conexao() if em_uso else ""}


@app.get("/api/configuracoes/mikrotik")
def ver_conexao(_: Sessao = Depends(sessao_atual)):
    return _estado_conexao()


@app.put("/api/configuracoes/mikrotik")
def gravar_conexao(dados: ConexaoMikrotik, s: Sessao = Depends(sessao_atual)):
    endereco = ajustes.montar_endereco(dados.ip, dados.porta)
    novo = EnderecoMikrotik(endereco, config.mikrotik_verificar_tls, transport=app.state.transport)
    try:
        url = novo.url()
        with Mikrotik(url, s.usuario, s.senha, config.mikrotik_verificar_tls, config.mikrotik_timeout,
                      transport=app.state.transport) as mk:
            identidade = mk.identidade()
    except ErroAutenticacao as erro:
        # Não encerra a sessão: só recusa o endereço novo.
        raise util.ErroDados(f"O MikroTik em {endereco} não aceitou o seu usuário e senha. Nada foi alterado.") from erro
    except ErroMikrotik as erro:
        raise util.ErroDados(f"{erro.mensagem} Nada foi alterado.") from erro
    ajustes.gravar_endereco(config.pasta_dados, endereco)
    app.state.endereco = novo
    registrar(s, f"mudou a conexão com o MikroTik para {endereco} ({identidade})")
    return {**_estado_conexao(), "identidade": identidade}


# ---------------------------------------------------------------- pontos de acesso (APs)

@app.get("/api/aps")
def ver_aps(mk: Mikrotik = Depends(mikrotik)):
    return aps.listar(mk)


@app.post("/api/aps")
def criar_ap(dados: DadosAP, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    item = aps.criar(mk, dados.nome, dados.ip)
    registrar(s, f"cadastrou o AP {item['nome']} ({item['ip']})")
    return item


@app.patch("/api/aps/{item_id}")
def alterar_ap(item_id: str, dados: DadosAP, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    item = aps.alterar(mk, item_id, dados.nome, dados.ip)
    registrar(s, f"alterou o AP {item['nome']} ({item['ip']})")
    return item


@app.delete("/api/aps/{item_id}")
def remover_ap(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    nome = aps.remover(mk, item_id)
    registrar(s, f"removeu o AP {nome}")
    return {"ok": True}


# ---------------------------------------------------------------- administradores do MikroTik

@app.get("/api/administradores")
def ver_administradores(mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    return {"usuarios": administradores.listar(mk), "grupos": administradores.grupos(mk), "eu": s.usuario,
            "eu_full": administradores.eh_full(mk, s.usuario)}


@app.post("/api/administradores")
def criar_administrador(dados: NovoAdministrador, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    item = administradores.criar(mk, dados.nome, dados.senha, dados.grupo, dados.comentario)
    registrar(s, f"cadastrou o administrador {item['nome']} (grupo {item['grupo']})")
    return item


@app.patch("/api/administradores/{item_id}")
def alterar_administrador(item_id: str, dados: AlterarAdministrador, mk: Mikrotik = Depends(mikrotik),
                          s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    item, campos = administradores.alterar(mk, item_id, s.usuario, dados.senha, dados.grupo, dados.comentario, dados.desativado)
    if dados.senha and item["nome"] == s.usuario:
        s.senha = dados.senha  # trocou a própria senha: a sessão segue com a nova
    registrar(s, f"alterou o administrador {item['nome']} ({', '.join(campos)})")
    return item


@app.delete("/api/administradores/{item_id}")
def excluir_administrador(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    nome = administradores.excluir(mk, item_id, s.usuario)
    registrar(s, f"excluiu o administrador {nome}")
    return {"ok": True}


# ---------------------------------------------------------------- relatório de consumo

def _estado_relatorio() -> dict:
    try:
        return json.loads((config.pasta_dados / "relatorio.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@app.get("/api/relatorio")
def relatorio(mk: Mikrotik = Depends(mikrotik)):
    return {
        "desde": _estado_relatorio().get("zerado_em", ""),
        "usuarios": [{"nome": u["nome"], "comentario": u["comentario"], "perfil": u["perfil"],
                      "uptime": u["uptime"], "bytes_in": u["bytes_in"], "bytes_out": u["bytes_out"]}
                     for u in listar_usuarios(mk)],
    }


@app.post("/api/relatorio/zerar")
def zerar_relatorio(mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    ids = [u.get(".id") for u in mk.listar(USUARIOS) if u.get(".id")]
    if ids:
        mk.executar(f"{USUARIOS}/reset-counters", {"numbers": ",".join(ids)})
    agora = datetime.now().isoformat(timespec="seconds")
    (config.pasta_dados / "relatorio.json").write_text(json.dumps({"zerado_em": agora}), encoding="utf-8")
    registrar(s, "zerou os contadores de consumo")
    return {"desde": agora}


# ---------------------------------------------------------------- aviso da escola

def _pasta_hotspot(mk: Mikrotik) -> str:
    """Pasta de páginas (html-directory) do perfil usado pelo hotspot."""
    servidores = mk.listar(SERVIDORES)
    perfil_usado = servidores[0].get("profile", "default") if servidores else "default"
    for perfil in mk.listar(PERFIS_HOTSPOT):
        if perfil.get("name") == perfil_usado and perfil.get("html-directory"):
            return perfil["html-directory"].strip("/")
    return "hotspot"


def _gravar_arquivo(mk: Mikrotik, nome: str, conteudo: str) -> None:
    arquivos = mk.listar(ARQUIVOS, {"name": nome})
    if arquivos:
        mk.alterar(ARQUIVOS, arquivos[0][".id"], {"contents": conteudo})
    else:
        mk.criar(ARQUIVOS, {"name": nome, "contents": conteudo})


@app.get("/api/aviso")
def ler_aviso(mk: Mikrotik = Depends(mikrotik)):
    nome = f"{_pasta_hotspot(mk)}/aviso.txt"
    arquivos = mk.listar(ARQUIVOS, {"name": nome})
    return {"texto": arquivos[0].get("contents", "") if arquivos else "", "arquivo": nome}


@app.put("/api/aviso")
def gravar_aviso(dados: Aviso, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    texto = dados.texto.replace("\r\n", "\n").strip()
    pasta = _pasta_hotspot(mk)
    try:
        # aviso.txt guarda o texto para o painel ler de volta; aviso-escola.js é o que
        # as páginas do hotspot carregam (<script>, como o CSS), em ASCII com escapes.
        _gravar_arquivo(mk, f"{pasta}/aviso.txt", texto)
        _gravar_arquivo(mk, f"{pasta}/aviso-escola.js", f"var AVISO_ESCOLA = {json.dumps(texto)};\n")
    except ErroAutenticacao:
        raise
    except ErroMikrotik as erro:
        raise ErroMikrotik(f"O MikroTik não aceitou gravar o aviso ({erro.mensagem}). "
                           "Pode ser preciso atualizar o RouterOS.", erro.status) from erro
    registrar(s, "alterou o aviso da escola" if texto else "apagou o aviso da escola")
    return {"texto": texto, "arquivo": f"{pasta}/aviso.txt"}


# ---------------------------------------------------------------- histórico

@app.get("/api/historico")
def ver_historico(busca: str = "", usuario: str = "", dias: int = 30, _: Sessao = Depends(sessao_atual)):
    return historico.ler(config.pasta_dados, busca[:100], usuario[:64], max(0, min(dias, 3650)))


# ---------------------------------------------------------------- backup

def _backup_do_dia(usuario: str, senha: str) -> None:
    if backup.existe_de_hoje(config.pasta_dados):
        return
    try:
        with conectar(usuario, senha) as mk:
            nome = backup.salvar(config.pasta_dados, backup.montar(mk))
        log_acoes.info("%s backup automático %s", usuario, nome)
    except Exception as erro:  # o login não pode falhar por causa do backup
        logging.getLogger("painel").warning("backup automático falhou: %r", erro)


@app.get("/api/backups")
def listar_backups(_: Sessao = Depends(sessao_atual)):
    return backup.listar(config.pasta_dados)


@app.post("/api/backups")
def fazer_backup(mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    nome = backup.salvar(config.pasta_dados, backup.montar(mk), sufixo_hora=True)
    registrar(s, f"fez backup {nome}")
    return {"nome": nome}


@app.get("/api/backups/{nome}")
def baixar_backup(nome: str, s: Sessao = Depends(sessao_atual)):
    arquivo = backup.caminho(config.pasta_dados, nome)
    registrar(s, f"baixou o backup {nome}")
    return FileResponse(arquivo, media_type="application/json", filename=nome)


@app.delete("/api/backups/{nome}")
def excluir_backup(nome: str, s: Sessao = Depends(sessao_atual)):
    backup.caminho(config.pasta_dados, nome).unlink()
    registrar(s, f"excluiu o backup {nome}")
    return {"ok": True}


@app.post("/api/backups/restaurar")
def restaurar_backup(dados: NomeBackup, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    conteudo = backup.ler(backup.caminho(config.pasta_dados, dados.nome).read_bytes())
    resultado = backup.restaurar(mk, conteudo)
    registrar(s, f"restaurou o backup {dados.nome}")
    return resultado


@app.post("/api/backups/restaurar-arquivo")
def restaurar_arquivo(arquivo: UploadFile = File(...), mk: Mikrotik = Depends(mikrotik),
                      s: Sessao = Depends(sessao_atual)):
    conteudo = arquivo.file.read(ARQUIVO_MAX_BYTES + 1)
    if len(conteudo) > ARQUIVO_MAX_BYTES:
        raise util.ErroDados("Arquivo grande demais (máximo de 5 MB).")
    resultado = backup.restaurar(mk, backup.ler(conteudo))
    registrar(s, f"restaurou o backup do arquivo {arquivo.filename}")
    return resultado


# ---------------------------------------------------------------- painel geral e atualização

_NOME_INTERFACE = re.compile(r"^[\w.@:+/ -]{1,64}$")


@app.get("/api/sistema")
def ver_sistema(mk: Mikrotik = Depends(mikrotik)):
    dados = sistema.resumo(mk)
    dados["conectados"] = len(mk.listar(ATIVOS))
    dados.update(sistema.licenca(mk))
    dados["usuarios"] = len(_usuarios_comuns(mk))
    dados["aps"] = aps.resumo(mk)
    return dados


@app.get("/api/trafego")
def ver_trafego(interfaces: str = "", mk: Mikrotik = Depends(mikrotik)):
    nomes = [n.strip() for n in interfaces.split(",") if n.strip()][:8]
    if any(not _NOME_INTERFACE.match(n) for n in nomes):
        raise util.ErroDados("Nome de interface inválido.")
    return sistema.trafego(mk, nomes)


@app.get("/api/atualizacao")
def ver_atualizacao(forcar: bool = False, mk: Mikrotik = Depends(mikrotik)):
    return app.state.atualizacao.obter(mk, forcar)


# ---------------------------------------------------------------- visitantes (senhas temporárias)

def _base_login(mk: Mikrotik) -> str:
    """Endereço da tela de login do hotspot em uso (domínio ou IP) para o QR code."""
    for perfil in controle.perfis_servidor(mk):
        if perfil["servidores"] and (perfil["dominio"] or perfil["endereco"]):
            return f"http://{perfil['dominio'] or perfil['endereco']}"
    return ""


def _com_qr(itens: list[dict], base: str) -> list[dict]:
    for item in itens:
        item["qr_login"] = qrcodes.imagem(qrcodes.url_login(base, item["usuario"], item["senha"])) if base else ""
    return itens


def _limite_visitantes(mk: Mikrotik) -> dict:
    """Quantos visitantes ainda cabem: o limite da licença (ou 200) menos as senhas válidas."""
    limite = sistema.licenca(mk)["limite_hotspot"] or visitantes.MAX_QUANTIDADE
    validos = sum(1 for v in visitantes.listar(mk) if not v["expirado"])
    return {"limite": limite, "validos": validos, "disponiveis": max(0, min(visitantes.MAX_QUANTIDADE, limite - validos))}


@app.get("/api/licenca")
def ver_licenca(mk: Mikrotik = Depends(mikrotik)):
    """Sessões do hotspot em uso agora contra o limite da licença."""
    dados = sistema.licenca(mk)
    sessoes = len(mk.listar(ATIVOS))
    limite = dados["limite_hotspot"]
    return {**dados, "sessoes": sessoes, "livres": None if limite is None else max(0, limite - sessoes)}


@app.get("/api/visitantes/limite")
def ver_limite_visitantes(mk: Mikrotik = Depends(mikrotik)):
    return _limite_visitantes(mk)


@app.get("/api/visitantes")
def ver_visitantes(mk: Mikrotik = Depends(mikrotik)):
    return _com_qr(visitantes.listar(mk), _base_login(mk))


@app.post("/api/visitantes")
def criar_visitantes(dados: NovosVisitantes, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    if dados.perfil and dados.perfil not in _perfis(mk):
        raise util.ErroDados("Escolha um perfil que exista no MikroTik.")
    folga = _limite_visitantes(mk)
    if dados.quantidade > folga["disponiveis"]:
        raise util.ErroDados(
            f"Já existem {folga['validos']} senha(s) de visitante válida(s) e o limite é {folga['limite']} "
            f"(sessões do hotspot na licença do MikroTik). Dá para criar no máximo {folga['disponiveis']} agora; "
            "encerre algumas para liberar mais.")
    ate = visitantes.validade(dados.minutos, dados.ate_fim_do_dia)
    criados = visitantes.criar(mk, dados.quantidade, ate, dados.perfil, dados.descricao, dados.nome)
    registrar(s, f"criou {len(criados)} senha(s) de visitante válida(s) até {ate:%d/%m/%Y %H:%M}"
                 + (f" ({dados.descricao.strip()})" if dados.descricao.strip() else ""))
    return {"criados": _com_qr(criados, _base_login(mk))}


@app.post("/api/visitantes/encerrar")
def encerrar_visitantes(dados: EncerrarVisitantes, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    if not dados.todos and not dados.ids:
        raise util.ErroDados("Selecione os visitantes para encerrar.")
    for item_id in dados.ids:
        _id_valido(item_id)
    resultado = visitantes.encerrar_varios(mk, None if dados.todos else dados.ids)
    registrar(s, f"encerrou {len(resultado['encerrados'])} visitante(s)" + (" (todos)" if dados.todos else ""))
    return resultado


@app.delete("/api/visitantes/{item_id}")
def encerrar_visitante(item_id: str, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    _id_valido(item_id)
    nome = visitantes.encerrar(mk, item_id)
    registrar(s, f"encerrou o visitante {nome}")
    return {"ok": True}


# ---------------------------------------------------------------- rede Alunos

@app.get("/api/rede-alunos")
def ver_rede_alunos(mk: Mikrotik = Depends(mikrotik)):
    return rede_alunos.estado(mk)


def _interfaces_protegidas(mk: Mikrotik) -> set[str]:
    """A interface da internet e a que tem o IP pelo qual o painel fala com o MikroTik."""
    protegidas = {sistema.interface_internet(mk)}
    ip, _ = ajustes.separar_endereco(ajustes.endereco_mikrotik(config.pasta_dados, config))
    try:
        for endereco in mk.listar("/ip/address"):
            if endereco.get("address", "").split("/")[0] == ip:
                protegidas.add(endereco.get("interface", ""))
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        pass
    return protegidas - {""}


@app.get("/api/rede-alunos/interfaces")
def interfaces_rede_alunos(mk: Mikrotik = Depends(mikrotik)):
    return rede_alunos.interfaces(mk, _interfaces_protegidas(mk))


@app.put("/api/rede-alunos/config")
def configurar_rede_alunos(dados: ConfigAlunos, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    rede_alunos.configurar(mk, dados.interface, [j.model_dump() for j in dados.janelas], _interfaces_protegidas(mk))
    registrar(s, f"alterou a rede Alunos: interface {dados.interface.strip()}, {len(dados.janelas)} horário(s)")
    return rede_alunos.estado(mk)


@app.put("/api/rede-alunos/modo")
def modo_rede_alunos(dados: ModoAlunos, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    rede_alunos.definir_modo(mk, dados.modo)
    nomes = {"horario": "por horário", "aberta": "sempre aberta", "fechada": "sempre fechada"}
    registrar(s, f"colocou a rede Alunos em modo {nomes[dados.modo]}")
    return rede_alunos.estado(mk)


@app.post("/api/rede-alunos/liberar")
def liberar_rede_alunos(dados: LiberarAlunos, mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    ate = rede_alunos.liberar(mk, dados.minutos)
    registrar(s, f"liberou a rede Alunos até {ate:%d/%m/%Y %H:%M}")
    return rede_alunos.estado(mk)


@app.post("/api/rede-alunos/fechar")
def fechar_rede_alunos(mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    ate = rede_alunos.fechar(mk)
    registrar(s, "fechou a rede Alunos" + (f" até {ate:%H:%M}" if ate else ""))
    return rede_alunos.estado(mk)


@app.post("/api/rede-alunos/horario")
def rede_alunos_no_horario(mk: Mikrotik = Depends(mikrotik), s: Sessao = Depends(sessao_atual)):
    rede_alunos.voltar_ao_horario(mk)
    registrar(s, "voltou a rede Alunos ao horário normal")
    return rede_alunos.estado(mk)


# ---------------------------------------------------------------- páginas

@app.get("/modelo.csv")
def modelo_csv():
    conteudo = "usuario;senha;nome;turma;perfil\nmaria.silva;;Maria da Silva;9º A;\njoao.souza;abc123;João Souza;1º B;\n"
    return Response(conteudo.encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="modelo-usuarios.csv"'})


app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")


@app.get("/logo")
def logo():
    arquivo = ajustes.caminho_logo(config.pasta_dados) or PASTA_STATIC / "logo.png"
    return FileResponse(arquivo, headers={"Cache-Control": "no-cache"})


@app.get("/")
def inicio():
    # A versão no endereço do CSS e dos scripts faz o navegador baixar os
    # arquivos novos depois de cada atualização (sem precisar de Ctrl+F5).
    html = (PASTA_STATIC / "index.html").read_text(encoding="utf-8").replace("__VERSAO__", APP_VERSION)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
