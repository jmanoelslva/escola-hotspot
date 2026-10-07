"""APs vigiados pelo Netwatch do MikroTik e nome da escola nas páginas do hotspot."""

NETWATCH = "/tool/netwatch"


def test_cadastrar_listar_alterar_e_remover_ap(logado, mk):
    r = logado.post("/api/aps", json={"nome": "AP3 – pátio", "ip": "172.16.1.13"})
    assert r.status_code == 200, r.text
    item = mk.tabelas[NETWATCH][-1]
    assert item["host"] == "172.16.1.13" and item["comment"] == "painel-ap: AP3 – pátio" and item["interval"] == "30s"
    assert logado.post("/api/aps", json={"nome": "Outro", "ip": "172.16.1.13"}).status_code == 400
    assert logado.post("/api/aps", json={"nome": "X", "ip": "172.16.1"}).status_code == 400
    assert logado.post("/api/aps", json={"nome": " ", "ip": "172.16.1.20"}).status_code == 400
    logado.post("/api/aps", json={"nome": "AP1 – secretaria", "ip": "172.16.1.11"})
    mk.tabelas[NETWATCH][0].update({"status": "down", "since": "2026-10-08 10:15:00"})
    mk.tabelas[NETWATCH][1]["status"] = "up"
    lista = logado.get("/api/aps").json()
    assert [(a["nome"], a["situacao"]) for a in lista] == [("AP1 – secretaria", "no_ar"), ("AP3 – pátio", "fora")]
    resumo = logado.get("/api/sistema").json()["aps"]
    assert resumo == {"total": 2, "no_ar": 1, "fora": [{"nome": "AP3 – pátio", "ip": "172.16.1.13", "desde": "2026-10-08 10:15:00"}]}

    ap3 = next(a for a in lista if a["ip"] == "172.16.1.13")
    r = logado.patch(f"/api/aps/{ap3['id']}", json={"nome": "AP3 – quadra", "ip": "172.16.1.14"})
    assert r.json()["nome"] == "AP3 – quadra" and mk.tabelas[NETWATCH][0]["host"] == "172.16.1.14"
    assert logado.delete(f"/api/aps/{ap3['id']}").status_code == 200
    alheio = mk.adicionar(NETWATCH, {"host": "8.8.8.8", "comment": "internet"})
    assert logado.delete(f"/api/aps/{alheio['.id']}").status_code == 400
    assert [a["nome"] for a in logado.get("/api/aps").json()] == ["AP1 – secretaria"]


def test_nome_da_escola_vai_para_o_hotspot(logado, mk):
    from app import ajustes
    from app.config import config
    try:
        r = logado.put("/api/configuracoes/escola", json={"nome": "Escola Teste", "cidade": "Arapiraca - AL"})
        assert r.status_code == 200 and r.json()["aviso_hotspot"] == ""
        arquivo = next(f for f in mk.tabelas["/file"] if f["name"] == "hotspot/escola-info.js")
        assert arquivo["contents"] == 'var ESCOLA_INFO = {"nome": "Escola Teste", "cidade": "Arapiraca - AL", "senha": ""};\n'
        logado.put("/api/configuracoes/escola", json={"nome": "Escola Nova", "cidade": ""})
        assert '"nome": "Escola Nova"' in arquivo["contents"]
    finally:
        (config.pasta_dados / ajustes.ARQUIVO).unlink(missing_ok=True)
