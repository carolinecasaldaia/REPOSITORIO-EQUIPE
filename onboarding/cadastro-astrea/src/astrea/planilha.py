#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptador planilha: escreve os clientes prontos numa planilha de conferência.

Existe por dois motivos:

1. É a rede de segurança. Se o Astrea mudar a tela e a automação de navegador
   parar, ninguém fica sem cadastro: troca-se uma linha do .env e os clientes
   passam a sair em planilha, para conferir e lançar à mão.
2. É o formato que a Aurum aceita para migração em massa (a "planilha padrão"),
   caso um dia você queira subir um lote de uma vez.

Ele NÃO consulta duplicidade — e por isso NÃO afirma que o cliente foi
cadastrado. O status final vira SIMULADO/PENDENTE, nunca CADASTRADO.
"""

import csv
from datetime import datetime
from pathlib import Path

from .base import (AdaptadorAstrea, ResultadoBusca, ResultadoCadastro,
                   payload_contato, payload_caso)

COLUNAS = [
    ("tipo_pessoa", "Tipo de pessoa"),
    ("perfil", "Perfil"),
    ("nome", "Nome / Razão social"),
    ("cpf", "CPF"),
    ("cnpj", "CNPJ"),
    ("rg", "RG"),
    ("orgao_expedidor", "Órgão expedidor"),
    ("nacionalidade", "Nacionalidade"),
    ("estado_civil", "Estado civil"),
    ("profissao", "Profissão"),
    ("email", "E-mail"),
    ("telefone", "Telefone"),
    ("cep", "CEP"),
    ("logradouro", "Logradouro"),
    ("numero", "Número"),
    ("complemento", "Complemento"),
    ("bairro", "Bairro"),
    ("cidade", "Cidade"),
    ("uf", "UF"),
]

COLUNAS_EXTRA = [
    ("pasta", "Pasta de origem"),
    ("tipo_acao", "Tipo de ação"),
    ("parte_contraria", "Banco adverso"),
    ("objeto", "Veículo"),
    ("confianca", "Confiança"),
    ("observacoes", "Observações"),
]


class AdaptadorPlanilha(AdaptadorAstrea):

    nome = "planilha"
    escreve_no_astrea = False
    verifica_duplicidade = False

    def __init__(self, config, log):
        AdaptadorAstrea.__init__(self, config, log)
        self.arquivo = None
        self._linhas = []

    def conectar(self):
        self.config.pasta_relatorios.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y-%m-%d_%H%M")
        self.arquivo = self.config.pasta_relatorios / ("clientes-para-astrea_%s.csv"
                                                       % carimbo)
        self.log.info("Adaptador planilha: os clientes sairão em %s"
                      % self.arquivo.name)

    def buscar_por_documento(self, documento, nome_cliente=""):
        return ResultadoBusca(
            encontrado=False,
            detalhe="duplicidade NÃO verificada (adaptador planilha) — confira "
                    "no Astrea antes de importar")

    def cadastrar_contato(self, ficha):
        dados = payload_contato(ficha)
        caso = payload_caso(ficha)
        linha = {rotulo: dados.get(chave, "") for chave, rotulo in COLUNAS}
        linha["Pasta de origem"] = ficha.pasta_nome
        linha["Tipo de ação"] = caso.get("tipo_acao", "")
        linha["Banco adverso"] = caso.get("parte_contraria", "")
        linha["Veículo"] = caso.get("objeto", "")
        linha["Confiança"] = "%.2f" % ficha.confianca
        linha["Observações"] = " | ".join(ficha.observacoes)
        self._linhas.append(linha)
        self._gravar()
        return ResultadoCadastro(
            sucesso=False, astrea_id=None,
            detalhe="gravado na planilha %s (cadastro no Astrea continua manual)"
                    % self.arquivo.name)

    def criar_caso(self, ficha, contato_id):
        return ResultadoCadastro(
            sucesso=False,
            detalhe="dados do caso incluídos na planilha, na mesma linha do cliente")

    def _gravar(self):
        cabecalho = [rotulo for _, rotulo in COLUNAS] + \
                    [rotulo for _, rotulo in COLUNAS_EXTRA]
        with open(str(self.arquivo), "w", encoding="utf-8-sig", newline="") as fh:
            escritor = csv.DictWriter(fh, fieldnames=cabecalho, delimiter=";")
            escritor.writeheader()
            for linha in self._linhas:
                escritor.writerow({c: linha.get(c, "") for c in cabecalho})

    def encerrar(self):
        if self._linhas:
            self.log.ok("Planilha com %d cliente(s): %s"
                        % (len(self._linhas), self.arquivo))
