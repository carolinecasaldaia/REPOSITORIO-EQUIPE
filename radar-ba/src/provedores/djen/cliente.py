"""DJEN / API Comunica do CNJ — motor de detecção do RADAR B&A.

Por que esta é a fonte primária (medido em 18/08/2026):
  · pública, sem autenticação e sem CAPTCHA;
  · nacional — dispensa iterar tribunal a tribunal;
  · atualizada em D+1, contra 1 a 2 meses de defasagem do DataJud;
  · traz NOME DAS PARTES com polo, classe processual, órgão e número do processo.

Duas armadilhas confirmadas nos testes, tratadas aqui dentro:
  1. a API ACEITA E IGNORA parâmetros desconhecidos, sem erro. `codigoClasse`
     não filtra nada. Por isso TODO filtro de classe é aplicado no nosso lado.
  2. `nomeParte` casa por sequência exata: um caractere diferente devolve zero.
     Por isso consultamos também o prefixo do nome (ver casador_nomes).
"""
import datetime

from src.config import ajustes
from src.provedores.base import (CONFIRMADO, POSSIVEL, ProvedorJudicial,
                                 ResultadoProcesso)
from src.servicos import normalizador_bancos as bancos
from src.servicos.casador_nomes import casa, variantes_consulta
from src.servicos.classificador_busca_apreensao import classificar
from src.util.http import Cliente, FalhaConsulta
from src.util.log import obter
from src.util import cnj

log = obter("djen")

POLO_ATIVO = "A"
POLO_PASSIVO = "P"

# Parâmetros que a API realmente honra (testados um a um em 18/08/2026).
# Qualquer outro é ignorado em silêncio — não confiar.
_PARAMS_VALIDOS = {"nomeParte", "numeroProcesso", "siglaTribunal", "numeroOab",
                   "ufOab", "texto", "dataDisponibilizacaoInicio",
                   "dataDisponibilizacaoFim", "itensPorPagina", "pagina", "meio"}


