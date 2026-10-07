"""Rede Alunos: aberta nos horários ou quando o painel libera.

Quem liga e desliga a interface é o script painel-alunos do próprio MikroTik,
que roda a cada minuto (agendador painel-alunos). O painel escreve esse script
(interface e horários, cada um com os seus dias) e cria ou apaga os agendadores
que ele consulta:
- painel-alunos-liberado: aberta até a hora marcada (depois se apaga);
- painel-alunos-fechado: fechada até o fim do horário atual (depois se apaga).
Modos: "horario" (o agendador roda), "aberta" e "fechada" (agendador parado,
interface ligada ou desligada). Tudo continua valendo com o painel fechado.
"""

import re
from dataclasses import dataclass
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
MAX_JANELAS = 20
DIAS_UTEIS = frozenset({1, 2, 3, 4, 5})  # 0 = domingo ... 6 = sábado (como no script)
MODOS = ("horario", "aberta", "fechada")

_JANELAS = re.compile(r':local janelas \{([^}]*)\}')
# "08:50-09:10 12345" (com os dias) ou "08:50-09:10" (formato antigo: segunda a sexta)
_JANELA = re.compile(r'"(\d{2}):(\d{2})-(\d{2}):(\d{2})(?: ([0-6]{1,7}))?"')
_VLAN = re.compile(r':local vlan "([^"]+)"')
_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_NOME_INTERFACE = re.compile(r'^[^"\\$\r\n]{1,64}$')
_MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


@dataclass(frozen=True)
class Janela:
    dias: frozenset[int]
    inicio: time
    fim: time

    def para_json(self) -> dict:
        return {"inicio": f"{self.inicio:%H:%M}", "fim": f"{self.fim:%H:%M}", "dias": sorted(self.dias)}


def _dia_semana(quando: datetime) -> int:
    return (quando.weekday() + 1) % 7  # Python: segunda = 0; aqui: domingo = 0


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


# ------------------------------------------------------------------ horários

def ler_janelas(fonte: str) -> list[Janela]:
    m = _JANELAS.search(fonte or "")
    if not m:
        return []
    return [Janela(frozenset(int(d) for d in dias) if dias else DIAS_UTEIS, time(int(a), int(b)), time(int(c), int(d)))
            for a, b, c, d, dias in _JANELA.findall(m.group(1))]


def validar_janelas(itens: list[dict]) -> list[Janela]:
    if len(itens) > MAX_JANELAS:
        raise util.ErroDados(f"No máximo {MAX_JANELAS} horários.")
    janelas = []
    for n, item in enumerate(itens, 1):
        inicio, fim = str(item.get("inicio", "")).strip(), str(item.get("fim", "")).strip()
        if not _HORA.match(inicio) or not _HORA.match(fim):
            raise util.ErroDados(f"Horário {n}: use horas no formato 08:50.")
        ini, fi = time(*map(int, inicio.split(":"))), time(*map(int, fim.split(":")))
        if ini >= fi:
            raise util.ErroDados(f"Horário {n}: o início ({inicio}) precisa ser antes do fim ({fim}).")
        dias = frozenset(int(d) for d in item.get("dias", []) if str(d).isdigit() and 0 <= int(d) <= 6)
        if not dias:
            raise util.ErroDados(f"Horário {n}: marque pelo menos um dia.")
        janelas.append(Janela(dias, ini, fi))
    return sorted(janelas, key=lambda j: (min(j.dias), j.inicio, j.fim))


def janela_atual(janelas: list[Janela], agora: datetime) -> tuple[datetime, datetime] | None:
    """Horário em que estamos agora (no dia da semana dele)."""
    dia = _dia_semana(agora)
    for j in janelas:
        if dia in j.dias and j.inicio <= agora.time() < j.fim:
            return datetime.combine(agora.date(), j.inicio), datetime.combine(agora.date(), j.fim)
    return None


def proxima_abertura(janelas: list[Janela], depois: datetime) -> datetime | None:
    for dias in range(8):
        dia = (depois + timedelta(days=dias)).date()
        semana = _dia_semana(datetime.combine(dia, time()))
        for j in sorted(janelas, key=lambda j: j.inicio):
            quando = datetime.combine(dia, j.inicio)
            if semana in j.dias and quando >= depois:
                return quando
    return None


