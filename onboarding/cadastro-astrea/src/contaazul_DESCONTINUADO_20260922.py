#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DESCONTINUADO em 22/09/2026 — nada mais importa este arquivo.

O OAuth2 do aplicativo criado no portal do Conta Azul nunca chegou a
autorizar de verdade (ver "E-MAIL PARA A CONTA AZUL.txt", na raiz do
projeto — suporte deles não respondeu ao ponto de destravar). A confirmação
da ENTRADA paga passou a ser feita pela API do Asaas: ver `src/asaas.py` e
`executar.abrir_casos_com_entrada_paga`. Mantido só como referência histórica
de como a integração teria funcionado, caso o Conta Azul volte a ser cogitado.

Conta Azul: conferir se a ENTRADA do cliente foi paga.

Regra do escritório (18/08/2026): o caso só é aberto no Astrea depois que o
boleto de entrada aparece pago aqui. Este módulo é só o portão — ele não abre
caso nenhum, apenas responde "pago" / "não pago" / "não achei".

Autenticação (API v2, OAuth2 sobre AWS Cognito):

    autorizar : https://auth.contaazul.com/login?response_type=code&...
    token     : POST https://auth.contaazul.com/oauth2/token  (Basic base64(id:secret))
    chamadas  : https://api-v2.contaazul.com/v1/...  com Bearer

