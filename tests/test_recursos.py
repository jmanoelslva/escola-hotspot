"""Testes das funções da versão 1.1: lote, senha, exportação, perfis, horário,
sites bloqueados, relatório, aviso, histórico e backup."""

import json
from io import BytesIO

from app import controle, util

USUARIOS = "/ip/hotspot/user"
PERFIS = "/ip/hotspot/user/profile"
FILTROS = "/ip/firewall/filter"
DNS = "/ip/dns/static"


def _criar(logado, *nomes, perfil="alunos"):
    for nome in nomes:
        assert logado.post("/api/usuarios", json={"nome": nome, "senha": "x", "perfil": perfil,
                                                  "comentario": f"{nome.title()} - 9º A"}).status_code == 200
    return {u["nome"]: u["id"] for u in logado.get("/api/usuarios").json()}


# ------------------------------------------------------------- lote, senha, exportação

def test_lote_desativar_ativar_e_trocar_perfil(logado, mk):
    ids = _criar(logado, "a1", "a2", "a3")
    alvo = [ids["a1"], ids["a2"]]
    r = logado.post("/api/usuarios/lote", json={"ids": alvo, "acao": "desativar"})
    assert r.json() == {"alterados": 2, "erros": []}
    estado = {u["name"]: u for u in mk.tabelas[USUARIOS]}
    assert estado["a1"]["disabled"] == "true" and estado["a3"]["disabled"] == "false"

    logado.post("/api/usuarios/lote", json={"ids": alvo, "acao": "ativar"})
    assert estado["a1"]["disabled"] == "false"

    r = logado.post("/api/usuarios/lote", json={"ids": alvo, "acao": "perfil", "perfil": "default"})
    assert r.status_code == 200 and estado["a2"]["profile"] == "default"

    r = logado.post("/api/usuarios/lote", json={"ids": alvo, "acao": "perfil", "perfil": "nao-existe"})
    assert r.status_code == 400


def test_nova_senha(logado, mk):
    ids = _criar(logado, "bia")
    r = logado.post(f"/api/usuarios/{ids['bia']}/nova-senha")
    assert r.status_code == 200
    senha = r.json()["senha"]
    assert len(senha) == 6 and senha != "x"
    assert mk.tabelas[USUARIOS][-1]["password"] == senha


def test_exportar_xlsx(logado):
    from openpyxl import load_workbook
    _criar(logado, "ana")
    r = logado.get("/api/usuarios/exportar?senhas=true")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    folha = load_workbook(BytesIO(r.content)).active
    linhas = list(folha.iter_rows(values_only=True))
    assert linhas[0][:4] == ("Usuário", "Senha", "Nome", "Turma")
    assert linhas[1][:4] == ("ana", "x", "Ana", "9º A")

    sem = load_workbook(BytesIO(logado.get("/api/usuarios/exportar").content)).active
    assert "Senha" not in next(sem.iter_rows(values_only=True))


def test_separar_turma():
    assert util.separar_turma("Maria da Silva - 9º A") == ("Maria da Silva", "9º A")
    assert util.separar_turma("Ana - Paula - 1B") == ("Ana - Paula", "1B")
    assert util.separar_turma("Professor João") == ("Professor João", "")


# ------------------------------------------------------------- perfis

def test_velocidade_ida_e_volta():
    assert controle.montar_velocidade(10, 2) == "2M/10M"
    assert controle.ler_velocidade("2M/10M") == (10, 2)
    assert controle.ler_velocidade("512k/1M 2M/4M") == (1, 0.512)
    assert controle.montar_velocidade(0.5, 0) == "0/500k"
    assert controle.montar_velocidade(0, 0) == ""


