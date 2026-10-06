"""Painel geral (saúde e tráfego) e aviso de atualização."""


def test_resumo_do_sistema(logado, mk):
    mk.adicionar("/ip/hotspot/active", {"user": "ana"})
    dados = logado.get("/api/sistema").json()
    assert dados["modelo"] == "hEX" and dados["versao"] == "7.15.3 (stable)"
    assert dados["cpu"] == 7 and dados["temperatura"] == 41.0
    assert dados["memoria_total"] == 268435456 and dados["memoria_usada"] == 67108864
    assert dados["internet"] == "ether1"
    assert dados["conectados"] == 1 and dados["usuarios"] == 0
    nomes = [i["nome"] for i in dados["interfaces"]]
    assert "lo" not in nomes  # loopback fica de fora
    assert nomes[-1] == "ether5"  # desligadas por último


def test_temperatura_no_formato_antigo_e_sem_sensor(logado, mk):
    mk.objetos["/system/health"] = {"temperature": "39"}
    assert logado.get("/api/sistema").json()["temperatura"] == 39.0
    del mk.objetos["/system/health"]
    assert logado.get("/api/sistema").json()["temperatura"] is None


def test_internet_pelo_gateway_interface(logado, mk):
    mk.tabelas["/ip/route"][0].pop("immediate-gw")
    mk.tabelas["/ip/route"][0]["gateway"] = "pppoe-out1"
    assert logado.get("/api/sistema").json()["internet"] == "pppoe-out1"


def test_trafego(logado, mk):
    r = logado.get("/api/trafego?interfaces=ether1,bridge-hotspot")
    assert r.json() == [
        {"nome": "ether1", "entrada_bps": 10_000_000, "saida_bps": 1_000_000},
        {"nome": "bridge-hotspot", "entrada_bps": 20_000_000, "saida_bps": 2_000_000},
    ]
    assert logado.get("/api/trafego").json() == []
    assert logado.get("/api/trafego?interfaces=ether1;/system/reboot").status_code == 400


def test_atualizacao_disponivel_e_cache(logado, mk):
    from app.main import app
    app.state.atualizacao.esquecer()
    r = logado.get("/api/atualizacao").json()
    assert r["atualizacao_routeros"] and r["instalada"] == "7.15.3" and r["disponivel"] == "7.16.1"
    assert not r["atualizacao_firmware"] and not r["falhou"]
    logado.get("/api/atualizacao")
    assert mk.verificacoes == 1  # a segunda vem da memória (6 horas)
    logado.get("/api/atualizacao?forcar=true")
    assert mk.verificacoes == 2


def test_sem_atualizacao_e_firmware_atrasado(logado, mk):
    from app.main import app
    app.state.atualizacao.esquecer()
    mk.versao_disponivel = "7.15.3"
    mk.objetos["/system/routerboard"]["current-firmware"] = "7.10"
    r = logado.get("/api/atualizacao").json()
    assert not r["atualizacao_routeros"] and r["atualizacao_firmware"]
    assert r["firmware_novo"] == "7.15.3"


def test_comparacao_de_versoes():
    from app.sistema import _versao
    assert _versao("7.16.1") > _versao("7.15.3")
    assert _versao("7.10") > _versao("7.9.2")
    assert _versao("7.17beta2") == (7, 17)
    assert _versao("7.15.3 (stable)") == (7, 15, 3)
    assert _versao("") == ()
