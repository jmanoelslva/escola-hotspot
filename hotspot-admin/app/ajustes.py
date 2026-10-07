"""Ajustes feitos pelo painel (Sistema → Configurações), guardados em dados/.

- dados/ajustes.json: nome e cidade da escola, IP e porta do MikroTik. Valem
  por cima do .env (NOME_ESCOLA, CIDADE_ESCOLA, MIKROTIK_URL).
- dados/logo.png ou dados/logo.jpg: logotipo da escola (sem ele, static/logo.png).
"""

import json
import re
from pathlib import Path

from . import util
from .config import Config

ARQUIVO = "ajustes.json"
IP_PADRAO = "192.168.88.1"
LOGO_MAX_BYTES = 2 * 1024 * 1024
_FORMATOS_LOGO = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}
_HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")


def ler(pasta: Path) -> dict:
    try:
        dados = json.loads((pasta / ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar(pasta: Path, mudancas: dict) -> dict:
    dados = {**ler(pasta), **mudancas}
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ARQUIVO).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return dados


# ------------------------------------------------------------------ escola

def escola(pasta: Path, config: Config) -> dict:
    dados = ler(pasta)
    return {
        "nome": dados.get("escola", config.nome_escola),
        "cidade": dados.get("cidade", config.cidade_escola),
        "logo_proprio": caminho_logo(pasta) is not None,
    }


def gravar_escola(pasta: Path, nome: str, cidade: str) -> None:
    nome = " ".join((nome or "").split())
    cidade = " ".join((cidade or "").split())
    if not nome:
        raise util.ErroDados("Informe o nome da escola.")
    if len(nome) > 120 or len(cidade) > 80:
        raise util.ErroDados("Nome (até 120 letras) ou cidade (até 80) grande demais.")
    _gravar(pasta, {"escola": nome, "cidade": cidade})


def caminho_logo(pasta: Path) -> Path | None:
    for extensao in ("png", "jpg"):
        arquivo = pasta / f"logo.{extensao}"
        if arquivo.is_file():
            return arquivo
    return None


def gravar_logo(pasta: Path, conteudo: bytes) -> None:
    if len(conteudo) > LOGO_MAX_BYTES:
        raise util.ErroDados("Imagem grande demais (máximo de 2 MB).")
    extensao = next((ext for assinatura, ext in _FORMATOS_LOGO.items() if conteudo.startswith(assinatura)), None)
    if not extensao:
        raise util.ErroDados("Envie uma imagem PNG ou JPG.")
    remover_logo(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"logo.{extensao}").write_bytes(conteudo)


def remover_logo(pasta: Path) -> None:
    for extensao in ("png", "jpg"):
        (pasta / f"logo.{extensao}").unlink(missing_ok=True)


# ------------------------------------------------------------------ conexão com o MikroTik

def montar_endereco(ip: str, porta: int | None) -> str:
    """IP (ou nome) e porta do MikroTik; sem IP, usa o padrão 192.168.88.1.
    Sem porta, o painel testa HTTPS (443) e HTTP (80); com porta, HTTPS e HTTP nela."""
    ip = (ip or "").strip() or IP_PADRAO
    if not _HOST.match(ip):
        raise util.ErroDados("Endereço do MikroTik inválido. Exemplo: 192.168.88.1")
    if porta is not None and not 1 <= porta <= 65535:
        raise util.ErroDados("Porta inválida (1 a 65535).")
    return f"{ip}:{porta}" if porta else ip


def separar_endereco(endereco: str) -> tuple[str, int | None]:
    """"192.168.88.1:8443" -> ("192.168.88.1", 8443); aceita também http(s)://."""
    texto = re.sub(r"^https?://", "", endereco or "").rstrip("/")
    if ":" in texto:
        ip, porta = texto.rsplit(":", 1)
        if porta.isdigit():
            return ip, int(porta)
    return texto, None


def endereco_mikrotik(pasta: Path, config: Config) -> str:
    return ler(pasta).get("mikrotik", config.mikrotik_url)


def gravar_endereco(pasta: Path, endereco: str) -> None:
    _gravar(pasta, {"mikrotik": endereco})
