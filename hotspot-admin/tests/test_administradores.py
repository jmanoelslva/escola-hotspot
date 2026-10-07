"""Administradores do MikroTik (/user): cadastro, grupo "painel" e proteções."""

USUARIOS = "/user"
GRUPOS = "/user/group"


def _por_nome(mk, nome):
    return next(u for u in mk.tabelas[USUARIOS] if u["name"] == nome)


def test_listar_sem_mostrar_senha(logado, mk):
    r = logado.get("/api/administradores").json()
    assert r["eu"] == "admin" and r["grupos"][:2] == ["painel", "full"]
    assert r["usuarios"] == [{"id": "*1", "nome": "admin", "grupo": "full", "comentario": "system default user",
                              "ultimo_acesso": "2026-10-07 08:00:00", "desativado": False}]


def test_cadastrar_no_grupo_painel_cria_o_grupo(logado, mk):
    r = logado.post("/api/administradores", json={"nome": "coordenacao", "senha": "senha-forte-1", "comentario": "Coordenação"})
    assert r.status_code == 200, r.text
    assert r.json()["grupo"] == "painel" and "senha" not in r.json()
    grupo = next(g for g in mk.tabelas[GRUPOS] if g["name"] == "painel")
    assert "rest-api" in grupo["policy"] and "winbox" not in grupo["policy"] and "reboot" not in grupo["policy"]
    assert _por_nome(mk, "coordenacao")["password"] == "senha-forte-1"
    # Segundo cadastro reaproveita o grupo.
    logado.post("/api/administradores", json={"nome": "secretaria", "senha": "outra-senha-2"})
    assert sum(g["name"] == "painel" for g in mk.tabelas[GRUPOS]) == 1


def test_validacoes(logado):
    assert logado.post("/api/administradores", json={"nome": "x", "senha": "curta"}).status_code == 400
    assert logado.post("/api/administradores", json={"nome": "admin", "senha": "senha-forte-1"}).status_code == 400
    assert logado.post("/api/administradores", json={"nome": "y", "senha": "senha-forte-1", "grupo": "nao-existe"}).status_code == 400
    assert logado.post("/api/administradores", json={"nome": "joão", "senha": "senha-forte-1"}).status_code == 400


def test_alterar_desativar_e_excluir(logado, mk):
    item = logado.post("/api/administradores", json={"nome": "ti", "senha": "senha-forte-1", "grupo": "full"}).json()
    r = logado.patch(f"/api/administradores/{item['id']}", json={"senha": "nova-senha-99", "comentario": "Técnico"})
    assert r.status_code == 200 and _por_nome(mk, "ti")["password"] == "nova-senha-99"
    from app.config import config
    log = (config.pasta_dados / "acoes.log").read_text(encoding="utf-8")
    assert "nova-senha-99" not in log and "alterou o administrador ti (senha, comentário)" in log
    assert logado.patch(f"/api/administradores/{item['id']}", json={"desativado": True}).status_code == 200
    assert _por_nome(mk, "ti")["disabled"] == "true"
    assert logado.delete(f"/api/administradores/{item['id']}").status_code == 200
    assert all(u["name"] != "ti" for u in mk.tabelas[USUARIOS])


def test_nao_mexe_no_proprio_usuario_nem_no_ultimo_full(logado, mk):
    assert logado.delete("/api/administradores/*1").status_code == 400  # eu mesmo
    assert logado.patch("/api/administradores/*1", json={"desativado": True}).status_code == 400
    assert logado.patch("/api/administradores/*1", json={"grupo": "read"}).status_code == 400
    # Outro full, o último ativo além de mim desativado: não pode sair.
    outro = mk.adicionar(USUARIOS, {"name": "rede", "group": "full", "disabled": "false"})
    mk.tabelas[USUARIOS][0]["disabled"] = "true"  # imita o admin desativado por fora
    r = logado.delete(f"/api/administradores/{outro['.id']}")
    assert r.status_code == 400 and "último administrador full" in r.json()["erro"]


def test_trocar_a_propria_senha_mantem_a_sessao(logado, mk):
    import mikrotik_falso
    r = logado.patch("/api/administradores/*1", json={"senha": "senha-nova-123"})
    assert r.status_code == 200
    # O MikroTik falso passa a aceitar só a senha nova; a sessão continua funcionando.
    original = mikrotik_falso.AUTORIZACAO
    import base64
    mikrotik_falso.AUTORIZACAO = "Basic " + base64.b64encode(b"admin:senha-nova-123").decode()
    try:
        assert logado.get("/api/administradores").status_code == 200
    finally:
        mikrotik_falso.AUTORIZACAO = original


def test_agendadores_do_painel_tem_politica_minima(logado, mk):
    logado.post("/api/visitantes", json={"quantidade": 1, "minutos": 60})
    assert mk.tabelas["/system/scheduler"][-1]["policy"] == "read,write,test"
