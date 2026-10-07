"""Pontos de acesso (APs) vigiados pelo próprio MikroTik (/tool netwatch).

Cada AP é uma entrada do Netwatch com comentário "painel-ap: <nome>": o
roteador testa o IP a cada 30 segundos, mesmo com o painel fechado, e o painel
só lê se está no ar (status up/down) e desde quando.
"""

import re

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

NETWATCH = "/tool/netwatch"
PREFIXO = "painel-ap:"
_IPV4 = re.compile(r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$")


def _nome(item: dict) -> str:
    return item.get("comment", "")[len(PREFIXO):].strip()


def listar(mk: Mikrotik) -> list[dict]:
    try:
        itens = mk.listar(NETWATCH)
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        return []
    lista = [{
        "id": i.get(".id"),
        "nome": _nome(i),
        "ip": i.get("host", ""),
        "situacao": "pausado" if util.sim(i.get("disabled")) else {"up": "no_ar", "down": "fora"}.get(i.get("status", ""), "testando"),
        "desde": i.get("since", ""),
    } for i in itens if i.get("comment", "").startswith(PREFIXO)]
    return sorted(lista, key=lambda a: util.chave_natural(a["nome"]))


def resumo(mk: Mikrotik) -> dict:
    lista = [a for a in listar(mk) if a["situacao"] != "pausado"]
    fora = [a for a in lista if a["situacao"] == "fora"]
    return {"total": len(lista), "no_ar": sum(1 for a in lista if a["situacao"] == "no_ar"),
            "fora": [{"nome": a["nome"], "ip": a["ip"], "desde": a["desde"]} for a in fora]}


def _validar(nome: str, ip: str) -> tuple[str, str]:
    nome = " ".join((nome or "").split())[:60]
    ip = (ip or "").strip()
    if not nome:
        raise util.ErroDados("Dê um nome ao AP (ex.: AP3 – pátio).")
    if not _IPV4.match(ip):
        raise util.ErroDados("IP inválido. Exemplo: 172.16.1.13")
    return nome, ip


def criar(mk: Mikrotik, nome: str, ip: str) -> dict:
    nome, ip = _validar(nome, ip)
    if any(a["ip"] == ip for a in listar(mk)):
        raise util.ErroDados("Esse IP já está na lista.")
    mk.criar(NETWATCH, {"host": ip, "interval": "30s", "timeout": "1s", "comment": f"{PREFIXO} {nome}"})
    return next(a for a in listar(mk) if a["ip"] == ip)


def _do_painel(mk: Mikrotik, item_id: str) -> dict:
    atual = mk.obter(NETWATCH, item_id)
    if not atual.get("comment", "").startswith(PREFIXO):
        raise util.ErroDados("Esse item do Netwatch não foi criado pelo painel.")
    return atual


def alterar(mk: Mikrotik, item_id: str, nome: str, ip: str) -> dict:
    _do_painel(mk, item_id)
    nome, ip = _validar(nome, ip)
    mk.alterar(NETWATCH, item_id, {"host": ip, "comment": f"{PREFIXO} {nome}"})
    return next(a for a in listar(mk) if a["id"] == item_id)


def remover(mk: Mikrotik, item_id: str) -> str:
    atual = _do_painel(mk, item_id)
    mk.remover(NETWATCH, item_id)
    return _nome(atual)
