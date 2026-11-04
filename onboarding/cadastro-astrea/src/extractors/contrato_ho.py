#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extração dos dados do cliente a partir do contrato de honorários assinado.

Esta é a fonte principal, e por um motivo concreto: o contrato de prestação de
serviços do escritório é **PDF com camada de texto** (não é digitalização), e
traz a qualificação completa num padrão estável:

    ... e do outro lado, como Cliente Contratante FULANO DE TAL, brasileiro,
    casado, vigilante, portador do RG n°: 9901234 SSP/AL, inscrito no CPF de
    nº 049.123.456-56, residente e domiciliado na Rua Bom Jesus, 27 A –
    Benedito Bentes – Maceió/AL – CEP: 57084-818, endereço eletrônico:
    fulano@gmail.com e contato telefônico (82) 99188-6196 ...

Ler daí é mais seguro do que fazer OCR de foto de RG: o texto é digital, o
documento foi assinado eletronicamente pelo próprio cliente, e é a mesma fonte
que o gerador de onboarding já usa em produção.

Casos reais que o parser precisa aguentar (todos vistos nas pastas de 2026):
  - dois qualificados no mesmo contrato: "Cliente Contratante" e
    "Cliente Responsável" (quem paga / corresponsável);
  - cliente sem RG no contrato (só CPF);
  - cliente sem telefone (só o do responsável);
  - endereço com e sem complemento, separado por "–" ou por "-";
  - espaços intrusos do extrator de PDF: "57038 -637", "( 82) 99185-5820".
