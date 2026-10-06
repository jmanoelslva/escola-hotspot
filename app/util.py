"""Validações e conversões usadas pelas rotas."""

import re
import secrets

_MAC = re.compile(r"^[0-9A-Fa-f]{12}$")
_NOME_USUARIO = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
_TEMPO = re.compile(r"^(\d+w)?(\d+d)?(\d+h)?(\d+m)?(\d+s)?$")
_IPV4 = re.compile(r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$")


class ErroDados(ValueError):
    """Dado digitado inválido; a mensagem vai para a tela."""


# Sem letras e números que se confundem no papel (0/O, 1/l/I).
_ALFABETO_SENHA = "abcdefghjkmnpqrstuvwxyz23456789"


def normalizar_mac(valor: str) -> str:
    """Aceita AA:BB:CC:DD:EE:FF, AA-BB-..., AABB.CCDD.EEFF ou AABBCCDDEEFF."""
    limpo = re.sub(r"[\s:.\-]", "", valor or "")
    if not _MAC.match(limpo):
        raise ErroDados("Endereço MAC inválido. Use o formato AA:BB:CC:DD:EE:FF.")
    limpo = limpo.upper()
    return ":".join(limpo[i:i + 2] for i in range(0, 12, 2))


def validar_usuario(nome: str) -> str:
    nome = (nome or "").strip()
    if not _NOME_USUARIO.match(nome):
        raise ErroDados("Usuário inválido: use letras sem acento, números, ponto, hífen, @ ou _ (até 64).")
    return nome


def validar_senha(senha: str) -> str:
    senha = senha or ""
    if not senha.strip():
        raise ErroDados("Informe a senha.")
    if len(senha) > 64 or any(c in senha for c in "\"\\\n\r\t"):
        raise ErroDados("Senha inválida (até 64 caracteres, sem aspas ou barra invertida).")
    return senha


def validar_tempo(valor: str) -> str:
    """Limite de tempo no formato do RouterOS: 1h, 30m, 1d12h, 2w..."""
    valor = (valor or "").strip().lower().replace(" ", "")
    if valor in ("", "0", "0s"):
        return ""
    if not _TEMPO.match(valor):
        raise ErroDados("Tempo inválido. Exemplos: 30m, 2h, 1d, 1d12h.")
    return valor


def validar_ip(valor: str) -> str:
    valor = (valor or "").strip()
    if valor and not _IPV4.match(valor):
        raise ErroDados("Endereço IP inválido.")
    return valor


def gerar_senha(tamanho: int = 6) -> str:
    return "".join(secrets.choice(_ALFABETO_SENHA) for _ in range(tamanho))


def sim(valor: object) -> bool:
    """A REST API devolve booleanos como texto ("true"/"false")."""
    return str(valor).lower() in ("true", "yes", "1")


def inteiro(valor: object) -> int:
    try:
        return int(str(valor))
    except (TypeError, ValueError):
        return 0
