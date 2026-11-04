#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversa com a API do Autentique (GraphQL v2) e decide o que já está assinado.

Endpoint:  POST https://api.autentique.com.br/v2/graphql
Cabeçalho: Authorization: Bearer <chave>
Limite:    60 requisições por minuto (documentação oficial).

Só a biblioteca padrão do Python é usada aqui — nada de dependência externa
para falar HTTP; o único pacote instalado no ambiente é o pypdf, usado na
separação dos documentos.

O QUE CONTA COMO "TODAS AS PARTES ASSINARAM"
--------------------------------------------
O campo `files.signed` NÃO serve como sinal de conclusão: ele é um link fixo do
painel (`painel.autentique.com.br/documentos/<id>/assinado.pdf`) que existe
desde antes de qualquer assinatura. Quem responde isso é a lista `signatures`:
o documento está pronto quando toda assinatura tem `signed` preenchido e
nenhuma tem `rejected`. É a mesma contagem que o Autentique manda nos webhooks
(`signatures_count` / `signed_count` / `rejected_count`).
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

# Preferida: traz as contagens que o Autentique usa internamente.
QUERY_COMPLETA = """
query Documentos($limite: Int!, $pagina: Int!) {
  documents(limit: $limite, page: $pagina) {
    total
    data {
      id
      name
      created_at
      signatures_count
      signed_count
      rejected_count
      files { original signed }
      signatures {
        public_id
        name
        email
        created_at
        action { name }
        user { id name email }
        signed { created_at }
        rejected { created_at }
      }
    }
  }
}
"""

# Reserva: só campos que a documentação pública garante. É usada
# automaticamente se a conta/versão da API não conhecer as contagens.
QUERY_BASICA = """
query Documentos($limite: Int!, $pagina: Int!) {
  documents(limit: $limite, page: $pagina) {
    total
    data {
      id
      name
      created_at
      files { original signed }
      signatures {
        public_id
        name
        email
        created_at
        action { name }
        user { id name email }
        signed { created_at }
        rejected { created_at }
      }
    }
  }
}
"""

QUERY_PASTA = """
query DocumentosDaPasta($pasta: UUID!, $limite: Int!, $pagina: Int!) {
  documentsByFolder(folder_id: $pasta, limit: $limite, page: $pagina) {
    total
    data {
      id
      name
      created_at
      files { original signed }
      signatures {
        public_id
        name
        email
        created_at
        action { name }
        user { id name email }
        signed { created_at }
        rejected { created_at }
      }
    }
  }
}
"""


class ErroAutentique(Exception):
    """Falha ao falar com o Autentique (rede, chave inválida, erro do GraphQL)."""


class ChaveInvalida(ErroAutentique):
    """A chave da API foi recusada (401/403) — precisa gerar outra no painel."""


# ---------------------------------------------------------------------------
# Regras de leitura do documento
# ---------------------------------------------------------------------------

def _evento(valor):
    """`signed`/`rejected` vêm como {"created_at": ...} ou nulo."""
    if isinstance(valor, dict):
        return valor.get("created_at") or True
    return valor or None


def quem_e(assinatura: dict) -> str:
    """
    Nome de um participante.

    O `name` vem NULO nesta conta; quem tem o nome é `user.name`. Procurar só
    em `name` fazia a busca por cliente não achar ninguém (20/10/2026).
    """
    return (assinatura.get("name") or (assinatura.get("user") or {}).get("name")
            or assinatura.get("email") or "signatário sem nome")


def e_signatario(assinatura: dict) -> bool:
    """
    Este participante tem assinatura a dar?

    Quem CRIOU o documento também aparece na lista de `signatures`, mas sem
    `action` — não é signatário, é o autor. No contrato da Angela
    (20/10/2026) o autor era o contato@, que não assina; as quatro
    assinaturas estavam todas dadas, e ainda assim o documento ficava
    "faltando uma" e nunca era baixado. Assinante de verdade vem com
    action SIGN ou SIGN_AS_A_WITNESS.
    """
    return bool((assinatura.get("action") or {}).get("name"))


def resumo_assinaturas(documento: dict) -> dict:
    """Quantas partes existem, quantas assinaram, quem falta e quem recusou."""
    assinaturas = documento.get("signatures") or []
    faltam, recusaram, assinaram, autores = [], [], [], []
    for a in assinaturas:
        quem = quem_e(a)
        if not e_signatario(a):
            # Autor do documento. Se ele assinou, conta como assinatura (há
            # envelope em que a própria autora é parte); se não, é só o autor.
            if _evento(a.get("signed")):
                assinaram.append(quem)
            else:
                autores.append(quem)
            continue
        if _evento(a.get("rejected")):
            recusaram.append(quem)
        elif _evento(a.get("signed")):
            assinaram.append(quem)
        else:
            faltam.append(quem)
    return {
        "total": len(assinaturas) - len(autores),
        "assinaram": assinaram,
        "faltam": faltam,
        "recusaram": recusaram,
        "autores": autores,
    }


