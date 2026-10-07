"""Configurações feitas pelo painel: escola, logotipo e conexão com o MikroTik."""

from io import BytesIO

import pytest

from app import ajustes
from app.config import config

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def limpar():
    yield
    (config.pasta_dados / ajustes.ARQUIVO).unlink(missing_ok=True)
    ajustes.remover_logo(config.pasta_dados)


def test_nome_e_cidade_da_escola(logado):
    assert logado.get("/api/configuracoes/escola").json()["nome"] == config.nome_escola  # do .env
    r = logado.put("/api/configuracoes/escola", json={"nome": "  Escola  Estadual   PMAPG ", "cidade": "Coité do Noia - AL"})
    assert r.json()["nome"] == "Escola Estadual PMAPG"
    info = logado.get("/api/info").json()
    assert info["escola"] == "Escola Estadual PMAPG" and info["cidade"] == "Coité do Noia - AL"
    assert logado.put("/api/configuracoes/escola", json={"nome": "   "}).status_code == 400


def test_logotipo_trocar_e_voltar_ao_padrao(logado):
    padrao = logado.get("/logo").content
    assert padrao.startswith(b"\x89PNG")
    r = logado.post("/api/configuracoes/logo", files={"arquivo": ("logo.png", BytesIO(PNG), "image/png")})
    assert r.status_code == 200 and r.json()["logo_proprio"] is True
    assert logado.get("/logo").content == PNG
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    logado.post("/api/configuracoes/logo", files={"arquivo": ("logo.jpg", BytesIO(jpg), "image/jpeg")})
    assert logado.get("/logo").content == jpg and not (config.pasta_dados / "logo.png").exists()
    r = logado.post("/api/configuracoes/logo", files={"arquivo": ("x.svg", BytesIO(b"<svg/>"), "image/svg+xml")})
    assert r.status_code == 400
    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * ajustes.LOGO_MAX_BYTES
    assert logado.post("/api/configuracoes/logo", files={"arquivo": ("g.png", BytesIO(grande), "image/png")}).status_code == 400
    assert logado.delete("/api/configuracoes/logo").json()["logo_proprio"] is False
    assert logado.get("/logo").content == padrao


def test_logo_sem_login_e_cadastro_exige_login(cliente):
    assert cliente.get("/logo").status_code == 200  # aparece na tela de login
    r = cliente.post("/api/configuracoes/logo", files={"arquivo": ("logo.png", BytesIO(PNG), "image/png")})
    assert r.status_code == 401


def test_montar_e_separar_endereco():
    assert ajustes.montar_endereco("", None) == "192.168.88.1"
    assert ajustes.montar_endereco("", 8443) == "192.168.88.1:8443"  # só a porta mudou: IP padrão
    assert ajustes.montar_endereco(" 10.0.0.1 ", 8080) == "10.0.0.1:8080"
    for ip, porta in (("10.0.0.1/24", None), ("http://x", None), ("10.0.0.1", 0), ("10.0.0.1", 70000)):
        with pytest.raises(Exception):
            ajustes.montar_endereco(ip, porta)
    assert ajustes.separar_endereco("https://192.168.88.1:8443/") == ("192.168.88.1", 8443)
    assert ajustes.separar_endereco("192.168.88.1") == ("192.168.88.1", None)


def test_trocar_a_conexao_com_o_mikrotik(logado, mk):
    from app.main import app
    estado = logado.get("/api/configuracoes/mikrotik").json()
    assert estado["ip"] == "mikrotik.teste" and estado["porta"] is None and estado["conexao"] == "HTTPS"

    r = logado.put("/api/configuracoes/mikrotik", json={"ip": "", "porta": 8443})
    assert r.status_code == 200, r.text
    assert r.json()["ip"] == "192.168.88.1" and r.json()["porta"] == 8443
    assert r.json()["em_uso"] == "https://192.168.88.1:8443" and r.json()["identidade"] == "hEX-escola"
    assert ajustes.ler(config.pasta_dados)["mikrotik"] == "192.168.88.1:8443"
    assert app.state.endereco.url() == "https://192.168.88.1:8443"
    assert logado.get("/api/usuarios").status_code == 200  # o painel continua funcionando no endereço novo


def test_endereco_que_nao_responde_nao_muda_nada(logado, mk):
    from app.main import app
    mk.fora_do_ar.add("10.9.9.9")
    r = logado.put("/api/configuracoes/mikrotik", json={"ip": "10.9.9.9"})
    assert r.status_code == 400 and "Nada foi alterado" in r.json()["erro"]
    assert ajustes.ler(config.pasta_dados) == {}
    assert app.state.endereco.url() == "https://mikrotik.teste"
    assert logado.get("/api/sessao").status_code == 200  # a sessão continua aberta
