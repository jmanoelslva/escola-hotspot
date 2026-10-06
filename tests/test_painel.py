from io import BytesIO

from app import util
from mikrotik_falso import SENHA, USUARIO

USUARIOS = "/ip/hotspot/user"
BINDINGS = "/ip/hotspot/ip-binding"


# ------------------------------------------------------------- login e segurança

def test_sem_login_recusa(cliente):
    assert cliente.get("/api/usuarios").status_code == 401


def test_login_errado_e_bloqueio(cliente):
    for _ in range(5):
        r = cliente.post("/api/login", json={"usuario": USUARIO, "senha": "errada"})
        assert r.status_code == 401
        assert "incorretos" in r.json()["erro"]
    r = cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    assert r.status_code == 429


def test_login_certo_e_sair(logado):
    r = logado.get("/api/sessao")
    assert r.json() == {"usuario": USUARIO, "identidade": "hEX-escola", "conexao": "HTTPS"}
    assert logado.post("/api/logout").status_code == 200
    assert logado.get("/api/sessao").status_code == 401


def test_cookie_protegido(cliente):
    r = cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_alteracao_sem_cabecalho_do_painel_e_recusada(logado):
    r = logado.post("/api/usuarios", json={"nome": "x", "senha": "y"}, headers={"X-Painel": ""})
    assert r.status_code == 403


def test_id_invalido_nao_vai_para_o_mikrotik(logado, mk):
    r = logado.delete("/api/usuarios/..%2Fsystem")
    assert r.status_code in (400, 404)
    assert not any(m == "DELETE" for m, _, _ in mk.pedidos)


# ------------------------------------------------------------- usuários

def test_criar_listar_alterar_excluir_usuario(logado, mk):
    r = logado.post("/api/usuarios", json={
        "nome": "maria.silva", "senha": "abc123", "perfil": "alunos",
        "comentario": "Maria - 9A", "limite_tempo": "2h", "mac": "aa-bb-cc-dd-ee-ff",
    })
    assert r.status_code == 200, r.text
    criado = mk.tabelas[USUARIOS][-1]
    assert criado["name"] == "maria.silva"
    assert criado["profile"] == "alunos"
    assert criado["limit-uptime"] == "2h"
    assert criado["mac-address"] == "AA:BB:CC:DD:EE:FF"

    lista = logado.get("/api/usuarios").json()
    assert [u["nome"] for u in lista] == ["maria.silva"]  # default-trial fica de fora
    usuario = lista[0]
    assert usuario["senha"] == "abc123"

    r = logado.patch(f"/api/usuarios/{usuario['id']}", json={"desativado": True, "limite_tempo": "", "mac": ""})
    assert r.status_code == 200, r.text
    assert criado["disabled"] == "true"
    assert criado["limit-uptime"] == "0s"
    assert criado["mac-address"] == "00:00:00:00:00:00"
    assert logado.get("/api/usuarios").json()[0]["mac"] == ""

    assert logado.delete(f"/api/usuarios/{usuario['id']}").status_code == 200
    assert logado.get("/api/usuarios").json() == []


def test_usuario_repetido_mostra_erro_em_portugues(logado):
    logado.post("/api/usuarios", json={"nome": "joao", "senha": "1"})
    r = logado.post("/api/usuarios", json={"nome": "joao", "senha": "2"})
    assert r.status_code == 400
    assert r.json()["erro"] == "Já existe um usuário com esse nome."


def test_usuario_com_acento_e_recusado(logado, mk):
    r = logado.post("/api/usuarios", json={"nome": "joão", "senha": "1"})
    assert r.status_code == 400
    assert not mk.tabelas[USUARIOS][1:]


def test_excluir_varios(logado, mk):
    for nome in ("a1", "a2", "a3"):
        logado.post("/api/usuarios", json={"nome": nome, "senha": "x"})
    ids = [u["id"] for u in logado.get("/api/usuarios").json()][:2]
    r = logado.post("/api/usuarios/excluir", json={"ids": ids})
    assert r.json() == {"removidos": 2, "erros": []}
    assert [u["nome"] for u in logado.get("/api/usuarios").json()] == ["a3"]


def test_alterar_senha_nao_grava_senha_no_log(logado, mk):
    logado.post("/api/usuarios", json={"nome": "ana", "senha": "velha"})
    item_id = logado.get("/api/usuarios").json()[0]["id"]
    logado.patch(f"/api/usuarios/{item_id}", json={"senha": "nova-senha"})
    from app.config import config
    log = (config.pasta_dados / "acoes.log").read_text(encoding="utf-8")
    assert "nova-senha" not in log
    assert "alterou usuário ana (senha)" in log


