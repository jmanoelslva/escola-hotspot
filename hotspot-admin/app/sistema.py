"""Painel geral: saúde do roteador, tráfego das interfaces e aviso de atualização."""

import logging
import re
import threading
import time
from datetime import datetime

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

log = logging.getLogger("painel")


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


# ------------------------------------------------------------------ relógio

RELOGIO = "/system/clock"
NTP = "/system/ntp/client"
TOLERANCIA_RELOGIO = 120  # segundos de diferença para o PC antes de avisar
_MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _data_relogio(data: str, hora: str) -> datetime | None:
    """"2026-11-07" (7.10+) ou "nov/07/2026", com "HH:MM:SS"."""
    try:
        if "/" in data:
            mes, dia, ano = data.split("/")
            data = f"{ano}-{_MESES.index(mes.lower()) + 1:02d}-{dia}"
        return datetime.strptime(f"{data} {hora[:8]}", "%Y-%m-%d %H:%M:%S")
    except (ValueError, IndexError):
        return None


def _texto_diferenca(segundos: int) -> str:
    minutos = round(abs(segundos) / 60)
    quanto = f"{minutos} minuto(s)" if minutos < 120 else f"{round(minutos / 60)} hora(s)"
    return f"{quanto} {'adiantada' if segundos > 0 else 'atrasada'}"


def relogio(mk: Mikrotik, agora: datetime | None = None) -> dict:
    """Hora do MikroTik contra a deste PC e o estado do NTP: os visitantes e a
    rede Alunos dependem do relógio do roteador."""
    agora = agora or datetime.now()
    clock = _objeto(mk, RELOGIO)
    hora_mk = _data_relogio(clock.get("date", ""), clock.get("time", ""))
    ntp = _opcional(lambda: _objeto(mk, NTP), {})
    diferenca = round((hora_mk - agora).total_seconds()) if hora_mk else None
    ntp_ligado = util.sim(ntp.get("enabled"))
    sincronizado = ntp_ligado and ntp.get("status", "") == "synchronized"
    motivos = []
    if diferenca is None:
        motivos.append("não foi possível ler a hora do MikroTik")
    elif abs(diferenca) > TOLERANCIA_RELOGIO:
        motivos.append(f"a hora do MikroTik está {_texto_diferenca(diferenca)} em relação a este computador")
    if not ntp_ligado:
        motivos.append("o NTP do MikroTik está desligado")
    elif not sincronizado:
        motivos.append(f"o NTP do MikroTik não está sincronizado ({ntp.get('status') or 'sem resposta'})")
    return {
        "hora": f"{hora_mk:%Y-%m-%dT%H:%M:%S}" if hora_mk else "",
        "fuso": clock.get("time-zone-name", ""),
        "diferenca": diferenca,
        "ntp_ligado": ntp_ligado,
        "sincronizado": sincronizado,
        "servidor": ntp.get("synced-server", ""),
        "servidores": [s for s in (ntp.get("servers") or "").split(",") if s],
        "alerta": bool(motivos),
        "motivos": motivos,
    }


# ------------------------------------------------------------------ atualização do painel

REPOSITORIO = "jmanoelslva/escola-hotspot"
URL_RELEASE = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"


def verificar_painel(versao_atual: str, buscar=None) -> dict:
    """Última release do painel no GitHub (repositório público, sem token)."""
    import httpx

    resultado = {"atual": versao_atual, "disponivel": "", "tem": False, "nome": "", "url": "", "zip": "",
                 "verificado_em": time.strftime("%Y-%m-%dT%H:%M:%S"), "falhou": False, "motivo": ""}
    try:
        if buscar:
            dados = buscar()
        else:
            resposta = httpx.get(URL_RELEASE, timeout=10, headers={"Accept": "application/vnd.github+json",
                                                                    "User-Agent": "painel-hotspot"})
            resposta.raise_for_status()
            dados = resposta.json()
    except Exception as erro:  # sem internet no PC, GitHub fora etc.
        log.info("verificação do painel falhou: %r", erro)
        return {**resultado, "falhou": True, "motivo": "sem resposta do GitHub"}
    disponivel = (dados.get("tag_name") or "").lstrip("v")
    return {**resultado, "disponivel": disponivel, "nome": dados.get("name", ""), "url": dados.get("html_url", ""),
            "zip": dados.get("zipball_url", ""),
            "tem": bool(disponivel and _versao(disponivel) > _versao(versao_atual))}


class VerificadorPainel:
    """Consulta o GitHub no máximo a cada 6 horas."""

    def __init__(self, versao_atual: str, buscar=None):
        self._versao = versao_atual
        self._buscar = buscar
        self._resultado: dict | None = None
        self._quando = 0.0
        self._trava = threading.Lock()

    def obter(self, forcar: bool = False) -> dict:
        with self._trava:
            if not forcar and self._resultado and time.monotonic() - self._quando < INTERVALO_VERIFICACAO:
                return self._resultado
        resultado = verificar_painel(self._versao, self._buscar)
        with self._trava:
            self._resultado, self._quando = resultado, time.monotonic()
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

    log.info("verificação de atualização: instalada=%s disponível=%s status=%r firmware=%s/%s erro=%r",
             instalada, disponivel, status, firmware_atual, firmware_novo, erro)
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


# ------------------------------------------------------------------ licença do RouterOS

# Usuários logados no hotspot ao mesmo tempo, por nível de licença (None = sem limite).
LIMITE_HOTSPOT = {3: 1, 4: 200, 5: 500, 6: None}
LIMITE_PADRAO = 200  # nível 4, o que vem no hEX


def licenca(mk: Mikrotik) -> dict:
    dados = _opcional(lambda: mk.ler("/system/license"), {}) or {}
    if isinstance(dados, list):
        dados = dados[0] if dados else {}
    texto = str(dados.get("nlevel") or dados.get("level") or "")
    nivel = int(texto) if texto.isdigit() else None
    limite = LIMITE_HOTSPOT.get(nivel, LIMITE_PADRAO) if nivel is not None else LIMITE_PADRAO
    return {"nivel": nivel, "limite_hotspot": limite}
