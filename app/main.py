"""Painel web do hotspot MikroTik: usuários, conectados, bypass/bloqueio e importação."""

import logging
from logging.handlers import RotatingFileHandler
from typing import Literal

from fastapi import Depends, FastAPI, File, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import importacao, util
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
app.state.endereco = EnderecoMikrotik(config.mikrotik_url, config.mikrotik_verificar_tls)


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
    return {"escola": config.nome_escola, "cidade": config.cidade_escola, "versao": APP_VERSION}


# ---------------------------------------------------------------- usuários

@app.get("/api/perfis")
def perfis(mk: Mikrotik = Depends(mikrotik)):
    return sorted(_perfis(mk))


@app.get("/api/servidores")
def servidores(mk: Mikrotik = Depends(mikrotik)):
    return sorted(s.get("name", "") for s in mk.listar(SERVIDORES))


@app.get("/api/usuarios")
def listar_usuarios(mk: Mikrotik = Depends(mikrotik)):
    itens = [u for u in mk.listar(USUARIOS) if not util.sim(u.get("default")) and u.get("name") != "default-trial"]
    return sorted((_usuario(u) for u in itens), key=lambda u: u["nome"].lower())


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
    mk.remover(ATIVOS, item_id)
    registrar(s, f"desconectou {atual.get('user')} ({atual.get('mac-address')})")
    return {"ok": True}


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


# ---------------------------------------------------------------- páginas

@app.get("/modelo.csv")
def modelo_csv():
    conteudo = "usuario;senha;nome;turma;perfil\nmaria.silva;;Maria da Silva;9º A;\njoao.souza;abc123;João Souza;1º B;\n"
    return Response(conteudo.encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="modelo-usuarios.csv"'})


app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")


@app.get("/")
def inicio():
    return FileResponse(PASTA_STATIC / "index.html", headers={"Cache-Control": "no-cache"})
