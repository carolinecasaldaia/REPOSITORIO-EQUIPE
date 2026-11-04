#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptador dry-run: não fala com o Astrea, não grava nada, não precisa de senha.

Serve para a homologação (item 17 do projeto): a automação lê as pastas, extrai,
valida, decide — e mostra na tela exatamente o que teria enviado.

Como não consegue consultar o Astrea, ele NÃO afirma que o cliente é novo.
Devolve "não verificado", e o orquestrador registra o cliente como
SIMULADO (MODO TESTE) em vez de CADASTRADO. Nada de fingir sucesso.
"""

from .base import AdaptadorAstrea, ResultadoBusca, ResultadoCadastro, payload_contato, payload_caso


class AdaptadorDryRun(AdaptadorAstrea):

    nome = "dry-run"
    escreve_no_astrea = False
    verifica_duplicidade = False

    def conectar(self):
        self.log.info("Adaptador dry-run: nada será enviado ao Astrea.")

    def buscar_por_documento(self, documento, nome_cliente=""):
        return ResultadoBusca(
            encontrado=False, astrea_id=None,
            detalhe="duplicidade NÃO verificada (modo dry-run, sem acesso ao Astrea)")

    def cadastrar_contato(self, ficha):
        dados = payload_contato(ficha)
        self.log.info("[TEST MODE] CLIENTE SERIA CADASTRADO")
        for rotulo, valor, confianca in ficha.resumo_para_tela():
            self.log.info("            %-18s %s   (confiança %.2f)"
                          % (rotulo + ":", valor, confianca))
        return ResultadoCadastro(
            sucesso=False, astrea_id=None,
            detalhe="simulação: %d campos seriam enviados" % len(dados))

    def criar_caso(self, ficha, contato_id):
        dados = payload_caso(ficha)
        if not dados:
            return ResultadoCadastro(sucesso=False, detalhe="sem dados de caso")
        self.log.info("[TEST MODE] CASO SERIA CRIADO: %s"
                      % dados.get("titulo", "(sem título)"))
        for chave, valor in sorted(dados.items()):
            if chave != "titulo":
                self.log.info("            %-18s %s" % (chave + ":", valor))
        return ResultadoCadastro(sucesso=False, detalhe="simulação de caso")
