"""Importador da RODAGEM PROCESSUAL — a carteira real do escritório.

A planilha tem uma aba por estado, e cada aba começa com um bloco de resumo
antes da tabela. Duas dificuldades reais, tratadas aqui:

  CABEÇALHO EM LINHA VARIÁVEL. Fica na 9ª ou na 10ª linha, conforme a aba.
  Procuramos a linha que contém "NOME".

  CABEÇALHO DESALINHADO. Em MARANHÃO e AMAPÁ o cabeçalho não nomeia a coluna de
  CPF, mas os dados a têm — ler pelo rótulo pegaria o número do processo no
  lugar do CPF. Por isso a coluna de CPF é localizada por CONTEÚDO: procuramos
  a coluna cujos valores passam na validação de dígito verificador.

A coluna BUSCA é o gabarito do escritório ("1.0" = já tem busca e apreensão).
Guardamos esse valor para medir o acerto do radar.
"""
import re
import unicodedata

from src.seguranca import documento as sdoc
from src.util import cnj
from src.util.log import obter

log = obter("rodagem")

_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")

UF_POR_ABA = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE",
    "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def _norm(valor):
    # normaliza ANTES de maiusculizar: "Nº" decompõe para "No" minúsculo, e
    # maiusculizar depois é o que faz "Nº PROCESSO" virar "NO PROCESSO".
    t = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper().strip()


def _rotulo(valor):
    """Normaliza rótulo de cabeçalho: sem acento, sem 'º/°', espaços colapsados."""
    t = _norm(valor).replace("º", "").replace("°", "").replace(".", " ")
    return re.sub(r"\s+", " ", t).strip()


def localizar_cabecalho(linhas, max_busca=30):
    """Devolve (indice_da_linha, {campo: coluna}) ou (None, {})."""
    for i, linha in enumerate(linhas[:max_busca]):
        rotulos = [_rotulo(c) for c in linha]
        if "NOME" not in rotulos:
            continue
        mapa = {"nome": rotulos.index("NOME")}
        for campo, nomes in (
            ("cpf", ("CPF",)),
            ("processo", ("N PROCESSO", "NO PROCESSO", "NUMERO DA ACAO")),
            ("busca", ("BUSCA",)),
            ("revisional", ("REVISIONAL",)),
            ("processo_busca", ("N PROC BUSCA/ESPEC", "N PROC BUSCA ESPEC")),
            ("sistema", ("SISTEMA",)),
            ("situacao", ("SITUACAO",)),
        ):
            for n in nomes:
                if n in rotulos:
                    mapa[campo] = rotulos.index(n)
                    break
        return i, mapa
    return None, {}


def localizar_cpf_por_conteudo(linhas_dados, ignorar=()):
    """Acha a coluna do documento pelos próprios dados, quando o cabeçalho falha.

    Vence a coluna com mais valores que passam no dígito verificador — de CPF
    ou de CNPJ.
    """
    placar = {}
    for linha in linhas_dados[:200]:
        for j, valor in enumerate(linha):
            if j in ignorar:
                continue
            if sdoc.validar(valor):
                placar[j] = placar.get(j, 0) + 1
    if not placar:
        return None
    melhor = max(placar, key=placar.get)
    return melhor if placar[melhor] >= 1 else None


def _texto(valor):
    return "" if valor is None else str(valor).strip()


def _sim(valor):
    """A coluna BUSCA usa '1.0' para sim e 'NÃO' para não."""
    t = _norm(valor)
    if not t or t in ("NONE", "NAO", "N"):
        return False
    return t in ("1", "1.0", "SIM", "S") or t.startswith("1")


def importar_planilha(caminho, abas=None):
    """Lê a RODAGEM inteira. Devolve (clientes, problemas, resumo_por_aba)."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("para ler .xlsx é preciso o pacote openpyxl")

    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    por_cpf = {}
    problemas = []
    resumo = []

    for aba in wb.sheetnames:
        if abas and aba not in abas:
            continue
        ws = wb[aba]
        linhas = list(ws.iter_rows(values_only=True))
        i, mapa = localizar_cabecalho(linhas)
        if i is None:
            resumo.append({"aba": aba, "situacao": "sem cabeçalho reconhecido",
                           "linhas": 0, "aceitos": 0, "recusados": 0})
            continue

        dados = linhas[i + 1:]
        col_cpf = mapa.get("cpf")
        # O cabeçalho pode não nomear o CPF (MARANHÃO, AMAPÁ): confere pelo dado.
        detectada = localizar_cpf_por_conteudo(dados, ignorar={mapa["nome"]})
        if detectada is not None and detectada != col_cpf:
            if col_cpf is None:
                log.info("aba %s: coluna de CPF localizada por conteúdo", aba)
            else:
                log.warning("aba %s: cabeçalho aponta CPF na coluna %s, mas os "
                            "dados estão na %s — usando os dados", aba, col_cpf, detectada)
            col_cpf = detectada

        aceitos = recusados = 0
        uf = UF_POR_ABA.get(_norm(aba), "")
        for n, linha in enumerate(dados, start=i + 2):
            def campo(chave):
                j = mapa.get(chave)
                return _texto(linha[j]) if j is not None and j < len(linha) else ""

            nome = " ".join(campo("nome").split())
            if not nome:
                continue
            bruto = _texto(linha[col_cpf]) if col_cpf is not None and col_cpf < len(linha) else ""
            if not sdoc.validar(bruto):
                recusados += 1
                problemas.append("%s linha %d: documento ausente ou inválido (%s)"
                                 % (aba, n, sdoc.mascarar(bruto)))
                continue

            digitos = sdoc.normalizar(bruto)
            processo = campo("processo")
            registro = por_cpf.get(digitos)
            if registro is None:
                registro = {
                    "id": sdoc.hash_deterministico(digitos)[:16],
                    "nome": nome,
                    "cpf_hash": sdoc.hash_deterministico(digitos),
                    "cpf_cifrado": sdoc.cifrar(digitos),
                    "cpf_mascara": sdoc.mascarar(digitos),
                    "tipo_documento": sdoc.tipo(digitos),
                    "telefone": "",
                    "banco": "",
                    "ufs": [],
                    "processos": [],
                    "processos_busca": [],   # os de Busca e Apreensão, a acompanhar
                    "tem_busca_na_planilha": False,
                    "monitoramento_ativo": True,
                }
                por_cpf[digitos] = registro
            if uf and uf not in registro["ufs"]:
                registro["ufs"].append(uf)
            if processo and processo not in registro["processos"]:
                registro["processos"].append(processo)
            if _sim(campo("busca")):
                registro["tem_busca_na_planilha"] = True
                # o número da B&A pode estar em coluna própria ou ser o principal
                for candidato in (campo("processo_busca"), processo):
                    if candidato and cnj.ano(candidato):
                        if candidato not in registro["processos_busca"]:
                            registro["processos_busca"].append(candidato)
                        break
            aceitos += 1

        resumo.append({"aba": aba, "situacao": "ok", "linhas": len(dados),
                       "aceitos": aceitos, "recusados": recusados,
                       "cabecalho_linha": i + 1})
    wb.close()
    return list(por_cpf.values()), problemas, resumo
