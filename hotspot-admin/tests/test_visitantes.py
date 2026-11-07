"""Senhas temporárias de visitantes."""

from datetime import datetime, timedelta

import pytest

from app import visitantes

USUARIOS = "/ip/hotspot/user"
AGENDA = "/system/scheduler"
SCRIPTS = "/system/script"


# ------------------------------------------------------------- visitantes

def test_duracao():
    assert visitantes.duracao(120, False) == 120
    assert visitantes.duracao(None, True) is None
    for errado in (0, 5, 31 * 24 * 60):
        with pytest.raises(Exception):
            visitantes.duracao(errado, False)
    assert visitantes.texto_duracao(120) == "2 horas" and visitantes.texto_duracao(1440) == "1 dia"
    assert visitantes.texto_duracao(None) == "até o fim do dia"


def test_prazo():
    agora = datetime(2026, 11, 7, 10, 0)
    assert visitantes.validar_prazo(None, agora) is None
    assert visitantes.validar_prazo(datetime(2026, 11, 10, 18, 0, 30), agora) == datetime(2026, 11, 10, 18, 0)
    for errado in (agora, datetime(2027, 11, 8, 10, 0)):
        with pytest.raises(Exception):
            visitantes.validar_prazo(errado, agora)


def test_comentario_ida_e_volta():
    texto = visitantes.comentario(120, "  Reunião   de pais ")
    assert texto == "painel-visitante por 120 min | Reunião de pais"
    assert visitantes.ler_duracao(texto) == (True, 120, None, "", "Reunião de pais")
    prazo = datetime(2026, 11, 10, 18, 0)
    texto = visitantes.comentario(None, "", prazo)
    assert texto == "painel-visitante por fim do dia prazo 2026-11-10 18:00"
    assert visitantes.ler_duracao(texto) == (True, None, prazo, "", "")
    # Cartões antigos continuam reconhecidos.
    antigo = "painel-visitante até 2026-10-06 18:00 | Palestra"
    assert visitantes.ler_comentario(antigo) == (datetime(2026, 10, 6, 18, 0), "Palestra")
    assert visitantes.eh_visitante(antigo) and visitantes.eh_visitante(texto)
    assert not visitantes.eh_visitante("Maria - 9A") and visitantes.ler_duracao("Maria - 9A")[0] is False


def test_script_do_vigia_casa_com_o_comentario():
    # O vigia lê a duração a partir da letra 21 e procura o comentário do prazo.
    assert len("painel-visitante por ") == 21
    assert visitantes.comentario(None, "")[21:31] == "fim do dia"
    assert visitantes.COMENTARIO_PRAZO.startswith("Painel do Hotspot: prazo")
    assert '[find user=\\"" . $nome . "\\"]' in visitantes.SCRIPT_VIGIA


def test_criar_sem_prazo_aguarda_o_primeiro_acesso(logado, mk):
    r = logado.post("/api/visitantes", json={"quantidade": 3, "minutos": 120, "perfil": "alunos", "descricao": "Palestra"})
    assert r.status_code == 200, r.text
    criados = r.json()["criados"]
    assert [c["usuario"] for c in criados] == ["visita1", "visita2", "visita3"]
    assert all(len(c["senha"]) == 6 and c["senha"].isdigit() and c["aguardando"] for c in criados)

    usuario = next(u for u in mk.tabelas[USUARIOS] if u["name"] == "visita1")
    assert usuario["profile"] == "alunos" and usuario["comment"] == f"painel-visitante por 120 min lote {criados[0]['lote']} | Palestra"
    agenda = {a["name"]: a for a in mk.tabelas[AGENDA]}
    # Sem prazo: nenhum agendamento por visitante, só o vigia.
    assert not any(n.startswith("painel-visitante-") for n in agenda)
    assert agenda["painel-visitantes"]["interval"] == "30s"
    assert any(s["name"] == "painel-visitantes" and s["source"] == visitantes.SCRIPT_VIGIA for s in mk.tabelas[SCRIPTS])

    lista = logado.get("/api/visitantes").json()
    assert len(lista) == 3 and all(v["aguardando"] and v["agendado"] and not v["expirado"] and v["duracao"] == "2 horas"
                                   and v["descricao"] == "Palestra" for v in lista)

    # O vigia (no MikroTik) agenda a saída no primeiro acesso: o painel mostra a hora.
    fim = datetime.now() + timedelta(minutes=120)
    mk.adicionar(AGENDA, {"name": "painel-visitante-visita1", "interval": "2h", "comment": "Painel do Hotspot: remove o visitante visita1",
                          "next-run": f"{fim:%Y-%m-%d %H:%M:%S}"})
    v1 = next(v for v in logado.get("/api/visitantes").json() if v["usuario"] == "visita1")
    assert not v1["aguardando"] and v1["ate"] == f"{fim:%Y-%m-%dT%H:%M}"

    # Criar de novo não duplica o vigia.
    logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60})
    assert sum(a["name"] == "painel-visitantes" for a in mk.tabelas[AGENDA]) == 1


