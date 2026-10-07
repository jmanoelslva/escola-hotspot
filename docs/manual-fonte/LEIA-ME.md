# Fonte do manual

O PDF `../Manual do Painel do Hotspot.pdf` é gerado a partir destes arquivos:

- `manual.html`: o texto do manual.
- `telas/`: as telas do painel, capturadas com o MikroTik simulado e dados fictícios.
- `demo_manual.py`: sobe o painel na porta 8770 com dados de demonstração (rode com o Python da `.venv` do painel).
- `capturar_telas.py`: tira as telas (precisa de `pip install playwright` e do Google Chrome).
- `gerar_pdf.py`: gera o PDF a partir do `manual.html` (copia o logotipo para esta pasta).

Para atualizar: suba o `demo_manual.py`, rode o `capturar_telas.py`, ajuste o `manual.html` e rode `python gerar_pdf.py "../Manual do Painel do Hotspot.pdf"`.