class ProvedorDJEN(ProvedorJudicial):
    nome = "DJEN"
    cobertura = []          # nacional
    permite_cpf = False     # a API não expõe CPF

    def __init__(self, cliente_http=None):
        self.http = cliente_http or Cliente("DJEN", ajustes.DJEN_RPM)
        self.base = ajustes.DJEN_BASE.rstrip("/")

    # --- saúde ----------------------------------------------------------
    def verificar_saude(self):
        try:
            ontem = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            d = self._consultar(dataDisponibilizacaoInicio=ontem,
                                dataDisponibilizacaoFim=ontem, itensPorPagina=1)
            return isinstance(d, dict) and "items" in d
        except Exception as e:
            log.warning("DJEN indisponível: %s", e)
            return False

    # --- chamada crua ---------------------------------------------------
    def _consultar(self, **params):
        limpos = {}
        for k, v in params.items():
            if k not in _PARAMS_VALIDOS:
                log.debug("parâmetro '%s' ignorado pela API — descartado", k)
                continue
            if v not in (None, ""):
                limpos[k] = v
        return self.http.pedir_get(self.base + "/comunicacao", limpos,
                                   tribunal=params.get("siglaTribunal") or "NACIONAL")

    # --- busca por nome -------------------------------------------------
    def buscar_por_nome(self, nome, dias=7, tribunal=None, cliente_id=None,
                        limite_nome=0.85, usar_prefixo=True):
        """Consulta o nome (e, por padrão, também seu prefixo).

        `usar_prefixo=False` corta pela metade o número de requisições — útil na
        carga inicial de uma carteira grande, onde o custo importa mais que o
        último ponto de alcance.
        """
        fim = datetime.date.today()
        inicio = fim - datetime.timedelta(days=max(0, dias))
        vistos = set()
        achados = []
        termos = variantes_consulta(nome)
        if not usar_prefixo:
            termos = termos[:1]
        for termo in termos:
            try:
                dados = self._consultar(
                    nomeParte=termo,
                    siglaTribunal=tribunal,
                    dataDisponibilizacaoInicio=inicio.isoformat(),
                    dataDisponibilizacaoFim=fim.isoformat(),
                    itensPorPagina=ajustes.DJEN_ITENS_POR_PAGINA,
                )
            except FalhaConsulta as e:
                log.warning("falha ao consultar nome no DJEN: %s", e)
                continue
            for item in dados.get("items") or []:
                if item.get("id") in vistos:
                    continue
                vistos.add(item.get("id"))
                r = self.converter(item, nome_cliente=nome, cliente_id=cliente_id,
                                   limite_nome=limite_nome)
                if r is not None:
                    achados.append(r)
        return achados

    # --- varredura nacional ---------------------------------------------
    def varrer(self, data_inicio, data_fim, tribunal=None, max_paginas=400):
        """Percorre todas as comunicações do período, página a página.

        Estratégia recomendada para a rotina diária: baixar tudo uma vez e
        casar contra a carteira localmente. Sai mais barato que uma consulta
        por cliente e ainda permite casamento tolerante a erro de grafia.
        """
        pagina = 1
        while pagina <= max_paginas:
            try:
                dados = self._consultar(
                    siglaTribunal=tribunal,
                    dataDisponibilizacaoInicio=data_inicio,
                    dataDisponibilizacaoFim=data_fim,
                    itensPorPagina=ajustes.DJEN_ITENS_POR_PAGINA,
                    pagina=pagina,
                )
            except FalhaConsulta as e:
                log.error("varredura interrompida na página %d: %s", pagina, e)
                return
            itens = dados.get("items") or []
            for item in itens:
                yield item
            if len(itens) < ajustes.DJEN_ITENS_POR_PAGINA:
                return
            pagina += 1
        log.warning("varredura parou no teto de %d páginas — houve corte de cobertura",
                    max_paginas)

    # --- conversão -------------------------------------------------------
    def converter(self, item, nome_cliente=None, cliente_id=None, limite_nome=0.85):
        """Item cru do DJEN -> ResultadoProcesso, já classificado.

        Devolve None quando o item não interessa (classe fora do alvo ou o
        cliente não está no polo passivo).
        """
        destinatarios = item.get("destinatarios") or []
        ativos = [d.get("nome", "") for d in destinatarios if d.get("polo") == POLO_ATIVO]
        passivos = [d.get("nome", "") for d in destinatarios if d.get("polo") == POLO_PASSIVO]

        autor = ativos[0] if ativos else ""
        banco = bancos.descrever(autor)

        classificacao = classificar(
            classe_codigo=item.get("codigoClasse"),
            classe_nome=(item.get("nomeClasse") or "").upper(),
            banco_normalizado=bancos.normalizar_banco(autor),
        )
        if not classificacao.eh_busca_apreensao:
            return None

        # O cliente precisa estar no POLO PASSIVO — ele é o requerido na B&A.
        reu = ""
        status = POSSIVEL
        confianca_nome = 0.0
        motivo_nome = ""
        if nome_cliente:
            melhor = (False, 0.0, "")
            for p in passivos:
                ok, nota, motivo = casa(nome_cliente, p, limite=limite_nome)
                if nota > melhor[1]:
                    melhor = (ok, nota, motivo)
                    reu = p
            if not melhor[0]:
                return None      # nome não bate: não é processo do nosso cliente
            confianca_nome, motivo_nome = melhor[1], melhor[2]
        else:
            reu = passivos[0] if passivos else ""

        numero = item.get("numeroprocessocommascara") or item.get("numero_processo", "")
        # o DJEN devolve codigoClasse como TEXTO ("81"); o DataJud, como inteiro.
        # Normalizamos aqui para o campo ter sempre o mesmo tipo.
        try:
            codigo = int(item.get("codigoClasse"))
        except (TypeError, ValueError):
            codigo = None
        return ResultadoProcesso(
            numero_processo=numero,
            uf=cnj.uf(numero),
            ano_ajuizamento=cnj.ano(numero),
            tribunal=item.get("siglaTribunal", ""),
            classe_codigo=codigo,
            # a API maiusculiza só o ASCII e devolve "APREENSãO"; normalizamos
            classe_nome=(item.get("nomeClasse") or "").upper(),
            orgao_julgador=item.get("nomeOrgao", ""),
            autor=autor,
            reu=reu,
            banco_normalizado=banco,
            data_publicacao=item.get("data_disponibilizacao"),
            ultima_movimentacao=item.get("tipoComunicacao", ""),
            fonte="DJEN",
            status_casamento=status,
            confianca=round(min(classificacao.confianca, confianca_nome or classificacao.confianca), 3),
            motivo="%s. %s" % (classificacao.motivo, motivo_nome or "sem cliente informado"),
            cliente_id=cliente_id,
            bruto=item,
        )
