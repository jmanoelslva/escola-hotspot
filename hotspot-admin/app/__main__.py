"""Inicia o painel: python -m app"""

import logging
import os

import uvicorn

from .ajustes import endereco_mikrotik
from .config import config

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # sem uma linha por requisição ao MikroTik
    logging.getLogger("painel").info("Painel em http://localhost:%s, MikroTik em %s", config.porta,
                                    endereco_mikrotik(config.pasta_dados, config))
    os.environ["PAINEL_COLETA"] = "1"  # liga a coleta do histórico de uso (os testes não ligam)
    uvicorn.run("app.main:app", host=config.host, port=config.porta, log_level="warning")
