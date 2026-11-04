#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Asaas: conferir se a ENTRADA do cliente foi paga.

Regra do escritório (22/09/2026): o caso só é aberto no Astrea depois que a
cobrança de entrada aparece paga aqui. Este módulo é só o portão — ele não
abre caso nenhum, apenas responde "pago" / "não pago" / "não achei".

Autenticação: chave de API única (Asaas > Integrações > Chaves API), enviada
no cabeçalho `access_token`. Sem OAuth, sem token que expira — é o que torna
a checagem automática possível sem intervenção dela a cada rodada.

A cobrança de entrada é identificada pela DESCRIÇÃO: sempre começa com
"ENTRADA" (decisão dela, 22/09/2026; amostragem confirmada em três clientes
reais — Wellingta, Vektor Pharma e Eber Roberto — inclusive um caso em que o
Asaas gravou "Entrada" com caixa diferente, por isso a comparação abaixo
ignora maiúscula/minúscula). Mensalidade de honorários em atraso usa outro
texto ("Honorários em atraso referente a ...") e nunca é confundida com isto.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.asaas.com/v3"

# Status do Asaas que contam como "pago" para a nossa regra. RECEIVED_IN_CASH
# é o pagamento registrado manualmente (dinheiro/PIX fora do boleto); os
# outros dois são o fluxo normal de boleto/cartão/PIX pela plataforma.
STATUS_PAGO = ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH")

TEXTO_ENTRADA_PADRAO = "ENTRADA"

# Pagamento à vista (decisão dela, 19/10/2026, no caso da Dione): o cliente
# quitou tudo de uma vez e a cobrança no Asaas se chamava "AÇÃO DE BUSCA E
# APREENSÃO", não "ENTRADA" — a automação nunca abriria o caso. Agora uma
# cobrança quitada que cubra o contrato inteiro vale como entrada paga.
#
# A fração existe porque o valor pago raramente é igual ao do contrato: pode
# vir com juros do cartão (a Dione pagou R$ 4.948,19 por um contrato de
# R$ 4.497,00) ou com desconto à vista. Fica em 90% porque entrada e parcela
# são sempre MUITO menores que o total — nenhuma delas chega perto disso, e é
# isso que impede um pagamento parcial de passar por quitação.
FRACAO_A_VISTA = 0.90


class ErroAsaas(Exception):
    """Falha ao falar com o Asaas (rede, chave inválida, resposta estranha)."""


def _chamar(caminho: str, api_key: str, parametros: dict = None) -> dict:
    if not api_key:
        raise ErroAsaas("ASAAS_API_KEY não configurada.")
    url = BASE_URL + caminho
    if parametros:
        url += "?" + urllib.parse.urlencode(parametros)
    requisicao = urllib.request.Request(url, headers={
        "access_token": api_key,
        "User-Agent": "cadastro-astrea (integracao interna)",
    })
    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        corpo = erro.read().decode("utf-8", "replace")
        raise ErroAsaas("Asaas respondeu %s em %s: %s"
                        % (erro.code, caminho, corpo[:300])) from erro
    except urllib.error.URLError as erro:
        raise ErroAsaas("Sem conexão com o Asaas: %s" % erro) from erro
    except ValueError as erro:
        raise ErroAsaas("Resposta do Asaas não é JSON válido: %s" % erro) from erro


def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def buscar_cliente_por_cpf(cpf_cnpj: str, api_key: str):
    """Devolve o id do cliente no Asaas (cus_...) ou None se não achar."""
    digitos = _so_digitos(cpf_cnpj)
    if not digitos:
        return None
    resposta = _chamar("/customers", api_key, {"cpfCnpj": digitos})
    dados = resposta.get("data") or []
    return dados[0]["id"] if dados else None


def entrada_paga(cpf_cnpj: str, api_key: str, texto_entrada: str = TEXTO_ENTRADA_PADRAO):
    """
    Confere se existe cobrança de ENTRADA paga para este CPF/CNPJ.

    Devolve o dicionário da cobrança do Asaas (id, value, paymentDate, ...) se
    achar uma cujo status é de pago (`STATUS_PAGO`) e cuja descrição começa
    com `texto_entrada`, sem diferenciar maiúscula/minúscula. Devolve None se
    o cliente não existir no Asaas, não tiver cobrança de entrada, ou a
    entrada ainda estiver em aberto/vencida.
    """
    # "cus_..." é o id do cadastro no Asaas, usado quando a entrada foi
    # cobrada num cadastro com o CPF de outra pessoa (PAGAMENTO EM OUTRO
    # CADASTRO DO ASAAS.txt) — o CPF devolveria só o primeiro cadastro.
    if (cpf_cnpj or "").strip().startswith("cus_"):
        cliente_id = cpf_cnpj.strip()
    else:
        cliente_id = buscar_cliente_por_cpf(cpf_cnpj, api_key)
    if not cliente_id:
        return None
    alvo = (texto_entrada or TEXTO_ENTRADA_PADRAO).strip().upper()
    offset = 0
    while True:
        resposta = _chamar("/payments", api_key,
                           {"customer": cliente_id, "limit": 100, "offset": offset})
        for cobranca in resposta.get("data") or []:
            descricao = (cobranca.get("description") or "").strip().upper()
            if descricao.startswith(alvo) and cobranca.get("status") in STATUS_PAGO:
                return cobranca
        if not resposta.get("hasMore"):
            return None
        offset += 100


def pagamento_quitado(cpf_cnpj: str, api_key: str, valor_total: float,
                      fracao_minima: float = FRACAO_A_VISTA):
    """
    Cobrança paga que cobre o contrato inteiro — pagamento à vista.

    Devolve a cobrança do Asaas cujo status é de pago e cujo valor é de pelo
    menos `fracao_minima` do total do contrato, qualquer que seja a descrição.
    Devolve None sem o valor do contrato: sem ele não há como saber se o que
    foi pago quita alguma coisa, e chutar abriria caso de quem pagou entrada.
    """
    try:
        minimo = float(valor_total) * float(fracao_minima)
    except (TypeError, ValueError):
        return None
    if minimo <= 0:
        return None

    cliente_id = buscar_cliente_por_cpf(cpf_cnpj, api_key)
    if not cliente_id:
        return None
    offset = 0
    while True:
        resposta = _chamar("/payments", api_key,
                           {"customer": cliente_id, "limit": 100, "offset": offset})
        for cobranca in resposta.get("data") or []:
            if cobranca.get("status") not in STATUS_PAGO:
                continue
            try:
                valor = float(cobranca.get("value") or 0)
            except (TypeError, ValueError):
                continue
            if valor >= minimo:
                return cobranca
        if not resposta.get("hasMore"):
            return None
        offset += 100
