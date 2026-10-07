"""Cópia de segurança do que o painel administra, guardada em dados/backups.

Feita sozinha no primeiro login de cada dia (o painel não guarda senha do
MikroTik, então só consegue ler o roteador enquanto alguém está logado).
Atenção: o arquivo tem as senhas dos alunos; a pasta dados fica só neste PC.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from . import controle, util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

USUARIOS = "/ip/hotspot/user"
BINDINGS = "/ip/hotspot/ip-binding"
MANTER = 30
_NOME = re.compile(r"^backup-\d{4}-\d{2}-\d{2}(-\d{6})?\.json$")

_CAMPOS_USUARIO = ("name", "password", "profile", "comment", "limit-uptime", "mac-address", "disabled")
_CAMPOS_BINDING = ("type", "mac-address", "address", "server", "comment", "disabled")
_CAMPOS_PERFIL = ("name", "rate-limit", "shared-users", "session-timeout", "address-list")


def pasta(dados: Path) -> Path:
    destino = dados / "backups"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _so(item: dict, campos: tuple[str, ...]) -> dict:
    return {c: item[c] for c in campos if item.get(c) not in (None, "")}


def montar(mk: Mikrotik) -> dict:
    usuarios = [u for u in mk.listar(USUARIOS) if not util.sim(u.get("default")) and u.get("name") != "default-trial"]
    perfis = [p for p in mk.listar(controle.PERFIS) if not util.sim(p.get("default"))]
    try:
        bloqueios = [b for b in mk.listar(controle.DNS_ESTATICO)
                     if b.get("comment", "").startswith(controle.PREFIXO_BLOQUEIO)]
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        bloqueios = []
    return {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "perfis": [_so(p, _CAMPOS_PERFIL) for p in perfis],
        "usuarios": [_so(u, _CAMPOS_USUARIO) for u in usuarios],
        "aparelhos": [_so(b, _CAMPOS_BINDING) for b in mk.listar(BINDINGS)],
        "bloqueios": [{"dominio": b.get("name", ""), "motivo": controle.bloqueio_para_json(b)["motivo"]} for b in bloqueios],
    }


def salvar(dados: Path, conteudo: dict, sufixo_hora: bool = False) -> str:
    agora = datetime.now()
    nome = f"backup-{agora:%Y-%m-%d}" + (f"-{agora:%H%M%S}" if sufixo_hora else "") + ".json"
    (pasta(dados) / nome).write_text(json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8")
    antigos = sorted(listar(dados), key=lambda b: b["nome"], reverse=True)[MANTER:]
    for item in antigos:
        (pasta(dados) / item["nome"]).unlink(missing_ok=True)
    return nome


def existe_de_hoje(dados: Path) -> bool:
    return any(pasta(dados).glob(f"backup-{datetime.now():%Y-%m-%d}*.json"))


def listar(dados: Path) -> list[dict]:
    resultado = []
    for arquivo in pasta(dados).glob("backup-*.json"):
        if not _NOME.match(arquivo.name):
            continue
        try:
            conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        resultado.append({
            "nome": arquivo.name,
            "criado_em": conteudo.get("criado_em", ""),
            "usuarios": len(conteudo.get("usuarios", [])),
            "aparelhos": len(conteudo.get("aparelhos", [])),
            "perfis": len(conteudo.get("perfis", [])),
            "bloqueios": len(conteudo.get("bloqueios", [])),
            "tamanho": arquivo.stat().st_size,
        })
    return sorted(resultado, key=lambda b: b["nome"], reverse=True)


def caminho(dados: Path, nome: str) -> Path:
    if not _NOME.match(nome or ""):
        raise util.ErroDados("Nome de backup inválido.")
    arquivo = pasta(dados) / nome
    if not arquivo.is_file():
        raise util.ErroDados("Backup não encontrado.")
    return arquivo


def ler(conteudo: bytes) -> dict:
    try:
        dados = json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise util.ErroDados("Arquivo de backup inválido.") from erro
    if not isinstance(dados, dict) or not isinstance(dados.get("usuarios", []), list):
        raise util.ErroDados("Arquivo de backup inválido.")
    return dados


def restaurar(mk: Mikrotik, conteudo: dict) -> dict:
    """Recria o que falta; não altera nem apaga o que já existe no roteador."""
    resultado = {"perfis": 0, "usuarios": 0, "aparelhos": 0, "bloqueios": 0, "erros": []}

    def criar(tabela: str, corpo: dict, chave: str, rotulo: str) -> None:
        try:
            mk.criar(tabela, corpo)
            resultado[chave] += 1
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            resultado["erros"].append(f"{rotulo}: {erro.mensagem}")

    perfis = {p.get("name") for p in mk.listar(controle.PERFIS)}
    for p in conteudo.get("perfis", []):
        if isinstance(p, dict) and p.get("name") and p["name"] not in perfis:
            criar(controle.PERFIS, _so(p, _CAMPOS_PERFIL), "perfis", f"perfil {p['name']}")

    usuarios = {u.get("name") for u in mk.listar(USUARIOS)}
    for u in conteudo.get("usuarios", []):
        if isinstance(u, dict) and u.get("name") and u["name"] not in usuarios:
            criar(USUARIOS, _so(u, _CAMPOS_USUARIO), "usuarios", f"usuário {u['name']}")

    aparelhos = {(b.get("mac-address", "").upper(), b.get("type")) for b in mk.listar(BINDINGS)}
    for b in conteudo.get("aparelhos", []):
        if isinstance(b, dict) and b.get("mac-address") and (b["mac-address"].upper(), b.get("type")) not in aparelhos:
            criar(BINDINGS, _so(b, _CAMPOS_BINDING), "aparelhos", f"aparelho {b.get('comment') or b['mac-address']}")

    existentes = set()
    try:
        existentes = {b.get("name") for b in mk.listar(controle.DNS_ESTATICO)}
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        pass
    for b in conteudo.get("bloqueios", []):
        if isinstance(b, dict) and b.get("dominio") and b["dominio"] not in existentes:
            try:
                controle.criar_bloqueio(mk, controle.normalizar_dominio(b["dominio"]), b.get("motivo", ""))
                resultado["bloqueios"] += 1
            except ErroAutenticacao:
                raise
            except (ErroMikrotik, util.ErroDados) as erro:
                resultado["erros"].append(f"site {b['dominio']}: {getattr(erro, 'mensagem', str(erro))}")
    return resultado
