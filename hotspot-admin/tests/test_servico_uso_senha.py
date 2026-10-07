"""Usuário de serviço, histórico de uso, relatório mensal e troca de senha pelo Wi-Fi."""

from datetime import datetime, timedelta

import pytest

from app import ajustes, coleta, servico
from app.config import config
from app.main import app

USUARIOS = "/ip/hotspot/user"


@pytest.fixture(autouse=True)
def limpar():
    yield
    (config.pasta_dados / servico.ARQUIVO).unlink(missing_ok=True)
    (config.pasta_dados / ajustes.ARQUIVO).unlink(missing_ok=True)
    for arquivo in (config.pasta_dados / "uso").glob("*") if (config.pasta_dados / "uso").exists() else []:
        arquivo.unlink()


def _ativar_servico(logado, mk):
    import mikrotik_falso
    r = logado.post("/api/servico")
    assert r.status_code == 200, r.text
    # O MikroTik falso só aceita admin/segredo: faz o usuário de serviço usar a mesma conta.
    dados = servico.ler(config.pasta_dados)
    (config.pasta_dados / servico.ARQUIVO).write_text(
        f'{{"usuario": "{mikrotik_falso.USUARIO}", "senha": "{mikrotik_falso.SENHA}"}}', encoding="utf-8")
    return dados


# ------------------------------------------------------------- usuário de serviço

def test_ativar_e_desativar_servico(logado, mk):
    assert logado.get("/api/servico").json() == {"ativo": False, "usuario": "painel-servico"}
    r = logado.post("/api/servico")
    assert r.json()["ativo"] is True
    usuario = next(u for u in mk.tabelas["/user"] if u["name"] == "painel-servico")
    assert usuario["group"] == "painel" and len(usuario["password"]) == 28
    assert servico.ler(config.pasta_dados)["senha"] == usuario["password"]
    logado.post("/api/servico")  # de novo: troca a senha, não duplica
    assert sum(u["name"] == "painel-servico" for u in mk.tabelas["/user"]) == 1
    assert logado.delete("/api/servico").json()["ativo"] is False
    assert all(u["name"] != "painel-servico" for u in mk.tabelas["/user"])


def test_so_full_ativa_servico(logado, mk):
    mk.tabelas["/user"][0]["group"] = "painel"
    r = logado.post("/api/servico")
    assert r.status_code == 400 and "full" in r.json()["erro"]


# ------------------------------------------------------------- coleta e histórico

def _wan(mk, rx, tx):
    ether1 = next(i for i in mk.tabelas["/interface"] if i["name"] == "ether1")
    ether1.update({"rx-byte": str(rx), "tx-byte": str(tx)})


def test_coleta_grava_diferencas_e_trata_reinicio(mk):
    from app.mikrotik import Mikrotik
    import mikrotik_falso
    pasta = config.pasta_dados
    t0 = datetime(2026, 10, 8, 10, 0)
    mk.adicionar("/ip/hotspot/active", {"user": "ana"})
    mk.adicionar("/ip/dhcp-server/lease", {"status": "bound", "mac-address": "AA"})
    with Mikrotik("https://falso", mikrotik_falso.USUARIO, mikrotik_falso.SENHA, transport=mk.transport()) as cliente:
        _wan(mk, 1_000_000, 100_000)
        assert coleta.coletar(cliente, pasta, t0) is None  # primeira leitura: só guarda os contadores
        _wan(mk, 1_000_000 + 375_000_000, 100_000 + 37_500_000)
        linha = coleta.coletar(cliente, pasta, t0 + timedelta(minutes=5))
        assert linha["baixado"] == 375_000_000 and linha["enviado"] == 37_500_000
        assert linha["sessoes"] == 1 and linha["aparelhos"] == 1 and linha["segundos"] == 300
        _wan(mk, 5_000, 1_000)  # roteador reiniciou: contadores voltaram a zero
        assert coleta.coletar(cliente, pasta, t0 + timedelta(minutes=10))["baixado"] == 5_000
        _wan(mk, 6_000, 1_000)
        assert coleta.coletar(cliente, pasta, t0 + timedelta(hours=2)) is None  # painel ficou desligado

    dia = coleta.serie(pasta, "dia", t0 + timedelta(minutes=11))
    assert dia["pontos"][0]["baixa"] == 10.0  # 375 MB em 5 min = 10 Mbps
    mes = coleta.resumo_mes(pasta, 2026, 10)
    assert mes["baixado_gb"] == 0.38 and mes["pico_sessoes"]["valor"] == 1 and len(mes["dias"]) == 1
    trinta = coleta.serie(pasta, "30d", t0 + timedelta(days=1))
    assert trinta["unidade"] == "GB" and trinta["pontos"][0]["quando"] == "2026-10-08"


