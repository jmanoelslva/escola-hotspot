"""Painel com MikroTik simulado e dados fictícios, só para as telas do manual."""
import os
import sys
import tempfile

os.environ["PORTA"] = "8770"
os.environ["PASTA_DADOS"] = tempfile.mkdtemp(prefix="manual-")
# Histórico de uso fictício (30 dias, a cada 5 minutos) e serviço do painel ativo.
import json, math, random
from datetime import datetime, timedelta
from pathlib import Path as _P
_dados = _P(os.environ["PASTA_DADOS"]); (_dados / "uso").mkdir(parents=True, exist_ok=True)
(_dados / "servico.json").write_text(json.dumps({"usuario": "admin", "senha": "segredo"}), encoding="utf-8")
random.seed(7)
_agora = datetime.now().replace(second=0, microsecond=0)
_t = _agora - timedelta(days=30)
_arquivos = {}
while _t < _agora:
    hora = _t.hour + _t.minute / 60
    util = _t.weekday() < 5
    aula = 7 <= hora <= 17
    fator = (0.9 if util else 0.25) * (1.0 if aula else 0.08) * (1.6 if (8.8 <= hora <= 9.2 or 12 <= hora <= 12.8) else 1)
    mbps = max(0.3, 60 * fator * random.uniform(0.6, 1.3))
    baixado = int(mbps * 1e6 / 8 * 300)
    sessoes = int((70 if util else 10) * (1 if aula else 0.1) * random.uniform(0.7, 1.2))
    aparelhos = sessoes + int((220 if (util and (8.8 <= hora <= 9.2 or 12 <= hora <= 12.8)) else 10) * random.uniform(0.7, 1))
    linha = f"{_t.isoformat()};300;{baixado};{int(baixado*0.12)};{sessoes};{aparelhos}" + chr(10)
    _arquivos.setdefault(f"{_t:%Y-%m}", []).append(linha)
    _t += timedelta(minutes=5)
for _mes, _linhas in _arquivos.items():
    (_dados / "uso" / f"{_mes}.csv").write_text("".join(_linhas), encoding="utf-8")
os.environ["MIKROTIK_URL"] = "192.168.88.1"
os.environ["NOME_ESCOLA"] = "Escola Estadual Professora Maria Aldineide Pessoa Gomes"
os.environ["CIDADE_ESCOLA"] = "Coité do Noia - AL"
sys.path[:0] = ["D:/ESCOLA/hotspot-admin", "D:/ESCOLA/hotspot-admin/tests"]

from mikrotik_falso import MikrotikFalso  # noqa: E402
from app.main import app  # noqa: E402
from app.mikrotik import EnderecoMikrotik  # noqa: E402
import uvicorn  # noqa: E402

mk = MikrotikFalso()
mk.versao_disponivel = "7.15.3"  # sem faixa de atualização nas telas
mk.trafego_aleatorio = True
mk.alunos_no_horario = True
mk.objetos["/system/clock"].update({"date": "2026-10-08", "time": "12:10:00"})

mk.tabelas["/ip/hotspot/user/profile"][1].update({"rate-limit": "2M/5M", "shared-users": "1"})
mk.adicionar("/ip/hotspot/user/profile", {"name": "professores", "rate-limit": "5M/20M", "shared-users": "2", "session-timeout": "8h"})

usuarios = [
    ("ana.lima", "Ana Lima - Matemática", "professores", "false", "5h12m", "50000000", "900000000"),
    ("carlos.melo", "Carlos Melo - Secretaria", "professores", "false", "3h", "8000000", "320000000"),
    ("joana.dir", "Joana Santos - Direção", "professores", "false", "1h", "2000000", "90000000"),
    ("maria.silva", "Maria da Silva - 9º A", "alunos", "false", "2h", "4000000", "210000000"),
    ("joao.souza", "João Souza - 9º A", "alunos", "false", "45m", "1000000", "80000000"),
    ("pedro.alves", "Pedro Alves - 1º B", "alunos", "false", "30m", "900000", "60000000"),
    ("luiza.costa", "Luiza Costa - 1º B", "alunos", "false", "0s", "0", "0"),
    ("rafael.lima", "Rafael Lima - 2º A", "alunos", "true", "0s", "0", "0"),
]
for nome, comentario, perfil, desativado, uptime, entrada, saida in usuarios:
    mk.adicionar("/ip/hotspot/user", {"name": nome, "password": "k7m2pq", "profile": perfil, "comment": comentario,
                                      "disabled": desativado, "uptime": uptime, "bytes-in": entrada, "bytes-out": saida})

ativos = [("ana.lima", "10.0.1.20", "A4:C3:F0:12:34:56", "1h12m", "Galaxy-A15"),
          ("carlos.melo", "10.0.1.31", "86:14:EA:6D:3C:3D", "40m", "Notebook-Secretaria"),
          ("maria.silva", "10.0.1.45", "3C:22:FB:9A:10:02", "15m", "iPhone-de-Maria")]
