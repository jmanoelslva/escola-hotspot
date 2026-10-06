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
            "/ip/hotspot/profile": [{".id": "*1", "name": "hsprof1", "html-directory": "hotspot"}],
            "/ip/firewall/filter": [],
            "/ip/dns/static": [],
            "/file": [],
        }
        self.tabelas["/ip/hotspot"][0]["profile"] = "hsprof1"
        self.adicionar("/ip/hotspot/user", {"name": "default-trial", "default": "true"})
        self.pedidos: list[tuple[str, str, dict | None]] = []
        self.https = True  # False imita o www-ssl desligado
        self.aceita_nxdomain = True  # False imita RouterOS sem DNS type=NXDOMAIN

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