def test_criar_alterar_excluir_perfil(logado, mk):
    r = logado.post("/api/perfis", json={"nome": "professores", "download_mbps": 20, "envio_mbps": 5,
                                         "aparelhos": 3, "tempo_sessao": "8h"})
    assert r.status_code == 200, r.text
    perfil = mk.tabelas[PERFIS][-1]
    assert perfil == {".id": perfil[".id"], "disabled": "false", "name": "professores",
                      "rate-limit": "5M/20M", "shared-users": "3", "session-timeout": "8h"}

    lista = {p["nome"]: p for p in logado.get("/api/perfis/detalhes").json()}
    assert lista["professores"]["download_mbps"] == 20 and lista["professores"]["aparelhos"] == 3
    assert lista["default"]["padrao"]

    logado.patch(f"/api/perfis/{perfil['.id']}", json={"aparelhos": 0, "tempo_sessao": ""})
    assert perfil["shared-users"] == "unlimited" and perfil["session-timeout"] == "0s"

    assert logado.delete(f"/api/perfis/{perfil['.id']}").status_code == 200
    assert all(p["name"] != "professores" for p in mk.tabelas[PERFIS])


def test_nao_exclui_perfil_em_uso_nem_default(logado, mk):
    _criar(logado, "carla")
    alunos = next(p for p in mk.tabelas[PERFIS] if p["name"] == "alunos")
    r = logado.delete(f"/api/perfis/{alunos['.id']}")
    assert r.status_code == 400 and "usuário" in r.json()["erro"]
    assert logado.delete("/api/perfis/*0").status_code == 400


# ------------------------------------------------------------- horário

def test_janelas_fechadas():
    h = controle.validar_horario("07:00", "17:30", ["fri", "mon", "tue", "wed", "thu"])
    assert controle.janelas_fechadas(h) == [
        "00:00:00-07:00:00,mon,tue,wed,thu,fri",
        "17:30:00-23:59:59,mon,tue,wed,thu,fri",
        "00:00:00-23:59:59,sat,sun",
    ]
    todos = controle.validar_horario("00:00", "23:59", list(controle.DIAS))
    assert controle.janelas_fechadas(todos) == []


def test_horario_invalido(logado):
    alunos = "*1"
    for dados in ({"ativo": True, "inicio": "18:00", "fim": "07:00", "dias": ["mon"]},
                  {"ativo": True, "inicio": "7h", "fim": "17:00", "dias": ["mon"]},
                  {"ativo": True, "inicio": "07:00", "fim": "17:00", "dias": []}):
        assert logado.put(f"/api/perfis/{alunos}/horario", json=dados).status_code == 400


def test_aplicar_e_retirar_horario(logado, mk):
    regra_existente = mk.adicionar(FILTROS, {"chain": "forward", "action": "fasttrack-connection"})
    r = logado.put("/api/perfis/*1/horario", json={"ativo": True, "inicio": "07:00", "fim": "12:00",
                                                    "dias": ["mon", "tue", "wed", "thu", "fri"]})
    assert r.status_code == 200, r.text
    alunos = next(p for p in mk.tabelas[PERFIS] if p["name"] == "alunos")
    assert alunos["address-list"] == "painel-alunos"
    regras = mk.tabelas[FILTROS]
    assert [r["time"] for r in regras[:3]] == [
        "00:00:00-07:00:00,mon,tue,wed,thu,fri", "12:00:00-23:59:59,mon,tue,wed,thu,fri", "00:00:00-23:59:59,sat,sun"]
    assert regras[-1] is regra_existente  # as novas ficam antes das regras que já existiam
    assert all(r.get("src-address-list") == "painel-alunos" and r.get("action") == "drop" for r in regras[:3])

    perfil = next(p for p in logado.get("/api/perfis/detalhes").json() if p["nome"] == "alunos")
    assert perfil["horario"] == {"ativo": True, "inicio": "07:00", "fim": "12:00",
                                 "dias": ["mon", "tue", "wed", "thu", "fri"]}

    # Trocar o horário substitui as regras; desligar remove todas.
    logado.put("/api/perfis/*1/horario", json={"ativo": True, "inicio": "08:00", "fim": "23:59", "dias": list(controle.DIAS)})
    assert [r.get("time") for r in mk.tabelas[FILTROS]] == ["00:00:00-08:00:00,mon,tue,wed,thu,fri,sat,sun", None]
    logado.put("/api/perfis/*1/horario", json={"ativo": False})
    assert mk.tabelas[FILTROS] == [regra_existente]


