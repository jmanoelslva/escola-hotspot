"""Rede Alunos: estado, liberar e fechar (o script painel-alunos fica no MikroTik)."""

from datetime import datetime, time

from app import rede_alunos

AGENDA = "/system/scheduler"
FONTE = ':local janelas {"08:50-09:10";"12:00-12:50";"14:40-15:00"}\r\n:local vlan "VLAN300-ALUNOS"\r\n'


def _preparar(mk, data="2026-10-06", hora="22:10:30", aberta=False):
    mk.adicionar("/system/script", {"name": "painel-alunos", "source": FONTE})
    mk.adicionar("/interface", {"name": "VLAN300-ALUNOS", "type": "vlan", "disabled": "false" if aberta else "true"})
    mk.objetos["/system/clock"].update({"date": data, "time": hora})


def _agenda(mk):
    return {a["name"]: a for a in mk.tabelas[AGENDA]}


def test_janelas_e_proxima_abertura():
    janelas = rede_alunos.ler_janelas(FONTE)
    assert janelas == [(time(8, 50), time(9, 10)), (time(12, 0), time(12, 50)), (time(14, 40), time(15, 0))]
    terca = datetime(2026, 10, 6, 12, 10)
    assert rede_alunos.janela_atual(janelas, terca) == (datetime(2026, 10, 6, 12, 0), datetime(2026, 10, 6, 12, 50))
    assert rede_alunos.janela_atual(janelas, datetime(2026, 10, 10, 12, 10)) is None  # sábado
    assert rede_alunos.proxima_abertura(janelas, datetime(2026, 10, 6, 22, 0)) == datetime(2026, 10, 7, 8, 50)
    assert rede_alunos.proxima_abertura(janelas, datetime(2026, 10, 9, 16, 0)) == datetime(2026, 10, 12, 8, 50)  # sexta → segunda


def test_sem_script(logado):
    assert logado.get("/api/rede-alunos").json() == {"configurado": False}
    assert logado.post("/api/rede-alunos/liberar", json={"minutos": 30}).status_code == 400


def test_fora_do_horario_liberar_e_fechar(logado, mk):
    _preparar(mk)
    e = logado.get("/api/rede-alunos").json()
    assert e["configurado"] and not e["aberta"] and e["motivo"] == "fora"
    assert e["abre_em"] == "2026-10-07T08:50" and e["janelas"][0] == ["08:50", "09:10"]

    e = logado.post("/api/rede-alunos/liberar", json={"minutos": 30}).json()
    tarefa = _agenda(mk)["painel-alunos-liberado"]
    assert tarefa["start-date"] == "2026-10-06" and tarefa["start-time"] == "22:40:00" and tarefa["interval"] == "0s"
    assert "/system script run painel-alunos" in tarefa["on-event"]
    assert e["aberta"] and e["motivo"] == "liberado" and e["fecha_em"] == "2026-10-06T22:40"

    e = logado.post("/api/rede-alunos/fechar").json()
    assert "painel-alunos-liberado" not in _agenda(mk) and "painel-alunos-fechado" not in _agenda(mk)
    assert not e["aberta"] and e["motivo"] == "fora"


def test_fechar_dentro_do_horario_e_voltar(logado, mk):
    _preparar(mk, hora="12:10:00", aberta=True)
    mk.alunos_no_horario = True
    assert logado.get("/api/rede-alunos").json()["motivo"] == "horario"

    e = logado.post("/api/rede-alunos/fechar").json()
    assert _agenda(mk)["painel-alunos-fechado"]["start-time"] == "12:50:00"
    assert not e["aberta"] and e["motivo"] == "fechado" and e["abre_em"] == "2026-10-06T14:40"

    e = logado.post("/api/rede-alunos/horario").json()
    assert _agenda(mk) == {} and e["aberta"] and e["motivo"] == "horario" and e["fecha_em"] == "2026-10-06T12:50"

    logado.post("/api/rede-alunos/fechar")
    e = logado.post("/api/rede-alunos/liberar", json={"minutos": 60}).json()  # liberar tira o "fechado"
    assert set(_agenda(mk)) == {"painel-alunos-liberado"} and e["aberta"] and e["fecha_em"] == "2026-10-06T13:10"


def test_liberar_validacoes_e_data_antiga(logado, mk):
    _preparar(mk)
    assert logado.post("/api/rede-alunos/liberar", json={"minutos": 2}).status_code == 400
    assert logado.post("/api/rede-alunos/liberar", json={"minutos": 9 * 60}).status_code == 400
    mk.aceita_data_iso = False
    mk.objetos["/system/clock"]["date"] = "oct/06/2026"
    e = logado.post("/api/rede-alunos/liberar", json={"minutos": 120}).json()
    assert _agenda(mk)["painel-alunos-liberado"]["start-date"] == "oct/07/2026"
    assert e["fecha_em"] == "2026-10-07T00:10"


def test_perfil_novo_herda_scripts_do_padrao(logado, mk):
    mk.tabelas["/ip/hotspot/user/profile"][0].update({"on-login": "login-v6", "on-logout": "saida-v6"})
    assert logado.post("/api/perfis", json={"nome": "professores"}).status_code == 200
    novo = next(p for p in mk.tabelas["/ip/hotspot/user/profile"] if p["name"] == "professores")
    assert novo["on-login"] == "login-v6" and novo["on-logout"] == "saida-v6"
