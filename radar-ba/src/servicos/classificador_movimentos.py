"""O que aconteceu dentro de uma Busca e Apreensão já conhecida.

O escritório precisa de dois avisos, e eles valem mais quanto mais cedo chegam:

    LIMINAR DEFERIDA  — o juiz autorizou a apreensão
    MANDADO EXPEDIDO  — o oficial já pode buscar o veículo

Duas fontes, com pesos diferentes:

  DJEN (D+1) — o inteiro teor da publicação. É a fonte rápida, e é nela que a
  decisão aparece por extenso ("concedo liminarmente a BUSCA E APREENSÃO do
  veículo"). Foi conferida em 215 publicações reais de classe 81 do TJAL em
  14/08/2026: 31 liminares deferidas e 47 mandados.

  DataJud (1 a 2 meses de atraso) — os códigos da tabela unificada do CNJ,
  levantados por amostragem de 600 processos:
      60  + complemento tipo_de_documento = Mandado  -> expedição de mandado
      106 Mandado (com resultado entregue/não entregue)
      985 Mandado
      339 Liminar
      332 Antecipação de tutela
  Serve para confirmar e para preencher histórico, nunca para alertar na hora.

Ordem de decisão: indeferimento é checado ANTES do deferimento, senão
"INDEFIRO o pedido de liminar" cairia na regra de deferimento.
"""
import re
from dataclasses import dataclass, field
from typing import List

LIMINAR_DEFERIDA = "LIMINAR_DEFERIDA"
LIMINAR_INDEFERIDA = "LIMINAR_INDEFERIDA"
MANDADO_EXPEDIDO = "MANDADO_EXPEDIDO"
MANDADO_CUMPRIDO = "MANDADO_CUMPRIDO"
VEICULO_APREENDIDO = "VEICULO_APREENDIDO"
CITACAO = "CITACAO"

# Eventos que o escritório quer saber na hora.
URGENTES = (LIMINAR_DEFERIDA, MANDADO_EXPEDIDO, VEICULO_APREENDIDO, MANDADO_CUMPRIDO)

_NEGATIVA = r"(?:indefiro|indeferid[oa]|indeferi\b|nego\b|denego|n[ãa]o\s+concedo|"\
            r"n[ãa]o\s+conced[ia]|deixo\s+de\s+(?:deferir|conceder))"
_POSITIVA = r"(?:defiro|deferid[oa]|deferi\b|concedo|conced[ia]|concedid[oa]|"\
            r"autorizo|autorizad[oa])"
_MEDIDA = r"(?:liminar\w*|tutela|medida|busca\s+e\s+apreens[ãa]o)"

# Vetos: expressões que, aparecendo no trecho casado, derrubam a detecção.
# Vieram de falsos positivos reais encontrados em 60 publicações do TJAL.
_VETO_NAO_CUMPRIDO = r"(?is)(n[ãa]o\s+cumprid|se\s+n[ãa]o\s+|sob\s+pena\s+de|" \
                     r"caso\s+n[ãa]o|devolver\s+o\s+mandado|restar\s+infrutífer)"
_VETO_LIMINAR_ANTIGA = r"(?is)(outrora|anteriormente|j[áa]\s+(concedid|deferid)|" \
                       r"torna(ndo)?\s+definitiva|torno\s+definitiva|confirmo\s+a\s+liminar|" \
                       r"liminar\s+deferida\s+[àa]s\s+fls)"