def test_horario_aproveita_lista_que_o_perfil_ja_tinha(logado, mk):
    alunos = next(p for p in mk.tabelas[PERFIS] if p["name"] == "alunos")
    alunos["address-list"] = "lista-antiga"
    logado.put("/api/perfis/*1/horario", json={"ativo": True, "inicio": "07:00", "fim": "17:00", "dias": ["mon"]})
    assert alunos["address-list"] == "lista-antiga"
    assert all(r["src-address-list"] == "lista-antiga" for r in mk.tabelas[FILTROS])


# ------------------------------------------------------------- sites bloqueados

def test_normalizar_dominio():
    assert controle.normalizar_dominio("https://www.Bet365.com/pt/jogo?x=1") == "bet365.com"
    assert controle.normalizar_dominio("*.tiktok.com") == "tiktok.com"
    for errado in ("", "localhost", "bet 365.com", "http://"):
        try:
            controle.normalizar_dominio(errado)
        except util.ErroDados:
            continue
        raise AssertionError(errado)


def test_bloquear_pausar_e_desbloquear_site(logado, mk):
    r = logado.post("/api/bloqueios", json={"dominio": "https://www.bet365.com/", "motivo": "apostas"})
    assert r.json()["dominio"] == "bet365.com"
    registro = mk.tabelas[DNS][-1]
    assert registro["type"] == "NXDOMAIN" and registro["match-subdomain"] == "true"
    assert registro["comment"] == "painel-bloqueio: apostas"

    assert logado.post("/api/bloqueios", json={"dominio": "bet365.com"}).status_code == 400  # repetido

    lista = logado.get("/api/bloqueios").json()
    assert lista == [{"id": registro[".id"], "dominio": "bet365.com", "motivo": "apostas", "desativado": False}]

    logado.patch(f"/api/bloqueios/{registro['.id']}", json={"desativado": True})
    assert registro["disabled"] == "true"
    assert logado.delete(f"/api/bloqueios/{registro['.id']}").status_code == 200
    assert mk.tabelas[DNS] == []


def test_bloqueio_sem_nxdomain_usa_0000(logado, mk):
    mk.aceita_nxdomain = False
    assert logado.post("/api/bloqueios", json={"dominio": "tiktok.com"}).status_code == 200
    assert mk.tabelas[DNS][-1]["address"] == "0.0.0.0"


def test_nao_mexe_em_dns_que_nao_e_do_painel(logado, mk):
    alheio = mk.adicionar(DNS, {"name": "servidor.escola", "address": "192.168.88.10"})
    assert logado.get("/api/bloqueios").json() == []
    assert logado.delete(f"/api/bloqueios/{alheio['.id']}").status_code == 400
    assert alheio in mk.tabelas[DNS]


# ------------------------------------------------------------- relatório

def test_relatorio_e_zerar(logado, mk):
    _criar(logado, "dani")
    usuario = mk.tabelas[USUARIOS][-1]
    usuario.update({"bytes-in": "1000", "bytes-out": "50000", "uptime": "3h"})
    r = logado.get("/api/relatorio").json()
    assert r["desde"] == ""
    assert r["usuarios"][0]["bytes_out"] == 50000

    r = logado.post("/api/relatorio/zerar")
    assert r.status_code == 200 and r.json()["desde"]
    assert usuario["bytes-out"] == "0"
    assert logado.get("/api/relatorio").json()["desde"] == r.json()["desde"]


# ------------------------------------------------------------- aviso

