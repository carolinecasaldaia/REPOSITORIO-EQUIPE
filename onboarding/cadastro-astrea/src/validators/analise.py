#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análise da ficha do cliente: o que foi extraído dá para cadastrar sozinho?

Aqui mora a regra mais importante do projeto: **na dúvida, conferência humana.**
Este módulo nunca preenche um campo que não veio de documento. Ele só decide
entre quatro caminhos:

    pode cadastrar  |  falta informação  |  há conflito  |  confiança baixa

E, nos três últimos, escreve exatamente o motivo para aparecer no relatório de
pendências.
"""

import unicodedata
from ..database import controle as St
from ..extractors.contrato_ho import Campo, vazio
from ..extractors import documentos as D

# Campos que exigem confiança alta por serem críticos (item 16 do projeto).
CAMPOS_CRITICOS = ("nome", "cpf", "rg", "cep", "logradouro", "telefone", "email")

ROTULOS = {
    "nome": "Nome completo", "cpf": "CPF", "cnpj": "CNPJ", "rg": "RG",
    "orgao_expedidor": "Órgão expedidor", "estado_civil": "Estado civil",
    "profissao": "Profissão", "nacionalidade": "Nacionalidade",
    "email": "E-mail", "telefone": "Telefone", "cep": "CEP",
    "logradouro": "Logradouro", "numero": "Número",
    "complemento": "Complemento", "bairro": "Bairro", "cidade": "Cidade",
    "uf": "UF", "data_nascimento": "Data de nascimento",
}


class Ficha(object):
    """Tudo que se sabe sobre um cliente, pronto para virar cadastro."""

    def __init__(self, pasta_nome="", caminho=""):
        self.pasta_nome = pasta_nome
        self.caminho = caminho
        self.pessoa = None                 # Pessoa (contratante)
        self.corresponsavel = None         # Pessoa | None — extraído, não cadastrado
        self.tipo_acao = vazio()
        self.banco_adverso = vazio()
        self.veiculo = vazio()
        self.documentos = []
        self.nao_interpretados = []
        self.pendencias = []
        self.divergencias = []
        self.observacoes = []
        self.status = None
        self.detalhe = ""
        self.confianca = 0.0

    # -- atalhos ---------------------------------------------------------

    def campo(self, nome) -> Campo:
        if self.pessoa is None:
            return vazio()
        return self.pessoa.campo(nome)

    def valor(self, nome) -> str:
        return self.campo(nome).valor

    @property
    def nome(self):
        return self.valor("nome")

    @property
    def cpf(self):
        return self.valor("cpf") or self.valor("cnpj")

    @property
    def pessoa_juridica(self) -> bool:
        return bool(self.valor("cnpj")) and not bool(self.valor("cpf"))

    def pode_cadastrar(self) -> bool:
        return self.status is None

    def como_dict(self):
        return {
            "pasta": self.pasta_nome,
            "pessoa": self.pessoa.como_dict() if self.pessoa else None,
            "corresponsavel": (self.corresponsavel.como_dict()
                               if self.corresponsavel else None),
            "tipo_acao": self.tipo_acao.como_dict(),
            "banco_adverso": self.banco_adverso.como_dict(),
            "veiculo": self.veiculo.como_dict(),
            "documentos": [d.como_dict() for d in self.documentos],
            "nao_interpretados": list(self.nao_interpretados),
            "pendencias": list(self.pendencias),
            "divergencias": list(self.divergencias),
            "observacoes": list(self.observacoes),
            "confianca": round(self.confianca, 2),
            "status": self.status,
            "detalhe": self.detalhe,
        }

    def resumo_para_tela(self):
        """O que seria enviado ao Astrea — usado pelo TEST_MODE."""
        linhas = []
        for nome in ("nome", "cpf", "cnpj", "rg", "orgao_expedidor",
                     "nacionalidade", "estado_civil", "profissao", "email",
                     "telefone", "cep", "logradouro", "numero", "complemento",
                     "bairro", "cidade", "uf"):
            campo = self.campo(nome)
            if campo.preenchido:
                linhas.append((ROTULOS.get(nome, nome), campo.valor,
                               round(campo.confianca, 2)))
        return linhas


def _sem_acento_maiusculo(texto):
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c)).upper().strip()


def _mesma_pessoa(nome_a, nome_b) -> bool:
    """
    Comparação tolerante de nomes. A conta de luz costuma abreviar
    ('EDGARD JOSE SANTOS B OLIVEIRA' x 'EDGARD JOSE SANTOS BARROS OLIVEIRA'),
    então comparar palavra por palavra geraria alarme falso: comparamos o
    primeiro e o último nome.
    """
    a = _sem_acento_maiusculo(nome_a).split()
    b = _sem_acento_maiusculo(nome_b).split()
    if not a or not b:
        return True
    return a[0] == b[0] and a[-1] == b[-1]


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------

def analisar(ficha: Ficha, obrigatorios, limiar: float) -> Ficha:
    """
    Preenche pendências, divergências e status da ficha.

    status None = liberada para cadastro automático.
    """
    if ficha.pessoa is None:
        ficha.status = St.PENDENTE
        ficha.detalhe = ficha.detalhe or "Não foi possível extrair a qualificação do cliente."
        return ficha

    _checar_obrigatorios(ficha, obrigatorios)
    _checar_invalidos(ficha)
    _checar_divergencias(ficha)
    _calcular_confianca(ficha, limiar)

    if ficha.pendencias:
        ficha.status = St.PENDENTE
        ficha.detalhe = "; ".join(ficha.pendencias)
    elif ficha.divergencias:
        ficha.status = St.DIVERGENTE
        ficha.detalhe = "; ".join(ficha.divergencias)
    return ficha


def _checar_obrigatorios(ficha: Ficha, obrigatorios):
    for nome in obrigatorios:
        campo = ficha.campo(nome)
        if nome == "cpf" and ficha.campo("cnpj").preenchido:
            continue                                   # pessoa jurídica
        if not campo.preenchido:
            ficha.pendencias.append(
                "%s não localizado nos documentos" % ROTULOS.get(nome, nome))


# Campos que identificam a pessoa: se estiverem errados, o cadastro para.
CAMPOS_DE_IDENTIDADE = ("nome", "cpf", "cnpj")


def _checar_invalidos(ficha: Ficha):
    """
    Campo inválido nunca é enviado ao Astrea.

    Se for de identidade (nome, CPF, CNPJ), o cadastro inteiro para e vira
    pendência. Se for acessório — um telefone truncado no contrato, um e-mail
    com erro de digitação — o campo é **descartado** e registrado em
    observação: cadastrar o cliente sem o telefone é melhor do que travar o
    cliente inteiro por causa dele, e melhor ainda do que gravar um número
    que se sabe estar errado.
    """
    for nome in ficha.pessoa.CAMPOS:
        campo = ficha.campo(nome)
        if not campo.preenchido or campo.valido or not campo.motivo:
            continue
        rotulo = ROTULOS.get(nome, nome)
        if nome in CAMPOS_DE_IDENTIDADE:
            ficha.pendencias.append("%s inválido (%s)" % (rotulo, campo.motivo))
            continue
        ficha.observacoes.append(
            "%s NÃO foi cadastrado: %s. Valor que consta no contrato: '%s'. "
            "Conferir e lançar à mão se for o caso."
            % (rotulo, campo.motivo, campo.valor))
        setattr(ficha.pessoa, nome,
                Campo("", 0.0, False, campo.motivo, campo.origem, campo.valor))


# Confiança do CPF lido da identidade por OCR. Abaixo do que vem do contrato
# (0.97) e acima do limiar padrão (0.8): cadastra, mas fica registrado que o
# número não veio do contrato assinado.
CONFIANCA_CPF_DA_IDENTIDADE = 0.90


def _completar_cpf_pela_identidade(ficha: Ficha):
    """
    Contrato sem CPF: aproveita o que está escrito na CNH/RG da pasta.

    Até 14/10/2026 o CPF só era procurado no contrato de honorários. Quando o
    contrato vinha sem ele, o cliente virava "CPF não localizado nos
    documentos" mesmo com a CNH na pasta e o número legível nela (foi o caso
    da Priscila, 13/10/2026).

    Cadastrar CPF errado é muito pior do que uma pendência, então só aproveita
    quando as quatro condições valem ao mesmo tempo:

      · o número vem DEPOIS do rótulo "CPF" no documento (CNH tem vários
        números longos que passariam por CPF se a busca fosse por formato);
      · passa no dígito verificador;
      · o primeiro nome E o sobrenome do cliente aparecem no documento —
        mesma prova de titularidade usada no comprovante de residência;
      · há um único candidato. Dois CPFs diferentes na mesma identidade é
        sinal de leitura suja: fica pendente para ela conferir.
    """
    identidades = D.do_tipo(ficha.documentos, "cnh", "rg", "identidade")
    partes = _sem_acento_maiusculo(ficha.nome).split()
    if not partes:
        return

    candidatos = {}
    for documento in identidades:
        texto = _sem_acento_maiusculo(documento.texto or "")
        if not texto:
            continue
        if partes[0] not in texto or (len(partes) >= 2 and partes[-1] not in texto):
            continue                     # identidade de outra pessoa (ou ilegível)
        for cpf in D.cpfs_rotulados(documento):
            candidatos.setdefault(cpf, documento.nome)

    if not candidatos:
        return
    if len(candidatos) > 1:
        ficha.observacoes.append(
            "A identidade na pasta tem mais de um CPF legível (%s) — não "
            "aproveitei nenhum para não arriscar cadastrar o errado."
            % ", ".join(sorted(candidatos)))
        return

    cpf, arquivo = list(candidatos.items())[0]
    ficha.pessoa.cpf = Campo(cpf, CONFIANCA_CPF_DA_IDENTIDADE, True, "",
                             origem=arquivo)
    ficha.observacoes.append(
        "CPF não constava no contrato de honorários: foi lido de '%s' por "
        "reconhecimento de imagem e confere no dígito verificador. O nome do "
        "cliente aparece no documento. Vale conferir." % arquivo)


def _checar_divergencias(ficha: Ficha):
    """
    Compara o contrato com o comprovante de residência, quando dá.

    Uma conta de luz em PDF quase sempre tem camada de texto, mas nem sempre a
    parte que interessa: às vezes só o cabeçalho da distribuidora é texto, e o
    endereço do cliente está dentro de uma imagem. Nesse caso o único CEP
    legível é o **da concessionária** — e acusar divergência ali seria alarme
    falso em quase todo mundo (aconteceu em 6 das 51 pastas no teste).

    Por isso o CEP só vira DIVERGÊNCIA quando há prova de que se leu mesmo o
    bloco do cliente: o sobrenome dele aparecer no documento. Fora disso, fica
    registrado como observação para conferência, sem travar o cadastro.
    """
    # Declaração de residência assinada manda mais que a conta de luz: é o
    # documento que o escritório usa justamente para quem não tem comprovante
    # no próprio nome (decisão dela, 14/10/2026, no caso do Leanderson). Se
    # ela confirma o CEP do contrato, está conferido e não se discute mais.
    ceps_declarados = D.ceps_da_declaracao(ficha.documentos)
    if ficha.valor("cep") and ficha.valor("cep") in ceps_declarados:
        ficha.observacoes.append(
            "Endereço conferido pela declaração de residência assinada (CEP %s)."
            % ficha.valor("cep"))
        return

    if ficha.valor("cep") and ceps_declarados:
        # Dois documentos assinados dizendo CEPs diferentes é contradição de
        # verdade, não leitura suja de conta de luz: ela decide qual vale.
        ficha.divergencias.append(
            "CEP do contrato (%s) não confere com o da declaração de "
            "residência assinada (lá consta: %s)"
            % (ficha.valor("cep"), ", ".join(ceps_declarados[:3])))
        return

    conferencia = D.conferir_no_comprovante(ficha.documentos)
    if conferencia is None:
        return

    if not conferencia.ceps and conferencia.ceps_do_emissor:
        ficha.observacoes.append(
            "Não foi possível conferir o endereço pelo comprovante '%s': o(s) "
            "CEP(s) legíveis no arquivo (%s) estão junto do CNPJ de quem "
            "emitiu a conta, então são da empresa, não do cliente."
            % (conferencia.arquivo, ", ".join(conferencia.ceps_do_emissor[:2])))

    partes = _sem_acento_maiusculo(ficha.nome).split()
    texto = _sem_acento_maiusculo(conferencia.texto)
    tem_primeiro = bool(partes) and partes[0] in texto
    tem_sobrenome = len(partes) >= 2 and partes[-1] in texto

    if conferencia.ceps and ficha.valor("cep"):
        if conferencia.confere_cep(ficha.valor("cep")):
            ficha.observacoes.append(
                "Endereço conferido: o CEP do contrato aparece no comprovante "
                "de residência (%s)." % conferencia.arquivo)
        elif tem_sobrenome:
            ficha.divergencias.append(
                "CEP do contrato (%s) não confere com o do comprovante de "
                "residência '%s', que está no nome do cliente (lá consta: %s)"
                % (ficha.valor("cep"), conferencia.arquivo,
                   ", ".join(conferencia.ceps[:4])))
        else:
            ficha.observacoes.append(
                "Não foi possível conferir o endereço pelo comprovante '%s': o "
                "CEP legível no arquivo (%s) parece ser o da concessionária, "
                "não o do cliente. Conferir se houver dúvida."
                % (conferencia.arquivo, ", ".join(conferencia.ceps[:2])))

    if texto and tem_primeiro and not tem_sobrenome:
        ficha.observacoes.append(
            "Conferir titularidade: o comprovante de residência '%s' pode estar "
            "em nome de terceiro (o sobrenome de %s não aparece nele)."
            % (conferencia.arquivo, ficha.nome))

    if conferencia.cpf_mascarado and ficha.valor("cpf"):
        if not D.cpf_compativel_com_mascara(ficha.valor("cpf"),
                                            conferencia.cpf_mascarado):
            # Este é objetivo: os dígitos visíveis do CPF simplesmente não batem.
            ficha.divergencias.append(
                "CPF do contrato não confere com os dígitos visíveis no "
                "comprovante de residência '%s'" % conferencia.arquivo)


def _calcular_confianca(ficha: Ficha, limiar: float):
    """
    Confiança da ficha = menor confiança entre os campos críticos preenchidos.

    Campo crítico abaixo do limiar não é cadastrado às cegas: vai para
    conferência humana, como manda o item 16 do projeto.
    """
    criticos = [(n, ficha.campo(n)) for n in CAMPOS_CRITICOS
                if ficha.campo(n).preenchido]
    if not criticos:
        ficha.confianca = 0.0
        return
    ficha.confianca = min(c.confianca for _, c in criticos)
    for nome, campo in criticos:
        if campo.confianca < limiar:
            ficha.divergencias.append(
                "%s com confiança baixa (%.2f, mínimo %.2f) — conferir antes de "
                "cadastrar" % (ROTULOS.get(nome, nome), campo.confianca, limiar))


# ---------------------------------------------------------------------------
# Montagem da ficha
# ---------------------------------------------------------------------------

def montar(pasta_nome, caminho, resultado_contrato, documentos,
           extrair_corresponsavel=True) -> Ficha:
    ficha = Ficha(pasta_nome, str(caminho))
    ficha.documentos = documentos
    ficha.nao_interpretados = [
        {"arquivo": d.nome, "tipo": d.tipo, "motivo": d.motivo_ilegivel}
        for d in D.ilegiveis(documentos)
    ]

    if resultado_contrato is None:
        ficha.status = St.PENDENTE
        ficha.detalhe = ("Contrato de honorários não localizado na pasta — sem ele "
                         "não há fonte confiável para a qualificação do cliente.")
        return ficha

    if resultado_contrato.erros:
        ficha.status = St.PENDENTE
        ficha.detalhe = "; ".join(resultado_contrato.erros)
        ficha.pendencias.extend(resultado_contrato.erros)
        return ficha

    ficha.pessoa = resultado_contrato.contratante
    ficha.tipo_acao = resultado_contrato.tipo_acao
    ficha.banco_adverso = resultado_contrato.banco_adverso
    ficha.veiculo = getattr(resultado_contrato, "veiculo", vazio())
    ficha.observacoes.extend(resultado_contrato.observacoes)
    ficha.observacoes.extend(resultado_contrato.contratante.observacoes)

    if not resultado_contrato.contratante.cpf.valor:
        _completar_cpf_pela_identidade(ficha)

    if resultado_contrato.responsavel and extrair_corresponsavel:
        ficha.corresponsavel = resultado_contrato.responsavel
        ficha.observacoes.append(
            "Corresponsável identificado no contrato (%s) — NÃO cadastrado no "
            "Astrea, conforme configuração. Avaliar manualmente."
            % (resultado_contrato.responsavel.nome.valor or "sem nome"))

    if ficha.nao_interpretados:
        ficha.observacoes.append(
            "%d documento(s) não interpretados (ver relatório) — não impedem o "
            "cadastro porque a qualificação veio do contrato assinado."
            % len(ficha.nao_interpretados))
    return ficha
