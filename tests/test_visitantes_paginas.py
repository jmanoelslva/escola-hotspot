"""Senhas temporárias de visitantes e envio das páginas do hotspot ao roteador."""

import dataclasses
from datetime import datetime, timedelta

import pytest

from app import visitantes

USUARIOS = "/ip/hotspot/user"
AGENDA = "/system/scheduler"


# ------------------------------------------------------------- visitantes

def test_validade():
    agora = datetime(2026, 10, 6, 14, 30, 45)
    assert visitantes.validade(120, False, agora) == datetime(2026, 10, 6, 16, 30)
    assert visitantes.validade(None, True, agora) == datetime(2026, 10, 6, 23, 59)
    for errado in (0, 5, 31 * 24 * 60):
        with pytest.raises(Exception):
            visitantes.validade(errado, False, agora)


def test_comentario_ida_e_volta():
    ate = datetime(2026, 10, 6, 18, 0)
    texto = visitantes.comentario(ate, "  Reunião   de pais ")
    assert texto == "painel-visitante até 2026-10-06 18:00 | Reunião de pais"
    assert visitantes.ler_comentario(texto) == (ate, "Reunião de pais")
    assert visitantes.ler_comentario("Maria - 9A") == (None, "")


def test_criar_listar_e_encerrar_visitantes(logado, mk):
    r = logado.post("/api/visitantes", json={"quantidade": 3, "minutos": 120, "perfil": "alunos", "descricao": "Palestra"})
    assert r.status_code == 200, r.text
    criados = r.json()["criados"]
    assert len(criados) == 3 and len({c["usuario"] for c in criados}) == 3
    assert all(c["usuario"].startswith("vis-") and len(c["senha"]) == 6 for c in criados)

    usuario = next(u for u in mk.tabelas[USUARIOS] if u["name"] == criados[0]["usuario"])
    assert usuario["profile"] == "alunos" and usuario["comment"].startswith("painel-visitante até ")
    agenda = {a["name"]: a for a in mk.tabelas[AGENDA]}
    tarefa = agenda[f"painel-visitante-{usuario['name']}"]
    ate = datetime.now() + timedelta(minutes=120)
    assert tarefa["start-date"] == f"{ate:%Y-%m-%d}" and tarefa["interval"] == "0s"
    script = tarefa["on-event"]
    assert f'/ip hotspot user remove [find name="{usuario["name"]}"]' in script
    assert f'/ip hotspot active remove [find user="{usuario["name"]}"]' in script
    assert f'/system scheduler remove [find name="painel-visitante-{usuario["name"]}"]' in script

    lista = logado.get("/api/visitantes").json()
    assert len(lista) == 3 and all(v["agendado"] and not v["expirado"] and v["descricao"] == "Palestra" for v in lista)

    mk.adicionar("/ip/hotspot/active", {"user": usuario["name"]})
    mk.adicionar("/ip/hotspot/cookie", {"user": usuario["name"], "mac-address": "AA:AA:AA:AA:AA:AA"})
    assert logado.delete(f"/api/visitantes/{usuario['.id']}").status_code == 200
    assert usuario not in mk.tabelas[USUARIOS]
    assert f"painel-visitante-{usuario['name']}" not in {a["name"] for a in mk.tabelas[AGENDA]}
    assert mk.tabelas["/ip/hotspot/active"] == [] and mk.tabelas["/ip/hotspot/cookie"] == []
    assert len(logado.get("/api/visitantes").json()) == 2


def test_visitante_ate_o_fim_do_dia_e_data_antiga(logado, mk):
    mk.aceita_data_iso = False
    r = logado.post("/api/visitantes", json={"quantidade": 1, "ate_fim_do_dia": True})
    assert r.status_code == 200, r.text
    tarefa = mk.tabelas[AGENDA][-1]
    meses = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    hoje = datetime.now()
    assert tarefa["start-date"] == f"{meses[hoje.month - 1]}/{hoje:%d/%Y}" and tarefa["start-time"] == "23:59:00"


def test_nao_encerra_usuario_comum(logado, mk):
    comum = mk.adicionar(USUARIOS, {"name": "maria", "comment": "Maria - 9A"})
    r = logado.delete(f"/api/visitantes/{comum['.id']}")
    assert r.status_code == 400 and comum in mk.tabelas[USUARIOS]


