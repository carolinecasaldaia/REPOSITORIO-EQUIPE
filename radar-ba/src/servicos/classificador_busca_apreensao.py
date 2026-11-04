"""Classificador de Busca e Apreensão.

Não decide por texto. O sinal primário é o CÓDIGO DA CLASSE processual (tabela
unificada do CNJ), porque "busca e apreensão" em texto livre também aparece em
processo criminal e de menores — misturar isso seria um erro grave.

Ordem de decisão:
  1. classe em lista de exclusão  -> não é (encerra na hora)
  2. classe alvo                  -> é, com confiança conforme a classe
  3. assunto confirma alienação fiduciária -> reforça a confiança
  4. banco no polo ativo          -> reforça a confiança
  5. sem código de classe         -> cai para texto, com confiança baixa

Todos os códigos abaixo foram conferidos por agregação na API do DataJud em
18/08/2026 (ver docs/mapeamento-tribunais.md §8), não presumidos.
"""
import re
import unicodedata
from dataclasses import dataclass

# --- classes alvo -------------------------------------------------------
BUSCA_APREENSAO_FIDUCIARIA = 81
BUSCA_APREENSAO_CIVEL = 181
EXECUCAO_TITULO = 12154
EXECUCAO_TITULO_LEGADO = 159

CLASSES_ALVO = {
    BUSCA_APREENSAO_FIDUCIARIA: (0.98, "Busca e Apreensão em Alienação Fiduciária (DL 911/1969)"),
    BUSCA_APREENSAO_CIVEL: (0.70, "Busca e Apreensão cível — exige conferência do objeto"),
    EXECUCAO_TITULO: (0.75, "Execução de Título Extrajudicial"),
    EXECUCAO_TITULO_LEGADO: (0.75, "Execução de Título Extrajudicial (código legado)"),
}

# --- exclusões: nunca são o nosso caso ----------------------------------
CLASSES_EXCLUIDAS = {
    309: "Pedido de Busca e Apreensão Criminal — matéria penal",
    12072: "Busca e Apreensão Infracional — ato infracional",
    1438: "Busca e Apreensão Infância e Juventude — sigilo de menor",
    12079: "Execução contra a Fazenda Pública — polo incompatível",
}

# --- assuntos que confirmam alienação fiduciária ------------------------
ASSUNTOS_FIDUCIARIA = {
    9582: "Alienação Fiduciária",
    10481: "Propriedade Fiduciária",
    7773: "Financiamento de Produto",
    14757: "Crédito Direto ao Consumidor - CDC",
    10677: "Busca e Apreensão",
}

# Nomes de classe que identificam a classe sem ambiguidade. O e-SAJ devolve o
# NOME da classe, não o código; sem esta ponte, um processo confirmado por CPF
# e chamado "Busca e Apreensão em Alienação Fiduciária" caía na regra de texto
# genérica e saía com confiança baixa.
_NOME_PARA_CODIGO = {
    "busca e apreensao em alienacao fiduciaria": BUSCA_APREENSAO_FIDUCIARIA,
    "execucao de titulo extrajudicial": EXECUCAO_TITULO,
    "busca e apreensao": BUSCA_APREENSAO_CIVEL,
    "pedido de busca e apreensao criminal": 309,
    "busca e apreensao infracional": 12072,
    "busca e apreensao infancia e juventude": 1438,
    "execucao de titulo extrajudicial contra a fazenda publica": 12079,
}


def codigo_pelo_nome(classe_nome):
    """Descobre o código da classe pelo nome exato, quando a fonte não o dá."""
    chave = re.sub(r"\s+", " ", _sem_acento(classe_nome).lower()).strip()
    return _NOME_PARA_CODIGO.get(chave)


_TEXTO_ALVO = re.compile(
    r"(busca e apreens\w+.*(alienac|fiducia)|alienacao fiduciaria|"
    r"decreto[- ]?lei\s*911|dl\s*911|execucao de titulo extrajudicial)", re.I
)
_TEXTO_EXCLUI = re.compile(
    r"(criminal|infracional|infancia e juventude|ato infracional|penal)", re.I
)


