"""Usuário de serviço do painel no MikroTik ("painel-servico").

Com ele o painel fala com o roteador mesmo sem ninguém logado: registra o uso
da internet a cada 5 minutos e atende a página de troca de senha do Wi-Fi.
É criado por um administrador full (Sistema → Configurações), no grupo
"painel" (sem Winbox nem reboot), com senha aleatória guardada só neste PC em
dados/servico.json, como os backups.
"""

import json
import secrets
import string
from pathlib import Path

from . import administradores
from .mikrotik import Mikrotik

ARQUIVO = "servico.json"
USUARIO = "painel-servico"
_ALFABETO = string.ascii_letters + string.digits


def ler(pasta: Path) -> dict | None:
    try:
        dados = json.loads((pasta / ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict) or not dados.get("usuario") or not dados.get("senha"):
        return None
    return dados


def estado(pasta: Path) -> dict:
    dados = ler(pasta)
    return {"ativo": dados is not None, "usuario": dados["usuario"] if dados else USUARIO}


def ativar(mk: Mikrotik, pasta: Path) -> None:
    """Cria (ou recria com senha nova) o usuário de serviço e guarda a senha neste PC."""
    administradores._garantir_grupo_painel(mk)
    senha = "".join(secrets.choice(_ALFABETO) for _ in range(28))
    existente = next((u for u in mk.listar(administradores.USUARIOS) if u.get("name") == USUARIO), None)
    corpo = {"password": senha, "group": administradores.GRUPO_PAINEL, "disabled": "false",
             "comment": "Painel do Hotspot: coleta de uso e troca de senha (não apague)"}
    if existente:
        mk.alterar(administradores.USUARIOS, existente[".id"], corpo)
    else:
        mk.criar(administradores.USUARIOS, {"name": USUARIO, **corpo})
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ARQUIVO).write_text(json.dumps({"usuario": USUARIO, "senha": senha}), encoding="utf-8")


def desativar(mk: Mikrotik, pasta: Path) -> None:
    for u in mk.listar(administradores.USUARIOS):
        if u.get("name") == USUARIO:
            mk.remover(administradores.USUARIOS, u[".id"])
    (pasta / ARQUIVO).unlink(missing_ok=True)
