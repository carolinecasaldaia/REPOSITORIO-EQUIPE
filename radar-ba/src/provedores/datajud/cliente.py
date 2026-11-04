"""DataJud / API Pública do CNJ — enriquecimento, nunca detecção.

Duas limitações confirmadas empiricamente em 18/08/2026 definem este papel:

  SEM PARTES. Testados 10 nomes de campo (partes, poloAtivo, autor, cpf,
  documento...): todos com zero documentos. Busca textual por "BANCO PAN" no
  índice do TJAL: zero resultados. Não há como perguntar "há processo contra
  o CPF X" — e não existe contorno legítimo.

  DEFASAGEM DE ATÉ 2 MESES. No TJSP a B&A mais recente visível havia sido
  ajuizada 49 dias antes. Serve para enriquecer processo já conhecido e para
  estatística, não para alertar.

ARMADILHA DO CAMPO dataAjuizamento: chega como "20260630235628" mas o índice o
interpreta como epoch_millis — um processo de 2026 vai parar no ano 2612.
Filtro com semântica de data devolve resultado errado EM SILÊNCIO. Use sempre
o número cru (ver `faixa_periodo`).
"""
import datetime
import re

from src.config import ajustes
from src.provedores.base import (REVISAO_MANUAL, DetalheProcesso,
                                 ProvedorJudicial, ResultadoProcesso,
                                 so_digitos)
from src.util.http import Cliente, FalhaConsulta
from src.util.log import obter

log = obter("datajud")

TRIBUNAIS = ["tjac", "tjal", "tjam", "tjap", "tjba", "tjce", "tjdft", "tjes",
             "tjgo", "tjma", "tjmg", "tjms", "tjmt", "tjpa", "tjpb", "tjpe",
             "tjpi", "tjpr", "tjrj", "tjrn", "tjro", "tjrr", "tjrs", "tjsc",
             "tjse", "tjsp", "tjto"]

# O tribunal está nos dígitos 14-15 do número CNJ (NNNNNNN DD AAAA J TR OOOO).
_TR_PARA_SIGLA = {
    "01": "tjac", "02": "tjal", "03": "tjap", "04": "tjam", "05": "tjba",
    "06": "tjce", "07": "tjdft", "08": "tjes", "09": "tjgo", "10": "tjma",
    "11": "tjmt", "12": "tjms", "13": "tjmg", "14": "tjpa", "15": "tjpb",
    "16": "tjpr", "17": "tjpe", "18": "tjpi", "19": "tjrj", "20": "tjrn",
    "21": "tjrs", "22": "tjro", "23": "tjrr", "24": "tjsc", "25": "tjse",
    "26": "tjsp", "27": "tjto",
}


def sigla_pelo_numero(numero_processo):
    """Descobre o tribunal a partir do número CNJ. '' se não for justiça estadual."""
    d = so_digitos(numero_processo)
    if len(d) != 20:
        return ""
    if d[13] != "8":            # J=8 é a Justiça Estadual
        return ""
    return _TR_PARA_SIGLA.get(d[14:16], "")


def normalizar_data_ajuizamento(valor):
    """Converte os DOIS formatos que convivem no índice para ISO aaaa-mm-dd.

    Formatos observados: "20260630235628" (yyyyMMddHHmmss) e "2025-07-15T13:19:10".
    Devolve None quando a data é implausível (o índice tem lixo, como ano 4022).
    """
    if valor in (None, ""):
        return None
    texto = str(valor)
    d = so_digitos(texto)
    if len(d) >= 8:
        ano, mes, dia = int(d[0:4]), int(d[4:6]), int(d[6:8])
        if 1970 <= ano <= datetime.date.today().year + 1 and 1 <= mes <= 12 and 1 <= dia <= 31:
            try:
                return datetime.date(ano, mes, dia).isoformat()
            except ValueError:
                return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if m:
        ano = int(m.group(1))
        if 1970 <= ano <= datetime.date.today().year + 1:
            return "%s-%s-%s" % m.groups()
    return None


