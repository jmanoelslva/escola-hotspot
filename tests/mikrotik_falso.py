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
        }
        self.adicionar("/ip/hotspot/user", {"name": "default-trial", "default": "true"})
        self.pedidos: list[tuple[str, str, dict | None]] = []
        self.https = True  # False imita o www-ssl desligado

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

        m = re.match(r"^(.*)/(\*[0-9A-F]+)$", caminho)
        tabela, item_id = (m.group(1), m.group(2)) if m else (caminho, None)
        if tabela not in self.tabelas:
            return self._erro(400, "no such command prefix")
        itens = self.tabelas[tabela]

        if item_id is None:
            if pedido.method == "GET":
                return httpx.Response(200, json=itens)
            if pedido.method == "PUT":
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
