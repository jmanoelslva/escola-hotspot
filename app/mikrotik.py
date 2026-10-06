"""Cliente da REST API do RouterOS 7 (https://help.mikrotik.com/docs/display/ROS/REST+API).

Cada requisição vai com o usuário e a senha de quem está logado no painel,
então o próprio MikroTik decide o que essa pessoa pode fazer.
"""

import logging
import threading
import time
from typing import Any

import httpx

log = logging.getLogger("painel")


class ErroMikrotik(Exception):
    """O MikroTik recusou a operação (mensagem já em texto para o usuário)."""

    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class ErroAutenticacao(ErroMikrotik):
    def __init__(self, mensagem: str = "Usuário ou senha do MikroTik incorretos."):
        super().__init__(mensagem, 401)


class ErroConexao(ErroMikrotik):
    def __init__(self, mensagem: str = "Não foi possível falar com o MikroTik. Confira o endereço e se o serviço www ou www-ssl está ativo."):
        super().__init__(mensagem, 502)


# Mensagens comuns do RouterOS traduzidas para o painel.
_TRADUCOES = {
    "already have user with this name": "Já existe um usuário com esse nome.",
    "already have such entry": "Esse aparelho já está cadastrado.",
    "no such item": "O item não existe mais no MikroTik (atualize a lista).",
    "not enough permissions": "Seu usuário do MikroTik não tem permissão para isso.",
    "invalid value for argument mac-address": "Endereço MAC inválido.",
    "invalid value for argument address": "Endereço IP inválido.",
    "input does not match any value of profile": "Perfil inexistente no MikroTik.",
}


def _traduzir(texto: str) -> str:
    minusculo = texto.lower()
    for trecho, traducao in _TRADUCOES.items():
        if trecho in minusculo:
            return traducao
    return texto


class EnderecoMikrotik:
    """Decide se a REST API responde por HTTPS (www-ssl) ou HTTP (www).

    Com MIKROTIK_URL só com o IP, testa HTTPS e depois HTTP e guarda o que
    funcionou por alguns minutos. Com http:// ou https:// usa o que veio.
    """

    VALIDADE = 300

    def __init__(self, endereco: str, verificar_tls: bool = False,
                 transport: httpx.BaseTransport | None = None):
        self._endereco = endereco
        self._verificar_tls = verificar_tls
        self._transport = transport
        self._url: str | None = None
        self._quando = 0.0
        self._trava = threading.Lock()

    @property
    def automatico(self) -> bool:
        return not self._endereco.startswith(("http://", "https://"))

    def url(self) -> str:
        if not self.automatico:
            return self._endereco
        with self._trava:
            if self._url and time.monotonic() - self._quando < self.VALIDADE:
                return self._url
            for esquema in ("https", "http"):
                candidato = f"{esquema}://{self._endereco}"
                try:
                    with httpx.Client(verify=self._verificar_tls, timeout=4, transport=self._transport) as cliente:
                        # Sem senha: qualquer resposta (401) mostra que a REST API está ali.
                        cliente.get(f"{candidato}/rest/system/identity")
                except httpx.HTTPError:
                    continue
                self._url, self._quando = candidato, time.monotonic()
                return candidato
            self._url = None
            raise ErroConexao(f"Não foi possível falar com o MikroTik em {self._endereco} (nem por HTTPS nem por HTTP).")

    def esquecer(self) -> None:
        with self._trava:
            self._url = None


class Mikrotik:
    def __init__(self, url: str, usuario: str, senha: str, verificar_tls: bool = False,
                 timeout: float = 10, transport: httpx.BaseTransport | None = None):
        self._cliente = httpx.Client(
            base_url=f"{url}/rest",
            auth=(usuario, senha),
            verify=verificar_tls,
            timeout=timeout,
            transport=transport,
        )
        self._endereco = url

    def fechar(self) -> None:
        self._cliente.close()

    def __enter__(self) -> "Mikrotik":
        return self

    def __exit__(self, *_: Any) -> None:
        self.fechar()

    def _pedir(self, metodo: str, caminho: str, **kwargs: Any) -> Any:
        try:
            resposta = self._cliente.request(metodo, caminho, **kwargs)
        except httpx.TimeoutException as erro:
            raise ErroConexao(f"O MikroTik ({self._endereco}) demorou demais para responder.") from erro
        except httpx.HTTPError as erro:
            log.warning("falha ao falar com %s: %r", self._endereco, erro)
            raise ErroConexao(f"Não foi possível falar com o MikroTik em {self._endereco}. "
                              "Confira o MIKROTIK_URL no arquivo .env e se o serviço www ou www-ssl está ativo.") from erro

        if resposta.status_code == 401:
            raise ErroAutenticacao()
        if resposta.status_code == 403:
            raise ErroMikrotik("Seu usuário do MikroTik não tem permissão para isso.", 403)
        if resposta.status_code >= 400:
            try:
                corpo = resposta.json()
                texto = corpo.get("detail") or corpo.get("message") or resposta.text
            except ValueError:
                texto = resposta.text or f"Erro {resposta.status_code}"
            if resposta.status_code == 404 and "no such command" in texto.lower():
                texto = "Recurso não encontrado no MikroTik (a REST API precisa do RouterOS 7)."
            raise ErroMikrotik(_traduzir(texto.strip()), 400 if resposta.status_code < 500 else 502)

        if not resposta.content:
            return None
        return resposta.json()

    def listar(self, caminho: str) -> list[dict[str, Any]]:
        dados = self._pedir("GET", caminho)
        return dados if isinstance(dados, list) else []

    def obter(self, caminho: str, item_id: str) -> dict[str, Any]:
        return self._pedir("GET", f"{caminho}/{item_id}")

    def criar(self, caminho: str, dados: dict[str, Any]) -> dict[str, Any]:
        return self._pedir("PUT", caminho, json=dados)

    def alterar(self, caminho: str, item_id: str, dados: dict[str, Any]) -> dict[str, Any]:
        return self._pedir("PATCH", f"{caminho}/{item_id}", json=dados)

    def remover(self, caminho: str, item_id: str) -> None:
        self._pedir("DELETE", f"{caminho}/{item_id}")

    def identidade(self) -> str:
        dados = self._pedir("GET", "/system/identity")
        return (dados or {}).get("name", "MikroTik")