def test_criar_com_prazo_agenda_o_prazo(logado, mk):
    prazo = (datetime.now() + timedelta(days=3)).replace(second=0, microsecond=0)
    r = logado.post("/api/visitantes", json={"quantidade": 1, "ate_fim_do_dia": True, "prazo": f"{prazo:%Y-%m-%dT%H:%M}"})
    assert r.status_code == 200, r.text
    usuario = mk.tabelas[USUARIOS][-1]
    assert usuario["comment"] == f"painel-visitante por fim do dia prazo {prazo:%Y-%m-%d %H:%M} lote {r.json()['criados'][0]['lote']}"
    tarefa = next(a for a in mk.tabelas[AGENDA] if a["name"] == f"painel-visitante-{usuario['name']}")
    assert tarefa["start-date"] == f"{prazo:%Y-%m-%d}" and tarefa["start-time"] == f"{prazo:%H:%M:00}"
    assert tarefa["interval"] == "0s" and tarefa["comment"].startswith(visitantes.COMENTARIO_PRAZO)
    assert f'/ip hotspot user remove [find name="{usuario["name"]}"]' in tarefa["on-event"]
    v = logado.get("/api/visitantes").json()[0]
    assert v["aguardando"] and v["agendado"] and v["prazo"] == f"{prazo:%Y-%m-%dT%H:%M}"

    passado = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
    assert logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60, "prazo": passado}).status_code == 400


def test_cartao_antigo_continua_listado(logado, mk):
    mk.aceita_data_iso = False
    ate = datetime.now() + timedelta(hours=1)
    mk.adicionar(USUARIOS, {"name": "pais1", "password": "123456", "comment": f"painel-visitante até {ate:%Y-%m-%d %H:%M}"})
    mk.adicionar(AGENDA, {"name": "painel-visitante-pais1"})
    v = logado.get("/api/visitantes").json()[0]
    assert v["usuario"] == "pais1" and v["ate"] == f"{ate:%Y-%m-%dT%H:%M}" and v["agendado"] and not v["aguardando"]


def test_data_do_agendador():
    assert visitantes._data_hora("2026-11-07 14:30:00") == datetime(2026, 11, 7, 14, 30)
    assert visitantes._data_hora("nov/07/2026 14:30:00") == datetime(2026, 11, 7, 14, 30)
    assert visitantes._data_hora("") is None


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
    assert agenda == {"painel-visitantes"}  # sem prazo: o tempo só é agendado no primeiro acesso


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
    mk.adicionar(USUARIOS, {"name": "aluno10", "comment": "Aluno - 9A"})
    mk.adicionar(USUARIOS, {"name": "aluno2", "comment": "Aluno - 9A"})
    usuarios = [u["nome"] for u in logado.get("/api/usuarios").json()]
    assert usuarios == ["aluno2", "aluno10"]  # visitantes ficam fora (têm a própria tela)
    assert logado.get("/api/sistema").json()["usuarios"] == 2
