"""e-SAJ — confirmação de identidade por CPF.

É a única fonte testada que cruza CPF de forma automatizável: a consulta
pública do e-SAJ oferece "Documento da Parte" (cbPesquisa=DOCPARTE) e não
apresenta CAPTCHA. Cobre TJSP, TJAL, TJAC, TJAM e TJCE — 36% do volume
nacional de busca e apreensão.

ATENÇÃO — LEIA ANTES DE LIGAR:
A ausência de CAPTCHA é um fato técnico, NÃO uma autorização. Este provedor
nasce DESLIGADO (ESAJ_HABILITADO=false). Só deve ser ligado depois de o
escritório analisar os Termos de Uso de cada tribunal. Quando ligado, opera:
  · identificado (User-Agent com o nome do escritório);
  · em ritmo baixo, uma consulta a cada ESAJ_INTERVALO_S segundos;
  · restrito a clientes da carteira, com procuração;
  · sem nenhuma técnica de evasão de bloqueio — se o tribunal recusar,
    o resultado vira MANUAL_REVIEW_REQUIRED e o sistema para de insistir.
"""
import html
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from src.config import ajustes
from src.provedores.base import (CONFIRMADO, REVISAO_MANUAL, ProvedorJudicial,
                                 ResultadoProcesso)
from src.seguranca.documento import mascarar, normalizar, validar
from src.servicos import normalizador_bancos as bancos
from src.servicos.classificador_busca_apreensao import classificar
from src.util.http import AUDITORIA
from src.util.log import obter

log = obter("esaj")

# Domínios confirmados em 18/08/2026 (busca por documento presente, sem CAPTCHA).
# UF do cliente -> tribunal e-SAJ que atende por documento.
# TJSP entra com ressalva: depois da migração para o eproc (18/08/2026) o e-SAJ
# só alcança o acervo anterior — serve para o histórico, não para caso novo.
UF_PARA_TRIBUNAL = {"SP": "TJSP", "AL": "TJAL", "AC": "TJAC", "AM": "TJAM", "CE": "TJCE"}

DOMINIOS = {
    "TJSP": "https://esaj.tjsp.jus.br",
    "TJAL": "https://www2.tjal.jus.br",
    "TJAC": "https://esaj.tjac.jus.br",
    "TJAM": "https://consultasaj.tjam.jus.br",
    "TJCE": "https://esaj.tjce.jus.br",
}

# Detecção de CAPTCHA de VERDADE. A palavra "captcha" sozinha não serve: o
# e-SAJ carrega um JavaScript adormecido que só repassa um parâmetro
# `uuidCaptcha` quando ele existe na URL. Procurar a palavra fazia o sistema
# recusar consultas perfeitamente livres.
_CAPTCHA_REAL = re.compile(
    r'(?is)(g-recaptcha|grecaptcha\.|recaptcha/api\.js|hcaptcha|'
    r'<img[^>]+captcha|name="vlCaptcha"|id="imagemCaptcha"|id="captchaCode")')

# Quando a busca acha UM único processo, o e-SAJ abre a página de detalhe em
# vez da lista. Sem tratar isso, o resultado mais preciso possível — um cliente
# com um único processo — era justamente o que se perdia.
_DETALHE = re.compile(r'(?is)id="numeroProcesso"[^>]*>(.*?)</span>')


def _campo_detalhe(corpo, ident):
    m = re.search(r'(?is)id="%s"[^>]*>(.*?)</span>' % ident, corpo)
    return _texto(m.group(1)) if m else ""


_BLOCO = re.compile(r'<div id="divProcesso.*?(?=<div id="divProcesso|</ul>)', re.S)
_NUMERO = re.compile(r'class="linkProcesso"[^>]*>\s*([\d.\-]{20,30})', re.S)
_CLASSE = re.compile(r'class="classeProcesso"[^>]*>(.*?)</div>', re.S)
_ASSUNTO = re.compile(r'class="assuntoPrincipalProcesso"[^>]*>(.*?)</div>', re.S)
_PARTE = re.compile(r'class="unj-label tipoDeParticipacao"[^>]*>(.*?)</label>.*?'
                    r'class="unj-base-alt nomeParte"[^>]*>(.*?)</div>', re.S)
_FORO = re.compile(r'class="[^"]*foroDosProcessos"[^>]*>(.*?)</h2>', re.S)


def _sem_acento(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c))


