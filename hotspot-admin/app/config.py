"""Configuração lida do arquivo .env (na pasta do projeto) e das variáveis de ambiente."""

import os
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "1.11.1"

PASTA_PROJETO = Path(__file__).resolve().parent.parent


def _carregar_env(arquivo: Path) -> None:
    """Lê linhas CHAVE=valor sem sobrescrever o que já está no ambiente."""
    if not arquivo.is_file():
        return
    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(chave.strip(), valor)


def _sim(valor: str) -> bool:
    return valor.strip().lower() in ("1", "sim", "s", "true", "yes")


@dataclass(frozen=True)
class Config:
    mikrotik_url: str
    mikrotik_verificar_tls: bool
    mikrotik_timeout: float
    host: str
    porta: int
    sessao_minutos: int
    nome_escola: str
    cidade_escola: str
    pasta_dados: Path


def carregar() -> Config:
    _carregar_env(PASTA_PROJETO / ".env")
    pasta_dados = Path(os.environ.get("PASTA_DADOS", PASTA_PROJETO / "dados"))
    return Config(
        # Só o IP (sem http/https) = o painel escolhe sozinho: HTTPS se o www-ssl
        # estiver ativo, senão HTTP.
        mikrotik_url=os.environ.get("MIKROTIK_URL", "192.168.88.1").strip().rstrip("/"),
        mikrotik_verificar_tls=_sim(os.environ.get("MIKROTIK_VERIFICAR_TLS", "nao")),
        mikrotik_timeout=float(os.environ.get("MIKROTIK_TIMEOUT", "10")),
        host=os.environ.get("HOST", "0.0.0.0"),
        porta=int(os.environ.get("PORTA", "8080")),
        sessao_minutos=int(os.environ.get("SESSAO_MINUTOS", "60")),
        nome_escola=os.environ.get("NOME_ESCOLA", "Escola"),
        cidade_escola=os.environ.get("CIDADE_ESCOLA", ""),
        pasta_dados=pasta_dados,
    )


config = carregar()