def todas_assinaram(documento: dict) -> bool:
    """Documento pronto: todo mundo assinou e ninguém recusou."""
    resumo = resumo_assinaturas(documento)
    if resumo["total"] == 0:
        return False
    if resumo["recusaram"] or resumo["faltam"]:
        return False

    # Quando a API devolve as contagens, elas mandam: protegem contra um
    # signatário adicionado depois e ainda não refletido na lista.
    total = documento.get("signatures_count")
    assinados = documento.get("signed_count")
    recusados = documento.get("rejected_count")
    if isinstance(total, int) and isinstance(assinados, int):
        if total <= 0 or assinados < total:
            return False
    if isinstance(recusados, int) and recusados > 0:
        return False
    return True


def quando_ficou_pronto(documento: dict) -> str:
    """Data/hora da última assinatura (ISO-8601), ou a criação como reserva."""
    datas = []
    for a in documento.get("signatures") or []:
        assinado = a.get("signed")
        if isinstance(assinado, dict) and assinado.get("created_at"):
            datas.append(assinado["created_at"])
    if datas:
        return max(datas)
    return documento.get("created_at") or ""


def para_datetime(texto: str):
    """ISO-8601 do Autentique ('2024-08-26T18:02:26.000000Z') -> datetime UTC."""
    if not texto:
        return None
    bruto = texto.strip().replace("Z", "+00:00")
    try:
        quando = datetime.fromisoformat(bruto)
    except ValueError:
        try:
            quando = datetime.strptime(texto[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return quando.astimezone(timezone.utc)


def signatarios_clientes(documento: dict, eh_do_escritorio) -> list:
    """
    Nomes que podem ser o cliente: todo signatário que não é do escritório.

    A ordem é a da lista do Autentique (normalmente o cliente vem primeiro).
    Quando o documento tem corresponsável, os dois aparecem aqui — quem casar
    com uma pasta existente vence, e o relatório mostra os dois.
    """
    nomes = []
    for a in documento.get("signatures") or []:
        email = a.get("email") or (a.get("user") or {}).get("email") or ""
        if eh_do_escritorio(email):
            continue
        nome = (a.get("name") or (a.get("user") or {}).get("name") or "").strip()
        if nome and nome not in nomes:
            nomes.append(nome)
    return nomes


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------

class Autentique(object):
    """Cliente mínimo da API. Uma instância por rodada."""

    def __init__(self, token: str, url: str = "https://api.autentique.com.br/v2/graphql",
                 timeout: int = 60, pausa_s: float = 1.0, abridor=None):
        self.token = token
        self.url = url
        self.timeout = timeout
        self.pausa_s = pausa_s          # respeita o limite de 60 req/min
        self._abridor = abridor or urllib.request.urlopen
        self._usar_contagens = True     # cai para a query básica se preciso
        self._ultima_chamada = 0.0

    # -- transporte ------------------------------------------------------

    def _esperar_a_vez(self):
        agora = time.monotonic()
        atraso = self.pausa_s - (agora - self._ultima_chamada)
        if atraso > 0:
            time.sleep(atraso)
        self._ultima_chamada = time.monotonic()

    def _post(self, query: str, variaveis: dict) -> dict:
        self._esperar_a_vez()
        corpo = json.dumps({"query": query, "variables": variaveis}).encode("utf-8")
        pedido = urllib.request.Request(
            self.url,
            data=corpo,
            headers={
                "Authorization": "Bearer %s" % self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "baixar-autentique/1.0 (escritório Caroline Macedo)",
            },
            method="POST",
        )
        try:
            with self._abridor(pedido, timeout=self.timeout) as resposta:
                bruto = resposta.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as erro:
            detalhe = ""
            try:
                detalhe = erro.read().decode("utf-8", "replace")[:400]
            except Exception:      # pragma: no cover - resposta ilegível
                pass
            if erro.code in (401, 403):
                raise ChaveInvalida(
                    "O Autentique recusou a chave da API (HTTP %s). Gere outra no "
                    "painel: Configurações → Chaves de API." % erro.code)
            if erro.code == 429:
                raise ErroAutentique(
                    "O Autentique pediu para diminuir o ritmo (limite de 60 "
                    "consultas por minuto). Tente de novo daqui a pouco.")
            raise ErroAutentique("Erro HTTP %s ao consultar o Autentique. %s"
                                 % (erro.code, detalhe))
        except urllib.error.URLError as erro:
            raise ErroAutentique("Não consegui falar com o Autentique: %s. "
                                 "Confira a conexão com a internet." % erro.reason)

        try:
            dados = json.loads(bruto)
        except ValueError:
            raise ErroAutentique("O Autentique respondeu algo que não é JSON: %s"
                                 % bruto[:200])

        if dados.get("errors"):
            mensagens = "; ".join(str(e.get("message", e)) for e in dados["errors"])
            if "unauthenticated" in mensagens.lower() or "unauthorized" in mensagens.lower():
                raise ChaveInvalida("O Autentique recusou a chave da API: %s" % mensagens)
            raise ErroAutentique("O Autentique recusou a consulta: %s" % mensagens)
        return dados.get("data") or {}

    # -- consultas -------------------------------------------------------

    def _pagina(self, pagina: int, limite: int, pasta: str = "") -> dict:
        variaveis = {"limite": limite, "pagina": pagina}
        if pasta:
            variaveis["pasta"] = pasta
            dados = self._post(QUERY_PASTA, variaveis)
            return dados.get("documentsByFolder") or {}

        if self._usar_contagens:
            try:
                dados = self._post(QUERY_COMPLETA, variaveis)
                return dados.get("documents") or {}
            except ErroAutentique as erro:
                # Conta antiga/versão sem os campos de contagem: segue com a
                # query documentada, que basta para decidir.
                if "Cannot query field" not in str(erro) and "não conhece" not in str(erro):
                    raise
                self._usar_contagens = False
        dados = self._post(QUERY_BASICA, variaveis)
        return dados.get("documents") or {}

    def listar(self, max_paginas: int = 5, limite: int = 60, pasta: str = "") -> list:
        """Documentos mais recentes primeiro, no máximo max_paginas × limite."""
        documentos, vistos = [], set()
        for pagina in range(1, max(1, max_paginas) + 1):
            bloco = self._pagina(pagina, limite, pasta)
            lote = bloco.get("data") or []
            for documento in lote:
                if documento.get("id") and documento["id"] not in vistos:
                    vistos.add(documento["id"])
                    documentos.append(documento)
            total = bloco.get("total")
            if len(lote) < limite:
                break
            if isinstance(total, int) and len(documentos) >= total:
                break
        return documentos

    def prontos(self, max_paginas: int = 5, limite: int = 60, pasta: str = "") -> list:
        """Só os documentos com assinatura de todas as partes."""
        return [d for d in self.listar(max_paginas, limite, pasta) if todas_assinaram(d)]

    # -- download --------------------------------------------------------

    def baixar_pdf(self, url: str, destino) -> int:
        """
        Baixa o PDF assinado. Devolve o tamanho em bytes.

        O link de `files.signed` é público (tem o hash do documento no caminho),
        mas o Autentique responde HTML quando algo dá errado — por isso o
        conteúdo é conferido: tem que começar com %PDF.
        """
        if not url:
            raise ErroAutentique("O documento não tem link de arquivo assinado.")
        pedido = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "application/pdf,*/*",
        })
        try:
            with self._abridor(pedido, timeout=self.timeout) as resposta:
                conteudo = resposta.read()
        except urllib.error.HTTPError as erro:
            raise ErroAutentique("Erro HTTP %s ao baixar o PDF assinado." % erro.code)
        except urllib.error.URLError as erro:
            raise ErroAutentique("Não consegui baixar o PDF assinado: %s" % erro.reason)

        if not conteudo[:5].startswith(b"%PDF"):
            raise ErroAutentique(
                "O link do documento não devolveu um PDF (vieram %d bytes começando "
                "com %r). Pode ser documento apagado no Autentique ou link expirado."
                % (len(conteudo), conteudo[:16]))

        destino = str(destino)
        with open(destino, "wb") as arquivo:
            arquivo.write(conteudo)
        return len(conteudo)

    # -- diagnóstico -----------------------------------------------------

    def testar(self) -> dict:
        """Uma consulta curta para validar a chave. Não baixa nada."""
        bloco = self._pagina(1, 5)
        lote = bloco.get("data") or []
        return {
            "total": bloco.get("total"),
            "amostra": [{"nome": d.get("name"),
                         "pronto": todas_assinaram(d),
                         "resumo": resumo_assinaturas(d)} for d in lote],
        }