for usuario, ip, mac, uptime, nome in ativos:
    mk.adicionar("/ip/hotspot/active", {"user": usuario, "address": ip, "mac-address": mac, "uptime": uptime,
                                        "bytes-in": "40050000", "bytes-out": "537600000", "login-by": "http-chap"})
    mk.adicionar("/ip/hotspot/host", {"mac-address": mac, "address": ip, "server": "hotspot-adm",
                                      "authorized": "true", "bypassed": "false", "uptime": uptime})
    mk.adicionar("/ip/dhcp-server/lease", {"mac-address": mac, "address": ip, "host-name": nome,
                                           "server": "ADMINISTRATIVO", "status": "bound"})

mk.adicionar("/ip/hotspot/host", {"mac-address": "D2:11:4B:7E:20:AA", "address": "10.0.1.52", "server": "hotspot-adm",
                                  "authorized": "false", "bypassed": "false"})
mk.adicionar("/ip/dhcp-server/lease", {"mac-address": "D2:11:4B:7E:20:AA", "address": "10.0.1.52", "host-name": "Redmi-Note-12",
                                       "server": "ADMINISTRATIVO", "status": "bound"})
mk.adicionar("/ip/hotspot/host", {"mac-address": "AA:BB:CC:00:00:01", "address": "10.0.1.60", "server": "hotspot-adm",
                                  "authorized": "true", "bypassed": "true"})
mk.adicionar("/ip/dhcp-server/lease", {"mac-address": "AA:BB:CC:00:00:01", "address": "10.0.1.60", "host-name": "SamsungTV-Sala5",
                                       "server": "ADMINISTRATIVO", "status": "bound"})
for i, nome in enumerate(["Moto-G54", "Galaxy-A05", "iPhone-11", "Redmi-13C", "Galaxy-M14"], start=21):
    mk.adicionar("/ip/dhcp-server/lease", {"mac-address": f"5E:00:00:00:00:{i:02d}", "address": f"10.1.0.{i}",
                                           "host-name": nome, "server": "ALUNOS", "status": "bound"})

mk.adicionar("/ip/hotspot/ip-binding", {"type": "bypassed", "mac-address": "AA:BB:CC:00:00:01", "comment": "TV sala 5",
                                        "server": "all", "disabled": "false"})
mk.adicionar("/ip/hotspot/ip-binding", {"type": "bypassed", "mac-address": "AA:BB:CC:00:00:07", "comment": "Impressora secretaria",
                                        "server": "all", "disabled": "false"})
mk.adicionar("/ip/hotspot/ip-binding", {"type": "blocked", "mac-address": "DE:AD:BE:EF:00:01", "comment": "Celular perdido",
                                        "server": "all", "disabled": "false"})

for dominio, motivo in (("bet365.com", "apostas"), ("blaze.com", "apostas"), ("tiktok.com", "redes sociais")):
    mk.adicionar("/ip/dns/static", {"name": dominio, "type": "NXDOMAIN", "match-subdomain": "true",
                                    "comment": f"painel-bloqueio: {motivo}", "disabled": "false"})

mk.adicionar("/interface", {"name": "VLAN200-ADMINISTRATIVO-X", "type": "vlan", "running": "true", "disabled": "false"})
mk.tabelas["/interface"] = [i for i in mk.tabelas["/interface"] if i["name"] != "VLAN200-ADMINISTRATIVO-X"]
mk.adicionar("/interface", {"name": "VLAN300-ALUNOS", "type": "vlan", "running": "true", "disabled": "false"})
mk.adicionar("/user", {"name": "coordenacao", "group": "painel", "disabled": "false", "comment": "Coordenação pedagógica",
                       "last-logged-in": "2026-10-08 07:45:00"})
mk.adicionar("/user/group", {"name": "painel", "policy": "read,write,test,sensitive,api,rest-api"})

for _n, (_nome, _st) in enumerate([("AP1 – secretaria", "up"), ("AP2 – sala dos professores", "up"),
                                   ("AP3 – pátio", "down"), ("AP4 – biblioteca", "up"),
                                   ("AP5 – bloco B", "up"), ("AP6 – quadra", "up")], start=11):
    mk.adicionar("/tool/netwatch", {"host": f"172.16.1.{_n}", "type": "icmp", "interval": "30s", "status": _st,
                                    "since": "2026-10-08 11:52:00", "comment": f"painel-ap: {_nome}", "disabled": "false"})
app.state.transport = mk.transport()
app.state.endereco = EnderecoMikrotik("192.168.88.1", transport=app.state.transport)
uvicorn.run(app, host="127.0.0.1", port=8770, log_level="warning")
