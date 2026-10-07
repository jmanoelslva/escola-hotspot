"""Leitura do dados/acoes.log (e dos arquivos girados acoes.log.1 ... .5)."""

import re
from datetime import datetime, timedelta
from pathlib import Path

_LINHA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+) (.*)$")
MAXIMO = 1000


def ler(pasta_dados: Path, busca: str = "", usuario: str = "", dias: int = 30) -> list[dict]:
    arquivos = [pasta_dados / "acoes.log"] + [pasta_dados / f"acoes.log.{i}" for i in range(1, 6)]
    limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S") if dias > 0 else ""
    busca = busca.strip().lower()
    usuario = usuario.strip().lower()
    itens = []
    for arquivo in arquivos:
        if not arquivo.is_file():
            continue
        for linha in arquivo.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _LINHA.match(linha)
            if not m:
                continue
            quando, quem, acao = m.groups()
            if limite and quando < limite:
                continue
            if usuario and quem.lower() != usuario:
                continue
            if busca and busca not in acao.lower() and busca not in quem.lower():
                continue
            itens.append({"quando": quando, "usuario": quem, "acao": acao})
    itens.sort(key=lambda i: i["quando"], reverse=True)
    return itens[:MAXIMO]