# ------------------------------------------------------------- conectados e aparelhos

def test_conectados_e_desconectar(logado, mk):
    ativo = mk.adicionar("/ip/hotspot/active", {"user": "ana", "address": "10.0.0.5", "mac-address": "AA:AA:AA:AA:AA:AA",
                                                "uptime": "5m", "bytes-in": "100", "bytes-out": "2000"})
    lista = logado.get("/api/conectados").json()
    assert lista[0]["usuario"] == "ana" and lista[0]["bytes_out"] == 2000
    cookie_dele = mk.adicionar("/ip/hotspot/cookie", {"user": "ana", "mac-address": "aa:aa:aa:aa:aa:aa"})
    outro = mk.adicionar("/ip/hotspot/cookie", {"user": "bia", "mac-address": "BB:BB:BB:BB:BB:BB"})
    r = logado.delete(f"/api/conectados/{ativo['.id']}")
    assert r.status_code == 200 and r.json()["cookies"] == 1
    assert mk.tabelas["/ip/hotspot/active"] == []
    assert cookie_dele not in mk.tabelas["/ip/hotspot/cookie"] and outro in mk.tabelas["/ip/hotspot/cookie"]
    # O cookie sai antes da sessão, para o aparelho não entrar sozinho de novo.
    remocoes = [c for m, c, _ in mk.pedidos if m == "DELETE"]
    assert remocoes[-2].startswith("/ip/hotspot/cookie/") and remocoes[-1].startswith("/ip/hotspot/active/")


def test_bypass_e_bloqueio(logado, mk):
    r = logado.post("/api/dispositivos", json={"tipo": "bypassed", "mac": "11:22:33:44:55:66", "comentario": "TV sala 3"})
    assert r.status_code == 200, r.text
    binding = mk.tabelas[BINDINGS][-1]
    assert binding["type"] == "bypassed" and binding["server"] == "all" and "address" not in binding

    r = logado.post("/api/dispositivos", json={"tipo": "blocked", "mac": "112233445577", "ip": "10.5.50.9", "comentario": "Celular X"})
    assert r.status_code == 200, r.text
    assert mk.tabelas[BINDINGS][-1]["address"] == "10.5.50.9"

    lista = logado.get("/api/dispositivos").json()
    assert [d["tipo"] for d in lista] == ["blocked", "bypassed"]

    tv = next(d for d in lista if d["tipo"] == "bypassed")
    logado.patch(f"/api/dispositivos/{tv['id']}", json={"desativado": True, "comentario": "TV sala 4"})
    assert binding["disabled"] == "true" and binding["comment"] == "TV sala 4"

    assert logado.delete(f"/api/dispositivos/{tv['id']}").status_code == 200
    assert len(mk.tabelas[BINDINGS]) == 1


def test_mac_invalido(logado):
    r = logado.post("/api/dispositivos", json={"tipo": "bypassed", "mac": "xyz", "comentario": "TV"})
    assert r.status_code == 400
    assert "MAC" in r.json()["erro"]


def test_aparelhos_da_rede_com_nome_do_dhcp(logado, mk):
    mk.adicionar("/ip/hotspot/host", {"mac-address": "AA:BB:CC:00:00:01", "address": "10.5.50.20", "authorized": "false", "bypassed": "false"})
    mk.adicionar("/ip/dhcp-server/lease", {"mac-address": "AA:BB:CC:00:00:01", "host-name": "SamsungTV"})
    lista = logado.get("/api/aparelhos").json()
    assert lista == [{"mac": "AA:BB:CC:00:00:01", "ip": "10.5.50.20", "nome": "SamsungTV", "autorizado": False, "bypass": False}]


# ------------------------------------------------------------- importação

def _csv(texto: str, codificacao: str = "utf-8-sig"):
    return {"arquivo": ("turma.csv", BytesIO(texto.encode(codificacao)), "text/csv")}


