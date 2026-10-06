"""Controle de uso: perfis (velocidade, aparelhos, tempo), horário de acesso e sites bloqueados."""

import re
from dataclasses import dataclass

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

PERFIS = "/ip/hotspot/user/profile"
FILTROS = "/ip/firewall/filter"
NAT = "/ip/firewall/nat"
DNS = "/ip/dns"
DNS_ESTATICO = "/ip/dns/static"
SERVIDORES_HOTSPOT = "/ip/hotspot"
PREFIXO_FORCAR_DNS = "painel-forcar-dns"

PREFIXO_HORARIO = "painel-horario:"
PREFIXO_LISTA = "painel-"
PREFIXO_BLOQUEIO = "painel-bloqueio"

DIAS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_NOME_PERFIL = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_DOMINIO = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


# ------------------------------------------------------------------ perfis

def validar_nome_perfil(nome: str) -> str:
    nome = (nome or "").strip()
    if not _NOME_PERFIL.match(nome):
        raise util.ErroDados("Nome de perfil inválido: use letras sem acento, números, ponto, hífen ou _ (até 32).")
    return nome


def _mbps(valor: str) -> float:
    """'5M' / '512k' / '0' do RouterOS em Mbps."""
    texto = str(valor or "0").strip().lower()
    m = re.match(r"^(\d+(?:\.\d+)?)([kmg]?)$", texto)
    if not m:
        return 0
    numero = float(m.group(1))
    return {"k": numero / 1000, "m": numero, "g": numero * 1000, "": numero / 1_000_000}[m.group(2)]


def _taxa(mbps: float) -> str:
    if not mbps or mbps <= 0:
        return "0"
    if mbps < 1:
        return f"{round(mbps * 1000)}k"
    return f"{mbps:g}M"


def ler_velocidade(rate_limit: str) -> tuple[float, float]:
    """rate-limit 'rx/tx' do ponto de vista do roteador: rx = envio do aluno, tx = download."""
    if not rate_limit:
        return 0, 0
    primeiro = rate_limit.split()[0]
    partes = primeiro.split("/")
    envio = _mbps(partes[0])
    download = _mbps(partes[1]) if len(partes) > 1 else envio
    return round(download, 3), round(envio, 3)


def montar_velocidade(download: float, envio: float) -> str:
    if not download and not envio:
        return ""
    return f"{_taxa(envio)}/{_taxa(download)}"


def perfil_para_json(item: dict, horarios: dict[str, dict]) -> dict:
    download, envio = ler_velocidade(item.get("rate-limit", ""))
    aparelhos = item.get("shared-users", "1")
    sessao = item.get("session-timeout", "")
    return {
        "id": item.get(".id"),
        "nome": item.get("name", ""),
        "download_mbps": download,
        "envio_mbps": envio,
        "aparelhos": 0 if aparelhos == "unlimited" else util.inteiro(aparelhos),
        "tempo_sessao": "" if sessao in ("", "0s", "0") else sessao,
        "lista": item.get("address-list", ""),
        "padrao": util.sim(item.get("default")) or item.get("name") == "default",
        "horario": horarios.get(item.get("name", ""), {"ativo": False}),
    }


def montar_perfil(nome: str | None, download: float | None, envio: float | None,
                  aparelhos: int | None, tempo_sessao: str | None) -> dict:
    corpo: dict[str, str] = {}
    if nome is not None:
        corpo["name"] = validar_nome_perfil(nome)
    if download is not None or envio is not None:
        if (download or 0) < 0 or (envio or 0) < 0 or (download or 0) > 10000 or (envio or 0) > 10000:
            raise util.ErroDados("Velocidade inválida (0 a 10000 Mbps; 0 = sem limite).")
        corpo["rate-limit"] = montar_velocidade(download or 0, envio or 0)
    if aparelhos is not None:
        if aparelhos < 0 or aparelhos > 100:
            raise util.ErroDados("Aparelhos por usuário: de 1 a 100 (0 = sem limite).")
        corpo["shared-users"] = "unlimited" if aparelhos == 0 else str(aparelhos)
    if tempo_sessao is not None:
        corpo["session-timeout"] = util.validar_tempo(tempo_sessao) or "0s"
    return corpo


