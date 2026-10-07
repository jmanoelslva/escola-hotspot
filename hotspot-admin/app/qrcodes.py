"""QR codes dos cartões de visitante: entrar no Wi-Fi e abrir o login já preenchido."""

import json
from pathlib import Path
from urllib.parse import urlencode

import segno

from . import util

ARQUIVO = "wifi.json"
SEGURANCAS = ("aberta", "wpa")


def _escapar(texto: str) -> str:
    # Formato WIFI: do padrão (o mesmo do Android/iPhone): \ ; , : " precisam de barra.
    for caractere in ('\\', ';', ',', ':', '"'):
        texto = texto.replace(caractere, '\\' + caractere)
    return texto


def texto_wifi(ssid: str, seguranca: str, senha: str) -> str:
    if seguranca == "wpa":
        return f"WIFI:T:WPA;S:{_escapar(ssid)};P:{_escapar(senha)};;"
    return f"WIFI:T:nopass;S:{_escapar(ssid)};;"


def url_login(base: str, usuario: str, senha: str) -> str:
    # Nomes próprios (visitante/senha): o MikroTik ignora e o login.html da escola
    # preenche os campos; o aluno ainda precisa aceitar os termos e tocar em Conectar.
    return f"{base}/login?{urlencode({'visitante': usuario, 'senha': senha})}"


def imagem(texto: str) -> str:
    """QR code como imagem SVG embutida (data:), pronta para <img src>."""
    return segno.make(texto, error="m").svg_data_uri(scale=4, border=2, dark="#0b1f33")


# ------------------------------------------------------------------ dados do Wi-Fi (guardados neste PC)

def ler_wifi(pasta_dados: Path) -> dict:
    try:
        dados = json.loads((pasta_dados / ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    return {
        "ssid": str(dados.get("ssid", "")),
        "seguranca": dados.get("seguranca", "aberta") if dados.get("seguranca") in SEGURANCAS else "aberta",
        "senha": str(dados.get("senha", "")),
    }


def gravar_wifi(pasta_dados: Path, ssid: str, seguranca: str, senha: str) -> dict:
    ssid = (ssid or "").strip()
    if len(ssid) > 32:
        raise util.ErroDados("O nome da rede (SSID) tem no máximo 32 caracteres.")
    if seguranca not in SEGURANCAS:
        raise util.ErroDados("Segurança inválida.")
    if seguranca == "wpa" and ssid and not 8 <= len(senha or "") <= 63:
        raise util.ErroDados("A senha do Wi-Fi (WPA) tem de 8 a 63 caracteres.")
    dados = {"ssid": ssid, "seguranca": seguranca, "senha": senha if seguranca == "wpa" else ""}
    pasta_dados.mkdir(parents=True, exist_ok=True)
    (pasta_dados / ARQUIVO).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return dados


def qr_wifi(pasta_dados: Path) -> str:
    wifi = ler_wifi(pasta_dados)
    return imagem(texto_wifi(wifi["ssid"], wifi["seguranca"], wifi["senha"])) if wifi["ssid"] else ""