def test_importar_csv(logado, mk):
    logado.post("/api/usuarios", json={"nome": "existente", "senha": "x"})
    texto = "Usuário;Senha;Nome;Turma;Perfil\nana.b;;Ana B;9º A;\nexistente;1;X;;\nana.b;2;Rep;;\ncarlos;c1;Carlos;;inexistente\njoão;1;;;\n"
    r = logado.post("/api/importar/previa", files=_csv(texto))
    assert r.status_code == 200, r.text
    linhas = r.json()["linhas"]
    assert linhas[0]["erro"] == "" and linhas[0]["senha_gerada"] and len(linhas[0]["senha"]) == 6
    assert linhas[0]["comentario"] == "Ana B - 9º A"
    assert linhas[1]["erro"] == "Já existe no MikroTik."
    assert linhas[2]["erro"] == "Repetido na planilha."
    assert "não existe" in linhas[3]["erro"]
    assert "inválido" in linhas[4]["erro"]

    validas = [{"usuario": l["usuario"], "senha": l["senha"], "comentario": l["comentario"], "perfil": l["perfil"]}
               for l in linhas if not l["erro"]]
    r = logado.post("/api/importar", json={"perfil": "alunos", "linhas": validas})
    assert r.json()["criados"] == 1
    criado = mk.tabelas[USUARIOS][-1]
    assert criado["name"] == "ana.b" and criado["profile"] == "alunos" and criado["comment"] == "Ana B - 9º A"


def test_importar_csv_do_excel_em_cp1252_com_virgula(logado):
    texto = "usuario,senha,nome\nmaria,123,Maria Conceição\n"
    r = logado.post("/api/importar/previa", files=_csv(texto, "cp1252"))
    assert r.json()["linhas"][0]["nome"] == "Maria Conceição"


def test_importar_xlsx(logado):
    from openpyxl import Workbook
    livro = Workbook()
    folha = livro.active
    folha.append(["Login", "Senha", "Aluno"])
    folha.append(["pedro", 123456, "Pedro"])
    arquivo = BytesIO()
    livro.save(arquivo)
    arquivo.seek(0)
    r = logado.post("/api/importar/previa", files={"arquivo": ("turma.xlsx", arquivo, "application/octet-stream")})
    linha = r.json()["linhas"][0]
    assert (linha["usuario"], linha["senha"], linha["nome"]) == ("pedro", "123456", "Pedro")


def test_importar_sem_coluna_usuario(logado):
    r = logado.post("/api/importar/previa", files=_csv("nome;turma\nAna;9A\n"))
    assert r.status_code == 400
    assert "usuario" in r.json()["erro"]


# ------------------------------------------------------------- utilidades

def test_normalizar_mac():
    assert util.normalizar_mac("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"
    assert util.normalizar_mac(" AA:bb:CC:dd:EE:ff ") == "AA:BB:CC:DD:EE:FF"


def test_validar_tempo():
    assert util.validar_tempo("1d 12h") == "1d12h"
    assert util.validar_tempo("") == ""
    for errado in ("2 horas", "h", "1x"):
        try:
            util.validar_tempo(errado)
        except util.ErroDados:
            continue
        raise AssertionError(errado)


def test_pagina_inicial_e_modelo(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "Painel do Hotspot" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert cliente.get("/modelo.csv").content.startswith(b"\xef\xbb\xbfusuario;senha")


def test_sem_www_ssl_usa_http(cliente, mk):
    mk.https = False
    r = cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    assert r.status_code == 200, r.text
    assert r.json()["conexao"] == "HTTP"


def test_endereco_com_protocolo_e_usado_como_esta():
    from app.mikrotik import EnderecoMikrotik
    assert EnderecoMikrotik("http://10.0.0.1").url() == "http://10.0.0.1"


def test_mikrotik_fora_do_ar(cliente, mk):
    import httpx

    def recusar(pedido):
        raise httpx.ConnectError("fora", request=pedido)
    from app.main import app
    from app.mikrotik import EnderecoMikrotik
    app.state.transport = httpx.MockTransport(recusar)
    app.state.endereco = EnderecoMikrotik("mikrotik.teste", transport=app.state.transport)
    r = cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    assert r.status_code == 502
    assert "nem por HTTPS nem por HTTP" in r.json()["erro"]


def test_arquivos_do_app(cliente):
    sw = cliente.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    manifesto = cliente.get("/manifest.webmanifest")
    assert manifesto.headers["content-type"].startswith("application/manifest+json")
    dados = manifesto.json()
    assert dados["display"] == "standalone" and dados["start_url"] == "/"
    for icone in dados["icons"]:
        assert cliente.get(icone["src"]).status_code == 200
    assert cliente.get("/static/icone.ico").status_code == 200
