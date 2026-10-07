"""Todos os aparelhos na rede: hotspot (com ou sem login) e DHCP de todas as redes."""


def test_todos_os_aparelhos(logado, mk):
    lease = lambda mac, ip, nome, servidor, status="bound": mk.adicionar(  # noqa: E731
        "/ip/dhcp-server/lease", {"mac-address": mac, "address": ip, "host-name": nome, "server": servidor, "status": status})
    lease("aa:00:00:00:00:01", "10.0.1.10", "Galaxy-Ana", "ADMINISTRATIVO")
    lease("AA:00:00:00:00:02", "10.0.1.11", "iPhone-X", "ADMINISTRATIVO")
    lease("AA:00:00:00:00:03", "10.0.1.12", "SamsungTV", "ADMINISTRATIVO")
    lease("AA:00:00:00:00:04", "10.0.1.13", "Celular-Perdido", "ADMINISTRATIVO")
    lease("AA:00:00:00:00:05", "10.1.0.20", "Moto-G", "ALUNOS")
    lease("AA:00:00:00:00:06", "10.1.0.21", "Antigo", "ALUNOS", status="waiting")  # não está conectado
    host = lambda mac, ip, **campos: mk.adicionar("/ip/hotspot/host", {  # noqa: E731
        "mac-address": mac, "address": ip, "server": "hotspot-adm", "authorized": "false", "bypassed": "false", **campos})
    host("AA:00:00:00:00:01", "10.0.1.10", authorized="true")
    host("AA:00:00:00:00:02", "10.0.1.11")
    host("AA:00:00:00:00:03", "10.0.1.12", bypassed="true")
    host("AA:00:00:00:00:04", "10.0.1.13")
    mk.adicionar("/ip/hotspot/active", {"user": "ana", "mac-address": "AA:00:00:00:00:01", "address": "10.0.1.10"})
    mk.adicionar("/ip/hotspot/ip-binding", {"type": "blocked", "mac-address": "AA:00:00:00:00:04", "disabled": "false"})

    r = logado.get("/api/rede").json()
    por_mac = {a["mac"]: a for a in r["aparelhos"]}
    assert set(por_mac) == {f"AA:00:00:00:00:0{i}" for i in range(1, 6)}
    assert por_mac["AA:00:00:00:00:01"]["situacao"] == "logado" and por_mac["AA:00:00:00:00:01"]["usuario"] == "ana"
    assert por_mac["AA:00:00:00:00:02"]["situacao"] == "sem_login" and por_mac["AA:00:00:00:00:02"]["nome"] == "iPhone-X"
    assert por_mac["AA:00:00:00:00:03"]["situacao"] == "liberado"
    assert por_mac["AA:00:00:00:00:04"]["situacao"] == "bloqueado"
    assert por_mac["AA:00:00:00:00:05"] == {"mac": "AA:00:00:00:00:05", "ip": "10.1.0.20", "nome": "Moto-G", "rede": "ALUNOS",
                                            "usuario": "", "situacao": "sem_hotspot", "uptime": ""}
    assert r["resumo"] == {"bloqueado": 1, "sem_login": 1, "logado": 1, "liberado": 1, "sem_hotspot": 1}
    assert r["redes"] == ["ALUNOS", "hotspot-adm"]
    assert r["aparelhos"][0]["situacao"] == "bloqueado"  # o que pede atenção vem primeiro


def test_sem_hotspot_nem_dhcp(logado, mk):
    assert logado.get("/api/rede").json() == {"aparelhos": [], "resumo": {"bloqueado": 0, "sem_login": 0, "logado": 0,
                                                                         "liberado": 0, "sem_hotspot": 0}, "redes": []}
