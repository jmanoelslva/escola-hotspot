"""Todos os aparelhos na rede: os que o hotspot vê (com ou sem login) e os que
pegaram IP no DHCP de qualquer rede (inclusive as sem hotspot, como a Alunos)."""

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

HOSTS = "/ip/hotspot/host"
ATIVOS = "/ip/hotspot/active"
BINDINGS = "/ip/hotspot/ip-binding"
LEASES = "/ip/dhcp-server/lease"

# Ordem da lista: primeiro o que pede atenção.
_ORDEM = {"bloqueado": 0, "sem_login": 1, "logado": 2, "liberado": 3, "sem_hotspot": 4}


def _tentar(mk: Mikrotik, caminho: str) -> list[dict]:
    try:
        return mk.listar(caminho)
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        return []  # sem hotspot ou sem DHCP no roteador: segue com o resto


def todos(mk: Mikrotik) -> dict:
    aparelhos: dict[str, dict] = {}

    def aparelho(mac: str) -> dict:
        return aparelhos.setdefault(mac, {"mac": mac, "ip": "", "nome": "", "rede": "", "usuario": "",
                                          "situacao": "sem_hotspot", "uptime": ""})

    nomes: dict[str, str] = {}
    for lease in _tentar(mk, LEASES):
        mac = lease.get("mac-address", "").upper()
        if not mac:
            continue
        nome = lease.get("comment") or lease.get("host-name") or ""
        if nome:
            nomes[mac] = nome  # o nome vale mesmo de lease antigo (ajuda a achar o aparelho no hotspot)
        if lease.get("status") != "bound" or util.sim(lease.get("disabled")):
            continue
        a = aparelho(mac)
        a["ip"] = lease.get("address", "")
        a["rede"] = lease.get("server", "")

    for host in _tentar(mk, HOSTS):
        mac = host.get("mac-address", "").upper()
        if not mac:
            continue
        a = aparelho(mac)
        a["ip"] = a["ip"] or host.get("address", "")
        a["rede"] = host.get("server") or a["rede"]
        a["uptime"] = host.get("uptime", "")
        if util.sim(host.get("bypassed")):
            a["situacao"] = "liberado"
        elif util.sim(host.get("authorized")):
            a["situacao"] = "logado"
        else:
            a["situacao"] = "sem_login"

    for ativo in _tentar(mk, ATIVOS):
        mac = ativo.get("mac-address", "").upper()
        if mac in aparelhos:
            aparelhos[mac]["usuario"] = ativo.get("user", "")
            aparelhos[mac]["situacao"] = "logado"

    for b in _tentar(mk, BINDINGS):
        mac = b.get("mac-address", "").upper()
        if mac in aparelhos and not util.sim(b.get("disabled")):
            if b.get("type") == "blocked":
                aparelhos[mac]["situacao"] = "bloqueado"
            elif b.get("type") == "bypassed":
                aparelhos[mac]["situacao"] = "liberado"

    for mac, a in aparelhos.items():
        a["nome"] = nomes.get(mac, "")

    lista = sorted(aparelhos.values(), key=lambda a: (_ORDEM[a["situacao"]], a["rede"], a["nome"] == "", a["nome"].lower(), a["ip"]))
    resumo = {chave: sum(1 for a in lista if a["situacao"] == chave) for chave in _ORDEM}
    return {"aparelhos": lista, "resumo": resumo, "redes": sorted({a["rede"] for a in lista if a["rede"]})}
