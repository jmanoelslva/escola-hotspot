"""Rede Alunos: interface, horários com dias, modos, liberar e fechar."""

from datetime import datetime, time

from app import rede_alunos

AGENDA = "/system/scheduler"
SCRIPTS = "/system/script"
ANTIGO = ':local janelas {"08:50-09:10";"12:00-12:50";"14:40-15:00"}\r\n:local vlan "VLAN300-ALUNOS"\r\n'
UTEIS = [1, 2, 3, 4, 5]
HORARIOS = [{"inicio": "08:50", "fim": "09:10", "dias": UTEIS}, {"inicio": "12:00", "fim": "12:50", "dias": UTEIS},
            {"inicio": "14:40", "fim": "15:00", "dias": UTEIS}]


def _preparar(mk, data="2026-10-06", hora="22:10:30", aberta=False, fonte=ANTIGO):
    mk.adicionar(SCRIPTS, {"name": "painel-alunos", "source": fonte})
    mk.adicionar(AGENDA, {"name": "painel-alunos", "interval": "1m", "disabled": "false"})
    mk.adicionar("/interface", {"name": "VLAN300-ALUNOS", "type": "vlan", "disabled": "false" if aberta else "true"})
    mk.objetos["/system/clock"].update({"date": data, "time": hora})


def _agenda(mk):
    return {a["name"]: a for a in mk.tabelas[AGENDA] if a["name"] != "painel-alunos"}


def _vlan(mk, nome="VLAN300-ALUNOS"):
    return next(i for i in mk.tabelas["/interface"] if i["name"] == nome)


# ------------------------------------------------------------- horários

def test_janelas_antigas_e_novas():
    antigas = rede_alunos.ler_janelas(ANTIGO)
    assert [(j.inicio, j.fim, sorted(j.dias)) for j in antigas][0] == (time(8, 50), time(9, 10), UTEIS)
    novas = rede_alunos.validar_janelas([{"inicio": "08:00", "fim": "12:00", "dias": [6]}, *HORARIOS])
    fonte = rede_alunos.montar_script("VLAN-X", novas)
    assert ':local janelas {"08:50-09:10 12345";"12:00-12:50 12345";"14:40-15:00 12345";"08:00-12:00 6"}' in fonte
    assert ':local vlan "VLAN-X"' in fonte
    assert rede_alunos.ler_janelas(fonte) == novas  # ida e volta


def test_janela_atual_e_proxima_abertura_com_dias():
    janelas = rede_alunos.validar_janelas([*HORARIOS, {"inicio": "08:00", "fim": "12:00", "dias": [6]}])
    terca = datetime(2026, 10, 6, 12, 10)
    assert rede_alunos.janela_atual(janelas, terca) == (datetime(2026, 10, 6, 12, 0), datetime(2026, 10, 6, 12, 50))
    sabado = datetime(2026, 10, 10, 9, 0)
    assert rede_alunos.janela_atual(janelas, sabado) == (datetime(2026, 10, 10, 8, 0), datetime(2026, 10, 10, 12, 0))
    assert rede_alunos.proxima_abertura(janelas, datetime(2026, 10, 9, 16, 0)) == datetime(2026, 10, 10, 8, 0)  # sexta → sábado
    assert rede_alunos.proxima_abertura(janelas, datetime(2026, 10, 10, 13, 0)) == datetime(2026, 10, 12, 8, 50)  # sábado → segunda


def test_validacoes_dos_horarios(logado, mk):
    _preparar(mk)
    for errado, trecho in (([{"inicio": "9:00", "fim": "10:00", "dias": [1]}], "formato"),
                           ([{"inicio": "10:00", "fim": "09:00", "dias": [1]}], "antes do fim"),
                           ([{"inicio": "08:00", "fim": "09:00", "dias": []}], "pelo menos um dia")):
        r = logado.put("/api/rede-alunos/config", json={"interface": "VLAN300-ALUNOS", "janelas": errado})
        assert r.status_code == 400 and trecho in r.json()["erro"], errado
    r = logado.put("/api/rede-alunos/config", json={"interface": "nao-existe", "janelas": HORARIOS})
    assert r.status_code == 400 and "interface" in r.json()["erro"]
    assert mk.tabelas[SCRIPTS][0]["source"] == ANTIGO  # nada mudou


# ------------------------------------------------------------- configurar

def test_configurar_do_zero_cria_script_e_agendador(logado, mk):
    mk.adicionar("/interface", {"name": "VLAN300-ALUNOS", "type": "vlan", "disabled": "false"})
    assert logado.get("/api/rede-alunos").json()["configurado"] is False
    nomes = [i["nome"] for i in logado.get("/api/rede-alunos/interfaces").json()]
    assert nomes[0] == "VLAN300-ALUNOS" and "lo" not in nomes  # VLANs primeiro, sem loopback

    r = logado.put("/api/rede-alunos/config", json={"interface": "VLAN300-ALUNOS", "janelas": HORARIOS})
    assert r.status_code == 200, r.text
    script = mk.tabelas[SCRIPTS][0]
    agendador = next(a for a in mk.tabelas[AGENDA] if a["name"] == "painel-alunos")
    assert script["policy"] == "read,write,test" and '"08:50-09:10 12345"' in script["source"]
    assert agendador["interval"] == "1m" and agendador["on-event"] == "/system script run painel-alunos"
    e = r.json()
    assert e["configurado"] and e["modo"] == "horario" and e["janelas"][0] == {"inicio": "08:50", "fim": "09:10", "dias": UTEIS}
    assert _vlan(mk)["disabled"] == "true"  # o script rodou: fora do horário, fechada