O access_token dura 1 hora; o refresh_token é o que fica guardado em
~/.cadastro-astrea/contaazul.json (permissão 600, fora do Google Drive). O
client_id e o client_secret ficam no .env, gravados pela janela do macOS —
nunca passam por conversa, log ou terminal.
"""

import base64
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTORIZAR = "https://auth.contaazul.com/login"
TOKEN = "https://auth.contaazul.com/oauth2/token"
API = "https://api-v2.contaazul.com/v1"
ESCOPO = "openid profile aws.cognito.signin.user.admin"
# O endereço de retorno TEM que ser idêntico ao cadastrado no portal de
# desenvolvedores — o Conta Azul recusa qualquer outro. No aplicativo dela está
# https://contaazul.com, que não é um servidor nosso; por isso existe o modo
# "colar a URL": ela autoriza, o navegador cai no site do Conta Azul com o
# código na barra de endereço, e ela cola essa URL numa janela do macOS.
REDIRECT = "http://localhost:8765/callback"
# O que está cadastrado no aplicativo dela, no portal de desenvolvedores:
REDIRECT_PORTAL = "https://contaazul.com"
PORTA = 8765

PAGO = ("PAID", "RECEIVED", "SETTLED", "PAGO", "RECEBIDO", "LIQUIDADO")


class ErroContaAzul(Exception):
    """Falha ao falar com o Conta Azul (rede, autorização, resposta estranha)."""


# ---------------------------------------------------------------------------
# Guarda do refresh_token
# ---------------------------------------------------------------------------

def arquivo_de_token(pasta_dados) -> Path:
    return Path(pasta_dados) / "contaazul.json"


def _ler_guardado(pasta_dados) -> dict:
    caminho = arquivo_de_token(pasta_dados)
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _guardar(pasta_dados, dados: dict):
    caminho = arquivo_de_token(pasta_dados)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(str(caminho), 0o600)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post_token(client_id, client_secret, campos: dict) -> dict:
    corpo = urllib.parse.urlencode(campos).encode("utf-8")
    credencial = base64.b64encode(("%s:%s" % (client_id, client_secret)).encode("utf-8")).decode()
    pedido = urllib.request.Request(TOKEN, data=corpo, method="POST", headers={
        "Authorization": "Basic %s" % credencial,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            return json.loads(resposta.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as erro:
        detalhe = ""
        try:
            detalhe = erro.read().decode("utf-8", "replace")[:300]
        except Exception:                                   # pragma: no cover
            pass
        raise ErroContaAzul("O Conta Azul recusou (HTTP %s). %s" % (erro.code, detalhe))
    except urllib.error.URLError as erro:
        raise ErroContaAzul("Não consegui falar com o Conta Azul: %s" % erro.reason)


class _Recebedor(BaseHTTPRequestHandler):
    """Recebe o /callback do navegador e guarda o código de autorização."""

    codigo = None
    erro = None

    def do_GET(self):                                       # noqa: N802
        partes = urllib.parse.urlparse(self.path)
        campos = urllib.parse.parse_qs(partes.query)
        if partes.path.rstrip("/") == "/callback":
            _Recebedor.codigo = (campos.get("code") or [None])[0]
            _Recebedor.erro = (campos.get("error_description") or campos.get("error") or [None])[0]
        pagina = ("<html><meta charset='utf-8'><body style='font:16px -apple-system;padding:40px'>"
                  "<h2>%s</h2><p>Pode fechar esta janela e voltar para o Terminal.</p></body></html>"
                  % ("Conta Azul conectado." if _Recebedor.codigo else
                     "Não deu certo: %s" % (_Recebedor.erro or "sem código")))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(pagina.encode("utf-8"))

    def log_message(self, *_):                              # silêncio no terminal
        return


def extrair_codigo(texto: str) -> str:
    """Pega o `code=` de uma URL colada (ou aceita o código puro)."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    achado = re.search(r"[?&]code=([^&#\s]+)", texto)
    if achado:
        return urllib.parse.unquote(achado.group(1))
    return texto if re.match(r"^[A-Za-z0-9._~-]{8,}$", texto) else ""


def trocar_codigo(config, codigo: str, redirect: str) -> dict:
    """Troca o código de autorização pelos tokens e guarda o refresh_token."""
    resposta = _post_token(config.contaazul_client_id, config.contaazul_client_secret, {
        "grant_type": "authorization_code",
        "code": codigo,
        "redirect_uri": redirect,
    })
    if not resposta.get("refresh_token"):
        raise ErroContaAzul("O Conta Azul não devolveu refresh_token: %s" % str(resposta)[:200])
    _guardar(config.pasta_dados, {
        "refresh_token": resposta["refresh_token"],
        "access_token": resposta.get("access_token", ""),
        "expira_em": time.time() + int(resposta.get("expires_in", 3600)) - 60,
        "autorizado_em": time.strftime("%d/%m/%Y %H:%M"),
        "redirect": redirect,
    })
    return resposta


def endereco_de_autorizacao(config, redirect: str) -> str:
    return AUTORIZAR + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": config.contaazul_client_id,
        "redirect_uri": redirect,
        "scope": ESCOPO,
        "state": "cadastro-astrea",
    })


def autorizar(config, espera_s: int = 300) -> dict:
    """
    Abre o navegador para ela autorizar e guarda o refresh_token.

    É a única etapa que precisa de gente: o Conta Azul pede login e o código do
    aplicativo autenticador (2FA). Depois disso a automação se vira sozinha.
    """
    if not (config.contaazul_client_id and config.contaazul_client_secret):
        raise ErroContaAzul("Faltam o Client ID e o Client Secret do Conta Azul.")

    _Recebedor.codigo = _Recebedor.erro = None
    servidor = HTTPServer(("127.0.0.1", PORTA), _Recebedor)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    endereco = AUTORIZAR + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": config.contaazul_client_id,
        "redirect_uri": REDIRECT,
        "scope": ESCOPO,
        "state": "cadastro-astrea",
    })
    print("\n  Abrindo o navegador para você autorizar o acesso.")
    print("  Se não abrir sozinho, cole este endereço no navegador:\n")
    print("  %s\n" % endereco)
    webbrowser.open(endereco)

    limite = time.time() + espera_s
    while time.time() < limite and not (_Recebedor.codigo or _Recebedor.erro):
        time.sleep(1)
    servidor.shutdown()

    if _Recebedor.erro:
        raise ErroContaAzul("O Conta Azul respondeu: %s" % _Recebedor.erro)
    if not _Recebedor.codigo:
        raise ErroContaAzul("Ninguém autorizou dentro de %d segundos." % espera_s)

    resposta = _post_token(config.contaazul_client_id, config.contaazul_client_secret, {
        "grant_type": "authorization_code",
        "code": _Recebedor.codigo,
        "redirect_uri": REDIRECT,
    })
    if not resposta.get("refresh_token"):
        raise ErroContaAzul("O Conta Azul não devolveu refresh_token: %s" % str(resposta)[:200])
    _guardar(config.pasta_dados, {
        "refresh_token": resposta["refresh_token"],
        "access_token": resposta.get("access_token", ""),
        "expira_em": time.time() + int(resposta.get("expires_in", 3600)) - 60,
        "autorizado_em": time.strftime("%d/%m/%Y %H:%M"),
    })
    return resposta


