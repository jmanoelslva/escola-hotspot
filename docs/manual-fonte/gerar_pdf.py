"""manual.html -> PDF A4 com rodapé de página."""
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PASTA = Path(__file__).parent
shutil.copy("D:/ESCOLA/hotspot-admin/static/logo.png", PASTA / "logo.png")
DESTINO = Path(sys.argv[1])

RODAPE = """<div style="width:100%; font-family:Segoe UI, Arial, sans-serif; font-size:8px; color:#52606d;
    padding:0 16mm; display:flex; justify-content:space-between;">
    <span>Painel do Hotspot · Manual de uso</span>
    <span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>"""

with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")
    page = navegador.new_page()
    page.goto((PASTA / "manual.html").as_uri())
    page.wait_for_load_state("networkidle")
    page.pdf(path=str(DESTINO), format="A4", print_background=True, display_header_footer=True,
             header_template="<div></div>", footer_template=RODAPE,
             margin={"top": "16mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
    navegador.close()
print("ok", DESTINO)
