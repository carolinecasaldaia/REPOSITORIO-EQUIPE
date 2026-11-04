"""Casamento de nomes entre a carteira do escritório e as partes do processo.

Dois problemas reais, medidos na FASE 1:

  FALSO NEGATIVO — o DJEN casa por sequência exata de caracteres. "CAMILA COSTA
  ALVEZ" (uma letra trocada) devolve zero. Compensamos consultando por PREFIXO
  (os dois primeiros nomes) e filtrando aqui dentro, com tolerância.

  FALSO POSITIVO — homônimo. Nome igual NUNCA confirma identidade; no máximo
  gera POSSIBLE_MATCH. Só CPF confirma (item 21 da especificação).
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Partículas que variam de cadastro para cadastro e não distinguem pessoas.
_PARTICULAS = {"DA", "DE", "DO", "DAS", "DOS", "E", "D"}
# Sufixos de geração.
_SUFIXOS = {"JUNIOR", "JR", "FILHO", "NETO", "SOBRINHO", "SEGUNDO", "TERCEIRO"}


def normalizar(nome):
    """Maiúsculas, sem acento, sem pontuação, espaços colapsados."""
    t = unicodedata.normalize("NFKD", str(nome or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Z\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(nome, manter_particulas=False):
    ts = normalizar(nome).split()
    if manter_particulas:
        return ts
    return [t for t in ts if t not in _PARTICULAS]


def _nucleo(ts):
    """Tokens que realmente identificam: sem partículas nem sufixo de geração."""
    return [t for t in ts if t not in _SUFIXOS]


def _distancia(a, b):
    """Distância de edição (Levenshtein), suficiente para nomes curtos."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1,
                             anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def token_igual(a, b):
    """Trata como mesmo token as variações banais de grafia.

    SOUZA/SOUSA, ALVES/ALVEZ, TEIXEIRA/TEIXERA: uma letra de diferença em nome
    de 4 letras ou mais é erro de digitação ou variante regional, não outra
    pessoa. Sem isso, o sistema perde o processo em silêncio.
    """
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and _distancia(a, b) <= 1:
        return True
    return _parecido(a, b) >= 0.90


def similaridade(a, b):
    """0.0 a 1.0 entre dois nomes."""
    ta, tb = _nucleo(tokens(a)), _nucleo(tokens(b))
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0

    primeiro_bate = token_igual(ta[0], tb[0])
    ultimo_bate = token_igual(ta[-1], tb[-1])

    # Casamento token a token, tolerante a variação de grafia.
    menor, maior = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    disponiveis = list(maior)
    casados = 0
    for t in menor:
        for i, u in enumerate(disponiveis):
            if token_igual(t, u):
                casados += 1
                disponiveis.pop(i)
                break
    cobertura = casados / float(len(menor))          # quanto do nome menor foi achado
    jaccard = casados / float(len(ta) + len(tb) - casados)
    base = _parecido(" ".join(ta), " ".join(tb))
    nota = max(base, jaccard)

    if primeiro_bate and cobertura == 1.0:
        # Todo o nome mais curto está contido no mais longo: cadastro incompleto.
        nota = max(nota, 0.95 if ultimo_bate else 0.88)
    elif primeiro_bate and ultimo_bate:
        nota = max(nota, 0.88)
    elif primeiro_bate or ultimo_bate:
        nota = min(max(nota, 0.60), 0.80)
    else:
        nota = min(nota, 0.55)
    return round(min(1.0, nota), 3)


def _parecido(a, b):
    return SequenceMatcher(None, a, b).ratio()


def casa(nome_cliente, nome_parte, limite=0.85):
    """Devolve (casou, nota, motivo). Nunca confirma identidade — só indica."""
    nota = similaridade(nome_cliente, nome_parte)
    if normalizar(nome_cliente) == normalizar(nome_parte):
        return True, 1.0, "Nome idêntico ao da carteira (homônimo ainda possível)"
    if nota >= limite:
        return True, nota, "Nome semelhante ao da carteira (%.0f%%)" % (nota * 100)
    return False, nota, "Nome não corresponde (%.0f%%)" % (nota * 100)


def variantes_consulta(nome):
    """Termos a consultar no DJEN, do mais específico ao mais amplo.

    O DJEN casa por sequência exata a partir do início do nome, então um
    PREFIXO ("CAMILA COSTA") alcança o registro completo ("CAMILA COSTA ALVES")
    mesmo que o cadastro do escritório esteja incompleto. Consultar o prefixo
    amplia o alcance; o filtro fino é feito aqui no nosso lado.
    """
    ts = tokens(nome, manter_particulas=True)
    if not ts:
        return []
    variantes = [" ".join(ts)]
    nucleo = [t for t in ts if t not in _PARTICULAS]
    if len(nucleo) >= 3:
        prefixo = " ".join(nucleo[:2])
        if prefixo not in variantes:
            variantes.append(prefixo)
    return variantes
