#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Acha o banco adverso no contrato de financiamento do cliente.

Por que existe: **contrato de busca e apreensão não nomeia o banco** (só as
revisionais dizem "em desfavor do Banco X"), e o onboarding exige esse campo.
Até 18/08/2026 esses clientes ficavam parados esperando ela digitar o nome.

O nome do banco costuma estar no contrato de financiamento que o cliente
mandou, guardado em DOC CLIENTE — no caso da Telma, a primeira linha do PDF era
"AYMORÉ CRÉDITO, FINANCIAMENTO E INVESTIMENTO S.A.".

Regra de ouro: **só devolve nome quando tem certeza**. Nada de deduzir pelo
nome do arquivo ("contrato honda.pdf" não vira Honda) — o texto do documento
precisa dizer. Sem certeza, devolve vazio e o onboarding continua pendente,
como era antes.
"""

import re
import unicodedata
from pathlib import Path

from . import ocr, pdf_protegido

# Financiadoras conhecidas -> nome como ela escreve no onboarding.
# A chave é procurada no texto do PDF (sem acento, maiúscula).
CONHECIDOS = (
    ("AYMORE", "Aymoré Crédito"),
    ("BANCO PAN", "Banco Pan"),
    ("PSA FINANCE", "Banco PSA Finance Brasil"),   # hoje Stellantis Financiamentos
    ("STELLANTIS", "Stellantis Financiamentos"),
    ("BANCO BV", "Banco BV"),
    ("BV FINANCEIRA", "Banco BV"),
    ("SANTANDER", "Banco Santander"),
    ("BRADESCO FINANCIAMENTOS", "Banco Bradesco Financiamentos S.A."),
    ("BRADESCO", "Banco Bradesco"),
    ("ITAU UNIBANCO", "Banco Itaú Unibanco"),
    ("ITAU", "Banco Itaú"),
    # "CREDITA" sozinho era chave perigosa: pegava o "CREDITAS" do contrato do
    # Rafael pela metade ("Banco Credita") e casaria também com palavra comum
    # de contrato — "valor creditado", "parcela creditada" (09/09/2026).
    ("CREDITAS", "Banco Creditas"),
    ("DIGIMAIS", "Banco Digimais"),
    ("OMNI", "Omni Banco"),
    ("SAFRA", "Banco Safra"),
    ("VOTORANTIM", "Banco Votorantim"),
    ("HONDA", "Banco Honda"),
    ("TOYOTA", "Banco Toyota"),
    ("VOLKSWAGEN", "Banco Volkswagen"),
    ("RENAULT", "Banco Renault"),
    ("FIDIS", "Banco Fidis"),
    ("CNH INDUSTRIAL", "Banco CNH Industrial"),
    ("CAIXA ECONOMICA", "Caixa Econômica Federal"),
    ("BANCO DO BRASIL", "Banco do Brasil"),
    ("SICREDI", "Sicredi"),
    ("SICOOB", "Sicoob"),
    ("PORTOSEG", "Portoseg"),
    ("BANCO DAYCOVAL", "Banco Daycoval"),
)

# Só vale procurar em documento que seja mesmo contrato/financiamento — ou o
# MANDADO de busca e apreensão, que traz o banco como AUTOR da ação. O mandado
# entrou em 08/09/2026, junto com o OCR: ele é sempre digitalizado, e até então
# a automação não conseguia ler uma linha dele.
ARQUIVOS_PROVAVEIS = r"CONTRATO|FINANCIAMENTO|CEDULA|CCB|CDC|MANDADO|INTIMACAO|CITACAO"

# Frases que confirmam ser um contrato de crédito, e não outra coisa qualquer.
MARCAS_DE_FINANCIAMENTO = (
    "CREDITO DIRETO AO CONSUMIDOR", "CEDULA DE CREDITO BANCARIO",
    "FINANCIAMENTO", "ALIENACAO FIDUCIARIA", "ARRENDAMENTO MERCANTIL",
    "CONTRATO DE CREDITO", "TAXA DE JUROS",
)


def _limpo(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    normal = "".join(c for c in normal if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", normal).upper()


# No mandado, quem move a ação é o banco: "AUTOR: SANTANDER SOCIEDADE DE
# CREDITO, FINANCIAMENTO E INVESTIMENTO S.A." (mandado da Joice, 08/09/2026).
# Cada tribunal chama de um jeito: AUTOR em Santa Catarina (Joice), REQUERENTE
# na Bahia (Adeson). O nome pode vir na linha de baixo, e o _limpo já juntou
# tudo numa linha só antes de chegar aqui.
_AUTOR = re.compile(r"\b(?:AUTOR(?:A|ES)?|REQUERENTE|EXEQUENTE|CREDOR(?:A)?)"
                    r"\s*:?\s*([A-Z0-9ÀÁÂÃÉÊÍÓÔÕÚÇ&./\- ]{4,80})")


def identificar_no_mandado(texto: str) -> str:
    """Banco que move a busca e apreensão, lido do mandado."""
    alvo = _limpo(texto)
    if "BUSCA E APREENSAO" not in alvo and "ALIENACAO FIDUCIARIA" not in alvo:
        return ""
    achado = _AUTOR.search(alvo)
    if not achado:
        return ""
    nome = achado.group(1).strip(" .-")
    for chave, conhecido in CONHECIDOS:
        if chave in nome:
            return conhecido
    # Fora da lista: só aceita se a linha do AUTOR parecer instituição, para
    # não trazer nome de pessoa por engano.
    if re.search(r"BANCO|CREDITO|FINANCIAMENTO|FUNDO|S\.?A\.?$|LTDA", nome):
        return nome_de_empresa(nome)
    return ""


_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "PARA"}


def nome_de_empresa(bruto: str) -> str:
    """
    "COOPERA FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS - RESPONSABILIDADE
    LIMITADA" -> "Coopera Fundo de Investimento em Direitos Creditorios".

    Esse nome vai para o onboarding que o CLIENTE recebe. A versão antiga
    cortava em 60 letras no meio da palavra ("... Creditorios - Resp") e deixava
    "DE" e "EM" em maiúsculas — foi o que sairia para a Gisleine (18/09/2026).
    O complemento depois do " - " é forma jurídica, não nome: fica de fora.
    """
    nome = re.split(r"\s+[-–]\s+", bruto.strip())[0]
    palavras = []
    for posicao, palavra in enumerate(nome.split()):
        if posicao > 0 and palavra.upper() in _PARTICULAS:
            palavras.append(palavra.lower())
        elif palavra.upper() in ("S.A.", "S/A", "SA", "LTDA", "LTDA."):
            palavras.append(palavra.upper().rstrip("."))
        else:
            palavras.append(palavra.capitalize())
    return " ".join(palavras)


def identificar(texto: str) -> str:
    """Nome do banco a partir do texto de um contrato de financiamento."""
    alvo = _limpo(texto)
    if not any(marca in alvo for marca in MARCAS_DE_FINANCIAMENTO):
        return ""                       # não parece contrato de crédito
    for chave, nome in CONHECIDOS:
        if chave in alvo:
            return nome
    # Fora da lista: aceita "<NOME> CREDITO, FINANCIAMENTO E INVESTIMENTO S.A."
    achado = re.search(r"([A-ZÀ-Ú][A-ZÀ-Ú&\. ]{2,40}?)\s+CREDITO,?\s+FINANCIAMENTO\s+E\s+INVESTIMENTO",
                       alvo)
    if achado:
        bruto = achado.group(1).strip().title()
        return "%s Crédito" % bruto
    return ""


def procurar_no_cliente(pasta_cliente, ler_pdf=None) -> tuple:
    """
    Procura o banco nos documentos do cliente. Devolve (nome, arquivo).

    `ler_pdf` existe para os testes; por padrão usa o pypdf.
    """
    if ler_pdf is None:
        def ler_pdf(caminho):
            # Contrato de banco costuma vir protegido; a senha, quando existe,
            # está no nome do arquivo ("CONTRATO, SENHA: 448.pdf").
            leitor, senha = pdf_protegido.abrir(caminho)
            if leitor is None:
                return ""
            texto = " ".join((p.extract_text() or "") for p in leitor.pages[:3])
            # Digitalização não tem camada de texto: cai no OCR do macOS. É o
            # que faltava para ler mandado e contrato fotografado — o banco da
            # Joice estava escrito no mandado dela o tempo todo.
            if len(re.sub(r"\s+", "", texto)) < 40:
                if senha:
                    with pdf_protegido.copia_aberta(leitor) as aberto:
                        return ocr.ler(aberto, paginas=3) if aberto else ""
                return ocr.ler(caminho, paginas=3)
            return texto

    pasta_cliente = Path(pasta_cliente)
    if not pasta_cliente.is_dir():
        return "", None

    candidatos = [p for p in pasta_cliente.rglob("*.pdf")
                  if re.search(ARQUIVOS_PROVAVEIS, _limpo(p.name))
                  and "ASSINADO" not in _limpo(p.name)          # o nosso, não
                  and "PRESTACAO DE SERVICOS" not in _limpo(p.name)]
    # O que estiver em DOC CLIENTE primeiro: é onde o documento do cliente mora.
    candidatos.sort(key=lambda p: 0 if "DOC CLIENTE" in _limpo(str(p.parent)) else 1)

    for caminho in candidatos:
        try:
            texto = ler_pdf(caminho)
        except Exception:
            continue
        nome = identificar(texto) or identificar_no_mandado(texto)
        if nome:
            return nome, caminho
    return "", None
