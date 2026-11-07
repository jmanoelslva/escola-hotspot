"""Cópia da configuração inteira do MikroTik (/export terse) guardada neste PC.

Uma vez por semana, sozinha (pelo usuário de serviço ou no primeiro login), e
quando alguém pede em Sistema → Backup. Inclui as senhas (show-sensitive) para
que a cópia sirva para reconstruir o roteador: fica em dados\\backups-config,
junto dos outros dados que não vão para o repositório.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import util
from .mikrotik import Mikrotik

COMANDO = "/export terse show-sensitive"
MANTER = 12  # cerca de 3 meses de cópias semanais
DIAS_ENTRE_COPIAS = 7
_NOME = re.compile(r"^config-(\d{4}-\d{2}-\d{2}-\d{6})\.rsc$")

ESPERA_APOS_FALHA = 6 * 3600

log = logging.getLogger("painel")
_ultima_falha = 0.0


def pasta(dados: Path) -> Path:
    destino = dados / "backups-config"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def exportar(mk: Mikrotik) -> str:
    """Texto do /export pela REST (POST /execute com as-string devolve {"ret": "..."})."""
    resposta = mk.executar("/execute", {"script": COMANDO, "as-string": ""})
    texto = resposta.get("ret", "") if isinstance(resposta, dict) else ""
    if not texto.strip().startswith("#"):
        raise util.ErroDados("O MikroTik não devolveu a configuração.")
    return texto.replace("\r\n", "\n")


def salvar(dados: Path, texto: str, agora: datetime | None = None) -> str:
    agora = agora or datetime.now()
    nome = f"config-{agora:%Y-%m-%d-%H%M%S}.rsc"
    (pasta(dados) / nome).write_text(texto, encoding="utf-8", newline="\n")
    for antigo in [a["nome"] for a in listar(dados)][MANTER:]:
        (pasta(dados) / antigo).unlink(missing_ok=True)
    return nome


def listar(dados: Path) -> list[dict]:
    itens = []
    for arquivo in pasta(dados).iterdir():
        m = _NOME.match(arquivo.name)
        if not m:
            continue
        quando = datetime.strptime(m.group(1), "%Y-%m-%d-%H%M%S")
        itens.append({"nome": arquivo.name, "criado_em": f"{quando:%Y-%m-%dT%H:%M:%S}",
                      "tamanho": arquivo.stat().st_size})
    return sorted(itens, key=lambda i: i["criado_em"], reverse=True)


def caminho(dados: Path, nome: str) -> Path:
    if not _NOME.match(nome or ""):
        raise util.ErroDados("Arquivo de configuração inválido.")
    arquivo = pasta(dados) / nome
    if not arquivo.is_file():
        raise util.ErroDados("Cópia da configuração não encontrada.")
    return arquivo


def precisa(dados: Path, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now()
    ultimo = next(iter(listar(dados)), None)
    return ultimo is None or datetime.fromisoformat(ultimo["criado_em"]) <= agora - timedelta(days=DIAS_ENTRE_COPIAS)


def semanal(mk: Mikrotik, dados: Path) -> str | None:
    """Faz a cópia se a última tiver 7 dias ou mais. Nunca levanta erro."""
    global _ultima_falha
    if not precisa(dados) or time.monotonic() - _ultima_falha < ESPERA_APOS_FALHA and _ultima_falha:
        return None
    try:
        nome = salvar(dados, exportar(mk))
        log.info("cópia semanal da configuração do MikroTik: %s", nome)
        return nome
    except Exception as erro:
        _ultima_falha = time.monotonic()
        log.warning("cópia semanal da configuração falhou: %r", erro)
        return None