# ------------------------------------------------------------------ horário

@dataclass
class Horario:
    inicio: str
    fim: str
    dias: list[str]

    def texto(self) -> str:
        return f"{self.inicio}-{self.fim} {','.join(self.dias)}"


def validar_horario(inicio: str, fim: str, dias: list[str]) -> Horario:
    if not _HORA.match(inicio or "") or not _HORA.match(fim or ""):
        raise util.ErroDados("Horário inválido. Use HH:MM, ex.: 07:00.")
    if inicio >= fim:
        raise util.ErroDados("O horário de início precisa ser antes do fim.")
    dias_ok = [d for d in DIAS if d in set(dias or [])]
    if not dias_ok:
        raise util.ErroDados("Escolha pelo menos um dia da semana.")
    return Horario(inicio, fim, dias_ok)


def janelas_fechadas(h: Horario) -> list[str]:
    """Períodos sem internet (o firewall do RouterOS não nega horário, então
    o painel cria uma regra de bloqueio para cada período fora do permitido)."""
    janelas = []
    if h.inicio > "00:00":
        janelas.append(f"00:00:00-{h.inicio}:00,{','.join(h.dias)}")
    if h.fim < "23:59":
        janelas.append(f"{h.fim}:00-23:59:59,{','.join(h.dias)}")
    outros = [d for d in DIAS if d not in h.dias]
    if outros:
        janelas.append(f"00:00:00-23:59:59,{','.join(outros)}")
    return janelas


def nome_lista(perfil: str) -> str:
    return PREFIXO_LISTA + perfil


def ler_horarios(regras: list[dict]) -> dict[str, dict]:
    """Horários gravados no comentário das regras: 'painel-horario:alunos 07:00-17:30 mon,tue'."""
    horarios: dict[str, dict] = {}
    for regra in regras:
        comentario = regra.get("comment", "")
        if not comentario.startswith(PREFIXO_HORARIO):
            continue
        m = re.match(r"^painel-horario:(\S+) (\d\d:\d\d)-(\d\d:\d\d) ([a-z,]+)$", comentario)
        if m and m.group(1) not in horarios:
            horarios[m.group(1)] = {"ativo": True, "inicio": m.group(2), "fim": m.group(3),
                                    "dias": m.group(4).split(",")}
    return horarios


def aplicar_horario(mk: Mikrotik, perfil: dict, horario: Horario | None) -> None:
    nome = perfil["name"]
    regras = mk.listar(FILTROS)
    for regra in regras:
        if regra.get("comment", "").startswith(f"{PREFIXO_HORARIO}{nome} ") and not util.sim(regra.get("dynamic")):
            mk.remover(FILTROS, regra[".id"])
    if horario is None:
        return

    # Quem entra com este perfil vai para uma lista de endereços; se o perfil já
    # usa uma lista (configurada por alguém no Winbox), aproveita a mesma.
    lista = perfil.get("address-list") or nome_lista(nome)
    if perfil.get("address-list") != lista:
        mk.alterar(PERFIS, perfil[".id"], {"address-list": lista})

    # As regras vão antes das outras regras fixas da cadeia forward.
    primeira = next((r[".id"] for r in mk.listar(FILTROS)
                     if r.get("chain") == "forward" and not util.sim(r.get("dynamic"))), None)
    for janela in janelas_fechadas(horario):
        corpo = {
            "chain": "forward",
            "action": "drop",
            "src-address-list": lista,
            "time": janela,
            "comment": f"{PREFIXO_HORARIO}{nome} {horario.texto()}",
        }
        if primeira:
            corpo["place-before"] = primeira
        mk.criar(FILTROS, corpo)


# ------------------------------------------------------------------ sites bloqueados

