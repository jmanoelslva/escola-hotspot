"""Troca da própria senha pela página do Wi-Fi (http://senha.<domínio do hotspot>:<porta>/senha).

Quem está no Wi-Fi digita usuário, senha atual e senha nova; o painel confere
no MikroTik com o usuário de serviço e grava a nova. Visitantes não trocam.
Quem vem das redes do Wi-Fi (REDES_WIFI) só enxerga esta página: o resto do
painel continua fechado para eles.
"""

import ipaddress
import socket

from . import util, visitantes
from .mikrotik import Mikrotik

USUARIOS = "/ip/hotspot/user"
DNS_ESTATICO = "/ip/dns/static"
COMENTARIO_DNS = "painel-senha"
SENHA_MIN = 6
ERRO_GENERICO = "Usuário ou senha atual incorretos."


def trocar(mk: Mikrotik, usuario: str, atual: str, nova: str) -> str:
    usuario = (usuario or "").strip()
    if not usuario or not atual:
        raise util.ErroDados("Informe o usuário e a senha atual.")
    nova = util.validar_senha(nova)
    if len(nova) < SENHA_MIN:
        raise util.ErroDados(f"A senha nova precisa de pelo menos {SENHA_MIN} caracteres.")
    if nova == atual:
        raise util.ErroDados("A senha nova precisa ser diferente da atual.")
    item = next((u for u in mk.listar(USUARIOS, {"name": usuario})), None)
    # Mesma mensagem para usuário inexistente, visitante ou senha errada: não revela quem existe.
    if (not item or item.get("password", "") != atual or util.sim(item.get("default"))
            or visitantes.ler_comentario(item.get("comment", ""))[0] is not None):
        raise util.ErroDados(ERRO_GENERICO)
    if util.sim(item.get("disabled")):
        raise util.ErroDados("Este usuário está desativado. Procure a secretaria.")
    mk.alterar(USUARIOS, item[".id"], {"password": nova})
    return item.get("name", usuario)


# ------------------------------------------------------------------ redes e endereço da página

def redes(texto: str) -> list:
    lista = []
    for parte in (texto or "").split(","):
        try:
            lista.append(ipaddress.ip_network(parte.strip(), strict=False))
        except ValueError:
            continue
    return lista


def do_wifi(ip: str, redes_wifi: list) -> bool:
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(endereco in rede for rede in redes_wifi)


def ip_deste_pc(ip_mikrotik: str) -> str:
    """IP pelo qual este PC fala com o MikroTik (o Wi-Fi chega ao painel por ele)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((ip_mikrotik, 9))
        return s.getsockname()[0]


def ativar_dns(mk: Mikrotik, dominio_hotspot: str, ip_pc: str) -> str:
    """Cria senha.<domínio> apontando para este PC (DNS do MikroTik) e devolve o nome usado."""
    if not dominio_hotspot:
        return ip_pc
    nome = f"senha.{dominio_hotspot}"
    existentes = [d for d in mk.listar(DNS_ESTATICO) if d.get("comment", "").startswith(COMENTARIO_DNS)]
    if existentes:
        mk.alterar(DNS_ESTATICO, existentes[0][".id"], {"name": nome, "address": ip_pc, "disabled": "false"})
        for extra in existentes[1:]:
            mk.remover(DNS_ESTATICO, extra[".id"])
    else:
        mk.criar(DNS_ESTATICO, {"name": nome, "address": ip_pc, "comment": f"{COMENTARIO_DNS} (Painel do Hotspot)"})
    return nome


def desativar_dns(mk: Mikrotik) -> None:
    for d in mk.listar(DNS_ESTATICO):
        if d.get("comment", "").startswith(COMENTARIO_DNS):
            mk.remover(DNS_ESTATICO, d[".id"])
