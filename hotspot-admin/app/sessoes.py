"""Sessões do painel, só em memória: reiniciar o programa desloga todo mundo.

A senha do MikroTik fica na memória enquanto a sessão estiver aberta, porque
a REST API pede usuário e senha em toda requisição. Nada vai para o disco.
"""

import secrets
import threading
import time
from dataclasses import dataclass, field


@dataclass
class Sessao:
    usuario: str
    senha: str
    identidade: str
    ultimo_uso: float = field(default_factory=time.monotonic)


class Sessoes:
    def __init__(self, minutos_inatividade: int):
        self._limite = minutos_inatividade * 60
        self._sessoes: dict[str, Sessao] = {}
        self._trava = threading.Lock()

    def criar(self, usuario: str, senha: str, identidade: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._trava:
            self._limpar()
            self._sessoes[token] = Sessao(usuario, senha, identidade)
        return token

    def obter(self, token: str | None) -> Sessao | None:
        if not token:
            return None
        with self._trava:
            sessao = self._sessoes.get(token)
            if sessao is None:
                return None
            agora = time.monotonic()
            if agora - sessao.ultimo_uso > self._limite:
                del self._sessoes[token]
                return None
            sessao.ultimo_uso = agora
            return sessao

    def encerrar(self, token: str | None) -> None:
        if token:
            with self._trava:
                self._sessoes.pop(token, None)

    def _limpar(self) -> None:
        agora = time.monotonic()
        vencidas = [t for t, s in self._sessoes.items() if agora - s.ultimo_uso > self._limite]
        for token in vencidas:
            del self._sessoes[token]


class LimiteLogin:
    """Bloqueia por alguns minutos o IP que erra a senha muitas vezes seguidas."""

    def __init__(self, tentativas: int = 5, minutos: int = 15):
        self._tentativas = tentativas
        self._janela = minutos * 60
        self._erros: dict[str, list[float]] = {}
        self._trava = threading.Lock()

    def _recentes(self, ip: str) -> list[float]:
        agora = time.monotonic()
        lista = [t for t in self._erros.get(ip, []) if agora - t < self._janela]
        self._erros[ip] = lista
        return lista

    def bloqueado(self, ip: str) -> bool:
        with self._trava:
            return len(self._recentes(ip)) >= self._tentativas

    def errou(self, ip: str) -> None:
        with self._trava:
            self._recentes(ip).append(time.monotonic())

    def acertou(self, ip: str) -> None:
        with self._trava:
            self._erros.pop(ip, None)