def faixa_periodo(inicio, fim):
    """Filtro de período seguro para dataAjuizamento.

    Passa o número CRU (20260301000000), que o índice compara como epoch_millis.
    A comparação numérica continua correta; a semântica de data, não. NUNCA
    escrever {"gte": "2026-03-01"} — isso casa errado sem avisar.
    """
    return {"range": {"dataAjuizamento": {
        "gte": int(inicio.strftime("%Y%m%d") + "000000"),
        "lt": int(fim.strftime("%Y%m%d") + "235959"),
    }}}


class ProvedorDataJud(ProvedorJudicial):
    nome = "DataJud"
    cobertura = [t.upper() for t in TRIBUNAIS]
    permite_cpf = False

    def __init__(self, cliente_http=None):
        if not ajustes.DATAJUD_API_KEY:
            log.warning("DATAJUD_API_KEY ausente no .env — provedor ficará indisponível")
        self.http = cliente_http or Cliente(
            "DataJud", ajustes.DATAJUD_RPM,
            cabecalhos={"Authorization": "APIKey " + ajustes.DATAJUD_API_KEY},
        )
        self.base = ajustes.DATAJUD_BASE.rstrip("/")

    def _url(self, sigla):
        return "%s/api_publica_%s/_search" % (self.base, sigla.lower())

    def consultar(self, sigla, corpo):
        return self.http.pedir(self._url(sigla), corpo=corpo, metodo="POST",
                               tribunal=sigla.upper())

    def verificar_saude(self, sigla="tjal"):
        try:
            d = self.consultar(sigla, {"size": 1, "query": {"match_all": {}}})
            return bool(d.get("hits", {}).get("hits"))
        except Exception as e:
            log.warning("DataJud indisponível (%s): %s", sigla, e)
            return False

    def buscar_por_cpf(self, cpf, **kw):
        """A API pública do CNJ não expõe partes. Limitação estrutural."""
        return [ResultadoProcesso(
            fonte=self.nome,
            status_casamento=REVISAO_MANUAL,
            motivo="DataJud não expõe partes nem CPF (verificado em 18/08/2026) — "
                   "use o DJEN para detectar e o e-SAJ para confirmar por CPF",
        )]

    def detalhar(self, numero_processo, tribunal=None):
        """Enriquece um processo já conhecido: classe, assuntos, vara, movimentos."""
        sigla = (tribunal or sigla_pelo_numero(numero_processo) or "").lower()
        if not sigla:
            log.warning("não foi possível deduzir o tribunal do número informado")
            return None
        corpo = {"size": 1, "query": {"match": {"numeroProcesso": so_digitos(numero_processo)}}}
        try:
            d = self.consultar(sigla, corpo)
        except FalhaConsulta as e:
            log.warning("falha ao detalhar processo: %s", e)
            return None
        hits = d.get("hits", {}).get("hits") or []
        if not hits:
            return None
        f = hits[0]["_source"]
        movimentos = sorted(f.get("movimentos") or [],
                            key=lambda m: m.get("dataHora") or "", reverse=True)
        return DetalheProcesso(
            numero_processo=f.get("numeroProcesso", ""),
            tribunal=f.get("tribunal", ""),
            classe_codigo=(f.get("classe") or {}).get("codigo"),
            classe_nome=(f.get("classe") or {}).get("nome", ""),
            assuntos=[a.get("nome", "") for a in (f.get("assuntos") or [])],
            orgao_julgador=(f.get("orgaoJulgador") or {}).get("nome", ""),
            data_distribuicao=normalizar_data_ajuizamento(f.get("dataAjuizamento")),
            movimentos=movimentos[:20],
            sistema=(f.get("sistema") or {}).get("nome", ""),
            fonte="DataJud",
        )

    def contar_classe_periodo(self, sigla, classe_codigo, inicio, fim):
        """Estatística de carteira/mercado. Usa o filtro numérico seguro."""
        corpo = {"size": 0, "query": {"bool": {"filter": [
            {"term": {"classe.codigo": classe_codigo}},
            faixa_periodo(inicio, fim),
        ]}}}
        d = self.consultar(sigla, corpo)
        return d.get("hits", {}).get("total", {}).get("value", 0)
