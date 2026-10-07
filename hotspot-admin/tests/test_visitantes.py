"""Senhas temporárias de visitantes."""

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
    assert [c["usuario"] for c in criados] == ["visita1", "visita2", "visita3"]
    assert all(len(c["senha"]) == 6 and c["senha"].isdigit() for c in criados)

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
    assert logado.post("/api/visitantes", json={"quantidade": 201, "minutos": 60}).status_code == 422
    assert logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60, "perfil": "nao-existe"}).status_code == 400
    assert logado.post("/api/visitantes", json={"quantidade": 1}).status_code == 400  # sem validade


# ------------------------------------------------------------- QR codes

def test_texto_do_qr_wifi():
    from app import qrcodes
    assert qrcodes.texto_wifi("Escola PMAPG", "aberta", "") == "WIFI:T:nopass;S:Escola PMAPG;;"
    assert qrcodes.texto_wifi('Rede;"1"', "wpa", r"a:b,c\d") == r'WIFI:T:WPA;S:Rede\;\"1\";P:a\:b\,c\\d;;'
    url = qrcodes.url_login("http://wifi.pmapg.internal", "vis-abc12", "k7m2pq")
    assert url == "http://wifi.pmapg.internal/login?visitante=vis-abc12&senha=k7m2pq"
    assert qrcodes.imagem(url).startswith("data:image/svg+xml")


def test_visitantes_com_qr_de_login(logado, mk):
    r = logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60}).json()
    assert r["criados"][0]["qr_login"].startswith("data:image/svg+xml")
    assert logado.get("/api/visitantes").json()[0]["qr_login"].startswith("data:image/svg+xml")


def test_sem_hotspot_nao_gera_qr_de_login(logado, mk):
    mk.tabelas["/ip/hotspot"].clear()
    r = logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60}).json()
    assert r["criados"][0]["qr_login"] == ""


def test_configurar_wifi_do_qr(logado):
    r = logado.get("/api/configuracoes/wifi").json()
    assert r["ssid"] == "" and r["qr"] == ""
    r = logado.put("/api/configuracoes/wifi", json={"ssid": "Wi-Fi Escola", "seguranca": "wpa", "senha": "curta"})
    assert r.status_code == 400
    r = logado.put("/api/configuracoes/wifi", json={"ssid": "Wi-Fi Escola", "seguranca": "wpa", "senha": "senha-do-wifi"}).json()
    assert r["ssid"] == "Wi-Fi Escola" and r["qr"].startswith("data:image/svg+xml")
    r = logado.put("/api/configuracoes/wifi", json={"ssid": "Wi-Fi Escola", "seguranca": "aberta", "senha": "ignorada"}).json()
    assert r["senha"] == "" and logado.get("/api/configuracoes/wifi").json()["seguranca"] == "aberta"
    logado.put("/api/configuracoes/wifi", json={"ssid": ""})


def test_encerrar_selecionados_e_todos(logado, mk):
    comum = mk.adicionar(USUARIOS, {"name": "maria", "comment": "Maria - 9A"})
    logado.post("/api/visitantes", json={"quantidade": 4, "minutos": 60})
    lista = logado.get("/api/visitantes").json()
    mk.adicionar("/ip/hotspot/active", {"user": lista[0]["usuario"]})
    r = logado.post("/api/visitantes/encerrar", json={"ids": [lista[0]["id"], lista[1]["id"], comum[".id"]]}).json()
    assert sorted(r["encerrados"]) == sorted([lista[0]["usuario"], lista[1]["usuario"]]) and r["erros"] == []
    assert comum in mk.tabelas[USUARIOS]  # usuário comum nunca é encerrado aqui
    assert mk.tabelas["/ip/hotspot/active"] == []
    assert len(logado.get("/api/visitantes").json()) == 2

    r = logado.post("/api/visitantes/encerrar", json={"todos": True}).json()
    assert len(r["encerrados"]) == 2
    assert logado.get("/api/visitantes").json() == []
    assert not [a for a in mk.tabelas[AGENDA] if a["name"].startswith("painel-visitante-")]
    assert comum in mk.tabelas[USUARIOS]
    assert logado.post("/api/visitantes/encerrar", json={}).status_code == 400


def test_nome_do_usuario_escolhido(logado, mk):
    from app import visitantes
    assert visitantes.prefixo_nome("Reunião de Pais!") == "reuniaodep"
    assert visitantes.prefixo_nome("  Técnico  ") == "tecnico"
    assert visitantes.prefixo_nome("123 ---") == "visita" and visitantes.prefixo_nome("") == "visita"
    mk.adicionar(USUARIOS, {"name": "pais1", "comment": "usuário comum que já existia"})
    r = logado.post("/api/visitantes", json={"quantidade": 3, "minutos": 60, "nome": "Pais", "descricao": "Reunião"}).json()
    assert [c["usuario"] for c in r["criados"]] == ["pais2", "pais3", "pais4"]
    agenda = {a["name"] for a in mk.tabelas[AGENDA]}
    assert {"painel-visitante-pais2", "painel-visitante-pais4"} <= agenda


def test_nome_do_visitante_reaproveita_o_menor_numero_livre(logado, mk):
    logado.post("/api/visitantes", json={"quantidade": 3, "minutos": 60})
    lista = logado.get("/api/visitantes").json()
    logado.delete(f"/api/visitantes/{next(v['id'] for v in lista if v['usuario'] == 'visita2')}")
    novo = logado.post("/api/visitantes", json={"quantidade": 2, "minutos": 60}).json()["criados"]
    assert [c["usuario"] for c in novo] == ["visita2", "visita4"]


def test_limite_de_visitantes_pela_licenca(logado, mk):
    assert logado.get("/api/visitantes/limite").json() == {"limite": 200, "validos": 0, "disponiveis": 200}
    assert logado.post("/api/visitantes", json={"quantidade": 150, "minutos": 60}).status_code == 200
    assert logado.get("/api/visitantes/limite").json() == {"limite": 200, "validos": 150, "disponiveis": 50}
    r = logado.post("/api/visitantes", json={"quantidade": 51, "minutos": 60})
    assert r.status_code == 400 and "no máximo 50" in r.json()["erro"]
    assert logado.post("/api/visitantes", json={"quantidade": 50, "minutos": 60}).status_code == 200
    assert logado.post("/api/visitantes", json={"quantidade": 201, "minutos": 60}).status_code == 422
    mk.objetos["/system/license"]["nlevel"] = "5"
    assert logado.get("/api/visitantes/limite").json()["disponiveis"] == 200  # 500 - 200, até 200 por vez


def test_visitantes_e_usuarios_em_ordem_natural(logado, mk):
    logado.post("/api/visitantes", json={"quantidade": 12, "minutos": 60})
    nomes = [v["usuario"] for v in logado.get("/api/visitantes").json()]
    assert nomes[:3] == ["visita1", "visita2", "visita3"] and nomes[-3:] == ["visita10", "visita11", "visita12"]
    usuarios = [u["nome"] for u in logado.get("/api/usuarios").json()]
    assert usuarios.index("visita2") < usuarios.index("visita10")
