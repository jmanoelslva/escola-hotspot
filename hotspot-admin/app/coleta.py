"""Histórico de uso da internet, guardado neste PC em dados/uso/AAAA-MM.csv.

A cada 5 minutos (com o usuário de serviço ativo) o painel lê do MikroTik:
- os contadores de bytes da interface da internet (baixado e enviado no período);
- quantas pessoas estão logadas no hotspot;
- quantos aparelhos pegaram IP no DHCP (todas as redes).
Cada linha: quando;segundos;baixado;enviado;sessoes;aparelhos. Guarda 13 meses.
"""

import csv
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import backup_config, sistema, util
from .mikrotik import Mikrotik

INTERVALO = 300
MESES_GUARDADOS = 13
_log = logging.getLogger("painel")


def _pasta(dados: Path) -> Path:
    pasta = dados / "uso"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


# ------------------------------------------------------------------ coleta

def coletar(mk: Mikrotik, dados: Path, agora: datetime | None = None) -> dict | None:
    """Lê o roteador e grava uma linha (a primeira leitura só guarda os contadores)."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    wan = sistema.interface_internet(mk)
    interface = next(iter(mk.listar("/interface", {"name": wan})), {}) if wan else {}
    rx, tx = util.inteiro(interface.get("rx-byte")), util.inteiro(interface.get("tx-byte"))
    sessoes = len(mk.listar("/ip/hotspot/active"))
    aparelhos = sum(1 for lease in mk.listar("/ip/dhcp-server/lease") if lease.get("status") == "bound")

    pasta = _pasta(dados)
    arquivo_ultimo = pasta / "ultimo.json"
    try:
        ultimo = json.loads(arquivo_ultimo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ultimo = None
    arquivo_ultimo.write_text(json.dumps({"quando": agora.isoformat(), "rx": rx, "tx": tx, "wan": wan}), encoding="utf-8")
    if not ultimo or ultimo.get("wan") != wan:
        return None
    segundos = int((agora - datetime.fromisoformat(ultimo["quando"])).total_seconds())
    if segundos <= 0 or segundos > 3 * INTERVALO:
        return None  # painel ficou parado: não inventa o consumo do intervalo
    # Contador menor que o anterior = roteador reiniciou: conta a partir do zero.
    baixado = rx - ultimo["rx"] if rx >= ultimo["rx"] else rx
    enviado = tx - ultimo["tx"] if tx >= ultimo["tx"] else tx
    linha = {"quando": agora.isoformat(), "segundos": segundos, "baixado": baixado, "enviado": enviado,
             "sessoes": sessoes, "aparelhos": aparelhos}
    with open(pasta / f"{agora:%Y-%m}.csv", "a", newline="", encoding="utf-8") as saida:
        csv.writer(saida, delimiter=";").writerow(linha.values())
    _limpar(pasta, agora)
    return linha


def _limpar(pasta: Path, agora: datetime) -> None:
    corte = (agora.replace(day=1) - timedelta(days=31 * MESES_GUARDADOS)).strftime("%Y-%m")
    for arquivo in pasta.glob("*.csv"):
        if arquivo.stem < corte:
            arquivo.unlink(missing_ok=True)


# ------------------------------------------------------------------ leitura

def ler(dados: Path, desde: datetime, ate: datetime) -> list[dict]:
    pasta = _pasta(dados)
    linhas = []
    mes = desde.replace(day=1)
    while mes <= ate:
        arquivo = pasta / f"{mes:%Y-%m}.csv"
        if arquivo.is_file():
            with open(arquivo, newline="", encoding="utf-8") as entrada:
                for campos in csv.reader(entrada, delimiter=";"):
                    if len(campos) != 6:
                        continue
                    quando = datetime.fromisoformat(campos[0])
                    if desde <= quando < ate:
                        linhas.append({"quando": quando, "segundos": int(campos[1]), "baixado": int(campos[2]),
                                       "enviado": int(campos[3]), "sessoes": int(campos[4]), "aparelhos": int(campos[5])})
        mes = (mes + timedelta(days=32)).replace(day=1)
    return linhas


def _mbps(byts: int, segundos: int) -> float:
    return round(byts * 8 / max(segundos, 1) / 1_000_000, 2)


def serie(dados: Path, periodo: str, agora: datetime | None = None) -> dict:
    """Pontos do gráfico: "dia" (cada 5 min, 24 h), "7d" (por hora) ou "30d" (por dia)."""
    agora = agora or datetime.now()
    if periodo == "dia":
        linhas = ler(dados, agora - timedelta(hours=24), agora + timedelta(seconds=1))
        pontos = [{"quando": l["quando"].isoformat(timespec="minutes"), "baixa": _mbps(l["baixado"], l["segundos"]),
                   "envia": _mbps(l["enviado"], l["segundos"]), "sessoes": l["sessoes"], "aparelhos": l["aparelhos"]}
                  for l in linhas]
        return {"periodo": periodo, "unidade": "Mbps", "pontos": pontos}

    por_hora = periodo == "7d"
    inicio = agora - (timedelta(days=7) if por_hora else timedelta(days=30))
    grupos: dict[str, list[dict]] = {}
    for l in ler(dados, inicio, agora + timedelta(seconds=1)):
        chave = l["quando"].strftime("%Y-%m-%dT%H:00" if por_hora else "%Y-%m-%d")
        grupos.setdefault(chave, []).append(l)
    pontos = []
    for chave, itens in sorted(grupos.items()):
        segundos = sum(i["segundos"] for i in itens)
        baixado, enviado = sum(i["baixado"] for i in itens), sum(i["enviado"] for i in itens)
        ponto = {"quando": chave, "sessoes": max(i["sessoes"] for i in itens), "aparelhos": max(i["aparelhos"] for i in itens)}
        if por_hora:
            ponto.update(baixa=_mbps(baixado, segundos), envia=_mbps(enviado, segundos))
        else:
            ponto.update(baixa=round(baixado / 1e9, 2), envia=round(enviado / 1e9, 2))
        pontos.append(ponto)
    return {"periodo": periodo, "unidade": "Mbps" if por_hora else "GB", "pontos": pontos}


def resumo_mes(dados: Path, ano: int, mes: int) -> dict:
    inicio = datetime(ano, mes, 1)
    fim = (inicio + timedelta(days=32)).replace(day=1)
    linhas = ler(dados, inicio, fim)
    dias: dict[str, dict] = {}
    for l in linhas:
        d = dias.setdefault(l["quando"].strftime("%Y-%m-%d"), {"baixado": 0, "enviado": 0, "sessoes": 0, "aparelhos": 0})
        d["baixado"] += l["baixado"]
        d["enviado"] += l["enviado"]
        d["sessoes"] = max(d["sessoes"], l["sessoes"])
        d["aparelhos"] = max(d["aparelhos"], l["aparelhos"])
    pico = max(linhas, key=lambda l: l["sessoes"], default=None)
    pico_aparelhos = max(linhas, key=lambda l: l["aparelhos"], default=None)
    return {
        "dias": [{"dia": dia, "baixado_gb": round(v["baixado"] / 1e9, 2), "enviado_gb": round(v["enviado"] / 1e9, 2),
                  "sessoes": v["sessoes"], "aparelhos": v["aparelhos"]} for dia, v in sorted(dias.items())],
        "baixado_gb": round(sum(l["baixado"] for l in linhas) / 1e9, 2),
        "enviado_gb": round(sum(l["enviado"] for l in linhas) / 1e9, 2),
        "pico_sessoes": {"valor": pico["sessoes"], "quando": pico["quando"].isoformat(timespec="minutes")} if pico else None,
        "pico_aparelhos": {"valor": pico_aparelhos["aparelhos"], "quando": pico_aparelhos["quando"].isoformat(timespec="minutes")}
        if pico_aparelhos else None,
        "amostras": len(linhas),
    }


# ------------------------------------------------------------------ coletor em segundo plano

class Coletor(threading.Thread):
    """Roda a coleta a cada 5 minutos enquanto o painel estiver ligado."""

    def __init__(self, conectar_servico, dados: Path):
        super().__init__(name="coletor-uso", daemon=True)
        self._conectar = conectar_servico
        self._dados = dados
        self._parar = threading.Event()

    def run(self) -> None:
        espera = 5  # primeira leitura logo depois de ligar
        while not self._parar.wait(espera):
            espera = INTERVALO
            try:
                mk = self._conectar()
                if mk is None:
                    continue
                with mk:
                    coletar(mk, self._dados)
                    backup_config.semanal(mk, self._dados)
            except Exception as erro:  # a coleta nunca derruba o painel
                _log.warning("coleta de uso falhou: %r", erro)

    def parar(self) -> None:
        self._parar.set()