@dataclass
class Classificacao:
    eh_busca_apreensao: bool
    confianca: float
    motivo: str

    def para_json(self):
        """Formato exato pedido na especificação (item 6)."""
        return {
            "isSearchAndSeizure": self.eh_busca_apreensao,
            "confidence": round(self.confianca, 2),
            "reason": self.motivo,
        }


def _sem_acento(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c))


def classificar(classe_codigo=None, classe_nome="", assuntos=None,
                autor="", banco_normalizado="", movimentos=None):
    """Decide se o processo é de Busca e Apreensão / Execução de interesse.

    `assuntos` aceita lista de códigos (int) ou de dicionários {codigo, nome}.
    """
    assuntos = assuntos or []
    codigos_assunto = set()
    nomes_assunto = []
    for a in assuntos:
        if isinstance(a, dict):
            if a.get("codigo") is not None:
                codigos_assunto.add(int(a["codigo"]))
            nomes_assunto.append(a.get("nome", ""))
        elif isinstance(a, int):
            codigos_assunto.add(a)
        else:
            nomes_assunto.append(str(a))

    # Fonte sem código (e-SAJ): tenta descobrir pelo nome exato da classe.
    if classe_codigo is None:
        classe_codigo = codigo_pelo_nome(classe_nome)

    # 1. exclusão por código — decisão final, não há reforço que reverta
    if classe_codigo is not None:
        try:
            cod = int(classe_codigo)
        except (TypeError, ValueError):
            cod = None
        if cod in CLASSES_EXCLUIDAS:
            return Classificacao(False, 0.99,
                                 "Excluído: %s" % CLASSES_EXCLUIDAS[cod])

        # 2. classe alvo
        if cod in CLASSES_ALVO:
            confianca, descricao = CLASSES_ALVO[cod]
            motivo = "Classe processual %d identificada como %s" % (cod, descricao)

            # 3. assunto reforça
            batidos = codigos_assunto & set(ASSUNTOS_FIDUCIARIA)
            if batidos:
                nome = ASSUNTOS_FIDUCIARIA[sorted(batidos)[0]]
                confianca = min(0.99, confianca + 0.10)
                motivo += "; assunto CNJ confirma %s" % nome

            # 4. banco no polo ativo reforça
            if banco_normalizado:
                confianca = min(0.99, confianca + 0.05)
                motivo += "; polo ativo é instituição financeira (%s)" % banco_normalizado
            elif cod in (EXECUCAO_TITULO, EXECUCAO_TITULO_LEGADO):
                # execução sem banco identificado é fraca: pode ser qualquer credor
                confianca = max(0.35, confianca - 0.30)
                motivo += "; polo ativo não identificado como instituição financeira"

            return Classificacao(True, confianca, motivo)

        # classe conhecida que não é alvo
        if cod is not None:
            return Classificacao(False, 0.90,
                                 "Classe processual %d não é Busca e Apreensão nem Execução" % cod)

    # 5. sem código de classe: cai para texto, sempre com confiança baixa.
    #
    # O texto olha SÓ o nome da classe, nunca o assunto. O assunto descreve o
    # contrato, não o tipo de ação: "Procedimento Comum Cível" com assunto
    # "Alienação Fiduciária" é tipicamente a revisional do próprio escritório —
    # e chegou a ser alertada como busca e apreensão enquanto o assunto entrava
    # nesta regra. Assunto reforça uma classe alvo; jamais a estabelece.
    alvo = _sem_acento(classe_nome)
    if _TEXTO_EXCLUI.search(alvo):
        return Classificacao(False, 0.80,
                             "Texto indica matéria criminal/infracional — excluído")
    if _TEXTO_ALVO.search(alvo):
        confianca = 0.55 + (0.10 if banco_normalizado else 0.0)
        return Classificacao(True, confianca,
                             "Sem código de classe; texto '%s' sugere o tema — conferência recomendada"
                             % (classe_nome or "")[:60])
    return Classificacao(False, 0.60, "Nem código nem texto indicam Busca e Apreensão")
