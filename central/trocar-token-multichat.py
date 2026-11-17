#!/usr/bin/env python3
"""Troca o token da Multichat360 guardado no Porta-chaves (usado pelo painel Atendimentos da Central).

Uso:  /usr/bin/python3 trocar-token-multichat.py
Cole o token (não aparece na tela) e aperte Enter. Antes de gravar, testa na Multichat;
se a plataforma recusar, mantém o token antigo.

Por que não usar `security add-generic-password -w` direto: o prompt dele corta em 128
caracteres e o token da Multichat tem ~300.
"""
import getpass
import subprocess
import sys
import urllib.error
import urllib.request

URL = "https://new4api.multichat360.com.br/statistics-tickets-channels?startDate=2026-01-01&endDate=2026-01-02"


def main():
    token = getpass.getpass("Cole o token da Multichat (não aparece na tela) e aperte Enter: ").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if "token=" in token:  # colou a URL inteira da API externa
        token = token.split("token=", 1)[1].split("&", 1)[0]
    if token.count(".") != 2:
        sys.exit("Isso não parece um token completo (deveria ter 3 partes separadas por ponto). Nada foi gravado.")
    req = urllib.request.Request(URL, headers={"Authorization": f"Bearer {token}", "User-Agent": "central-escritorio"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"A Multichat recusou esse token (HTTP {e.code}). Nada foi gravado; o token antigo continua.")
    except Exception as e:
        sys.exit(f"Não consegui testar na Multichat ({e}). Nada foi gravado.")
    subprocess.run(["security", "add-generic-password", "-U", "-s", "multichat360", "-a", "token", "-w", token],
                   check=True)
    print("Token testado e gravado. Recarregue o painel Atendimentos na Central.")


if __name__ == "__main__":
    main()