def montar_script(vlan: str, janelas: list[Janela]) -> str:
    itens = ";".join(f'"{j.inicio:%H:%M}-{j.fim:%H:%M} {"".join(str(d) for d in sorted(j.dias))}"' for j in janelas)
    return f''':local janelas {{{itens}}}
:local vlan "{vlan}"
# Rede Alunos: aberta nos horarios ou quando o painel libera. Roda a cada minuto
# (agendador painel-alunos). Gerado pelo Painel do Hotspot: altere pelo painel.
# Cada horario: "inicio-fim dias", dias 0=dom 1=seg 2=ter 3=qua 4=qui 5=sex 6=sab.
:local d [/system clock get date]
:local ano [:tonum [:pick $d 0 4]]
:local mes ([:tonum ("1" . [:pick $d 5 7])] - 100)
:local dia ([:tonum ("1" . [:pick $d 8 10])] - 100)
:local tab {{0;3;2;5;0;3;5;1;4;6;2;4}}
:if ($mes < 3) do={{ :set ano ($ano - 1) }}
:local semana (($ano + ($ano / 4) - ($ano / 100) + ($ano / 400) + ($tab->($mes - 1)) + $dia) % 7)
:local agora [:totime [/system clock get time]]
:local aberta false
:foreach j in=$janelas do={{
    :local ini [:totime ([:pick $j 0 5] . ":00")]
    :local fim [:totime ([:pick $j 6 11] . ":00")]
    :local dias [:pick $j 12 [:len $j]]
    :if ([:len $dias] = 0) do={{ :set dias "12345" }}
    :if (([:typeof [:find $dias [:tostr $semana]]] != "nil") && ($agora >= $ini) && ($agora < $fim)) do={{ :set aberta true }}
}}
:if ([:len [/system scheduler find name="{FECHADO}"]] > 0) do={{ :set aberta false }}
:if ([:len [/system scheduler find name="{LIBERADO}"]] > 0) do={{ :set aberta true }}
:local desligada [/interface get [find name=$vlan] disabled]
:if ($aberta && $desligada) do={{
    /interface enable [find name=$vlan]
    :log info "painel-alunos: rede Alunos aberta"
}}
:if ((!$aberta) && (!$desligada)) do={{
    /interface disable [find name=$vlan]
    :log info "painel-alunos: rede Alunos fechada"
}}
'''


# ------------------------------------------------------------------ estado

def _iso(quando: datetime | None) -> str:
    return f"{quando:%Y-%m-%dT%H:%M}" if quando else ""


def _ate(agendamento: dict) -> datetime | None:
    try:
        return datetime.combine(_data(agendamento.get("start-date", "")), _hora(agendamento.get("start-time", "")))
    except (ValueError, IndexError):
        return None


def _script(mk: Mikrotik) -> dict | None:
    return next(iter(mk.listar(SCRIPTS, {"name": SCRIPT})), None)


def _agendador(mk: Mikrotik) -> dict | None:
    return next(iter(mk.listar(AGENDAMENTOS, {"name": SCRIPT})), None)


def interfaces(mk: Mikrotik) -> list[dict]:
    lista = [{"nome": i.get("name", ""), "tipo": i.get("type", ""), "desativada": util.sim(i.get("disabled")),
              "ativa": util.sim(i.get("running"))}
             for i in mk.listar(INTERFACES) if i.get("type") != "loopback" and not util.sim(i.get("dynamic"))]
    return sorted(lista, key=lambda i: (i["tipo"] != "vlan", i["nome"].lower()))


def estado(mk: Mikrotik) -> dict:
    script = _script(mk)
    agendador = _agendador(mk)
    if not script or not agendador:
        return {"configurado": False, "janelas": [j.para_json() for j in ler_janelas(script.get("source", ""))] if script else [],
                "interface": VLAN_PADRAO}
    fonte = script.get("source", "")
    m = _VLAN.search(fonte)
    vlan = m.group(1) if m else VLAN_PADRAO
    interface = next(iter(mk.listar(INTERFACES, {"name": vlan})), None)
    janelas = ler_janelas(fonte)
    base = {"configurado": True, "interface": vlan, "janelas": [j.para_json() for j in janelas]}
    if not interface:
        return {**base, "configurado": False, "erro": f"A interface {vlan} não existe no MikroTik."}

    aberta = interface.get("disabled") != "true"
    if util.sim(agendador.get("disabled")):
        return {**base, "aberta": aberta, "modo": "aberta" if aberta else "fechada", "motivo": "fixo",
                "agora": "", "abre_em": "", "fecha_em": ""}

    agora = relogio(mk)
    agendados = {a.get("name"): a for a in mk.listar(AGENDAMENTOS) if a.get("name") in (LIBERADO, FECHADO)}
    atual = janela_atual(janelas, agora)
    abre_em = fecha_em = None
    if LIBERADO in agendados:
        motivo = "liberado"
        fecha_em = max(filter(None, [_ate(agendados[LIBERADO]), atual[1] if atual else None]), default=None)
    elif FECHADO in agendados:
        motivo = "fechado"
        abre_em = proxima_abertura(janelas, _ate(agendados[FECHADO]) or agora)
    elif atual:
        motivo = "horario"
        fecha_em = atual[1]
    else:
        motivo = "fora"
        abre_em = proxima_abertura(janelas, agora)
    return {**base, "aberta": aberta, "modo": "horario", "motivo": motivo,
            "agora": _iso(agora), "abre_em": _iso(abre_em), "fecha_em": _iso(fecha_em)}


