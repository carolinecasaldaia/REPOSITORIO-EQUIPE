"""Cliente HTTP com controle de ritmo, novas tentativas e auditoria.

Três garantias que o projeto exige:
  1. nunca ultrapassar o limite de requisições publicado pela fonte;
  2. tentar de novo com espera crescente quando o erro for transitório;
  3. registrar toda consulta (item 17 da especificação) sem CPF completo.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

from src.config import ajustes
from src.util.log import obter

log = obter("http")

# Erros que valem nova tentativa. 429 = excesso de requisições; 5xx = falha do servidor.
_RETENTAR = {408, 425, 429, 500, 502, 503, 504}


class LimiteExcedido(Exception):
    """A fonte recusou por excesso de requisições e as tentativas se esgotaram."""


class FalhaConsulta(Exception):
    """Erro definitivo na consulta (4xx que não é 429, resposta ilegível)."""


class Limitador:
    """Token bucket com pausa geral.

    O DJEN não se comporta como um balde comum: quando o limite estoura, ele
    devolve 429 e **continuar pedindo mantém o castigo vivo** — o
    `x-ratelimit-reset` fica congelado e o `retry-after` vem negativo. Medido em
    18/08/2026: insistindo a cada 3,5s, 12 tentativas seguidas falharam.

    Por isso, além do balde, existe `pausar()`: ao receber 429 o cliente manda
    todo mundo parar de vez, e ninguém envia nada até a pausa terminar.
    """

    def __init__(self, por_minuto):
        self.por_minuto = max(1, int(por_minuto))
        self._marcas = deque()
        self._trava = threading.Lock()
        self._pausa_ate = 0.0

    def pausar(self, segundos):
        with self._trava:
            self._pausa_ate = max(self._pausa_ate, time.monotonic() + segundos)

    def aguardar(self):
        while True:
            with self._trava:
                agora = time.monotonic()
                if agora < self._pausa_ate:
                    espera = self._pausa_ate - agora
                else:
                    while self._marcas and agora - self._marcas[0] >= 60.0:
                        self._marcas.popleft()
                    if len(self._marcas) < self.por_minuto:
                        self._marcas.append(agora)
                        return
                    espera = 60.0 - (agora - self._marcas[0]) + 0.05
            time.sleep(max(0.05, espera))


class Auditoria:
    """Guarda o registro de cada consulta feita. Sem CPF, sem nome completo."""

    def __init__(self):
        self.registros = []

    def anotar(self, provedor, tribunal, status, duracao_s, qtd_resultados, detalhe=""):
        self.registros.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provedor": provedor,
            "tribunal": tribunal,
            "status": status,
            "duracao_s": round(duracao_s, 3),
            "qtd_resultados": qtd_resultados,
            "detalhe": detalhe[:200],
        })

    def resumo(self):
        ok = sum(1 for r in self.registros if r["status"] == "OK")
        return {
            "consultas": len(self.registros),
            "sucesso": ok,
            "erros": len(self.registros) - ok,
            "duracao_total_s": round(sum(r["duracao_s"] for r in self.registros), 1),
        }


AUDITORIA = Auditoria()


class Cliente:
    def __init__(self, nome, por_minuto, cabecalhos=None, tentativas=None):
        self.nome = nome
        self.limitador = Limitador(por_minuto)
        self.cabecalhos = dict(cabecalhos or {})
        self.cabecalhos.setdefault(
            "User-Agent",
            "RADAR-BA/1.0 (Caroline Macedo Advocacia; monitoramento de carteira propria)",
        )
        self.tentativas = tentativas or ajustes.TENTATIVAS_MAX

    def _abrir(self, url, corpo, metodo, timeout):
        dados = None
        cab = dict(self.cabecalhos)
        if corpo is not None:
            dados = json.dumps(corpo).encode("utf-8")
            cab["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()

    def pedir(self, url, corpo=None, metodo="GET", timeout=90, tribunal="-"):
        """Faz a requisição respeitando o ritmo e tentando de novo se preciso."""
        inicio = time.monotonic()
        ultimo = None
        for tentativa in range(1, self.tentativas + 1):
            self.limitador.aguardar()
            try:
                status, bruto = self._abrir(url, corpo, metodo, timeout)
                texto = bruto.decode("utf-8", errors="replace")
                try:
                    dados = json.loads(texto)
                except ValueError:
                    AUDITORIA.anotar(self.nome, tribunal, "ERRO_JSON",
                                     time.monotonic() - inicio, 0, texto[:120])
                    raise FalhaConsulta("resposta não é JSON válido")
                AUDITORIA.anotar(self.nome, tribunal, "OK", time.monotonic() - inicio,
                                 _contar(dados))
                return dados
            except urllib.error.HTTPError as e:
                ultimo = e
                if e.code not in _RETENTAR or tentativa == self.tentativas:
                    AUDITORIA.anotar(self.nome, tribunal, "HTTP_%d" % e.code,
                                     time.monotonic() - inicio, 0)
                    if e.code == 429:
                        raise LimiteExcedido("limite de requisições excedido em %s" % self.nome)
                    raise FalhaConsulta("HTTP %d em %s" % (e.code, self.nome))
                espera = _espera(e, tentativa)
                if e.code == 429:
                    # ninguém mais envia nada até a pausa passar
                    self.limitador.pausar(espera)
                log.warning("%s HTTP %d — nova tentativa em %.0fs (%d/%d)",
                            self.nome, e.code, espera, tentativa, self.tentativas)
                time.sleep(espera)
            except (urllib.error.URLError, OSError) as e:
                ultimo = e
                if tentativa == self.tentativas:
                    AUDITORIA.anotar(self.nome, tribunal, "REDE",
                                     time.monotonic() - inicio, 0, str(e)[:120])
                    raise FalhaConsulta("falha de rede em %s: %s" % (self.nome, e))
                espera = 2.0 ** tentativa
                log.warning("%s falha de rede — nova tentativa em %.0fs (%d/%d)",
                            self.nome, espera, tentativa, self.tentativas)
                time.sleep(espera)
        raise FalhaConsulta("esgotadas as tentativas em %s: %s" % (self.nome, ultimo))

    def pedir_get(self, caminho, parametros=None, **kw):
        url = caminho
        if parametros:
            limpos = {k: v for k, v in parametros.items() if v not in (None, "")}
            url += "?" + urllib.parse.urlencode(limpos)
        return self.pedir(url, metodo="GET", **kw)


def _espera(erro, tentativa):
    """Quanto esperar antes de tentar de novo.

    Cuidado com o DJEN: ele manda `retry-after` NEGATIVO (medido: -57, -61,
    -64...) e um `x-ratelimit-reset` que não avança enquanto continuamos
    pedindo. Valor negativo é descartado, e todo 429 tem piso de 60s — insistir
    antes disso só renova o castigo.
    """
    cabecalho = getattr(erro, "headers", None)
    if cabecalho:
        for nome in ("retry-after", "Retry-After"):
            v = cabecalho.get(nome)
            if v:
                try:
                    seg = float(v)
                    if seg > 0:
                        return min(seg + 1, 180)
                except ValueError:
                    pass
        reset = cabecalho.get("x-ratelimit-reset")
        if reset:
            try:
                faltam = float(reset) - time.time()
                if 0 < faltam <= 300:
                    return faltam + 2
            except ValueError:
                pass
    if getattr(erro, "code", 0) == 429:
        return min(60.0 * tentativa, 180)
    return min(2.0 ** tentativa + 1, 90)


def _contar(dados):
    if isinstance(dados, dict):
        if "items" in dados and isinstance(dados["items"], list):
            return len(dados["items"])
        if "hits" in dados and isinstance(dados["hits"], dict):
            return len(dados["hits"].get("hits") or [])
    return 0