def test_aviso_criar_e_alterar(logado, mk):
    assert logado.get("/api/aviso").json() == {"texto": "", "arquivo": "hotspot/aviso.txt"}
    logado.put("/api/aviso", json={"texto": "Feira de ciências sexta-feira!\r\nTragam o crachá."})
    arquivos = {a["name"]: a for a in mk.tabelas["/file"]}
    assert arquivos["hotspot/aviso.txt"]["contents"] == "Feira de ciências sexta-feira!\nTragam o crachá."
    # O que as páginas carregam: JavaScript só com ASCII (acentos em \u).
    script = arquivos["hotspot/aviso-escola.js"]["contents"]
    assert script == 'var AVISO_ESCOLA = "Feira de ci\\u00eancias sexta-feira!\\nTragam o crach\\u00e1.";\n'
    assert logado.get("/api/aviso").json()["texto"] == "Feira de ciências sexta-feira!\nTragam o crachá."

    logado.put("/api/aviso", json={"texto": ""})
    assert len(mk.tabelas["/file"]) == 2
    assert arquivos["hotspot/aviso.txt"]["contents"] == ""
    assert arquivos["hotspot/aviso-escola.js"]["contents"] == 'var AVISO_ESCOLA = "";\n'


def test_aviso_usa_pasta_do_perfil_do_hotspot(logado, mk):
    mk.tabelas["/ip/hotspot/profile"][0]["html-directory"] = "flash/hotspot"
    assert logado.get("/api/aviso").json()["arquivo"] == "flash/hotspot/aviso.txt"


# ------------------------------------------------------------- histórico

def test_historico_filtra(logado):
    _criar(logado, "eva")
    logado.post("/api/bloqueios", json={"dominio": "exemplo.com"})
    itens = logado.get("/api/historico").json()
    acoes = [i["acao"] for i in itens]
    assert "bloqueou o site exemplo.com" in acoes and "criou usuário eva" in acoes
    assert itens[0]["quando"] >= itens[-1]["quando"]
    filtrado = logado.get("/api/historico?busca=exemplo").json()
    assert filtrado and all("exemplo" in i["acao"] for i in filtrado)


# ------------------------------------------------------------- backup

def test_backup_automatico_no_login_e_restaurar(cliente, mk):
    from app.config import config
    from mikrotik_falso import SENHA, USUARIO
    for arquivo in (config.pasta_dados / "backups").glob("*.json") if (config.pasta_dados / "backups").exists() else []:
        arquivo.unlink()

    mk.adicionar(USUARIOS, {"name": "fabio", "password": "f1", "profile": "alunos", "comment": "Fabio - 1B"})
    mk.adicionar("/ip/hotspot/ip-binding", {"type": "bypassed", "mac-address": "11:22:33:44:55:66", "comment": "TV"})
    mk.adicionar(PERFIS, {"name": "professores", "rate-limit": "5M/20M"})
    mk.adicionar(DNS, {"name": "bet.com", "type": "NXDOMAIN", "comment": "painel-bloqueio: apostas"})

    cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    backups = cliente.get("/api/backups").json()
    assert len(backups) == 1
    assert backups[0]["usuarios"] == 1 and backups[0]["aparelhos"] == 1 and backups[0]["bloqueios"] == 1

    baixado = cliente.get(f"/api/backups/{backups[0]['nome']}").json()
    assert baixado["usuarios"][0] == {"name": "fabio", "password": "f1", "profile": "alunos", "comment": "Fabio - 1B"}

    # Segundo login no mesmo dia não faz outro backup.
    cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    assert len(cliente.get("/api/backups").json()) == 1

    # "Roteador resetado": some tudo; restaurar recria.
    mk.tabelas[USUARIOS][:] = [u for u in mk.tabelas[USUARIOS] if u["name"] == "default-trial"]
    mk.tabelas["/ip/hotspot/ip-binding"].clear()
    mk.tabelas[PERFIS][:] = [p for p in mk.tabelas[PERFIS] if p["name"] in ("default", "alunos")]
    mk.tabelas[DNS].clear()
    r = cliente.post("/api/backups/restaurar", json={"nome": backups[0]["nome"]})
    assert r.json() == {"perfis": 1, "usuarios": 1, "aparelhos": 1, "bloqueios": 1, "erros": []}
    assert any(u["name"] == "fabio" and u["password"] == "f1" for u in mk.tabelas[USUARIOS])

    # Restaurar de novo não duplica nada.
    r = cliente.post("/api/backups/restaurar", json={"nome": backups[0]["nome"]})
    assert r.json() == {"perfis": 0, "usuarios": 0, "aparelhos": 0, "bloqueios": 0, "erros": []}