def test_trocar_interface_religa_a_antiga(logado, mk):
    _preparar(mk)
    mk.adicionar("/interface", {"name": "VLAN400-NOVA", "type": "vlan", "disabled": "false"})
    r = logado.put("/api/rede-alunos/config", json={"interface": "VLAN400-NOVA",
                                                    "janelas": [{"inicio": "07:00", "fim": "08:00", "dias": [0, 6]}]})
    assert r.json()["interface"] == "VLAN400-NOVA" and r.json()["janelas"] == [{"inicio": "07:00", "fim": "08:00", "dias": [0, 6]}]
    assert _vlan(mk)["disabled"] == "false"  # a antiga não fica desligada para sempre


# ------------------------------------------------------------- modos

def test_modos_sempre_aberta_sempre_fechada_e_por_horario(logado, mk):
    _preparar(mk)
    agendador = next(a for a in mk.tabelas[AGENDA] if a["name"] == "painel-alunos")
    logado.post("/api/rede-alunos/liberar", json={"minutos": 30})

    e = logado.put("/api/rede-alunos/modo", json={"modo": "aberta"}).json()
    assert agendador["disabled"] == "true" and _vlan(mk)["disabled"] == "false" and _agenda(mk) == {}
    assert e["modo"] == "aberta" and e["aberta"] and e["motivo"] == "fixo"
    r = logado.post("/api/rede-alunos/liberar", json={"minutos": 30})
    assert r.status_code == 400 and "modo fixo" in r.json()["erro"]

    e = logado.put("/api/rede-alunos/modo", json={"modo": "fechada"}).json()
    assert _vlan(mk)["disabled"] == "true" and e["modo"] == "fechada" and not e["aberta"]

    mk.alunos_no_horario = True
    e = logado.put("/api/rede-alunos/modo", json={"modo": "horario"}).json()
    assert agendador["disabled"] == "false" and e["modo"] == "horario" and _vlan(mk)["disabled"] == "false"
    assert logado.put("/api/rede-alunos/modo", json={"modo": "outro"}).status_code == 422


def test_sem_configuracao(logado):
    assert logado.get("/api/rede-alunos").json()["configurado"] is False
    assert logado.post("/api/rede-alunos/liberar", json={"minutos": 30}).status_code == 400
    assert logado.put("/api/rede-alunos/modo", json={"modo": "aberta"}).status_code == 400


# ------------------------------------------------------------- liberar e fechar (modo por horário)

def test_fora_do_horario_liberar_e_fechar(logado, mk):
    _preparar(mk)
    e = logado.get("/api/rede-alunos").json()
    assert e["configurado"] and not e["aberta"] and e["motivo"] == "fora" and e["abre_em"] == "2026-10-07T08:50"

    e = logado.post("/api/rede-alunos/liberar", json={"minutos": 30}).json()
    tarefa = _agenda(mk)["painel-alunos-liberado"]
    assert tarefa["start-date"] == "2026-10-06" and tarefa["start-time"] == "22:40:00" and tarefa["interval"] == "0s"
    assert e["aberta"] and e["motivo"] == "liberado" and e["fecha_em"] == "2026-10-06T22:40"

    e = logado.post("/api/rede-alunos/fechar").json()
    assert _agenda(mk) == {} and not e["aberta"] and e["motivo"] == "fora"


def test_fechar_dentro_do_horario_e_voltar(logado, mk):
    _preparar(mk, hora="12:10:00", aberta=True)
    mk.alunos_no_horario = True
    e = logado.post("/api/rede-alunos/fechar").json()
    assert _agenda(mk)["painel-alunos-fechado"]["start-time"] == "12:50:00"
    assert not e["aberta"] and e["motivo"] == "fechado" and e["abre_em"] == "2026-10-06T14:40"
    e = logado.post("/api/rede-alunos/horario").json()
    assert _agenda(mk) == {} and e["aberta"] and e["motivo"] == "horario" and e["fecha_em"] == "2026-10-06T12:50"


def test_liberar_validacoes_e_data_antiga(logado, mk):
    _preparar(mk)
    assert logado.post("/api/rede-alunos/liberar", json={"minutos": 2}).status_code == 400
    assert logado.post("/api/rede-alunos/liberar", json={"minutos": 9 * 60}).status_code == 400
    mk.aceita_data_iso = False
    mk.objetos["/system/clock"]["date"] = "oct/06/2026"
    e = logado.post("/api/rede-alunos/liberar", json={"minutos": 120}).json()
    assert _agenda(mk)["painel-alunos-liberado"]["start-date"] == "oct/07/2026"
    assert e["fecha_em"] == "2026-10-07T00:10"