# ------------------------------------------------------------------ ações

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


def _exigir_horario(mk: Mikrotik) -> dict:
    script = _script(mk)
    agendador = _agendador(mk)
    if not script or not agendador:
        raise util.ErroDados("A rede Alunos ainda não está configurada: escolha a interface e os horários e salve.")
    if util.sim(agendador.get("disabled")):
        raise util.ErroDados("A rede Alunos está em modo fixo. Volte para \"Por horário\" para liberar ou fechar por um tempo.")
    return script


def _definir_interface(mk: Mikrotik, nome: str, ligada: bool) -> None:
    for i in mk.listar(INTERFACES, {"name": nome}):
        if util.sim(i.get("disabled")) == ligada:
            mk.alterar(INTERFACES, i[".id"], {"disabled": "false" if ligada else "true"})


def configurar(mk: Mikrotik, vlan: str, itens: list[dict]) -> None:
    """Grava a interface e os horários no script (cria script e agendador se faltarem)."""
    vlan = (vlan or "").strip()
    if not _NOME_INTERFACE.match(vlan) or not mk.listar(INTERFACES, {"name": vlan}):
        raise util.ErroDados("Escolha uma interface que exista no MikroTik.")
    janelas = validar_janelas(itens)
    fonte = montar_script(vlan, janelas)
    script = _script(mk)
    if script:
        m = _VLAN.search(script.get("source", ""))
        anterior = m.group(1) if m else ""
        mk.alterar(SCRIPTS, script[".id"], {"source": fonte})
        if anterior and anterior != vlan:
            _definir_interface(mk, anterior, True)  # a interface antiga deixa de ser controlada: fica ligada
    else:
        mk.criar(SCRIPTS, {"name": SCRIPT, "source": fonte, "policy": "read,write,test",
                           "comment": "Painel do Hotspot: abre e fecha a rede Alunos"})
    if not _agendador(mk):
        mk.criar(AGENDAMENTOS, {"name": SCRIPT, "interval": "1m", "start-time": "startup", "policy": "read,write,test",
                                "on-event": f"/system script run {SCRIPT}",
                                "comment": "Painel do Hotspot: horario da rede Alunos"})
    agendador = _agendador(mk)
    if agendador and not util.sim(agendador.get("disabled")):
        _aplicar(mk, _script(mk))


def definir_modo(mk: Mikrotik, modo: str) -> None:
    if modo not in MODOS:
        raise util.ErroDados("Modo inválido.")
    script, agendador = _script(mk), _agendador(mk)
    if not script or not agendador:
        raise util.ErroDados("A rede Alunos ainda não está configurada: escolha a interface e os horários e salve.")
    m = _VLAN.search(script.get("source", ""))
    vlan = m.group(1) if m else VLAN_PADRAO
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    mk.alterar(AGENDAMENTOS, agendador[".id"], {"disabled": "false" if modo == "horario" else "true"})
    if modo == "horario":
        _aplicar(mk, script)
    else:
        _definir_interface(mk, vlan, modo == "aberta")


def liberar(mk: Mikrotik, minutos: int) -> datetime:
    if minutos < MIN_MINUTOS or minutos > MAX_MINUTOS:
        raise util.ErroDados(f"Libere entre {MIN_MINUTOS} minutos e {MAX_MINUTOS // 60} horas.")
    script = _exigir_horario(mk)
    ate = (relogio(mk) + timedelta(minutes=minutos)).replace(second=0)
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    _agendar_fim(mk, LIBERADO, ate, f"rede Alunos liberada até {ate:%d/%m %H:%M}")
    _aplicar(mk, script)
    return ate


def fechar(mk: Mikrotik) -> datetime | None:
    """Fecha agora; dentro de um horário, fica fechada até o fim dele."""
    script = _exigir_horario(mk)
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    atual = janela_atual(ler_janelas(script.get("source", "")), relogio(mk))
    if atual:
        _agendar_fim(mk, FECHADO, atual[1], f"rede Alunos fechada até {atual[1]:%H:%M}")
    _aplicar(mk, script)
    return atual[1] if atual else None


def voltar_ao_horario(mk: Mikrotik) -> None:
    script = _exigir_horario(mk)
    _remover_agendamentos(mk, LIBERADO, FECHADO)
    _aplicar(mk, script)
