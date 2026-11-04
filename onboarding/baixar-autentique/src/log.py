#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Log da automação: aparece na tela quando ela roda no clique e fica gravado em
~/.baixar-autentique/logs/AAAA-MM.log quando roda sozinha pelo agendador.

Nome de cliente aparece no log (é o que permite conferir o que aconteceu);
a chave da API, nunca — ela só é impressa mascarada, pelo config.
"""

from datetime import datetime
from pathlib import Path

CORES = {"OK": "\033[32m", "AVISO": "\033[33m", "ERRO": "\033[31m"}
FIM = "\033[0m"


class Log(object):
    def __init__(self, pasta, mostrar_na_tela: bool = True):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta / ("%s.log" % datetime.now().strftime("%Y-%m"))
        self.mostrar = mostrar_na_tela

    def _escrever(self, nivel: str, mensagem: str, na_tela: str = None):
        carimbo = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        try:
            with open(str(self.arquivo), "a", encoding="utf-8") as arquivo:
                arquivo.write("%s  %-5s %s\n" % (carimbo, nivel, mensagem))
        except OSError:
            pass
        if self.mostrar:
            if na_tela is None:
                cor = CORES.get(nivel)
                na_tela = ("%s%s%s" % (cor, mensagem, FIM)) if cor else mensagem
            print(na_tela)

    def titulo(self, texto: str):
        self._escrever("INFO", texto,
                       na_tela="\n\033[1m%s\033[0m\n%s" % (texto, "─" * 64))

    def info(self, mensagem: str):
        self._escrever("INFO", mensagem)

    def ok(self, mensagem: str):
        self._escrever("OK", mensagem)

    def aviso(self, mensagem: str):
        self._escrever("AVISO", mensagem)

    def erro(self, mensagem: str):
        self._escrever("ERRO", mensagem)

    def limpar_antigos(self, meses: int = 12):
        """Log velho é apagado — o relatório guarda o que interessa."""
        arquivos = sorted(self.pasta.glob("*.log"))
        if len(arquivos) > meses:
            for antigo in arquivos[:-meses]:
                try:
                    antigo.unlink()
                except OSError:
                    pass