def test_rota_do_uso_e_relatorio_mensal(logado, mk):
    r = logado.get("/api/uso?periodo=7d").json()
    assert r["unidade"] == "Mbps" and r["pontos"] == [] and r["servico"] is False
    assert logado.get("/api/uso?periodo=ano").status_code == 422
    mk.adicionar(USUARIOS, {"name": "ana", "comment": "Ana - 9º A", "bytes-in": "1000", "bytes-out": "9000"})
    mk.adicionar(USUARIOS, {"name": "bia", "comment": "Bia - 9º A", "bytes-in": "500", "bytes-out": "500"})
    logado.post("/api/visitantes", json={"quantidade": 3, "minutos": 60})
    logado.post("/api/bloqueios", json={"dominio": "exemplo.com"})
    mes = datetime.now().strftime("%Y-%m")
    rel = logado.get(f"/api/relatorio-mensal?mes={mes}").json()
    assert rel["mes"] == mes and rel["visitantes_criados"] >= 3 and rel["acoes"]["sites_bloqueados"] >= 1
    assert rel["turmas"][0] == {"turma": "9º A", "usuarios": 2, "bytes": 11000}
    assert rel["maiores"][0]["nome"] == "ana" and rel["sites_bloqueados"] == 1
    assert logado.get("/api/relatorio-mensal?mes=2026-13").status_code == 400


# ------------------------------------------------------------- troca de senha pelo Wi-Fi

def test_troca_de_senha(logado, cliente, mk):
    mk.adicionar(USUARIOS, {"name": "ana", "password": "velha1", "comment": "Ana - Matemática"})
    logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60})
    visitante = next(u for u in mk.tabelas[USUARIOS] if u["name"] == "visita1")

    corpo = {"usuario": "ana", "atual": "velha1", "nova": "nova-123"}
    assert cliente.post("/api/senha", json=corpo).json()["erro"].startswith("A troca de senha pelo Wi-Fi está desligada")
    _ativar_servico(logado, mk)
    ajustes.gravar_senha_url(config.pasta_dados, "http://senha.wifi.teste:8080/senha")

    assert cliente.post("/api/senha", json={**corpo, "atual": "errada"}).json()["erro"] == "Usuário ou senha atual incorretos."
    assert cliente.post("/api/senha", json={**corpo, "nova": "curta"}).status_code == 400
    r = cliente.post("/api/senha", json={"usuario": "visita1", "atual": visitante["password"], "nova": "nova-456"})
    assert r.json()["erro"] == "Usuário ou senha atual incorretos."  # visitante não troca
    assert cliente.post("/api/senha", json=corpo).status_code == 200
    assert next(u for u in mk.tabelas[USUARIOS] if u["name"] == "ana")["password"] == "nova-123"
    assert "ana trocou a própria senha pelo Wi-Fi" in (config.pasta_dados / "acoes.log").read_text(encoding="utf-8")


def test_troca_de_senha_bloqueia_apos_erros(logado, cliente, mk):
    _ativar_servico(logado, mk)
    ajustes.gravar_senha_url(config.pasta_dados, "http://x:8080/senha")
    for _ in range(5):
        cliente.post("/api/senha", json={"usuario": "ninguem", "atual": "x", "nova": "nova-123"})
    assert cliente.post("/api/senha", json={"usuario": "ninguem", "atual": "x", "nova": "nova-123"}).status_code == 429


def test_quem_vem_do_wifi_so_ve_a_pagina_de_senha(mk):
    from fastapi.testclient import TestClient
    with TestClient(app, client=("10.0.1.50", 50000), headers={"X-Painel": "1"}) as wifi:
        assert wifi.get("/senha").status_code == 200
        assert wifi.get("/static/senha.js").status_code == 200
        assert wifi.get("/").status_code == 403
        assert wifi.get("/api/usuarios").status_code == 403
        assert wifi.post("/api/login", json={"usuario": "admin", "senha": "segredo"}).status_code == 403
        assert wifi.post("/api/senha", json={"usuario": "x", "atual": "y", "nova": "zzzzzz"}).status_code == 400
    with TestClient(app, client=("192.168.88.10", 50000)) as escritorio:
        assert escritorio.get("/").status_code == 200


def test_ligar_troca_de_senha_cria_dns_e_publica_o_link(logado, mk, monkeypatch):
    from app import senha
    assert logado.put("/api/configuracoes/troca-senha", json={"ativo": True}).status_code == 400  # sem serviço
    _ativar_servico(logado, mk)
    monkeypatch.setattr(senha, "ip_deste_pc", lambda _ip: "192.168.88.10")
    r = logado.put("/api/configuracoes/troca-senha", json={"ativo": True}).json()
    assert r["url"] == f"http://senha.wifi.pmapg.internal:{config.porta}/senha"
    dns = next(d for d in mk.tabelas["/ip/dns/static"] if d["comment"].startswith("painel-senha"))
    assert dns["name"] == "senha.wifi.pmapg.internal" and dns["address"] == "192.168.88.10"
    arquivo = next(f for f in mk.tabelas["/file"] if f["name"] == "hotspot/escola-info.js")
    assert r["url"] in arquivo["contents"]
    r = logado.put("/api/configuracoes/troca-senha", json={"ativo": False}).json()
    assert r["ativa"] is False and not any(d["comment"].startswith("painel-senha") for d in mk.tabelas["/ip/dns/static"])
    assert '"senha": ""' in arquivo["contents"]
