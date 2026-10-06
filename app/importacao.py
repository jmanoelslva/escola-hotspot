"""Leitura da planilha de cadastro em lote (CSV ou Excel .xlsx).

Colunas reconhecidas pelo cabeçalho (maiúsculas, acentos e espaços não importam):
  usuario (ou login, user)   obrigatória
  senha (ou password)        vazia = gera uma senha
  nome (ou aluno, comentario)
  turma (ou serie, classe)
  perfil (ou profile)        vazio = perfil escolhido na tela
"""

import csv
import io
import unicodedata
from dataclasses import asdict, dataclass

from . import util

MAX_LINHAS = 2000

_COLUNAS = {
    "usuario": ("usuario", "login", "user", "username", "matricula"),
    "senha": ("senha", "password", "pass"),
    "nome": ("nome", "aluno", "nomecompleto", "comentario", "comment", "descricao"),
    "turma": ("turma", "serie", "classe", "sala"),
    "perfil": ("perfil", "profile", "plano"),
}


@dataclass
class LinhaImportacao:
    linha: int
    usuario: str
    senha: str
    nome: str
    turma: str
    perfil: str
    senha_gerada: bool = False
    erro: str = ""

    @property
    def comentario(self) -> str:
        return " - ".join(p for p in (self.nome, self.turma) if p)

    def para_dict(self) -> dict:
        dados = asdict(self)
        dados["comentario"] = self.comentario
        return dados


def _chave(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def _ler_csv(conteudo: bytes) -> list[list[str]]:
    texto = ""
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    primeira = texto.splitlines()[0] if texto else ""
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    return [linha for linha in csv.reader(io.StringIO(texto), delimiter=separador)]


def _ler_xlsx(conteudo: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as erro:  # arquivo corrompido ou não é xlsx
        raise util.ErroDados("Não foi possível ler a planilha Excel.") from erro
    folha = livro.worksheets[0]
    linhas = []
    for linha in folha.iter_rows(values_only=True):
        linhas.append(["" if v is None else _texto_celula(v) for v in linha])
    livro.close()
    return linhas


def _texto_celula(valor: object) -> str:
    # Matrícula/senha numérica vem como float do Excel (123.0).
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def ler_planilha(nome_arquivo: str, conteudo: bytes) -> list[LinhaImportacao]:
    nome = (nome_arquivo or "").lower()
    if nome.endswith(".xlsx"):
        linhas = _ler_xlsx(conteudo)
    elif nome.endswith(".csv") or nome.endswith(".txt"):
        linhas = _ler_csv(conteudo)
    else:
        raise util.ErroDados("Envie um arquivo .csv ou .xlsx.")

    linhas = [l for l in linhas if any(str(c).strip() for c in l)]
    if not linhas:
        raise util.ErroDados("A planilha está vazia.")

    cabecalho = [_chave(c) for c in linhas[0]]
    posicoes: dict[str, int] = {}
    for campo, nomes in _COLUNAS.items():
        for i, coluna in enumerate(cabecalho):
            if coluna in nomes:
                posicoes[campo] = i
                break
    if "usuario" not in posicoes:
        raise util.ErroDados("A primeira linha precisa ter os títulos das colunas, com pelo menos \"usuario\".")
    if len(linhas) - 1 > MAX_LINHAS:
        raise util.ErroDados(f"A planilha tem mais de {MAX_LINHAS} linhas; divida em arquivos menores.")

    def celula(dados: list[str], campo: str) -> str:
        i = posicoes.get(campo)
        return str(dados[i]).strip() if i is not None and i < len(dados) else ""

    resultado = []
    for numero, dados in enumerate(linhas[1:], start=2):
        item = LinhaImportacao(
            linha=numero,
            usuario=celula(dados, "usuario"),
            senha=celula(dados, "senha"),
            nome=celula(dados, "nome"),
            turma=celula(dados, "turma"),
            perfil=celula(dados, "perfil"),
        )
        resultado.append(item)
    return resultado


def conferir(linhas: list[LinhaImportacao], existentes: set[str], perfis: set[str]) -> None:
    """Marca erros e gera senhas que faltam (altera as linhas)."""
    vistos: set[str] = set()
    existentes_min = {e.lower() for e in existentes}
    for item in linhas:
        try:
            item.usuario = util.validar_usuario(item.usuario)
        except util.ErroDados as erro:
            item.erro = str(erro)
            continue
        if item.usuario.lower() in existentes_min:
            item.erro = "Já existe no MikroTik."
            continue
        if item.usuario.lower() in vistos:
            item.erro = "Repetido na planilha."
            continue
        vistos.add(item.usuario.lower())
        if not item.senha:
            item.senha = util.gerar_senha()
            item.senha_gerada = True
        try:
            util.validar_senha(item.senha)
        except util.ErroDados as erro:
            item.erro = str(erro)
            continue
        if item.perfil and item.perfil not in perfis:
            item.erro = f"Perfil \"{item.perfil}\" não existe no MikroTik."
