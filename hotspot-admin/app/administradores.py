"""Usuários do próprio MikroTik (/user): quem entra no painel e no Winbox.

Dois grupos oferecidos: "full" (tudo no roteador) e "painel" (só o que o painel
usa: ler, alterar, REST API, ver senhas e rodar scripts; sem Winbox, SSH,
reboot nem criar administradores). O "painel" é criado sozinho na primeira vez.
Proteções: ninguém exclui, desativa ou rebaixa a si mesmo, e o último usuário
"full" ativo não pode sair.
"""

from . import util
from .mikrotik import ErroAutenticacao, ErroMikrotik, Mikrotik

USUARIOS = "/user"
GRUPOS = "/user/group"
GRUPO_PAINEL = "painel"
GRUPO_FULL = "full"
SENHA_MIN = 8
# Do mais novo para o mais antigo: RouterOS 7 recente tem "rest-api"; antes, a REST usava "api" e "web".
_POLITICAS_PAINEL = ("read,write,test,sensitive,api,rest-api", "read,write,test,sensitive,api,web")


def para_json(item: dict) -> dict:
    return {
        "id": item.get(".id"),
        "nome": item.get("name", ""),
        "grupo": item.get("group", ""),
        "comentario": item.get("comment", ""),
        "ultimo_acesso": item.get("last-logged-in", ""),
        "desativado": util.sim(item.get("disabled")),
    }


def listar(mk: Mikrotik) -> list[dict]:
    return sorted((para_json(u) for u in mk.listar(USUARIOS)), key=lambda u: u["nome"].lower())


def grupos(mk: Mikrotik) -> list[str]:
    nomes = {g.get("name", "") for g in mk.listar(GRUPOS)}
    nomes.add(GRUPO_PAINEL)  # criado na hora, se faltar
    return sorted(nomes, key=lambda n: (n not in (GRUPO_PAINEL, GRUPO_FULL), n != GRUPO_PAINEL, n))


def _garantir_grupo_painel(mk: Mikrotik) -> None:
    if any(g.get("name") == GRUPO_PAINEL for g in mk.listar(GRUPOS)):
        return
    erro_final: ErroMikrotik | None = None
    for politica in _POLITICAS_PAINEL:
        try:
            mk.criar(GRUPOS, {"name": GRUPO_PAINEL, "policy": politica,
                              "comment": "Painel do Hotspot: usa o painel, sem Winbox nem reboot"})
            return
        except ErroAutenticacao:
            raise
        except ErroMikrotik as erro:
            erro_final = erro
    raise erro_final or ErroMikrotik("Não foi possível criar o grupo painel.")


def _validar_grupo(mk: Mikrotik, grupo: str) -> str:
    grupo = (grupo or GRUPO_PAINEL).strip()
    if grupo == GRUPO_PAINEL:
        _garantir_grupo_painel(mk)
    elif grupo not in {g.get("name") for g in mk.listar(GRUPOS)}:
        raise util.ErroDados("Grupo inexistente no MikroTik.")
    return grupo


def _validar_senha(senha: str) -> str:
    senha = util.validar_senha(senha)
    if len(senha) < SENHA_MIN:
        raise util.ErroDados(f"A senha de administrador precisa de pelo menos {SENHA_MIN} caracteres.")
    return senha


def _fulls_ativos(mk: Mikrotik) -> list[dict]:
    return [u for u in mk.listar(USUARIOS) if u.get("group") == GRUPO_FULL and not util.sim(u.get("disabled"))]


def criar(mk: Mikrotik, nome: str, senha: str, grupo: str, comentario: str) -> dict:
    nome = util.validar_usuario(nome)
    if any(u.get("name") == nome for u in mk.listar(USUARIOS)):
        raise util.ErroDados("Já existe um usuário do MikroTik com esse nome.")
    corpo = {"name": nome, "password": _validar_senha(senha), "group": _validar_grupo(mk, grupo),
             "comment": " ".join((comentario or "").split())[:100]}
    mk.criar(USUARIOS, corpo)
    return next(u for u in listar(mk) if u["nome"] == nome)


def alterar(mk: Mikrotik, item_id: str, eu: str, senha: str | None, grupo: str | None,
            comentario: str | None, desativado: bool | None) -> tuple[dict, list[str]]:
    atual = mk.obter(USUARIOS, item_id)
    nome = atual.get("name", "")
    corpo: dict[str, str] = {}
    if senha:
        corpo["password"] = _validar_senha(senha)
    if grupo is not None and grupo != atual.get("group"):
        corpo["group"] = _validar_grupo(mk, grupo)
    if comentario is not None:
        corpo["comment"] = " ".join(comentario.split())[:100]
    if desativado is not None and desativado != util.sim(atual.get("disabled")):
        corpo["disabled"] = "true" if desativado else "false"
    if not corpo:
        raise util.ErroDados("Nada para alterar.")

    perde_acesso = corpo.get("disabled") == "true" or ("group" in corpo and atual.get("group") == GRUPO_FULL)
    if perde_acesso and nome == eu:
        raise util.ErroDados("Você não pode desativar nem tirar do grupo full o seu próprio usuário.")
    if perde_acesso and atual.get("group") == GRUPO_FULL and len(_fulls_ativos(mk)) <= 1:
        raise util.ErroDados("Este é o último administrador full ativo. Cadastre outro antes.")
    mk.alterar(USUARIOS, item_id, corpo)
    campos = ["senha" if c == "password" else {"group": "grupo", "comment": "comentário", "disabled": "situação"}[c] for c in corpo]
    return next(u for u in listar(mk) if u["id"] == item_id), campos


def eh_full(mk: Mikrotik, nome: str) -> bool:
    return any(u.get("name") == nome and u.get("group") == GRUPO_FULL for u in mk.listar(USUARIOS))


def excluir(mk: Mikrotik, item_id: str, eu: str) -> str:
    if not eh_full(mk, eu):
        raise util.ErroDados("Só administradores do grupo full podem excluir administradores.")
    atual = mk.obter(USUARIOS, item_id)
    nome = atual.get("name", "")
    if nome == eu:
        raise util.ErroDados("Você não pode excluir o seu próprio usuário.")
    if atual.get("group") == GRUPO_FULL and not util.sim(atual.get("disabled")) and len(_fulls_ativos(mk)) <= 1:
        raise util.ErroDados("Este é o último administrador full ativo. Cadastre outro antes.")
    mk.remover(USUARIOS, item_id)
    return nome