def test_restaurar_de_arquivo_e_nome_invalido(logado, mk):
    conteudo = json.dumps({"usuarios": [{"name": "gil", "password": "g"}]}).encode()
    r = logado.post("/api/backups/restaurar-arquivo", files={"arquivo": ("b.json", BytesIO(conteudo), "application/json")})
    assert r.json()["usuarios"] == 1
    assert logado.get("/api/backups/..%2F.env").status_code in (400, 404)
    assert logado.post("/api/backups/restaurar", json={"nome": "../.env"}).status_code == 400
    r = logado.post("/api/backups/restaurar-arquivo", files={"arquivo": ("b.json", BytesIO(b"nada"), "application/json")})
    assert r.status_code == 400


def test_excluir_backup(logado):
    nome = logado.post("/api/backups").json()["nome"]
    assert any(b["nome"] == nome for b in logado.get("/api/backups").json())
    assert logado.delete(f"/api/backups/{nome}").status_code == 200
    assert all(b["nome"] != nome for b in logado.get("/api/backups").json())
    assert logado.delete(f"/api/backups/{nome}").status_code == 400  # já não existe
    assert logado.delete("/api/backups/..%2F.env").status_code in (400, 404)


# ------------------------------------------------------------- forçar DNS

def test_forcar_dns_ligar_desligar_religar(logado, mk):
    nat = mk.tabelas["/ip/firewall/nat"]
    alheia = mk.adicionar("/ip/firewall/nat", {"chain": "srcnat", "action": "masquerade", "comment": "internet"})
    assert logado.get("/api/forcar-dns").json() == {"ativo": False, "regras": 0, "interfaces": ["bridge-hotspot"], "dns_remoto": True}

    r = logado.put("/api/forcar-dns", json={"ativo": True}).json()
    assert r["ativo"] and r["regras"] == 2
    novas = [x for x in nat if x is not alheia]
    assert sorted(x["protocol"] for x in novas) == ["tcp", "udp"]
    assert all(x["chain"] == "dstnat" and x["action"] == "redirect" and x["dst-port"] == "53"
               and x["in-interface"] == "bridge-hotspot" and x["disabled"] == "false" for x in novas)

    # Desligar só desativa (as regras continuam lá).
    r = logado.put("/api/forcar-dns", json={"ativo": False}).json()
    assert not r["ativo"] and r["regras"] == 2
    assert all(x["disabled"] == "true" for x in novas) and len(nat) == 3

    # Religar reaproveita as mesmas regras, sem duplicar.
    r = logado.put("/api/forcar-dns", json={"ativo": True}).json()
    assert r["ativo"] and len(nat) == 3 and all(x["disabled"] == "false" for x in novas)
    assert alheia.get("disabled", "false") == "false" and alheia in nat  # regra de outra pessoa intacta


def test_forcar_dns_sem_hotspot(logado, mk):
    mk.tabelas["/ip/hotspot"].clear()
    r = logado.put("/api/forcar-dns", json={"ativo": True})
    assert r.status_code == 400 and "hotspot" in r.json()["erro"]


def test_forcar_dns_avisa_dns_remoto_desligado(logado, mk):
    mk.objetos["/ip/dns"]["allow-remote-requests"] = "false"
    assert logado.get("/api/forcar-dns").json()["dns_remoto"] is False