"""

import re
import unicodedata
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:                                   # pragma: no cover
    PdfReader = None

from ..validators import campos as V


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c))


# --- Marcadores do contrato ------------------------------------------------

_INICIO_CONTRATANTE = re.compile(
    r"[Cc]liente\s+[Cc]ontratante\s*:?\s*", re.UNICODE)
_INICIO_RESPONSAVEL = re.compile(
    r"[Cc]liente\s+[Rr]espons[áa]vel\s*:?\s*", re.UNICODE)
_FIM_QUALIFICACAO = re.compile(
    r"(?:,?\s*e?\s*como\s+[Cc]liente\s+[Rr]espons[áa]vel)"
    r"|(?:,?\s*mediante\s+as\s+cl[áa]usulas)"
    r"|(?:\s*Cl[áa]usula\s*1)", re.UNICODE)

_INICIO_DOCUMENTOS = re.compile(
    r"\b(portador[ae]?|portadora|inscrit[oa]|residente|domiciliad[oa])\b", re.I)
# Marca mínima de que o trecho recortado é mesmo uma qualificação de pessoa.
_QUALIFICACAO = re.compile(
    r"\b(CPF|CNPJ|RG|residente\s+e\s+domiciliad|endere[çc]o\s+eletr[ôo]nico)\b", re.I)

_RG = re.compile(
    r"RG\s*(?:sob\s+o\s+|de\s+)?n?[º°o]?\s*[:.]?\s*(\d[\d.\-/\s]{3,22}?)\s*"
    r"(?:([A-ZÇ]{2,8}\s*/\s*[A-Z]{2})|(?=,|\s+inscrit))", re.UNICODE)
# O "de" entre "CPF" e "nº" vem partido em alguns contratos: a camada de
# texto do PDF escreve "inscrita no CPF d e nº 310.311.118 -59" (Priscila,
# 13/10/2026). Era por isso que o CPF "não era localizado" num contrato que
# tinha o CPF escrito. Por isso cada letra do conector aceita espaço ao
# lado, e "sob o nº" entra junto — a mesma variação que o RG já usava.
_CPF = re.compile(r"C\s*P\s*F\s*(?:d\s*e\s*|s\s*o\s*b\s*o\s*)?n?\s*[º°o]?\s*[:.]?\s*(\d[\d.\s-]{9,20}\d)", re.I)
# "CNPJ de nº" — o mesmo "de" que o CPF já aceitava. Faltava aqui, e o primeiro
# cliente pessoa jurídica (Vektor Pharma, 18/09/2026) ficou pendente por "CPF
# não localizado": sem CNPJ lido, a ficha parecia de pessoa física sem CPF.
_CNPJ = re.compile(r"C\s*N\s*P\s*J\s*(?:d\s*e\s*|s\s*o\s*b\s*o\s*)?n?\s*[º°o]?\s*[:.]?\s*(\d[\d./\s-]{12,24}\d)", re.I)
# O \s* dentro de "domiciliad[oa]" não é capricho: o PDF do contrato às vezes
# quebra a palavra ("residente e domiciliad a na Rua..."), e sem isso o
# endereço inteiro se perde — foi o que deixou a Maria Nizete sem endereço no
# Astrea em 18/08/2026.
# Pessoa física "reside"; empresa fica "localizada", "sediada", "com sede" —
# o contrato da Vektor Pharma diz "localizada na Rua General Clark".
_ENDERECO = re.compile(
    r"(?:residente\s+e\s+domicili\s*a\s*d\s*[oa]|localizad[oa]|sediad[oa]"
    r"|com\s+sede|estabelecid[oa])\s*(?:na|no|em|à|a)?\s*(.+?)\s*"
    r"CEP\s*[:.]?\s*(\d{2}[\d.\s-]{3,10}\d)", re.I | re.S)
_EMAIL = re.compile(
    r"endere[çc]o\s+eletr[ôo]nico\s*[:.]?\s*([^\s,;]+@[^\s,;]+?)(?=[\s,;]|$)", re.I)
# Os contratos escrevem o telefone de três jeitos: "contato telefônico",
# "telefone para contato" e só "telefone". Aceitar um só perdia o número —
# aconteceu com a Maria Nizete (18/08/2026).
_TELEFONE = re.compile(
    r"(?:contato\s+telef[ôo]nico|telefone\s+(?:para|de)\s+contato|telefone)"
    r"\s*[:.]?\s*(\(?\s*\d{2}\s*\)?[\s.\d-]{8,15})", re.I)

# O endereço do contrato aparece de várias formas — separado por travessão,
# por vírgula, com a UF em sigla ou por extenso:
#   "Rua Bom Jesus, 27 A – Benedito Bentes – Maceió/AL"
#   "Rua Sombra do Coco, 75, PQ R Jaqueline, Gravatai - RS"
#   "Rua Boa Vista, nº 63, Centro, Coqueiro Seco – Alagoas"
# A âncora confiável é a UF no fim: acha-se ela primeiro, e o que sobra é
# fatiado de trás para frente (cidade, bairro, resto).
ESTADOS_POR_EXTENSO = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE",
    "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
_NOMES_ESTADOS = ("ACRE|ALAGOAS|AMAP[ÁA]|AMAZONAS|BAHIA|CEAR[ÁA]|"
                  "DISTRITO FEDERAL|ESP[ÍI]RITO SANTO|GOI[ÁA]S|MARANH[ÃA]O|"
                  "MATO GROSSO DO SUL|MATO GROSSO|MINAS GERAIS|PAR[ÁA]IBA|"
                  "PARAN[ÁA]|PAR[ÁA]|PERNAMBUCO|PIAU[ÍI]|RIO DE JANEIRO|"
                  "RIO GRANDE DO NORTE|RIO GRANDE DO SUL|ROND[ÔO]NIA|RORAIMA|"
                  "SANTA CATARINA|S[ÃA]O PAULO|SERGIPE|TOCANTINS")
_SIGLAS = "|".join(V.UFS)
_CIDADE_UF_FINAL = re.compile(
    r"^(?P<resto>.+?)\s*[,–—/-]\s*(?P<uf>%s|%s)\s*[.,–—-]?\s*$"
    % (_SIGLAS, _NOMES_ESTADOS), re.I | re.UNICODE)
_SEPARADOR_ENDERECO = re.compile(r"\s*[–—,]\s*|\s+-\s+")
_PALAVRAS_COMPLEMENTO = ("QD", "QUADRA", "LT", "LOTE", "CASA", "APT", "APTO",
                         "APARTAMENTO", "BLOCO", "BL", "COND", "CONDOMINIO",
                         "CONDOMÍNIO", "FUNDOS", "SALA", "ANDAR", "RES",
                         "RESIDENCIAL", "CJ", "CONJUNTO", "KM")

_NACIONALIDADES = re.compile(
    r"^(brasileir[oa]|basileir[oa]|estrangeir[oa]|portugu[eê]s[a]?|"
    r"argentin[oa]|italian[oa]|espanhol[a]?|naturalizad[oa].*)$", re.I)

_BANCO_ADVERSO = re.compile(
    r"em\s+desfavor\s+d[oae]s?\s+([^,;.]{3,70}?)(?=\s*[,;.]|\s+mediante|\s+Cl[áa]usula)",
    re.I)
_VEICULO = re.compile(
    r"(?:do\s+)?ve[íi]culo\s+(?:de\s+)?(?:marca\s+)?([A-Z0-9][^,;.]{2,60}?)"
    r"(?=\s*[,;.]|\s+placa|\s+de\s+placa)", re.I)

# Cláusula 1ª: o que o escritório se obriga a fazer. É o texto que vira a
# DESCRIÇÃO do caso no Astrea — antes disso o comando em lote abria caso com a
# descrição vazia, porque lia um campo `objeto` que nunca existiu.
_CLAUSULA_1 = re.compile(r"Cl[áa]usula\s*1\s*[ªa°]?\.?\s*(.{40,1200}?)"
                         r"(?=Cl[áa]usula\s*2|$)", re.I | re.S)
# O trecho útil começa no "para realizar ..."; antes disso é fórmula igual em
# todo contrato. O \s* no meio das palavras é por causa do PDF, que parte
# palavras no meio ("obri ga-se", "Obri gação", "realiza r").
_INICIO_DO_OBJETO = re.compile(r"para\s+r\s*e\s*a\s*l\s*i\s*z\s*a\s*r\s+", re.I)

# "veículo apreendido no Estado de Santa Catarina, na data de 19.08.2026"
_APREENSAO = re.compile(
    r"ve[íi]culo\s+apreendido\s+no\s+Estado\s+d[eo]\s+([A-Za-zÀ-ú][^,;.]{2,40}?)\s*,?\s*"
    r"na\s+data\s+de\s*(\d[\d\s./-]{6,16}\d)", re.I)
_NUMERO_PROCESSO = re.compile(
    r"sob\s+o\s+n?[º°o]?\s*[:.]?\s*(\d[\d\s.\-/]{15,30}\d)", re.I)

# Cláusula 2ª: valor dos honorários, entrada e parcelamento. Formato visto em
# contratos reais (23/09/2026), sempre nessa ordem — total, depois entrada,
# depois o parcelamento:
#   "...a importância de R$ 18.717,10 (...), sendo este cobrado da seguinte
#    maneira: - Entrada no valor de R$ 1.300,00 (...) na data de 17.09.2026;
#    - 30 (trinta) parcelas de R$ 580,57 (...) com início em 17.10.2026 e a
#    última em 17.03.2029."
# Quando só sobra UMA parcela, o modelo não escreve "1 (uma) parcela" — vira
# uma linha solta "R$ R$ 810,50 (...) na data de 11.10.2026" (o "R$ R$" em
# dobro é como o gerador do escritório escreve mesmo; não se corrige aqui,
# só se lê).
#  A cláusula 2ª tem vários parágrafos sobre boleto/negativação dentro dela
#  antes da 3ª começar — medido em contrato real, passa de 2700 caracteres.
#  Por isso o limite é bem mais folgado que o da cláusula 1ª (objeto).
_CLAUSULA_2 = re.compile(r"Cl[áa]usula\s*2\s*[ªa°]?\.?\s*(.{20,4000}?)"
                         r"(?=Cl[áa]usula\s*\d|$)", re.I | re.S)
_VALOR_TOTAL_HONORARIOS = re.compile(
    r"import[âa]ncia\s+de\s+R\$\s*([\d.,]+)", re.I)
_ENTRADA_CLAUSULA = re.compile(
    r"Entrada\s+no\s+valor\s+de\s+R\$\s*([\d.,]+)[^;.]*?na\s+data\s+de\s*"
    r"(\d[\d\s./-]{6,16}\d)", re.I)
# Entrada dividida em datas (visto em 30/09/2026 — Tatiane, João Paulo,
# Rafael Wagner):
#   "- Entrada no valor de R$ 500,00 (...) sendo; - R$ 250,00 (...) na data
#    de 10/09/2026; - R$ 250,00 (...) na data de 21/09/2026; - 15 (...)"
# O ";" logo depois do "sendo" faz o padrão simples acima falhar. Aqui vale o
# total da entrada; a data guardada é a da PRIMEIRA fração.
_ENTRADA_DIVIDIDA = re.compile(
    r"Entrada\s+no\s+valor\s+de\s+R\$\s*([\d.,]+)\s*(?:\([^)]*\))?\s*sendo\s*[;:,]?"
    r"((?:\s*-?\s*R\$\s*[\d.,]+\s*(?:\([^)]*\))?\s*na\s+data\s+de\s*"
    r"\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*;?)+)", re.I)
_FRACAO_ENTRADA = re.compile(
    r"R\$\s*([\d.,]+)\s*(?:\([^)]*\))?\s*na\s+data\s+de\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", re.I)
# "c\s?o\s?m": o texto do PDF às vezes quebra a palavra ("co m início",
# contrato do Edielson, 30/09/2026).
_PARCELAS_MULTIPLAS = re.compile(
    r"(\d+)\s*\([^)]*\)\s*parcelas\s+de\s+R\$\s*([\d.,]+)[^;.]*?c\s?o\s?m\s+in[íi]cio"
    r"\s+em\s*(\d[\d\s./-]{6,16}\d)\s+e\s+a\s+[úu]ltima\s+em\s*"
    r"(\d[\d\s./-]{6,16}\d)", re.I)
_PARCELA_UNICA = re.compile(
    r"R\$\s*R?\$?\s*([\d.,]+)\s*\([^)]*\)\s*na\s+data\s+de\s*"
    r"(\d[\d\s./-]{6,16}\d)", re.I)

_RUIDO_ASSINATURA = re.compile(
    r"Assinado com Assinatura Eletr[ôo]nica.*?Validador", re.S | re.I)

# Tipos de ação, iguais aos do gerador de contratos.
_TIPOS_ACAO = (
    ("Busca e Apreensão (Defesa)",
     re.compile(r"busca\s+e\s+apreens[ãa]o", re.I)),
    # Os dois antes da revisional genérica. ATENÇÃO à exceção: "Revisional de
    # Empréstimo COM GARANTIA DE VEÍCULO" é VEICULAR no escritório — ela
    # corrigiu isso em 21/09/2026, com a Nubia; Jhonatas, Sidnei e Tatiane têm a
    # mesma frase. Só empréstimo SEM garantia de veículo vira caso de empréstimo.
    ("Ação Revisional de Empréstimo",
     re.compile(r"revisional\s+de\s+empr[ée]stimo"
                r"(?!\s+com\s+garantia\s+de\s+ve[íi]culo)", re.I)),
    ("Ação Revisional de Cartão de Crédito",
     re.compile(r"revisional\s+de\s+cart[ãa]o", re.I)),
    ("Ação Revisional",
     re.compile(r"revision(al|ais)|revis[ãa]o\s+(de\s+)?contrato", re.I)),
    ("Negativação Indevida",
     re.compile(r"negativa[çc][ãa]o\s+indevida|inscri[çc][ãa]o\s+indevida", re.I)),
    ("Fraude Bancária",
     re.compile(r"fraude\s+banc[áa]ria|golpe", re.I)),
    ("Ação de Danos Morais",
     re.compile(r"danos?\s+mora(l|is)", re.I)),
    # Vem por último: "Obrigação de Fazer c/c Dano Moral" já é pego acima.
    # Sozinha ela aparece em cobrança contra órgão público — a Vektor Pharma
    # contra a Secretaria de Saúde de Alagoas (18/09/2026) ficou sem tipo.
    ("Ação de Obrigação de Fazer",
     re.compile(r"obriga\s*[çc]\s*[ãa]\s*o\s+de\s+fazer", re.I)),
)

# Confiança de partida para dado lido do contrato assinado com camada de texto.
CONFIANCA_CONTRATO = 0.97


class Campo(object):
    """Um dado extraído, com de onde veio e o quanto se pode confiar nele."""

    def __init__(self, valor="", confianca=0.0, valido=False, motivo="",
                 origem="", bruto=""):
        self.valor = valor
        self.confianca = confianca
        self.valido = valido
        self.motivo = motivo
        self.origem = origem
        self.bruto = bruto

    @property
    def preenchido(self) -> bool:
        return bool(self.valor)

    def como_dict(self):
        return {"valor": self.valor, "confianca": round(self.confianca, 2),
                "valido": self.valido, "motivo": self.motivo,
                "origem": self.origem}

    def __repr__(self):
        return "<Campo %r conf=%.2f valido=%s>" % (self.valor, self.confianca,
                                                   self.valido)

    def __bool__(self):
        return self.preenchido

    __nonzero__ = __bool__


def vazio(motivo="não localizado nos documentos", origem="") -> Campo:
    return Campo("", 0.0, False, motivo, origem)


class Pessoa(object):
    """Qualificação de uma pessoa extraída do contrato."""

    CAMPOS = ("nome", "nacionalidade", "estado_civil", "profissao", "rg",
              "orgao_expedidor", "cpf", "cnpj", "logradouro", "numero",
              "complemento", "bairro", "cidade", "uf", "cep", "email",
              "telefone", "data_nascimento")

    def __init__(self, papel="contratante"):
        self.papel = papel
        for nome in self.CAMPOS:
            setattr(self, nome, vazio())
        self.observacoes = []
        self.bloco_bruto = ""

    def campo(self, nome) -> Campo:
        return getattr(self, nome, vazio())

    def preenchidos(self):
        return {n: getattr(self, n) for n in self.CAMPOS if getattr(self, n).preenchido}

    def como_dict(self):
        saida = {"papel": self.papel,
                 "observacoes": list(self.observacoes)}
        for nome in self.CAMPOS:
            campo = getattr(self, nome)
            if campo.preenchido or campo.motivo:
                saida[nome] = campo.como_dict()
        return saida

    def __repr__(self):
        return "<Pessoa %s %r>" % (self.papel, self.nome.valor)


class ResultadoContrato(object):
    def __init__(self, arquivo: Path):
        self.arquivo = arquivo
        self.contratante = None
        self.responsavel = None
        self.tipo_acao = vazio()
        self.banco_adverso = vazio()
        self.veiculo = vazio()
        self.objeto = vazio()
        self.apreensao = None          # {"estado", "data", "processo"} ou None
        # Cláusula 2ª — valor e parcelamento dos honorários. Cada campo é
        # independente: falhar num não trava os outros (ex.: total lido, mas
        # data da entrada não bateu no padrão esperado).
        self.valor_total_honorarios = vazio()
        self.entrada_valor = vazio()
        self.entrada_data = vazio()
        self.parcelas_qtd = vazio()
        self.parcelas_valor = vazio()
        self.parcelas_inicio = vazio()
        self.parcelas_fim = vazio()
        self.erros = []
        self.observacoes = []

    @property
    def legivel(self) -> bool:
        return self.contratante is not None and not self.erros

    def como_dict(self):
        return {
            "arquivo": self.arquivo.name if self.arquivo else "",
            "contratante": self.contratante.como_dict() if self.contratante else None,
            "responsavel": self.responsavel.como_dict() if self.responsavel else None,
            "tipo_acao": self.tipo_acao.como_dict(),
            "banco_adverso": self.banco_adverso.como_dict(),
            "veiculo": self.veiculo.como_dict(),
            "objeto": self.objeto.como_dict(),
            "apreensao": dict(self.apreensao) if self.apreensao else None,
            "valor_total_honorarios": self.valor_total_honorarios.como_dict(),
            "entrada_valor": self.entrada_valor.como_dict(),
            "entrada_data": self.entrada_data.como_dict(),
            "parcelas_qtd": self.parcelas_qtd.como_dict(),
            "parcelas_valor": self.parcelas_valor.como_dict(),
            "parcelas_inicio": self.parcelas_inicio.como_dict(),
            "parcelas_fim": self.parcelas_fim.como_dict(),
            "erros": list(self.erros),
            "observacoes": list(self.observacoes),
        }


# ---------------------------------------------------------------------------
# Leitura do PDF
# ---------------------------------------------------------------------------

def texto_do_pdf(caminho: Path, paginas: int = 3) -> str:
    """Texto das primeiras páginas, sem rodapé de assinatura, em linha única."""
    if PdfReader is None:
        raise RuntimeError("Biblioteca pypdf não instalada.")
    leitor = PdfReader(str(caminho))
    pedacos = []
    for pagina in leitor.pages[:paginas]:
        try:
            pedacos.append(pagina.extract_text() or "")
        except Exception:                              # página corrompida
            continue
    bruto = "\n".join(pedacos)
    bruto = _RUIDO_ASSINATURA.sub(" ", bruto)
    bruto = bruto.replace(" ", " ").replace("‑", "-")
    return re.sub(r"\s+", " ", bruto).strip()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _recortar(texto: str, inicio_re) -> str:
    achado = inicio_re.search(texto)
    if not achado:
        return ""
    resto = texto[achado.end():]
    fim = _FIM_QUALIFICACAO.search(resto)
    return (resto[:fim.start()] if fim else resto[:900]).strip()


def _parse_cabecalho(bloco: str, pessoa: Pessoa, origem: str):
    """Nome, nacionalidade, estado civil e profissão — a parte antes do RG/CPF."""
    corte = _INICIO_DOCUMENTOS.search(bloco)
    cabecalho = bloco[:corte.start()] if corte else bloco
    partes = [V.limpar_texto(p) for p in cabecalho.split(",")]
    partes = [p for p in partes if p]

    if not partes:
        pessoa.nome = vazio("nome não localizado no contrato", origem)
        return

    nome, ok, motivo = V.validar_nome(partes[0])
    pessoa.nome = Campo(nome, CONFIANCA_CONTRATO if ok else 0.3, ok, motivo,
                        origem, partes[0])

    resto = partes[1:]
    if resto and _NACIONALIDADES.match(resto[0]):
        # "basileiro" aparece digitado errado num contrato real; o dado é o
        # que está no documento, então guardamos como veio.
        pessoa.nacionalidade = Campo(resto[0].capitalize(), CONFIANCA_CONTRATO,
                                     True, "", origem, resto[0])
        resto = resto[1:]

    if resto:
        valor, reconhecido = V.normalizar_estado_civil(resto[0])
        pessoa.estado_civil = Campo(valor, CONFIANCA_CONTRATO if reconhecido else 0.6,
                                    reconhecido,
                                    "" if reconhecido else "estado civil não reconhecido",
                                    origem, resto[0])
        resto = resto[1:]

    if resto:
        profissao = V.limpar_texto(", ".join(resto))
        if profissao:
            pessoa.profissao = Campo(profissao, CONFIANCA_CONTRATO, True, "",
                                     origem, profissao)


def _parse_documentos(bloco: str, pessoa: Pessoa, origem: str):
    achado = _RG.search(bloco)
    if achado:
        # Mesma quebra do PDF que partia o CPF: o RG sai "34.048.615 -6"
        # (Priscila, 13/10/2026). Espaço dentro do número de documento é
        # sempre defeito de leitura, nunca parte do RG — então cai aqui.
        numero = re.sub(r"\s+", "", V.limpar_texto(achado.group(1)))
        pessoa.rg = Campo(numero, CONFIANCA_CONTRATO, bool(numero), "", origem,
                          achado.group(0))
        if achado.group(2):
            orgao = re.sub(r"\s+", "", achado.group(2)).upper()
            pessoa.orgao_expedidor = Campo(orgao, CONFIANCA_CONTRATO, True, "",
                                           origem, achado.group(2))
    else:
        pessoa.rg = vazio("RG não consta no contrato", origem)

    achado = _CPF.search(bloco)
    if achado:
        valor, ok, motivo = V.validar_cpf(achado.group(1))
        pessoa.cpf = Campo(valor, CONFIANCA_CONTRATO if ok else 0.0, ok, motivo,
                           origem, achado.group(1))
    else:
        pessoa.cpf = vazio("CPF não localizado nos documentos", origem)

    achado = _CNPJ.search(bloco)
    if achado:
        valor, ok, motivo = V.validar_cnpj(achado.group(1))
        pessoa.cnpj = Campo(valor, CONFIANCA_CONTRATO if ok else 0.0, ok, motivo,
                            origem, achado.group(1))


def _parse_endereco(bloco: str, pessoa: Pessoa, origem: str):
    achado = _ENDERECO.search(bloco)
    if not achado:
        for nome in ("logradouro", "numero", "bairro", "cidade", "uf", "cep"):
            setattr(pessoa, nome, vazio("endereço não localizado no contrato", origem))
        return

    corpo = V.limpar_texto(achado.group(1))
    cep, cep_ok, cep_motivo = V.validar_cep(achado.group(2))
    pessoa.cep = Campo(cep, CONFIANCA_CONTRATO if cep_ok else 0.2, cep_ok,
                       cep_motivo, origem, achado.group(2))

    achado_uf = _CIDADE_UF_FINAL.match(corpo)
    if not achado_uf:
        pessoa.cidade = vazio("cidade/UF não identificadas no endereço", origem)
        pessoa.uf = vazio("cidade/UF não identificadas no endereço", origem)
        pessoa.logradouro = Campo(corpo, 0.5, False,
                                  "endereço não pôde ser separado em partes",
                                  origem, corpo)
        pessoa.observacoes.append(
            "Endereço fora do padrão do contrato — conferir manualmente: %s" % corpo)
        return

    bruto_uf = V.limpar_texto(achado_uf.group("uf"))
    sigla = ESTADOS_POR_EXTENSO.get(
        re.sub(r"\s+", " ", _sem_acento(bruto_uf).upper()), bruto_uf.upper())
    uf, uf_ok, uf_motivo = V.validar_uf(sigla)
    pessoa.uf = Campo(uf, CONFIANCA_CONTRATO if uf_ok else 0.3, uf_ok, uf_motivo,
                      origem, bruto_uf)

    segmentos = [V.limpar_texto(s)
                 for s in _SEPARADOR_ENDERECO.split(achado_uf.group("resto"))]
    segmentos = [s for s in segmentos if s]

    cidade = segmentos[-1] if segmentos else ""
    bairro = segmentos[-2] if len(segmentos) >= 2 else ""
    cabeca = ", ".join(segmentos[:-2]) if len(segmentos) > 2 else ""

    pessoa.cidade = Campo(cidade, CONFIANCA_CONTRATO, bool(cidade),
                          "" if cidade else "cidade não identificada", origem, cidade)

    logradouro, numero, complemento = _separar_logradouro(cabeca)
    pessoa.logradouro = Campo(logradouro, CONFIANCA_CONTRATO, bool(logradouro),
                              "" if logradouro else "logradouro não identificado",
                              origem, cabeca)
    if numero:
        pessoa.numero = Campo(numero, CONFIANCA_CONTRATO, True, "", origem, cabeca)
    else:
        # Não presumir "S/N": o contrato pode simplesmente não ter trazido.
        pessoa.numero = vazio("número do endereço não localizado", origem)
        pessoa.observacoes.append("Número do endereço não consta no contrato.")
    if complemento:
        pessoa.complemento = Campo(complemento, CONFIANCA_CONTRATO, True, "",
                                   origem, complemento)
        if not any(complemento.upper().startswith(p) for p in _PALAVRAS_COMPLEMENTO):
            # Pode ser distrito/localidade em vez de complemento. Não segura o
            # cadastro (o endereço está completo), mas fica registrado.
            pessoa.observacoes.append(
                "Conferir a divisão do endereço: '%s' foi tratado como "
                "complemento, mas pode ser parte do bairro." % complemento)
    pessoa.bairro = Campo(bairro, CONFIANCA_CONTRATO, bool(bairro),
                          "" if bairro else "bairro não identificado", origem, bairro)


def _separar_logradouro(trecho: str):
    """
    'Rua X, nº 105, QD B'   -> ('Rua X', '105', 'QD B')
    'Rua Bom Jesus, 27 A'   -> ('Rua Bom Jesus', '27 A', '')
    'Rua PAMPA, 482 AP 5'   -> ('Rua PAMPA', '482', 'AP 5')
    'Rua Y, S/N, Lote 3'    -> ('Rua Y', 'S/N', 'Lote 3')
    """
    if not trecho:
        return "", "", ""

    # Com "nº" explícito. O marcador precisa ser mesmo "nº"/"n°"/"n." — aceitar
    # um "no" solto fazia "Rua Tamari|no Pimentel" virar logradouro "Rua Tamari"
    # com número "Pimentel" (aconteceu de verdade).
    achado = re.search(r"^(.*?),?\s*\b(?:n\s*[º°]|n\.)\s*"
                       r"([\dA-Za-z]+(?:\s*/\s*[A-Za-z0-9]+)?"
                       r"(?:\s+[A-Za-z0-9]{1,4})?)"
                       r"\s*(?:,\s*(.*))?$", trecho, re.I)
    if achado:
        return (V.limpar_texto(achado.group(1)),
                V.limpar_numero_endereco(achado.group(2)),
                V.limpar_texto(achado.group(3) or ""))

    # "S/N" é informação do documento, não suposição.
    achado = re.search(r"^(.*?),\s*(S\s*/\s*N|SN)\b\s*,?\s*(.*)$", trecho, re.I)
    if achado:
        return (V.limpar_texto(achado.group(1)), "S/N",
                V.limpar_texto(achado.group(3)))

    # Número depois da vírgula; letra solta logo após conta como parte do
    # número ("27 A"), mas "AP 5" é complemento.
    achado = re.search(r"^(.*?),\s*(\d+)(?:\s+([A-Za-z])(?!\w))?\s*,?\s*(.*)$", trecho)
    if achado:
        numero = achado.group(2) + ((" " + achado.group(3)) if achado.group(3) else "")
        return (V.limpar_texto(achado.group(1)), numero,
                V.limpar_texto(achado.group(4) or ""))

    return V.limpar_texto(trecho), "", ""


def _parse_contato(bloco: str, pessoa: Pessoa, origem: str):
    achado = _EMAIL.search(bloco)
    if achado:
        valor, ok, motivo = V.validar_email(achado.group(1))
        pessoa.email = Campo(valor, CONFIANCA_CONTRATO if ok else 0.3, ok, motivo,
                             origem, achado.group(1))
    else:
        pessoa.email = vazio("e-mail não consta no contrato", origem)

    achado = _TELEFONE.search(bloco)
    if achado:
        valor, ok, motivo = V.validar_telefone(achado.group(1))
        pessoa.telefone = Campo(valor, CONFIANCA_CONTRATO if ok else 0.3, ok,
                                motivo, origem, achado.group(1))
    else:
        pessoa.telefone = vazio("telefone não consta no contrato", origem)


def parse_bloco(bloco: str, papel: str, origem: str) -> Pessoa:
    pessoa = Pessoa(papel)
    pessoa.bloco_bruto = bloco
    _parse_cabecalho(bloco, pessoa, origem)
    _parse_documentos(bloco, pessoa, origem)
    _parse_endereco(bloco, pessoa, origem)
    _parse_contato(bloco, pessoa, origem)
    return pessoa


def _parse_processo(texto: str, resultado: ResultadoContrato, origem: str):
    for rotulo, padrao in _TIPOS_ACAO:
        if padrao.search(texto):
            resultado.tipo_acao = Campo(rotulo, 0.90, True, "", origem, rotulo)
            break
    else:
        resultado.tipo_acao = vazio("tipo de ação não identificado no contrato",
                                    origem)

    achado = _BANCO_ADVERSO.search(texto)
    if achado:
        banco = V.limpar_texto(achado.group(1))
        resultado.banco_adverso = Campo(banco, 0.90, True, "", origem, achado.group(0))
    else:
        # Comportamento conhecido: os contratos de busca e apreensão do
        # escritório não nomeiam o banco adverso.
        resultado.banco_adverso = vazio(
            "banco adverso não consta no contrato (normal em busca e apreensão)",
            origem)

    achado = _VEICULO.search(texto)
    if achado:
        veiculo = V.limpar_texto(achado.group(1))
        resultado.veiculo = Campo(veiculo, 0.85, True, "", origem, achado.group(0))
    else:
        resultado.veiculo = vazio("veículo não identificado no contrato", origem)

    _parse_objeto(texto, resultado, origem)


def _costurar(trecho: str) -> str:
    """Desfaz os espaços que o PDF enfia no meio de número e pontuação."""
    texto = V.limpar_texto(trecho)
    texto = re.sub(r"(\d)\s+([.\-/])\s*(\d)", r"\1\2\3", texto)   # 5092826 -32 -> 5092826-32
    texto = re.sub(r"\s+([,;.:])", r"\1", texto)                     # " ," -> ","
    # Nada de colar palavra separada por " - ": no contrato isso é separador de
    # verdade ("SPORTLINE - COR: VERMELHA - PLACA: ..."), não palavra partida.
    return texto.strip(" ,;.")


def _data_limpa(bruto: str) -> str:
    """'25.08.202 6' -> '25.08.2026'. O PDF parte o ano no meio."""
    junto = re.sub(r"\s+", "", bruto or "")
    achado = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", junto)
    return "%s.%s.%s" % achado.groups() if achado else junto


def _valor_para_float(bruto: str):
    """'18.717,10' -> 18717.10. Devolve None se não der para converter —
    nunca inventa número, melhor deixar em branco."""
    limpo = re.sub(r"\s+", "", bruto or "").replace(".", "").replace(",", ".")
    try:
        return round(float(limpo), 2)
    except ValueError:
        return None


def _parse_objeto(texto: str, resultado, origem: str):
    """Cláusula 1ª a partir do 'para realizar ...' — a descrição do caso."""
    clausula = _CLAUSULA_1.search(texto)
    if not clausula:
        resultado.objeto = vazio("cláusula 1ª não localizada no contrato", origem)
        return
    bruto = clausula.group(1)
    comeco = _INICIO_DO_OBJETO.search(bruto)
    trecho = bruto[comeco.end():] if comeco else bruto
    objeto = _costurar(trecho)
    if len(objeto) < 20:
        resultado.objeto = vazio("cláusula 1ª curta demais para servir de descrição",
                                 origem)
        return
    # Maiúscula no começo: o trecho vem depois de "para realizar".
    objeto = objeto[0].upper() + objeto[1:]
    resultado.objeto = Campo(objeto, 0.90, True, "", origem, clausula.group(0)[:120])

    apreensao = _APREENSAO.search(bruto)
    if apreensao:
        processo = _NUMERO_PROCESSO.search(bruto)
        resultado.apreensao = {
            "estado": V.limpar_texto(apreensao.group(1)).upper(),
            "data": _data_limpa(apreensao.group(2)),
            "processo": _costurar(processo.group(1)) if processo else "",
        }


def _parse_honorarios(texto: str, resultado, origem: str):
    """
    Cláusula 2ª: valor total, entrada e parcelamento dos honorários.

    Cada campo falha (fica vazio, com o motivo) independentemente dos
    outros — dado financeiro não se adivinha; o que não bate no padrão
    esperado vira pendência para conferência manual, nunca uma estimativa.
    """
    clausula = _CLAUSULA_2.search(texto)
    if not clausula:
        motivo = "cláusula 2ª (honorários) não localizada no contrato"
        resultado.valor_total_honorarios = vazio(motivo, origem)
        resultado.entrada_valor = vazio(motivo, origem)
        resultado.entrada_data = vazio(motivo, origem)
        resultado.parcelas_qtd = vazio(motivo, origem)
        resultado.parcelas_valor = vazio(motivo, origem)
        resultado.parcelas_inicio = vazio(motivo, origem)
        resultado.parcelas_fim = vazio(motivo, origem)
        return
    bruto = clausula.group(1)

    total = _VALOR_TOTAL_HONORARIOS.search(bruto)
    if total and _valor_para_float(total.group(1)) is not None:
        resultado.valor_total_honorarios = Campo(
            _valor_para_float(total.group(1)), 0.90, True, "", origem, total.group(0))
    else:
        resultado.valor_total_honorarios = vazio(
            "valor total dos honorários não reconhecido na cláusula 2ª", origem)

    entrada = _ENTRADA_CLAUSULA.search(bruto)
    dividida = None if entrada else _ENTRADA_DIVIDIDA.search(bruto)
    if dividida and _valor_para_float(dividida.group(1)) is not None:
        primeira = _FRACAO_ENTRADA.search(dividida.group(2))
        resultado.entrada_valor = Campo(
            _valor_para_float(dividida.group(1)), 0.85, True, "", origem, dividida.group(0))
        resultado.entrada_data = Campo(
            _data_limpa(primeira.group(2)), 0.85, True, "", origem, dividida.group(0))
        entrada = dividida
    elif entrada and _valor_para_float(entrada.group(1)) is not None:
        resultado.entrada_valor = Campo(
            _valor_para_float(entrada.group(1)), 0.90, True, "", origem, entrada.group(0))
        resultado.entrada_data = Campo(
            _data_limpa(entrada.group(2)), 0.90, True, "", origem, entrada.group(0))
    else:
        motivo = "entrada não reconhecida na cláusula 2ª"
        resultado.entrada_valor = vazio(motivo, origem)
        resultado.entrada_data = vazio(motivo, origem)

    # Parcelamento: só procura DEPOIS da entrada, senão o "R$X na data de Y"
    # da própria entrada seria lido de novo como se fosse a parcela.
    resto = bruto[entrada.end():] if entrada else bruto
    multiplas = _PARCELAS_MULTIPLAS.search(resto)
    if multiplas and _valor_para_float(multiplas.group(2)) is not None:
        resultado.parcelas_qtd = Campo(int(multiplas.group(1)), 0.90, True, "",
                                       origem, multiplas.group(0))
        resultado.parcelas_valor = Campo(
            _valor_para_float(multiplas.group(2)), 0.90, True, "", origem, multiplas.group(0))
        resultado.parcelas_inicio = Campo(_data_limpa(multiplas.group(3)), 0.90, True,
                                          "", origem, multiplas.group(0))
        resultado.parcelas_fim = Campo(_data_limpa(multiplas.group(4)), 0.90, True,
                                       "", origem, multiplas.group(0))
        return

    unica = _PARCELA_UNICA.search(resto)
    if unica and _valor_para_float(unica.group(1)) is not None:
        resultado.parcelas_qtd = Campo(1, 0.85, True, "", origem, unica.group(0))
        resultado.parcelas_valor = Campo(
            _valor_para_float(unica.group(1)), 0.85, True, "", origem, unica.group(0))
        resultado.parcelas_inicio = Campo(_data_limpa(unica.group(2)), 0.85, True,
                                          "", origem, unica.group(0))
        resultado.parcelas_fim = Campo(_data_limpa(unica.group(2)), 0.85, True,
                                       "", origem, unica.group(0))
        return

    motivo = "parcelamento não reconhecido na cláusula 2ª"
    resultado.parcelas_qtd = vazio(motivo, origem)
    resultado.parcelas_valor = vazio(motivo, origem)
    resultado.parcelas_inicio = vazio(motivo, origem)
    resultado.parcelas_fim = vazio(motivo, origem)


def extrair(caminho: Path) -> ResultadoContrato:
    """Lê um contrato de honorários e devolve o que deu para extrair."""
    caminho = Path(caminho)
    resultado = ResultadoContrato(caminho)
    origem = caminho.name

    try:
        texto = texto_do_pdf(caminho)
    except Exception as erro:
        resultado.erros.append("Não foi possível ler o PDF (%s): %s"
                               % (caminho.name, erro))
        return resultado

    if len(texto) < 400:
        resultado.erros.append(
            "PDF sem camada de texto suficiente (%d caracteres). Provavelmente é "
            "digitalização/imagem — não dá para extrair com segurança." % len(texto))
        return resultado

    bloco = _recortar(texto, _INICIO_CONTRATANTE)
    # Basta reconhecer que ali há uma qualificação. Exigir CPF aqui seria erro:
    # existe contrato real sem RG, e poderia existir sem CPF — nesse caso o
    # certo é extrair o resto e a falta do CPF virar pendência com o motivo
    # correto, não "modelo do contrato mudou".
    if not bloco or len(bloco) < 60 or not _QUALIFICACAO.search(bloco):
        resultado.erros.append(
            "Trecho de qualificação do Cliente Contratante não localizado no "
            "contrato — o modelo pode ter mudado.")
        return resultado

    resultado.contratante = parse_bloco(bloco, "contratante", origem)

    bloco_resp = _recortar(texto, _INICIO_RESPONSAVEL)
    if bloco_resp and len(bloco_resp) >= 60 and _QUALIFICACAO.search(bloco_resp):
        resultado.responsavel = parse_bloco(bloco_resp, "responsavel", origem)
        resultado.observacoes.append(
            "Contrato tem Cliente Responsável (corresponsável): %s."
            % (resultado.responsavel.nome.valor or "nome não identificado"))

    _parse_processo(texto, resultado, origem)
    _parse_honorarios(texto, resultado, origem)
    return resultado
