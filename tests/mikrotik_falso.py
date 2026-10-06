"""MikroTik de mentira para os testes: imita a REST API em memória."""

import base64
import json
import re

import httpx

USUARIO = "admin"
SENHA = "segredo"
AUTORIZACAO = "Basic " + base64.b64encode(f"{USUARIO}:{SENHA}".encode()).decode()


class MikrotikFalso:
    def __init__(self):
        self.proximo = 1
        self.tabelas: dict[str, list[dict]] = {
            "/ip/hotspot/user": [],
            "/ip/hotspot/user/profile": [{".id": "*0", "name": "default"}, {".id": "*1", "name": "alunos"}],
            "/ip/hotspot/active": [],
            "/ip/hotspot/ip-binding": [],
            "/ip/hotspot/host": [],
            "/ip/hotspot": [{".id": "*1", "name": "hotspot1"}],
            "/ip/dhcp-server/lease": [],
            "/ip/hotspot/profile": [
                {".id": "*1", "name": "hsprof1", "html-directory": "hotspot", "dns-name": "wifi.pmapg.internal", "hotspot-address": "192.168.130.1"},
                {".id": "*2", "name": "default", "html-directory": "hotspot", "dns-name": "", "hotspot-address": "0.0.0.0", "default": "true"},
            ],
            "/ip/firewall/filter": [],
            "/ip/dns/static": [],
            "/file": [],
            "/ip/hotspot/cookie": [],
            "/ip/firewall/nat": [],
            "/system/scheduler": [],
            "/interface": [
                {".id": "*1", "name": "ether1", "type": "ether", "running": "true", "disabled": "false", "comment": "internet"},
                {".id": "*2", "name": "bridge-hotspot", "type": "bridge", "running": "true", "disabled": "false"},
                {".id": "*3", "name": "ether5", "type": "ether", "running": "false", "disabled": "false"},
                {".id": "*4", "name": "lo", "type": "loopback", "running": "true", "disabled": "false"},
            ],
            "/ip/route": [{".id": "*1", "dst-address": "0.0.0.0/0", "gateway": "192.168.0.1",
                           "immediate-gw": "192.168.0.1%ether1", "active": "true", "disabled": "false"}],
        }
        self.tabelas["/ip/hotspot"][0]["profile"] = "hsprof1"
        self.tabelas["/ip/hotspot"][0]["interface"] = "bridge-hotspot"
        self.adicionar("/ip/hotspot/user", {"name": "default-trial", "default": "true"})
        self.pedidos: list[tuple[str, str, dict | None]] = []
        self.https = True  # False imita o www-ssl desligado
        self.aceita_nxdomain = True  # False imita RouterOS sem DNS type=NXDOMAIN
        self.objetos = {
            "/system/resource": {"board-name": "hEX", "version": "7.15.3 (stable)", "cpu-load": "7",
                                 "total-memory": "268435456", "free-memory": "201326592", "uptime": "3d4h5m"},
            "/system/health": [{".id": "*1", "name": "voltage", "value": "24.1", "type": "V"},
                               {".id": "*2", "name": "temperature", "value": "41", "type": "C"}],
            "/system/package/update": {"channel": "stable", "installed-version": "7.15.3"},
            "/system/routerboard": {"current-firmware": "7.15.3", "upgrade-firmware": "7.15.3"},
            "/ip/dns": {"servers": "8.8.8.8", "allow-remote-requests": "true"},
        }
        self.versao_disponivel = "7.16.1"
        self.verificacoes = 0
        self.trafego_aleatorio = False
        self.aceita_data_iso = True  # False imita RouterOS antigo (data mmm/dd/aaaa)
        self.baixar = None  # função(url) -> bytes, usada pelo /tool/fetch nos testes

    def adicionar(self, tabela: str, dados: dict) -> dict:
        item = {".id": f"*{self.proximo:X}", **dados}
        self.proximo += 1
        self.tabelas[tabela].append(item)
        return item

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._responder)

    def _erro(self, status: int, detalhe: str) -> httpx.Response:
        return httpx.Response(status, json={"error": status, "message": "Bad Request", "detail": detalhe})

    def _responder(self, pedido: httpx.Request) -> httpx.Response:
        if pedido.url.scheme == "https" and not self.https:
            raise httpx.ConnectError("conexão recusada", request=pedido)
        if pedido.headers.get("authorization") != AUTORIZACAO:
            return httpx.Response(401, json={"error": 401, "message": "Unauthorized"})
        caminho = pedido.url.path.removeprefix("/rest")
        corpo = json.loads(pedido.content) if pedido.content else None
        self.pedidos.append((pedido.method, caminho, corpo))

        if caminho == "/system/identity":
            return httpx.Response(200, json={"name": "hEX-escola"})

        if pedido.method == "GET" and caminho in self.objetos:
            return httpx.Response(200, json=self.objetos[caminho])
        if pedido.method == "POST" and caminho == "/system/package/update/check-for-updates":
            self.verificacoes += 1
            estado = self.objetos["/system/package/update"]
            estado["latest-version"] = self.versao_disponivel
            estado["status"] = "New version is available" if self.versao_disponivel != estado["installed-version"] else "System is already up to date"
            return httpx.Response(200, json=[{"status": estado["status"]}])
        if pedido.method == "POST" and caminho == "/tool/fetch":
            try:
                conteudo = self.baixar(corpo["url"])
            except Exception as erro:  # noqa: BLE001 - imita "failure: ..." do RouterOS
                return self._erro(400, f"failure: {erro}")
            destino = corpo["dst-path"]
            existente = next((a for a in self.tabelas["/file"] if a["name"] == destino), None)
            dados = {"name": destino, "type": "file", "size": str(len(conteudo))}
            if existente:
                existente.update(dados)
            else:
                self.adicionar("/file", dados)
            return httpx.Response(200, json=[{"status": "finished", "downloaded": str(len(conteudo))}])
        if pedido.method == "POST" and caminho == "/interface/monitor-traffic":
            nomes = (corpo or {}).get("interface", "").split(",")
            if self.trafego_aleatorio:  # só para a demonstração visual
                import random
                return httpx.Response(200, json=[{"name": n, "rx-bits-per-second": str(random.randint(5, 60) * 1_000_000),
                                                  "tx-bits-per-second": str(random.randint(1, 12) * 1_000_000)} for n in nomes])
            return httpx.Response(200, json=[{"name": n, "rx-bits-per-second": str(10_000_000 * (i + 1)),
                                              "tx-bits-per-second": str(1_000_000 * (i + 1))} for i, n in enumerate(nomes)])
        if pedido.method == "POST" and caminho.endswith("/reset-counters"):
            tabela = caminho.removesuffix("/reset-counters")
            ids = set((corpo or {}).get("numbers", "").split(","))
            for item in self.tabelas[tabela]:
                if item[".id"] in ids:
                    item.update({"bytes-in": "0", "bytes-out": "0", "uptime": "0s"})
            return httpx.Response(200, json=[])

        m = re.match(r"^(.*)/(\*[0-9A-F]+)$", caminho)
        tabela, item_id = (m.group(1), m.group(2)) if m else (caminho, None)
        if tabela not in self.tabelas:
            return self._erro(400, "no such command prefix")
        itens = self.tabelas[tabela]

        if item_id is None:
            if pedido.method == "GET":
                filtros = dict(pedido.url.params)
                return httpx.Response(200, json=[i for i in itens if all(i.get(k) == v for k, v in filtros.items())])
            if pedido.method == "PUT":
                corpo = dict(corpo)
                antes = corpo.pop("place-before", None)
                if tabela == "/ip/dns/static" and corpo.get("type") == "NXDOMAIN" and not self.aceita_nxdomain:
                    return self._erro(400, "input does not match any value of type")
                if tabela == "/system/scheduler" and "-" in corpo.get("start-date", "/") and not self.aceita_data_iso:
                    return self._erro(400, "invalid value for argument start-date")
                if tabela == "/file" and any(i["name"] == corpo["name"] for i in itens):
                    return self._erro(400, "failure: file already exists")
                if antes:
                    novo = self.adicionar(tabela, {"disabled": "false", **corpo})
                    itens.remove(novo)
                    posicao = next(i for i, x in enumerate(itens) if x[".id"] == antes)
                    itens.insert(posicao, novo)
                    return httpx.Response(201, json=novo)
                if tabela == "/ip/hotspot/user" and any(i["name"] == corpo["name"] for i in itens):
                    return self._erro(400, "failure: already have user with this name")
                if tabela == "/ip/hotspot/user" and corpo.get("profile", "default") not in {p["name"] for p in self.tabelas["/ip/hotspot/user/profile"]}:
                    return self._erro(400, "input does not match any value of profile")
                return httpx.Response(201, json=self.adicionar(tabela, {"disabled": "false", **corpo}))
            return self._erro(400, "unsupported")

        item = next((i for i in itens if i[".id"] == item_id), None)
        if item is None:
            return self._erro(404, "no such item")
        if pedido.method == "GET":
            return httpx.Response(200, json=item)
        if pedido.method == "PATCH":
            item.update(corpo)
            return httpx.Response(200, json=item)
        if pedido.method == "DELETE":
            itens.remove(item)
            return httpx.Response(204)
        return self._erro(400, "unsupported")