def _data_iso(bruto):
    """'08/12/2023 às 17:25 - Sorteio' -> '2023-12-08'."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(bruto or ""))
    return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None


def _texto(bruto):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", bruto or ""))).strip()


class ProvedorESAJ(ProvedorJudicial):
    nome = "e-SAJ"
    cobertura = list(DOMINIOS)
    permite_cpf = True

    def __init__(self, tribunal="TJSP"):
        self.tribunal = tribunal.upper()
        if self.tribunal not in DOMINIOS:
            raise ValueError("e-SAJ não disponível para %s" % tribunal)
        self.base = DOMINIOS[self.tribunal]
        self._ultima = 0.0
        self._cookie = None      # sessão reaproveitada entre consultas

    def _sessao(self):
        """Abre a sessão uma vez e reaproveita.

        Sem isso, cada cliente custava duas requisições (abrir + pesquisar) e a
        varredura da carteira levava o dobro do tempo — sem nenhum ganho.
        """
        if self._cookie:
            return self._cookie
        self._aguardar()
        _, cabecalho = self._baixar(self.base + "/cpopg/open.do")
        self._cookie = cabecalho.split(";")[0] if cabecalho else None
        return self._cookie

    # --- controle de ritmo próprio, deliberadamente lento ---------------
    def _aguardar(self):
        espera = ajustes.ESAJ_INTERVALO_S - (time.time() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.time()

    def _baixar(self, url, cookie=None):
        req = urllib.request.Request(url, headers={
            "User-Agent": "RADAR-BA/1.0 (Caroline Macedo Advocacia; "
                          "consulta de carteira propria; contato@carolinemacedoadv.com)",
            "Accept": "text/html",
        })
        if cookie:
            req.add_header("Cookie", cookie)
        with urllib.request.urlopen(req, timeout=60) as r:
            # o e-SAJ responde text/html;charset=UTF-8 (conferido no header)
            return r.read().decode("utf-8", errors="replace"), r.headers.get("Set-Cookie", "")

    def verificar_saude(self):
        try:
            self._aguardar()
            corpo, _ = self._baixar(self.base + "/cpopg/open.do")
            return "DOCPARTE" in corpo
        except Exception as e:
            log.warning("e-SAJ %s indisponível: %s", self.tribunal, e)
            return False

    def buscar_por_cpf(self, cpf, cliente_id=None, nome_cliente=None):
        """Consulta por documento da parte. Só roda se explicitamente habilitado."""
        if not ajustes.ESAJ_HABILITADO:
            return [ResultadoProcesso(
                tribunal=self.tribunal, fonte=self.nome,
                status_casamento=REVISAO_MANUAL, cliente_id=cliente_id,
                motivo="Confirmação por CPF no e-SAJ está DESLIGADA "
                       "(ESAJ_HABILITADO=false). Ligar apenas após análise dos "
                       "Termos de Uso do %s." % self.tribunal,
            )]
        d = normalizar(cpf)
        if not validar(d):
            raise ValueError("documento inválido")

        inicio = time.monotonic()
        try:
            cookie = self._sessao()
            url = self.base + "/cpopg/search.do?" + urllib.parse.urlencode({
                "conversationId": "", "cbPesquisa": "DOCPARTE", "dePesquisa": d,
                "tipoNuProcesso": "UNIFICADO", "paginaConsulta": "1",
            })
            self._aguardar()
            corpo, _ = self._baixar(url, cookie=cookie)
        except urllib.error.HTTPError as e:
            AUDITORIA.anotar(self.nome, self.tribunal, "HTTP_%d" % e.code,
                             time.monotonic() - inicio, 0)
            log.warning("e-SAJ %s recusou a consulta de %s (HTTP %d) — "
                        "não insistimos; vai para conferência humana",
                        self.tribunal, mascarar(d), e.code)
            return [ResultadoProcesso(
                tribunal=self.tribunal, fonte=self.nome, cliente_id=cliente_id,
                status_casamento=REVISAO_MANUAL,
                motivo="e-SAJ %s respondeu HTTP %d" % (self.tribunal, e.code))]
        except Exception as e:
            AUDITORIA.anotar(self.nome, self.tribunal, "ERRO",
                             time.monotonic() - inicio, 0, str(e)[:100])
            return [ResultadoProcesso(
                tribunal=self.tribunal, fonte=self.nome, cliente_id=cliente_id,
                status_casamento=REVISAO_MANUAL,
                motivo="falha ao consultar e-SAJ %s: %s" % (self.tribunal, e))]

        if _CAPTCHA_REAL.search(corpo):
            log.warning("e-SAJ %s passou a exigir CAPTCHA — automação suspensa",
                        self.tribunal)
            return [ResultadoProcesso(
                tribunal=self.tribunal, fonte=self.nome, cliente_id=cliente_id,
                status_casamento=REVISAO_MANUAL,
                motivo="e-SAJ %s passou a exigir CAPTCHA — não contornamos"
                       % self.tribunal)]

        achados = self._extrair(corpo, cliente_id=cliente_id)
        AUDITORIA.anotar(self.nome, self.tribunal, "OK",
                         time.monotonic() - inicio, len(achados))
        log.info("e-SAJ %s: %s -> %d processo(s) de interesse",
                 self.tribunal, mascarar(d), len(achados))
        return achados

    def _extrair(self, corpo, cliente_id=None):
        """Lê o resultado da consulta, seja lista ou página de detalhe."""
        if _DETALHE.search(corpo) and not _BLOCO.search(corpo):
            return self._extrair_detalhe(corpo, cliente_id=cliente_id)
        return self._extrair_lista(corpo, cliente_id=cliente_id)

    def _extrair_detalhe(self, corpo, cliente_id=None):
        """Resultado único: o e-SAJ abre direto a página do processo."""
        numero = _campo_detalhe(corpo, "numeroProcesso")
        if not numero:
            return []
        classe = _campo_detalhe(corpo, "classeProcesso")
        assunto = _campo_detalhe(corpo, "assuntoProcesso")
        vara = _campo_detalhe(corpo, "varaProcesso")
        foro = _campo_detalhe(corpo, "foroProcesso")
        distribuicao = _campo_detalhe(corpo, "dataHoraDistribuicaoProcesso")

        autor = reu = ""
        bloco = re.search(r'(?is)id="tableTodasPartes"(.*?)</table>', corpo) or \
            re.search(r'(?is)id="tablePartesPrincipais"(.*?)</table>', corpo)
        if bloco:
            for tr in re.finditer(r"(?is)<tr[^>]*>(.*?)</tr>", bloco.group(1)):
                celulas = [_texto(c) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>",
                                                         tr.group(1))]
                if len(celulas) < 2:
                    continue
                papel = _sem_acento(celulas[0]).lower()
                # o nome vem grudado nos advogados: "Fulano Advogado: Beltrano"
                nome = re.split(r"(?i)\badvogad[oa]s?:", celulas[1])[0].strip()
                if papel.startswith(("reu", "requerid", "execut", "apreend")):
                    reu = nome
                elif papel.startswith(("autor", "requerent", "exeqte", "exequent",
                                       "credor", "reqte")):
                    autor = nome

        classificacao = classificar(
            classe_nome=classe, assuntos=[assunto] if assunto else [],
            banco_normalizado=bancos.normalizar_banco(autor))
        if not classificacao.eh_busca_apreensao:
            return []
        return [ResultadoProcesso(
            numero_processo=numero, tribunal=self.tribunal,
            classe_nome=classe, assunto=assunto,
            orgao_julgador=" · ".join(x for x in (foro, vara) if x),
            comarca=foro, autor=autor, reu=reu,
            banco_normalizado=bancos.descrever(autor),
            data_distribuicao=_data_iso(distribuicao),
            fonte="e-SAJ", status_casamento=CONFIRMADO,
            confianca=classificacao.confianca,
            motivo="%s. Identidade confirmada por CPF/CNPJ na consulta do %s"
                   % (classificacao.motivo, self.tribunal),
            cliente_id=cliente_id)]

    def _extrair_lista(self, corpo, cliente_id=None):
        """Vários resultados: o e-SAJ mostra a listagem."""
        foros = _FORO.findall(corpo)
        achados = []
        for i, bloco in enumerate(_BLOCO.findall(corpo)):
            m = _NUMERO.search(bloco)
            if not m:
                continue
            mc, ma = _CLASSE.search(bloco), _ASSUNTO.search(bloco)
            classe = _texto(mc.group(1)) if mc else ""
            assunto = _texto(ma.group(1)) if ma else ""

            autor = reu = ""
            for rotulo, nome in _PARTE.findall(bloco):
                rot, nom = _sem_acento(_texto(rotulo)).lower(), _texto(nome)
                if rot.startswith(("reu", "requerid", "execut", "apreend")):
                    reu = nom
                elif rot.startswith(("autor", "reqte", "requerent", "exeqte",
                                     "exequent", "credor")):
                    autor = nom

            classificacao = classificar(
                classe_nome=classe, assuntos=[assunto] if assunto else [],
                banco_normalizado=bancos.normalizar_banco(autor),
            )
            if not classificacao.eh_busca_apreensao:
                continue
            achados.append(ResultadoProcesso(
                numero_processo=m.group(1).strip(),
                tribunal=self.tribunal,
                classe_nome=classe,
                assunto=assunto,
                orgao_julgador=_texto(foros[i]) if i < len(foros) else "",
                autor=autor,
                reu=reu,
                banco_normalizado=bancos.descrever(autor),
                fonte="e-SAJ",
                # CPF bateu na origem: identidade confirmada (item 21).
                status_casamento=CONFIRMADO,
                confianca=classificacao.confianca,
                motivo="%s. Identidade confirmada por CPF na consulta do %s"
                       % (classificacao.motivo, self.tribunal),
                cliente_id=cliente_id,
            ))
        return achados
