"""Tira as telas do painel (MikroTik simulado, dados fictícios) para o manual."""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8770"
SAIDA = Path(__file__).parent / "telas"
SAIDA.mkdir(parents=True, exist_ok=True)


def esperar(page, ms=900):
    page.wait_for_timeout(ms)


def limpar(page):
    page.evaluate("""() => {
        const f = document.querySelector('#faixa-atualizacao'); if (f) f.hidden = true;
        const a = document.querySelector('#aviso'); if (a) a.hidden = true;
        window.scrollTo(0, 0);
    }""")


def tela(page, nome, aba=None, ms=1200, pagina_inteira=True, antes=None):
    if aba:
        page.evaluate(f"abrirAba('{aba}')")
    esperar(page, ms)
    if antes:
        page.evaluate(antes)
        esperar(page, 500)
    limpar(page)
    page.screenshot(path=str(SAIDA / f"{nome}.png"), full_page=pagina_inteira)
    print("ok", nome)


def api(page, metodo, url, corpo=None):
    return page.evaluate("([m, u, c]) => api(m, u, c === null ? undefined : c)", [metodo, url, corpo])


with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")
    page = navegador.new_page(viewport={"width": 1180, "height": 760}, device_scale_factor=1.5, locale="pt-BR")
    page.goto(BASE + "/")
    esperar(page, 1500)
    page.screenshot(path=str(SAIDA / "01-entrar.png"))

    page.fill("#form-login input[name=usuario]", "admin")
    page.fill("#form-login input[name=senha]", "segredo")
    page.click("#form-login button[type=submit]")
    esperar(page, 2500)

    # Dados de exemplo criados pelo próprio painel
    api(page, "PUT", "/api/aviso", {"texto": "Feira de ciências nesta sexta-feira. Tragam o crachá!"})
    api(page, "PUT", "/api/configuracoes/wifi", {"ssid": "Administrativo", "seguranca": "wpa", "senha": "exemplo-2026"})
    api(page, "POST", "/api/visitantes", {"quantidade": 4, "minutos": 120, "nome": "pais", "descricao": "Reunião de pais"})
    api(page, "POST", "/api/visitantes", {"quantidade": 2, "ate_fim_do_dia": True, "nome": "tecnico", "descricao": "Manutenção"})
    api(page, "PUT", "/api/rede-alunos/config", {"interface": "VLAN300-ALUNOS", "janelas": [
        {"inicio": "08:50", "fim": "09:10", "dias": [1, 2, 3, 4, 5]},
        {"inicio": "12:00", "fim": "12:50", "dias": [1, 2, 3, 4, 5]},
        {"inicio": "14:40", "fim": "15:00", "dias": [1, 2, 3, 4, 5]},
        {"inicio": "08:00", "fim": "12:00", "dias": [6]}]})
    api(page, "PUT", "/api/perfis/*1/horario", {"ativo": True, "inicio": "07:00", "fim": "17:00", "dias": ["mon", "tue", "wed", "thu", "fri"]})
    api(page, "PUT", "/api/forcar-dns", {"ativo": True})
    api(page, "POST", "/api/backups")
    api(page, "PUT", "/api/configuracoes/escola", {"nome": "Escola Estadual Professora Maria Aldineide Pessoa Gomes", "cidade": "Coité do Noia - AL"})
    api(page, "PUT", "/api/configuracoes/troca-senha", {"ativo": True})
    page.reload()
    esperar(page, 2500)

    tela(page, "02-inicio", "geral", ms=40000, pagina_inteira=False)
    page.click('[data-periodo="30d"]')
    esperar(page, 1500)
    page.locator(".topo-uso").locator("..").screenshot(path=str(SAIDA / "02b-uso.png"))
    print("ok 02b-uso")
    tela(page, "03-usuarios", "usuarios")
    tela(page, "04-novo-usuario", None, antes="document.querySelector('#novo-usuario').click()", pagina_inteira=False)
    page.keyboard.press("Escape")
    tela(page, "05-visitantes", "visitantes", ms=1800)
    tela(page, "06-perfis", "perfis")
    tela(page, "07-importar", "importar")
    tela(page, "08-conectados", "conectados")
    tela(page, "09-todos-aparelhos", "rede")
    tela(page, "10-consumo", "relatorio")
    tela(page, "11-aparelhos", "aparelhos")
    tela(page, "12-rede-alunos", "alunos", ms=1800)
    tela(page, "13-sites", "sites")
    tela(page, "14-aviso", "aviso")
    page.evaluate("abrirAba('config')")
    esperar(page, 2000)
    limpar(page)
    page.locator("#form-escola").screenshot(path=str(SAIDA / "15a-escola.png"))
    page.locator("#form-ap").locator("..").screenshot(path=str(SAIDA / "15b-aps.png"))
    page.locator("#ativar-servico").locator("../..").screenshot(path=str(SAIDA / "15c-servico.png"))
    page.locator("#form-mikrotik").screenshot(path=str(SAIDA / "15d-conexao.png"))
    print("ok 15-configuracoes")
    tela(page, "16-administradores", "administradores")
    tela(page, "20-relatorio", "mensal", ms=2500)
    tela(page, "17-backup", "backup")
    tela(page, "18-historico", "historico")

    # Cartões de visitante como saem na impressão
    page.evaluate("abrirAba('visitantes')")
    esperar(page, 1500)
    page.evaluate("window.print = () => {}")
    page.evaluate("imprimir(estado.visitantes.slice(0, 3).map(cartaoVisitante))")
    esperar(page, 1500)
    page.emulate_media(media="print")
    esperar(page, 500)
    page.locator("#impressao").screenshot(path=str(SAIDA / "19-cartoes.png"))
    page.emulate_media(media="screen")
    print("ok 19-cartoes")
    celular = navegador.new_page(viewport={"width": 390, "height": 780}, device_scale_factor=2, locale="pt-BR")
    celular.goto(BASE + "/senha")
    esperar(celular, 1200)
    celular.screenshot(path=str(SAIDA / "21-senha.png"))
    print("ok 21-senha")
    navegador.close()
