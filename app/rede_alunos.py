"""Rede Alunos (VLAN 300): aberta nos horários ou quando o painel libera.

Quem liga e desliga a VLAN é o script painel-alunos do próprio MikroTik
(instalado pelo mikrotik-redes.rsc), que roda a cada minuto. O painel só cria
ou apaga os agendadores que o script consulta e o executa na hora:
- painel-alunos-liberado: aberta até a hora marcada (depois se apaga);
- painel-alunos-fechado: fechada até o fim do horário atual (depois se apaga).
Assim tudo continua valendo com o painel fechado ou o roteador reiniciado.
"""

import re
from datetime import datetime, time, timedelta

from . import util, visitantes
from .mikrotik import Mikrotik

SCRIPTS = "/system/script"
AGENDAMENTOS = "/system/scheduler"
INTERFACES = "/interface"

SCRIPT = "painel-alunos"
LIBERADO = "painel-alunos-liberado"
FECHADO = "painel-alunos-fechado"
VLAN_PADRAO = "VLAN300-ALUNOS"
MIN_MINUTOS = 5
MAX_MINUTOS = 8 * 60

_JANELAS = re.compile(r':local janelas \{([^}]*)\}')
_JANELA = re.compile(r'"(\d{2}):(\d{2})-(\d{2}):(\d{2})"')
_VLAN = re.compile(r':local vlan "([^"]+)"')
_MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _data(texto: str) -> datetime:
    """Data do RouterOS: AAAA-MM-DD (7.10+) ou mmm/dd/aaaa."""
    if "/" in texto:
        mes, dia, ano = texto.split("/")
        return datetime(int(ano), _MESES.index(mes.lower()) + 1, int(dia))
    return datetime.strptime(texto, "%Y-%m-%d")


def _hora(texto: str) -> time:
    return datetime.strptime(texto[:8], "%H:%M:%S").time()


def relogio(mk: Mikrotik) -> datetime:
    c = mk.ler("/system/clock") or {}
    return datetime.combine(_data(c.get("date", "")), _hora(c.get("time", "00:00:00")))


def ler_janelas(fonte: str) -> list[tuple[time, time]]:
    m = _JANELAS.search(fonte or "")
    if not m:
        return []
    return [(time(int(a), int(b)), time(int(c), int(d))) for a, b, c, d in _JANELA.findall(m.group(1))]


def janela_atual(janelas: list[tuple[time, time]], agora: datetime) -> tuple[datetime, datetime] | None:
    """Horário em que estamos agora (só de segunda a sexta)."""
    if agora.weekday() > 4:
        return None
    for ini, fim in janelas:
        if ini <= agora.time() < fim:
            return datetime.combine(agora.date(), ini), datetime.combine(agora.date(), fim)
    return None


def proxima_abertura(janelas: list[tuple[time, time]], depois: datetime) -> datetime | None:
    for dias in range(8):
        dia = (depois + timedelta(days=dias)).date()
        if dia.weekday() > 4:
            continue
        for ini, _fim in sorted(janelas):
            quando = datetime.combine(dia, ini)
            if quando >= depois:
                return quando
    return None


def _ate(agendamento: dict) -> datetime | None:
    try:
        return datetime.combine(_data(agendamento.get("start-date", "")), _hora(agendamento.get("start-time", "")))
    except (ValueError, IndexError):
        return None


def _iso(quando: datetime | None) -> str:
    return f"{quando:%Y-%m-%dT%H:%M}" if quando else ""


def _script(mk: Mikrotik) -> dict | None:
    return next(iter(mk.listar(SCRIPTS, {"name": SCRIPT})), None)


def estado(mk: Mikrotik) -> dict:
    script = _script(mk)
    if not script:
        return {"configurado": False}
    fonte = script.get("source", "")
    m = _VLAN.search(fonte)
    vlan = m.group(1) if m else VLAN_PADRAO
    interface = next(iter(mk.listar(INTERFACES, {"name": vlan})), None)
    if not interface:
        return {"configurado": False, "erro": f"A interface {vlan} não existe no MikroTik."}

    janelas = ler_janelas(fonte)
    agora = relogio(mk)
    agendados = {a.get("name"): a for a in mk.listar(AGENDAMENTOS) if a.get("name") in (LIBERADO, FECHADO)}
    liberado_ate = _ate(agendados[LIBERADO]) if LIBERADO in agendados else None
    fechado_ate = _ate(agendados[FECHADO]) if FECHADO in agendados else None
    atual = janela_atual(janelas, agora)

    abre_em = fecha_em = None
    if LIBERADO in agendados:
        motivo = "liberado"
        fecha_em = max(filter(None, [liberado_ate, atual[1] if atual else None]), default=None)
    elif FECHADO in agendados:
        motivo = "fechado"
        abre_em = proxima_abertura(janelas, fechado_ate or agora)
    elif atual:
        motivo = "horario"
        fecha_em = atual[1]
    else:
        motivo = "fora"
        abre_em = proxima_abertura(janelas, agora)

    return {
        "configurado": True,
        "interface": vlan,
        "aberta": interface.get("disabled") != "true",
        "motivo": motivo,
        "agora": _iso(agora),
        "abre_em": _iso(abre_em),
        "fecha_em": _iso(fecha_em),
        "janelas": [[f"{i:%H:%M}", f"{f:%H:%M}"] for i, f in janelas],
    }


def _remover_agendamentos(mk: Mikrotik, *nomes: str) -> None:
    for a in mk.listar(AGENDAMENTOS):
        if a.get("name") in nomes:
            mk.remover(AGENDAMENTOS, a[".id"])


def _agendar_fim(mk: Mikrotik, nome: str, quando: datetime, descricao: str) -> None:
    visitantes.agendar_uma_vez(mk, {
        "name": nome,
        "on-event": f'/system scheduler remove [find name="{nome}"]; /system script run {SCRIPT}',
        "comment": f"Painel do Hotspot: {descricao}",
    }, quando)


def _aplicar(mk: Mikrotik, script: dict) -> None:
    """Roda o painel-alunos agora, sem esperar o próximo minuto."""
    mk.executar(f"{SCRIPTS}/run", {".id": script[".id"]})


def _exigir_script(mk: Mikrotik) -> dict:
    script = _script(mk)
    if not script:
        raise util.ErroDados("O MikroTik ainda não tem o script painel-alunos. Rode o mikrotik-redes.rsc.")
    return script


def liberar(mk: Mikrotik, minutos: int) -> datetime:
    if minutos < MIN_MINUTOS or minutos > MAX_MINUTOS:
        raise util.ErroDados(f"Libere entre {MIN_MINUTOS} minutos e {MAX_MINUTOS // 60} horas.")
    script = _exigir_script(mk)
    ate = (relogio(mk) + timedelta(minutes=minutos)).replace(second=0)
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    _agendar_fim(mk, LIBERADO, ate, f"rede Alunos liberada até {ate:%d/%m %H:%M}")
    _aplicar(mk, script)
    return ate


def fechar(mk: Mikrotik) -> datetime | None:
    """Fecha agora; dentro de um horário, fica fechada até o fim dele."""
    script = _exigir_script(mk)
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    atual = janela_atual(ler_janelas(script.get("source", "")), relogio(mk))
    if atual:
        _agendar_fim(mk, FECHADO, atual[1], f"rede Alunos fechada até {atual[1]:%H:%M}")
    _aplicar(mk, script)
    return atual[1] if atual else None


def voltar_ao_horario(mk: Mikrotik) -> None:
    script = _exigir_script(mk)
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    _aplicar(mk, script)
