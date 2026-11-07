"""Lotes de visitantes, relógio do MikroTik, cópia da configuração e versão do painel."""

from datetime import datetime, timedelta

from app import backup_config, sistema, visitantes

USUARIOS = "/ip/hotspot/user"


# ------------------------------------------------------------- lotes

def test_lote_no_comentario():
    texto = visitantes.comentario(120, "Aula X", datetime(2026, 11, 13, 23, 59), "20261107003015")
    assert texto == "painel-visitante por 120 min prazo 2026-11-13 23:59 lote 20261107003015 | Aula X"
    assert visitantes.ler_duracao(texto) == (True, 120, datetime(2026, 11, 13, 23, 59), "20261107003015", "Aula X")
    # O vigia do MikroTik continua achando a duração.
    assert texto[21:texto.find(" min")] == "120"
    assert visitantes.criado_em("20261107003015") == "2026-11-07T00:30:15"
    assert visitantes.criado_em("") == ""


def test_criar_lote_e_listar_por_lote(logado, mk):
    r = logado.post("/api/visitantes", json={"quantidade": 3, "minutos": 60, "descricao": "Aula X", "nome": "aula"})
    assert r.status_code == 200, r.text
    criados = r.json()["criados"]
    lote = criados[0]["lote"]
    assert len(lote) == 14 and all(c["lote"] == lote for c in criados)
    assert all(f"lote {lote} | Aula X" in u["comment"] for u in mk.tabelas[USUARIOS] if u["name"].startswith("aula"))
    lista = logado.get("/api/visitantes").json()
    assert {v["lote"] for v in lista} == {lote} and all(v["criado_em"] for v in lista)

    # Cartão sem lote (de antes) aparece com lote vazio.
    mk.adicionar(USUARIOS, {"name": "velho1", "comment": "painel-visitante por 60 min | Antigo"})
    velho = next(v for v in logado.get("/api/visitantes").json() if v["usuario"] == "velho1")
    assert velho["lote"] == "" and velho["descricao"] == "Antigo"

    # Encerrar o lote = encerrar os ids dele.
    ids = [v["id"] for v in lista]
    r = logado.post("/api/visitantes/encerrar", json={"ids": ids})
    assert r.status_code == 200 and len(r.json()["encerrados"]) == 3
    assert [v["usuario"] for v in logado.get("/api/visitantes").json()] == ["velho1"]


def test_duas_criacoes_no_mesmo_segundo_sao_lotes_diferentes(logado):
    a = logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60, "descricao": "A"}).json()["criados"][0]
    b = logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60, "descricao": "B"}).json()["criados"][0]
    assert a["lote"] != b["lote"]


# ------------------------------------------------------------- relógio

def test_relogio_certo_e_com_problema(mk):
    from app.mikrotik import Mikrotik
    agora = datetime(2026, 10, 6, 22, 10, 0)
    with Mikrotik("https://mikrotik.teste", "admin", "segredo", transport=mk.transport()) as cliente:
        r = sistema.relogio(cliente, agora)
        assert r["diferenca"] == 30 and r["sincronizado"] and not r["alerta"] and r["servidor"] == "a.ntp.br"
        assert r["servidores"] == ["a.ntp.br", "b.ntp.br"]

        mk.objetos["/system/clock"]["time"] = "22:20:00"
        mk.objetos["/system/ntp/client"]["status"] = "waiting"
        r = sistema.relogio(cliente, agora)
        assert r["alerta"] and r["diferenca"] == 600
        assert "10 minuto(s) adiantada" in r["motivos"][0] and "não está sincronizado" in r["motivos"][1]

        mk.objetos["/system/clock"]["date"] = "oct/06/2026"
        mk.objetos["/system/clock"]["time"] = "21:00:00"
        mk.objetos["/system/ntp/client"]["enabled"] = "false"
        r = sistema.relogio(cliente, agora)
        assert "70 minuto(s) atrasada" in r["motivos"][0] and "desligado" in r["motivos"][1]


def test_sistema_traz_o_relogio(logado):
    dados = logado.get("/api/sistema").json()
    assert dados["relogio"]["servidores"] == ["a.ntp.br", "b.ntp.br"]


# ------------------------------------------------------------- cópia da configuração

def test_copia_da_configuracao(logado, mk, tmp_path):
    r = logado.post("/api/backups-config")
    assert r.status_code == 200, r.text
    nome = r.json()["nome"]
    assert ("POST", "/execute", {"script": "/export terse show-sensitive", "as-string": ""}) in mk.pedidos
    lista = logado.get("/api/backups-config").json()
    assert lista[0]["nome"] == nome and lista[0]["tamanho"] > 0
    baixado = logado.get(f"/api/backups-config/{nome}")
    assert baixado.status_code == 200 and "/ip hotspot profile add" in baixado.text and "\r" not in baixado.text
    assert logado.get("/api/backups-config/../../.env").status_code in (400, 404)
    assert logado.delete(f"/api/backups-config/{nome}").status_code == 200


def test_copia_semanal_e_limite(tmp_path):
    inicio = datetime(2026, 1, 1, 8, 0, 0)
    for semana in range(backup_config.MANTER + 3):
        backup_config.salvar(tmp_path, "# cópia\n", inicio + timedelta(days=7 * semana))
    assert len(backup_config.listar(tmp_path)) == backup_config.MANTER
    ultima = inicio + timedelta(days=7 * (backup_config.MANTER + 2))
    assert not backup_config.precisa(tmp_path, ultima + timedelta(days=6))
    assert backup_config.precisa(tmp_path, ultima + timedelta(days=7))


def test_export_vazio_e_erro(mk):
    from app.mikrotik import Mikrotik
    mk.export = ""
    with Mikrotik("https://mikrotik.teste", "admin", "segredo", transport=mk.transport()) as cliente:
        try:
            backup_config.exportar(cliente)
            assert False, "devia falhar"
        except Exception as erro:
            assert "configuração" in str(erro)


# ------------------------------------------------------------- versão do painel

def test_versao_do_painel(logado, mk):
    a = logado.get("/api/atualizacao").json()
    assert a["painel"]["tem"] is False and a["painel"]["disponivel"] == "1.0.0"
    mk.release = {"tag_name": "v99.0.0", "name": "v99.0.0 – Nova", "html_url": "https://github.com/x/y/releases/tag/v99.0.0"}
    a = logado.get("/api/atualizacao?forcar=true").json()
    assert a["painel"]["tem"] is True and a["painel"]["url"].endswith("v99.0.0")


def test_auditoria_protecoes(logado, mk):
    # Usuário comum não recebe a marca de visitante (o vigia o apagaria).
    r = logado.post("/api/usuarios", json={"nome": "joao", "senha": "abc123", "comentario": "painel-visitante por 1 min"})
    assert r.status_code == 400
    # O vigia só pega nomes de letras e números: aspas não entram no on-event.
    assert '!(name~"[^a-z0-9]")' in visitantes.SCRIPT_VIGIA
    # Backup não guarda (nem restaura) o limite de tempo vitalício.
    from app import backup
    assert "limit-uptime" not in backup._CAMPOS_USUARIO


def test_link_da_release_so_do_github():
    js = open("static/geral.js", encoding="utf-8").read()
    assert "/^https:\\/\\/github\\.com\\//.test(p.url" in js


def test_versao_do_painel_sem_internet():
    def falha():
        raise OSError("sem rede")
    r = sistema.verificar_painel("1.20.0", falha)
    assert r["falhou"] and not r["tem"]
