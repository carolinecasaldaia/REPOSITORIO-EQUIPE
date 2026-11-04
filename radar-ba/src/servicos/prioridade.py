"""Classificação de prioridade do alerta (item 12).

A régua é a data de DISTRIBUIÇÃO quando conhecida. Quando só temos a data de
publicação no DJEN — que é o caso comum na detecção, porque o DataJud está
defasado — usamos a publicação e dizemos isso no motivo, para ninguém confundir
"apareceu no diário hoje" com "foi distribuído hoje".
"""
import datetime

CRITICO = "CRÍTICO"
ALTO = "ALTO"
ATENCAO = "ATENÇÃO"
INFORMATIVO = "INFORMATIVO"

EMOJI = {CRITICO: "🚨", ALTO: "🔴", ATENCAO: "🟡", INFORMATIVO: "⚪"}
ORDEM = {CRITICO: 0, ALTO: 1, ATENCAO: 2, INFORMATIVO: 3}


def _data(valor):
    if not valor:
        return None
    try:
        return datetime.date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def classificar_prioridade(data_distribuicao=None, data_publicacao=None,
                           encerrado=False, hoje=None, ano_ajuizamento=None):
    """Devolve (prioridade, motivo).

    O ano de ajuizamento vem de graça no número CNJ e é o freio contra um erro
    real: na carga de 18/08/2026 um processo de **1984** saiu como CRÍTICO,
    porque a régua olhava a data de publicação no diário. Publicação recente em
    processo antigo é andamento de rotina, não busca e apreensão nova.
    """
    hoje = hoje or datetime.date.today()
    if encerrado:
        return INFORMATIVO, "Processo encerrado ou aparentemente relacionado"

    if ano_ajuizamento and (hoje.year - int(ano_ajuizamento)) >= 2:
        return ATENCAO, ("Processo ajuizado em %s — publicação recente é "
                         "andamento, não distribuição nova" % ano_ajuizamento)

    distribuicao = _data(data_distribuicao)
    referencia, rotulo = distribuicao, "distribuído"
    if referencia is None:
        referencia, rotulo = _data(data_publicacao), "publicado no diário"

    if referencia is None:
        return ATENCAO, "Sem data confiável — conferir manualmente"

    dias = (hoje - referencia).days
    if dias < 0:
        return ATENCAO, "Data futura no registro da fonte — conferir"
    if dias <= 7:
        return CRITICO, "Busca e Apreensão %s há %d dia(s)" % (rotulo, dias)
    if dias <= 30:
        return ALTO, "Busca e Apreensão %s há %d dias" % (rotulo, dias)
    return ATENCAO, "Processo %s há %d dias, ainda ativo" % (rotulo, dias)
