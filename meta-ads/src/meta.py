# -*- coding: utf-8 -*-
"""
Cliente mínimo da Graph API do Meta (Marketing API), só com a biblioteca padrão.

O token NUNCA aparece em mensagem de erro, log ou tela: tudo que sai daqui passa
por `_limpar`.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PASTA_DADOS = Path(os.environ.get("META_PASTA_DADOS") or Path.home() / ".meta-ads")
ARQUIVO_ENV = PASTA_DADOS / ".env"
HISTORICO = PASTA_DADOS / "historico.log"


class ErroMeta(Exception):
    pass


def ler_env(caminho=ARQUIVO_ENV):
    valores = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip().strip('"').strip("'")
    for chave in ("META_TOKEN", "META_API_VERSAO", "META_CONTA"):
        if os.environ.get(chave):
            valores[chave] = os.environ[chave]
    return valores


def gravar_no_env(chave, valor, caminho=ARQUIVO_ENV):
    caminho.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    novas, achou = [], False
    for linha in linhas:
        if linha.split("=", 1)[0].strip() == chave:
            novas.append(f"{chave}={valor}")
            achou = True
        else:
            novas.append(linha)
    if not achou:
        novas.append(f"{chave}={valor}")
    caminho.write_text("\n".join(novas) + "\n", encoding="utf-8")
    os.chmod(caminho, 0o600)


def mascarar(token):
    return token[:6] + "…" + token[-4:] if token and len(token) > 12 else "(vazio)"


class Meta:
    def __init__(self, token=None, versao=None):
        env = ler_env()
        self.token = token or env.get("META_TOKEN", "")
        self.versao = versao or env.get("META_API_VERSAO") or "v24.0"
        self.conta_padrao = env.get("META_CONTA", "")
        if not self.token:
            raise ErroMeta(f"Sem token. Rode: python3 executar.py chave  (fica em {ARQUIVO_ENV})")
        self.base = f"https://graph.facebook.com/{self.versao}/"

    def _limpar(self, texto):
        return str(texto).replace(self.token, "***")

    def _chamar(self, metodo, caminho, params=None, tentativas=7):
        params = dict(params or {})
        for k, v in list(params.items()):
            if isinstance(v, (dict, list)):
                params[k] = json.dumps(v)
        params["access_token"] = self.token
        dados = urllib.parse.urlencode(params)
        url = caminho if caminho.startswith("http") else self.base + caminho.lstrip("/")
        if metodo == "GET":
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + dados)
        else:
            req = urllib.request.Request(url, data=dados.encode(), method=metodo)
        for tentativa in range(tentativas):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                try:
                    erro = json.loads(e.read()).get("error", {})
                except ValueError:
                    erro = {"message": f"HTTP {e.code}"}
                # 4/17/32/613/80004 = limite de chamadas; espera (até 5 min) e tenta de novo
                if erro.get("code") in (4, 17, 32, 613, 80004) and tentativa < tentativas - 1:
                    espera = min(30 * 2 ** tentativa, 300)
                    print(f"  … o Meta pediu para ir devagar; esperando {espera}s", file=sys.stderr,
                          flush=True)
                    time.sleep(espera)
                    continue
                msg = erro.get("error_user_msg") or erro.get("message") or "erro desconhecido"
                raise ErroMeta(self._limpar(f"{msg} (código {erro.get('code')})")) from None
            except urllib.error.URLError as e:
                if tentativa < tentativas - 1:
                    time.sleep(3)
                    continue
                raise ErroMeta(self._limpar(f"Sem conexão com o Meta: {e.reason}")) from None

    def get(self, caminho, **params):
        return self._chamar("GET", caminho, params)

    def post(self, caminho, **params):
        resposta = self._chamar("POST", caminho, params)
        registrar(f"POST {caminho} {self._limpar(json.dumps(params, ensure_ascii=False))} -> "
                  f"{json.dumps(resposta, ensure_ascii=False)}")
        return resposta

    def delete(self, caminho):
        resposta = self._chamar("DELETE", caminho)
        registrar(f"DELETE {caminho} -> {json.dumps(resposta)}")
        return resposta

    def todos(self, caminho, limite=500, **params):
        """GET paginado: junta todas as páginas (até `limite` itens)."""
        params.setdefault("limit", 100)
        resposta = self.get(caminho, **params)
        itens = list(resposta.get("data", []))
        while len(itens) < limite and resposta.get("paging", {}).get("next"):
            proximo = resposta["paging"]["next"]
            # o "next" já traz o token na URL; tiramos para não duplicar
            partes = urllib.parse.urlsplit(proximo)
            q = [(k, v) for k, v in urllib.parse.parse_qsl(partes.query) if k != "access_token"]
            resposta = self._chamar("GET", urllib.parse.urlunsplit(
                partes._replace(query=urllib.parse.urlencode(q))))
            itens.extend(resposta.get("data", []))
        return itens[:limite]

    def conta(self, conta=None):
        conta = conta or self.conta_padrao
        if not conta:
            raise ErroMeta("Informe a conta (--conta act_...) ou defina META_CONTA no .env.")
        return conta if conta.startswith("act_") else "act_" + conta


def registrar(linha):
    PASTA_DADOS.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(HISTORICO, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + linha + "\n")
    os.chmod(HISTORICO, 0o600)
