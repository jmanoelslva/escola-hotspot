import os
import sys
import tempfile
from pathlib import Path

import pytest

# Dados dos testes numa pasta temporária, antes de importar o app.
os.environ["PASTA_DADOS"] = tempfile.mkdtemp(prefix="painel-testes-")
os.environ["MIKROTIK_URL"] = "mikrotik.teste"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.mikrotik import EnderecoMikrotik  # noqa: E402
from app.sessoes import LimiteLogin, Sessoes  # noqa: E402
from mikrotik_falso import SENHA, USUARIO, MikrotikFalso  # noqa: E402


@pytest.fixture
def mk():
    falso = MikrotikFalso()
    app.state.transport = falso.transport()
    app.state.endereco = EnderecoMikrotik("mikrotik.teste", transport=app.state.transport)
    app.state.sessoes = Sessoes(60)
    app.state.limite_login = LimiteLogin()
    yield falso
    app.state.transport = None


@pytest.fixture
def cliente(mk):
    with TestClient(app, headers={"X-Painel": "1"}) as c:
        yield c


@pytest.fixture
def logado(cliente):
    r = cliente.post("/api/login", json={"usuario": USUARIO, "senha": SENHA})
    assert r.status_code == 200, r.text
    return cliente