def test_visitantes_validacoes(logado):
    assert logado.post("/api/visitantes", json={"quantidade": 0, "minutos": 60}).status_code == 422
    assert logado.post("/api/visitantes", json={"quantidade": 51, "minutos": 60}).status_code == 422
    assert logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60, "perfil": "nao-existe"}).status_code == 400
    assert logado.post("/api/visitantes", json={"quantidade": 1}).status_code == 400  # sem validade


# ------------------------------------------------------------- páginas do hotspot

@pytest.fixture
def pasta_paginas(tmp_path, monkeypatch):
    from app import main, paginas
    pasta = tmp_path / "hotspot"
    (pasta / "css").mkdir(parents=True)
    (pasta / "img").mkdir()
    (pasta / ".git").mkdir()
    (pasta / "login.html").write_text("<html>login novo</html>", encoding="utf-8")
    (pasta / "status.html").write_text("<html>status</html>", encoding="utf-8")
    (pasta / "css" / "style.css").write_text("body{}", encoding="utf-8")
    (pasta / "img" / "logo.png").write_bytes(b"\x89PNG" + bytes(range(200)))
    (pasta / ".git" / "config").write_text("x", encoding="utf-8")
    (pasta / "aviso-escola.js").write_text("var AVISO_ESCOLA = '';", encoding="utf-8")
    monkeypatch.setattr(main, "config", dataclasses.replace(main.config, pasta_paginas=pasta))
    monkeypatch.setattr(paginas, "ip_do_painel", lambda url: "127.0.0.1")
    return pasta


def test_comparar_paginas(logado, mk, pasta_paginas):
    mk.adicionar("/file", {"name": "hotspot/status.html", "type": "file", "size": str(len("<html>status</html>"))})
    mk.adicionar("/file", {"name": "hotspot/login.html", "type": "file", "size": "6550"})
    mk.adicionar("/file", {"name": "hotspot/css", "type": "directory"})
    r = logado.get("/api/paginas").json()
    assert r["pasta_roteador"] == "hotspot"
    situacoes = {a["arquivo"]: a["situacao"] for a in r["arquivos"]}
    assert situacoes == {"css/style.css": "falta", "img/logo.png": "falta", "login.html": "diferente", "status.html": "igual"}


def test_enviar_paginas(logado, mk, pasta_paginas):
    pedidos = []

    def baixar(url):
        caminho = url.replace("http://127.0.0.1:8080", "")
        pedidos.append(caminho)
        resposta = logado.get(caminho)
        assert resposta.status_code == 200, caminho
        return resposta.content

    mk.baixar = baixar
    mk.adicionar("/file", {"name": "hotspot/status.html", "type": "file", "size": str(len("<html>status</html>"))})
    r = logado.post("/api/paginas/enviar", json={"todos": False})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["enviados"]) == ["css/style.css", "img/logo.png", "login.html"] and r.json()["erros"] == []
    arquivos = {a["name"]: a for a in mk.tabelas["/file"]}
    assert arquivos["hotspot/img/logo.png"]["size"] == str(204)
    assert "hotspot/aviso-escola.js" not in arquivos  # arquivo do painel nunca é enviado
    assert all("/.git/" not in p for p in pedidos)

    # Depois do envio, o código temporário não vale mais.
    assert logado.get(pedidos[0]).status_code == 404

    # Tudo igual: nada a enviar; "todos" reenvia os 4.
    assert logado.post("/api/paginas/enviar", json={"todos": False}).json()["enviados"] == []
    assert len(logado.post("/api/paginas/enviar", json={"todos": True}).json()["enviados"]) == 4


def test_endereco_de_envio_sem_codigo_valido(cliente):
    assert cliente.get("/hotspot-envio/inventado/login.html").status_code == 404
    assert cliente.get("/hotspot-envio/x/..%2F.env").status_code == 404


def test_pasta_das_paginas_inexistente(logado, monkeypatch, tmp_path):
    from app import main
    monkeypatch.setattr(main, "config", dataclasses.replace(main.config, pasta_paginas=tmp_path / "nao-existe"))
    r = logado.get("/api/paginas")
    assert r.status_code == 400 and "PASTA_PAGINAS_HOTSPOT" in r.json()["erro"]