def access_token(config) -> str:
    """Token válido, renovando pelo refresh_token quando preciso."""
    guardado = _ler_guardado(config.pasta_dados)
    if not guardado.get("refresh_token"):
        raise ErroContaAzul("O Conta Azul ainda não foi autorizado. "
                            "Use a opção 'Conectar o Conta Azul' no atalho.")
    if guardado.get("access_token") and guardado.get("expira_em", 0) > time.time():
        return guardado["access_token"]

    resposta = _post_token(config.contaazul_client_id, config.contaazul_client_secret, {
        "grant_type": "refresh_token",
        "refresh_token": guardado["refresh_token"],
    })
    if not resposta.get("access_token"):
        raise ErroContaAzul("Não consegui renovar o acesso ao Conta Azul. "
                            "Pode ser preciso autorizar de novo.")
    guardado["access_token"] = resposta["access_token"]
    guardado["expira_em"] = time.time() + int(resposta.get("expires_in", 3600)) - 60
    if resposta.get("refresh_token"):
        guardado["refresh_token"] = resposta["refresh_token"]
    _guardar(config.pasta_dados, guardado)
    return guardado["access_token"]


def chamar(config, caminho: str, parametros: dict = None) -> dict:
    """GET na API v2. `caminho` é relativo, ex.: '/financeiro/contas-a-receber'."""
    endereco = API + caminho
    if parametros:
        endereco += "?" + urllib.parse.urlencode(parametros)
    pedido = urllib.request.Request(endereco, headers={
        "Authorization": "Bearer %s" % access_token(config),
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            bruto = resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        detalhe = ""
        try:
            detalhe = erro.read().decode("utf-8", "replace")[:300]
        except Exception:                                   # pragma: no cover
            pass
        raise ErroContaAzul("HTTP %s em %s. %s" % (erro.code, caminho, detalhe))
    except urllib.error.URLError as erro:
        raise ErroContaAzul("Não consegui falar com o Conta Azul: %s" % erro.reason)
    try:
        return json.loads(bruto) if bruto.strip() else {}
    except ValueError:
        raise ErroContaAzul("Resposta que não é JSON em %s: %s" % (caminho, bruto[:150]))


# ---------------------------------------------------------------------------
# A pergunta que interessa
# ---------------------------------------------------------------------------

def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def situacao_do_pagamento(registro: dict) -> str:
    """Lê a situação de uma parcela sem depender do nome exato do campo."""
    for chave in ("status", "situacao", "situation", "paymentStatus", "state"):
        valor = registro.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip().upper()
    return ""


def esta_paga(registro: dict) -> bool:
    situacao = situacao_do_pagamento(registro)
    if situacao:
        return any(marca in situacao for marca in PAGO)
    # Sem campo de situação: só considera paga se houver data/valor de baixa.
    for chave in ("paidDate", "dataPagamento", "settlementDate", "paidValue", "valorPago"):
        if registro.get(chave):
            return True
    return False
