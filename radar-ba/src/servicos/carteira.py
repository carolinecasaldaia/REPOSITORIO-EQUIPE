"""Importação e guarda da carteira de clientes (item 15).

Aceita CSV e XLSX. Valida o CPF antes de aceitar, remove duplicidade pelo hash
do CPF e nunca grava o número em texto puro: em disco vão apenas o hash
determinístico (para comparar) e o CPF cifrado (para quando for mesmo preciso).

Na FASE 2 a carteira mora num JSON em ~/.radar-ba/dados/. O banco de dados
relacional é a FASE 3 — o formato aqui já espelha a tabela `clients`.
"""
import csv
import json
import os
from pathlib import Path

from src.config import ajustes
from src.seguranca import documento as sdoc
from src.util.log import obter

log = obter("carteira")

ARQUIVO = ajustes.PASTA_DADOS / "clientes.json"
COLUNAS = {
    "nome": ("nome", "cliente", "nome completo", "nome do cliente"),
    "cpf": ("cpf", "cnpj", "documento", "cpf/cnpj"),
    "telefone": ("telefone", "celular", "fone", "whatsapp"),
    "banco": ("banco", "instituicao", "instituição", "credor", "financeira"),
    "data_contratacao": ("data de contratacao", "data de contratação",
                         "data contratacao", "contratacao", "data do contrato"),
}


def _achar_coluna(cabecalho, alvo):
    normal = [c.strip().lower() for c in cabecalho]
    for apelido in COLUNAS[alvo]:
        if apelido in normal:
            return normal.index(apelido)
    return None


def _ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        amostra = f.read(4096)
        f.seek(0)
        try:
            dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
        except csv.Error:
            dialeto = csv.excel
        return [linha for linha in csv.reader(f, dialeto) if any(c.strip() for c in linha)]


def _ler_xlsx(caminho):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("para ler .xlsx é preciso o pacote openpyxl")
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    aba = wb[wb.sheetnames[0]]
    linhas = []
    for linha in aba.iter_rows(values_only=True):
        valores = ["" if c is None else str(c) for c in linha]
        if any(v.strip() for v in valores):
            linhas.append(valores)
    return linhas


def importar(caminho):
    """Lê o arquivo e devolve (clientes_novos, problemas)."""
    caminho = Path(caminho)
    linhas = _ler_xlsx(caminho) if caminho.suffix.lower() in (".xlsx", ".xlsm") else _ler_csv(caminho)
    if not linhas:
        return [], ["arquivo vazio"]

    cabecalho = linhas[0]
    idx = {k: _achar_coluna(cabecalho, k) for k in COLUNAS}
    if idx["nome"] is None or idx["cpf"] is None:
        return [], ["o arquivo precisa ter ao menos as colunas 'nome' e 'cpf' "
                    "(encontradas: %s)" % ", ".join(cabecalho)]

    existentes = {c["cpf_hash"] for c in carregar()}
    vistos = set()
    novos, problemas = [], []
    for n, linha in enumerate(linhas[1:], start=2):
        def campo(chave):
            i = idx[chave]
            return (linha[i].strip() if i is not None and i < len(linha) else "")

        nome, bruto = campo("nome"), campo("cpf")
        if not nome:
            problemas.append("linha %d: sem nome" % n)
            continue
        if not sdoc.validar(bruto):
            problemas.append("linha %d: documento inválido (%s)" % (n, sdoc.mascarar(bruto)))
            continue
        h = sdoc.hash_deterministico(bruto)
        if h in existentes or h in vistos:
            problemas.append("linha %d: duplicado (%s)" % (n, sdoc.mascarar(bruto)))
            continue
        vistos.add(h)
        novos.append({
            "id": h[:16],
            "nome": " ".join(nome.split()),
            "cpf_hash": h,
            "cpf_cifrado": sdoc.cifrar(bruto),
            # só os 2 últimos dígitos — o suficiente para conferir no alerta
            "cpf_mascara": sdoc.mascarar(bruto),
            "tipo_documento": sdoc.tipo(bruto),
            "telefone": campo("telefone"),
            "banco": campo("banco"),
            "data_contratacao": campo("data_contratacao"),
            "monitoramento_ativo": True,
        })
    return novos, problemas


def carregar():
    if not ARQUIVO.exists():
        return []
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except ValueError:
        log.error("clientes.json ilegível — tratando como carteira vazia")
        return []


def gravar(clientes):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(clientes, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(ARQUIVO))
    try:
        os.chmod(str(ARQUIVO), 0o600)
    except OSError:
        pass


def acrescentar(novos):
    atual = carregar()
    atual.extend(novos)
    gravar(atual)
    return len(atual)


def ativos():
    return [c for c in carregar() if c.get("monitoramento_ativo")]