def normalizar_dominio(valor: str) -> str:
    texto = (valor or "").strip().lower()
    texto = re.sub(r"^[a-z]+://", "", texto)
    texto = texto.split("/")[0].split("?")[0].split(":")[0].strip(".")
    if texto.startswith("www."):
        texto = texto[4:]
    if texto.startswith("*."):
        texto = texto[2:]
    if not _DOMINIO.match(texto):
        raise util.ErroDados("Endereço inválido. Exemplos: bet365.com, tiktok.com")
    return texto


def bloqueio_para_json(item: dict) -> dict:
    comentario = item.get("comment", "")
    motivo = comentario[len(PREFIXO_BLOQUEIO):].lstrip(": ").strip()
    return {
        "id": item.get(".id"),
        "dominio": item.get("name", ""),
        "motivo": motivo,
        "desativado": util.sim(item.get("disabled")),
    }


def criar_bloqueio(mk: Mikrotik, dominio: str, motivo: str) -> dict:
    comentario = PREFIXO_BLOQUEIO + (f": {motivo.strip()}" if motivo.strip() else "")
    tentativas = [
        # RouterOS 7 recente: responde "domínio não existe" para o site e subdomínios.
        {"name": dominio, "type": "NXDOMAIN", "match-subdomain": "true", "comment": comentario},
        # Versões sem NXDOMAIN: aponta para 0.0.0.0.
        {"name": dominio, "address": "0.0.0.0", "match-subdomain": "true", "comment": comentario},
    ]
    erro_final: ErroMikrotik | None = None
    for corpo in tentativas:
        try:
            return mk.criar(DNS_ESTATICO, corpo) or corpo
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            if "já" in erro.mensagem.lower():
                raise
            erro_final = erro
    raise erro_final or ErroMikrotik("Não foi possível bloquear o site.")


# ------------------------------------------------------------------ forçar o DNS do roteador

def interfaces_hotspot(mk: Mikrotik) -> list[str]:
    return sorted({s.get("interface", "") for s in mk.listar(SERVIDORES_HOTSPOT) if s.get("interface")})


def _regras_forcar_dns(mk: Mikrotik) -> list[dict]:
    return [r for r in mk.listar(NAT) if r.get("comment", "").startswith(PREFIXO_FORCAR_DNS)
            and not util.sim(r.get("dynamic"))]


def estado_forcar_dns(mk: Mikrotik) -> dict:
    regras = _regras_forcar_dns(mk)
    try:
        dns = mk.ler(DNS) or {}
        if isinstance(dns, list):
            dns = dns[0] if dns else {}
        remoto = util.sim(dns.get("allow-remote-requests"))
    except ErroAutenticacao:
        raise
    except ErroMikrotik:
        remoto = None
    return {
        "ativo": bool(regras) and all(not util.sim(r.get("disabled")) for r in regras),
        "regras": len(regras),
        "interfaces": interfaces_hotspot(mk),
        "dns_remoto": remoto,
    }


def aplicar_forcar_dns(mk: Mikrotik, ativo: bool) -> None:
    """Liga: cria (se faltar) e ativa as regras de redirecionamento da porta 53.
    Desliga: só desativa as regras, que ficam no roteador para reativar depois."""
    regras = _regras_forcar_dns(mk)
    if ativo:
        interfaces = interfaces_hotspot(mk)
        if not interfaces:
            raise util.ErroDados("Nenhum servidor de hotspot encontrado no MikroTik.")
        existentes = {(r.get("in-interface"), r.get("protocol")) for r in regras}
        for interface in interfaces:
            for protocolo in ("udp", "tcp"):
                if (interface, protocolo) in existentes:
                    continue
                mk.criar(NAT, {
                    "chain": "dstnat", "action": "redirect", "protocol": protocolo, "dst-port": "53",
                    "to-ports": "53", "in-interface": interface,
                    "comment": f"{PREFIXO_FORCAR_DNS} (Painel do Hotspot)",
                })
        regras = _regras_forcar_dns(mk)
    for regra in regras:
        desejado = "false" if ativo else "true"
        if regra.get("disabled", "false") != desejado:
            mk.alterar(NAT, regra[".id"], {"disabled": desejado})
