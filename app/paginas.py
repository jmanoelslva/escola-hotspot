"""Enviar as páginas do hotspot (pasta local) para a pasta do hotspot no MikroTik.

A REST API não grava arquivos binários, então o painel pede ao próprio
roteador que baixe cada arquivo do computador do painel (/tool fetch), por um
endereço temporário com um código aleatório que vale poucos minutos.
"""

import secrets
import socket
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

ARQUIVOS = "/file"
BUSCAR = "/tool/fetch"

# Gerados pelo painel no roteador: nunca são enviados nem comparados.
DO_PAINEL = {"aviso-escola.js", "aviso.txt"}
IGNORAR_PASTAS = {".git", ".github", "__pycache__", ".vscode", ".idea"}
IGNORAR_ARQUIVOS = {".gitignore", ".gitattributes", "Thumbs.db", "desktop.ini", ".DS_Store"}
MAX_ARQUIVOS = 300
VALIDADE_ENVIO = 300  # segundos


def arquivos_locais(pasta: Path) -> dict[str, Path]:
    if not pasta.is_dir():
        raise util.ErroDados(f"Pasta das páginas não encontrada: {pasta}. Ajuste PASTA_PAGINAS_HOTSPOT no arquivo .env.")
    resultado = {}
    for arquivo in sorted(pasta.rglob("*")):
        relativo = arquivo.relative_to(pasta)
        if not arquivo.is_file() or any(p in IGNORAR_PASTAS for p in relativo.parts):
            continue
        nome = relativo.as_posix()
        if nome in DO_PAINEL or arquivo.name in IGNORAR_ARQUIVOS or arquivo.name.startswith("."):
            continue
        resultado[nome] = arquivo
        if len(resultado) > MAX_ARQUIVOS:
            raise util.ErroDados("A pasta das páginas tem arquivos demais; confira PASTA_PAGINAS_HOTSPOT.")
    if "login.html" not in resultado:
        raise util.ErroDados(f"A pasta {pasta} não parece ter páginas do hotspot (falta login.html).")
    return resultado


def _tamanho(valor: object) -> int | None:
    texto = str(valor or "").strip().replace(" ", "")
    if texto.isdigit():
        return int(texto)
    # Algumas versões mostram "5.9KiB".
    for sufixo, fator in (("KiB", 1024), ("MiB", 1024 ** 2), ("B", 1)):
        if texto.endswith(sufixo):
            try:
                return int(float(texto[: -len(sufixo)]) * fator)
            except ValueError:
                return None
    return None


def comparar(mk: Mikrotik, pasta_local: Path, pasta_roteador: str) -> list[dict]:
    locais = arquivos_locais(pasta_local)
    prefixo = pasta_roteador.strip("/") + "/"
    no_roteador = {}
    for item in mk.listar(ARQUIVOS):
        nome = item.get("name", "")
        if nome.startswith(prefixo) and item.get("type") != "directory":
            no_roteador[nome[len(prefixo):]] = _tamanho(item.get("size"))
    lista = []
    for nome, arquivo in locais.items():
        tamanho = arquivo.stat().st_size
        remoto = no_roteador.get(nome, "falta")
        if remoto == "falta":
            situacao = "falta"
        elif remoto is None:
            situacao = "desconhecido"
        elif _parecido(remoto, tamanho):
            situacao = "igual"
        else:
            situacao = "diferente"
        lista.append({"arquivo": nome, "tamanho_painel": tamanho,
                      "tamanho_roteador": None if remoto == "falta" else remoto, "situacao": situacao})
    return lista


def _parecido(remoto: int, local: int) -> bool:
    # Tamanho exato em bytes, ou aproximado quando o roteador só informa "5.9KiB".
    return remoto == local or (local >= 1024 and abs(remoto - local) <= 52)


class Envios:
    """Códigos temporários que liberam o download dos arquivos para o roteador."""

    def __init__(self):
        self._envios: dict[str, tuple[float, dict[str, Path]]] = {}
        self._trava = threading.Lock()

    def abrir(self, arquivos: dict[str, Path]) -> str:
        codigo = secrets.token_urlsafe(24)
        with self._trava:
            agora = time.monotonic()
            self._envios = {c: v for c, v in self._envios.items() if agora - v[0] < VALIDADE_ENVIO}
            self._envios[codigo] = (agora, arquivos)
        return codigo

    def arquivo(self, codigo: str, nome: str) -> Path | None:
        with self._trava:
            envio = self._envios.get(codigo)
            if not envio or time.monotonic() - envio[0] >= VALIDADE_ENVIO:
                return None
            return envio[1].get(nome)

    def fechar(self, codigo: str) -> None:
        with self._trava:
            self._envios.pop(codigo, None)


def ip_do_painel(url_mikrotik: str) -> str:
    """IP deste computador na rede do roteador (o endereço que o MikroTik alcança)."""
    host = urlparse(url_mikrotik).hostname or url_mikrotik
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 80))  # UDP: não envia nada, só escolhe a placa de rede
        return s.getsockname()[0]


def enviar(mk: Mikrotik, envios: Envios, arquivos: dict[str, Path], pasta_roteador: str,
           base_url: str) -> dict:
    codigo = envios.abrir(arquivos)
    enviados, erros = [], []
    try:
        for nome in arquivos:
            url = f"{base_url}/hotspot-envio/{codigo}/{quote(nome)}"
            destino = f"{pasta_roteador.strip('/')}/{nome}"
            try:
                mk.executar(BUSCAR, {"url": url, "dst-path": destino, "mode": "http"})
                enviados.append(nome)
            except ErroAutenticacao:
                raise
            except ErroMikrotik as erro:
                erros.append(f"{nome}: {erro.mensagem}")
    finally:
        envios.fechar(codigo)
    return {"enviados": enviados, "erros": erros}