# Cada regra: (evento, padrão, confiança, veto). Avaliadas em ordem.
_REGRAS = [
    # --- negativas primeiro ---
    (LIMINAR_INDEFERIDA,
     r"(?is)\b%s\b[^.]{0,120}?\b%s" % (_NEGATIVA, _MEDIDA), 0.90, None),
    (LIMINAR_INDEFERIDA,
     r"(?is)\b%s\b[^.]{0,120}?\b%s\b" % (_MEDIDA, _NEGATIVA), 0.85, None),

    # --- apreensão consumada ---
    (VEICULO_APREENDIDO,
     r"(?is)(ve[íi]culo|bem|autom[óo]vel)[^.]{0,60}\b(apreendid[oa]|"
     r"foi\s+apreendid|restitu[íi]d[oa]\s+ao\s+(credor|autor))", 0.90,
     _VETO_NAO_CUMPRIDO),
    (MANDADO_CUMPRIDO,
     r"(?is)mandado[^.]{0,80}\b(cumprid[oa]|positiv[oa])\b|"
     r"\bcumprimento\s+do\s+mandado\b[^.]{0,40}(positiv|efetiv)", 0.85,
     _VETO_NAO_CUMPRIDO),

    # --- mandado expedido ---
    (MANDADO_EXPEDIDO,
     r"(?is)(expe[çc]a-se|expedi[çc][ãa]o\s+d[eo]|expedid[oa]|expe[çc]am-se)"
     r"[^.]{0,80}?mandado", 0.92, None),
    (MANDADO_EXPEDIDO,
     r"(?is)mandado[^.]{0,60}\bexpedid[oa]\b", 0.88, None),

    # --- liminar deferida ---
    (LIMINAR_DEFERIDA,
     r"(?is)\b%s\b[^.]{0,40}?liminarmente[^.]{0,60}?busca\s+e\s+apreens" % _POSITIVA,
     0.95, _VETO_LIMINAR_ANTIGA),
    (LIMINAR_DEFERIDA,
     r"(?is)\b%s\b[^.]{0,120}?\b%s" % (_POSITIVA, _MEDIDA), 0.88, _VETO_LIMINAR_ANTIGA),
    (LIMINAR_DEFERIDA,
     r"(?is)\b%s\b[^.]{0,120}?\b%s\b" % (_MEDIDA, _POSITIVA), 0.82, _VETO_LIMINAR_ANTIGA),

    (CITACAO, r"(?is)\bcite-se\b|\bcita[çc][ãa]o\s+d[oa]\s+(r[ée]u|demandad)", 0.75, None),
]
_COMPILADAS = [(evento, re.compile(p), conf, re.compile(v) if v else None)
               for evento, p, conf, v in _REGRAS]

# --- códigos do DataJud (levantados por amostragem, não presumidos) ---
COD_MANDADO_EXPEDIDO = 60          # exige complemento tipo_de_documento = Mandado
COD_MANDADO = {106, 985}
COD_LIMINAR = 339
COD_ANTECIPACAO_TUTELA = 332


@dataclass
class Evento:
    tipo: str
    confianca: float
    trecho: str = ""
    fonte: str = ""

    @property
    def urgente(self):
        return self.tipo in URGENTES


@dataclass
class Leitura:
    eventos: List[Evento] = field(default_factory=list)

    @property
    def urgentes(self):
        return [e for e in self.eventos if e.urgente]

    def tem(self, tipo):
        return any(e.tipo == tipo for e in self.eventos)


def classificar_texto(texto, fonte="DJEN"):
    """Lê o inteiro teor da publicação e devolve os eventos encontrados."""
    leitura = Leitura()
    if not texto:
        return leitura
    vistos = set()
    for evento, padrao, confianca, veto in _COMPILADAS:
        if evento in vistos:
            continue
        m = padrao.search(texto)
        if not m:
            continue
        # Deferimento não convive com indeferimento da mesma medida.
        if evento == LIMINAR_DEFERIDA and LIMINAR_INDEFERIDA in vistos:
            continue
        trecho = re.sub(r"\s+", " ", texto[max(0, m.start() - 70):m.end() + 90]).strip()
        # Veto: a vizinhança desmente a leitura ("se não cumprido", "liminar
        # outrora concedida"). Falsos positivos vistos em publicações reais.
        if veto is not None and veto.search(trecho):
            continue
        vistos.add(evento)
        leitura.eventos.append(Evento(evento, confianca, trecho, fonte))
    return leitura


def classificar_movimento_datajud(movimento):
    """Lê um movimento do DataJud (código + complementos tabelados)."""
    if not movimento:
        return None
    codigo = movimento.get("codigo")
    complementos = movimento.get("complementosTabelados") or []

    if codigo == COD_MANDADO_EXPEDIDO:
        for c in complementos:
            if str(c.get("nome", "")).strip().lower() == "mandado":
                return Evento(MANDADO_EXPEDIDO, 0.95,
                              "movimento 60 · tipo_de_documento = Mandado", "DataJud")
        return None
    if codigo in COD_MANDADO:
        for c in complementos:
            if "entregue ao destinat" in str(c.get("nome", "")).lower() \
                    and not str(c.get("nome", "")).lower().startswith("não"):
                return Evento(MANDADO_CUMPRIDO, 0.85,
                              "movimento %s · entregue ao destinatário" % codigo, "DataJud")
        return Evento(MANDADO_EXPEDIDO, 0.70,
                      "movimento %s (Mandado)" % codigo, "DataJud")
    if codigo in (COD_LIMINAR, COD_ANTECIPACAO_TUTELA):
        # O DataJud não diz se foi deferida: o código 339 é só "Liminar".
        return Evento(LIMINAR_DEFERIDA, 0.55,
                      "movimento %s (Liminar/Tutela) — o DataJud não informa o "
                      "resultado; conferir o teor" % codigo, "DataJud")
    return None
