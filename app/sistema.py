"""Painel geral: saúde do roteador, tráfego das interfaces e aviso de atualização."""

import re
import threading
import time

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

RECURSOS = "/system/resource"
SAUDE = "/system/health"
INTERFACES = "/interface"
ROTAS = "/ip/route"
ATUALIZACAO = "/system/package/update"
ROUTERBOARD = "/system/routerboard"

# Tipos de interface que fazem sentido no gráfico (sem loopback, túneis internos etc.).
TIPOS_GRAFICO = ("ether", "bridge", "wlan", "wifi", "vlan", "pppoe-out", "pppoe-in", "lte", "bond", "wg", "sfp")

INTERVALO_VERIFICACAO = 6 * 3600


def _objeto(mk: Mikrotik, caminho: str) -> dict:
    """Comandos como /system/resource devolvem um objeto (ou lista com um item)."""
    dados = mk.ler(caminho)
    if isinstance(dados, list):
        return dados[0] if dados else {}
    return dados or {}


def _opcional(funcao, padrao):
    try:
        return funcao()
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        return padrao


def temperatura(mk: Mikrotik) -> float | None:
    dados = _opcional(lambda: mk.ler(SAUDE), None)
    if isinstance(dados, list):  # RouterOS 7: [{"name": "temperature", "value": "45", "type": "C"}, ...]
        for item in dados:
            if "temperature" in item.get("name", ""):
                try:
                    return float(item.get("value"))
                except (TypeError, ValueError):
                    pass
    elif isinstance(dados, dict):  # versões antigas: {"temperature": "45"}
        for chave, valor in dados.items():
            if "temperature" in chave:
                try:
                    return float(valor)
                except (TypeError, ValueError):
                    pass
    return None


def interface_internet(mk: Mikrotik) -> str:
    """Interface da rota padrão (immediate-gw '192.168.0.1%ether1' ou gateway = interface)."""
    rotas = _opcional(lambda: mk.listar(ROTAS, {"dst-address": "0.0.0.0/0"}), [])
    for rota in rotas:
        if util.sim(rota.get("disabled")) or (rota.get("active") is not None and not util.sim(rota.get("active"))):
            continue
        gateway = rota.get("immediate-gw") or rota.get("gateway") or ""
        if "%" in gateway:
            return gateway.split("%", 1)[1]
        if gateway and not re.match(r"^\d+\.\d+\.\d+\.\d+$", gateway):
            return gateway
    return ""


def resumo(mk: Mikrotik) -> dict:
    recursos = _objeto(mk, RECURSOS)
    memoria_total = util.inteiro(recursos.get("total-memory"))
    memoria_livre = util.inteiro(recursos.get("free-memory"))
    interfaces = []
    for item in mk.listar(INTERFACES):
        tipo = item.get("type", "")
        if not tipo.startswith(TIPOS_GRAFICO):
            continue
        interfaces.append({
            "nome": item.get("name", ""),
            "tipo": tipo,
            "comentario": item.get("comment", ""),
            "ligada": util.sim(item.get("running")) and not util.sim(item.get("disabled")),
        })
    return {
        "modelo": recursos.get("board-name", ""),
        "versao": recursos.get("version", ""),
        "cpu": util.inteiro(recursos.get("cpu-load")),
        "memoria_total": memoria_total,
        "memoria_usada": max(memoria_total - memoria_livre, 0),
        "uptime": recursos.get("uptime", ""),
        "temperatura": temperatura(mk),
        "internet": interface_internet(mk),
        "interfaces": sorted(interfaces, key=lambda i: (not i["ligada"], i["nome"])),
    }


def trafego(mk: Mikrotik, nomes: list[str]) -> list[dict]:
    """Uma leitura de /interface/monitor-traffic (bits por segundo) das interfaces pedidas."""
    if not nomes:
        return []
    resposta = mk.executar(f"{INTERFACES}/monitor-traffic", {"interface": ",".join(nomes), "once": ""})
    itens = resposta if isinstance(resposta, list) else [resposta or {}]
    resultado = []
    for item in itens:
        resultado.append({
            "nome": item.get("name", ""),
            "entrada_bps": util.inteiro(item.get("rx-bits-per-second")),
            "saida_bps": util.inteiro(item.get("tx-bits-per-second")),
        })
    return resultado


# ------------------------------------------------------------------ atualização

class VerificadorAtualizacao:
    """Guarda a última consulta para não perguntar ao MikroTik (e aos servidores
    da MikroTik) a cada tela aberta: no máximo uma vez a cada 6 horas."""

    def __init__(self):
        self._resultado: dict | None = None
        self._quando = 0.0
        self._trava = threading.Lock()

    def obter(self, mk: Mikrotik, forcar: bool = False) -> dict:
        with self._trava:
            if not forcar and self._resultado and time.monotonic() - self._quando < INTERVALO_VERIFICACAO:
                return self._resultado
        resultado = verificar(mk)
        with self._trava:
            self._resultado, self._quando = resultado, time.monotonic()
        return resultado

    def esquecer(self) -> None:
        with self._trava:
            self._resultado = None


def _versao(texto: str) -> tuple[int, ...]:
    """'7.16.1' -> (7, 16, 1); sufixo de teste ('7.17beta2', '7.15.3 (stable)') é ignorado."""
    m = re.match(r"\s*(\d+(?:\.\d+)*)", texto or "")
    return tuple(int(n) for n in m.group(1).split(".")) if m else ()


def verificar(mk: Mikrotik) -> dict:
    # check-for-updates consulta os servidores da MikroTik (o roteador precisa de internet).
    erro = ""
    try:
        mk.executar(f"{ATUALIZACAO}/check-for-updates")
    except ErroAutenticacao:
        raise
    except ErroMikrotik as falha:
        erro = falha.mensagem
    estado = _objeto(mk, ATUALIZACAO)
    instalada = estado.get("installed-version", "")
    disponivel = estado.get("latest-version", "")
    status = estado.get("status", "") or erro
    tem_routeros = bool(instalada and disponivel and _versao(disponivel) > _versao(instalada))

    placa = _opcional(lambda: _objeto(mk, ROUTERBOARD), {})
    firmware_atual = placa.get("current-firmware", "")
    firmware_novo = placa.get("upgrade-firmware", "")
    tem_firmware = bool(firmware_atual and firmware_novo and _versao(firmware_novo) > _versao(firmware_atual))

    return {
        "canal": estado.get("channel", ""),
        "instalada": instalada,
        "disponivel": disponivel,
        "status": status,
        "atualizacao_routeros": tem_routeros,
        "firmware_atual": firmware_atual,
        "firmware_novo": firmware_novo,
        "atualizacao_firmware": tem_firmware,
        "verificado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "falhou": bool(erro) or status.upper().startswith("ERROR"),
    }
