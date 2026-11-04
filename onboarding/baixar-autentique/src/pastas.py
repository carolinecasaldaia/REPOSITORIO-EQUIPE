#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Acha (ou cria) a pasta do cliente em PREPARAÇÃO PARA INGRESSO.

A pasta é organizada por mês — `PREPARAÇÃO PARA INGRESSO/AGOSTO 2026/<cliente>` —
e o nome da pasta traz marcações do comercial: "01 - OK - FULANO DE TAL",
"6 - INDICACAO ISRAEL - FULANO - AGUARDANDO DOC". Nada disso é nome de cliente.

Duas armadilhas conhecidas, das duas gerações de pasta que convivem lá:

1. A pasta pode ter erro de digitação que o documento não tem
   ("01 - OK - ANDESON" x "ANDERSON LOPES DA SILVA" no contrato). Por isso a
   comparação é por semelhança, não por igualdade.
2. O mesmo cliente aparece em dois meses quando a pasta é movida pelo Drive
   (JULHO/15 e AGOSTO/01 são o MESMO item do Drive). Empate assim não é
   ambiguidade: é a mesma pasta, e vence o mês mais recente.
"""

import difflib
import hashlib
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path

XATTR_DRIVE_ID = "com.google.drivefs.item-id#S"

MESES = ("JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO",
         "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")

# Prefixo numérico do comercial: "01 - ", "6 - ".
_PREFIXO_NUMERO = re.compile(r"^\s*\d{1,3}\s*[-–]\s*")

# Marcações operacionais que aparecem entre traços no nome da pasta.
_MARCACOES = ("OK", "AGUARDANDO DOC", "AGUARDANDO DOCUMENTO", "AGUARDANDO",
              "PENDENTE", "URGENTE", "REVISIONAL", "BUSCA E APREENSAO",
              "VEICULO APREENDIDO", "EMPRESTIMO GARANTIA", "EMPESTIMO GARANTIA",
              "INDICACAO", "ASSINADO", "CONTRATO", "PROCURACAO", "DECLARACAO")

_UFS = ("ACRE", "ALAGOAS", "AMAPA", "AMAZONAS", "BAHIA", "CEARA",
        "DISTRITO FEDERAL", "ESPIRITO SANTO", "GOIAS", "MARANHAO",
        "MATO GROSSO", "MATO GROSSO DO SUL", "MINAS GERAIS", "PARA", "PARAIBA",
        "PARANA", "PERNAMBUCO", "PIAUI", "RIO DE JANEIRO", "RIO GRANDE DO NORTE",
        "RIO GRANDE DO SUL", "RONDONIA", "RORAIMA", "SANTA CATARINA",
        "SAO PAULO", "SERGIPE", "TOCANTINS")

IGNORAR = (".DS_Store", ".git", "__pycache__", "RELATÓRIOS", "RELATORIOS",
           "MODELOS", "MODELO")

SUBPASTAS_PADRAO = ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO",
                    "ONBOARDING", "PETIÇÕES")


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c))


def limpo(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(texto)).strip().upper()


def normalizar_nome(nome: str) -> str:
    """Só letras e espaço, maiúsculas, sem acento — para comparar nomes."""
    alvo = limpo(nome)
    alvo = re.sub(r"[^A-Z ]+", " ", alvo)
    return re.sub(r"\s+", " ", alvo).strip()


def eh_pasta_de_mes(nome: str) -> bool:
    alvo = limpo(nome)
    return any(alvo.startswith(limpo(mes)) for mes in MESES)


def mes_para_chave(nome: str):
    """'AGOSTO 2026' -> (2026, 8). Serve para saber qual mês é o mais recente."""
    alvo = limpo(nome)
    ano = 0
    achado = re.search(r"(19|20)\d{2}", alvo)
    if achado:
        ano = int(achado.group(0))
    for numero, mes in enumerate(MESES, start=1):
        if alvo.startswith(limpo(mes)):
            return (ano, numero)
    return (ano, 0)


def nome_provavel_do_cliente(nome_pasta: str) -> str:
    """
    Tira do nome da pasta o prefixo numérico, as marcações e o estado.

    Serve só para casar pastas e mostrar na tela — o nome que vale é o do
    documento assinado.
    """
    nome = _PREFIXO_NUMERO.sub("", nome_pasta or "").strip()
    partes = [p.strip() for p in re.split(r"\s+[-–]\s+", nome) if p.strip()]
    uteis = []
    for parte in partes:
        alvo = limpo(parte)
        if alvo in _MARCACOES or alvo in _UFS:
            continue
        if any(alvo.startswith(m + " ") for m in _MARCACOES):
            continue
        uteis.append(parte)
    return re.sub(r"\s+", " ", " ".join(uteis) if uteis else nome).strip()


def nomes_do_documento(nome_documento: str) -> list:
    """
    Tenta extrair o nome do cliente do título do envelope no Autentique.

    "CONTRATO - PROCURAÇÃO - DECLARAÇÃO - ANDERSON" -> ["ANDERSON"]

    É pista fraca (muitas vezes só o primeiro nome), usada apenas quando os
    signatários não resolvem — e mesmo assim exigindo casamento forte.
    """
    palavras_de_documento = {
        "CONTRATO", "CONTRATOS", "PROCURACAO", "DECLARACAO", "DECLARACOES",
        "HIPOSSUFICIENCIA", "RESIDENCIA", "HONORARIOS", "HO", "ASSINADO",
        "ASSINATURA", "DOCUMENTOS", "DOCUMENTO", "PRESTACAO", "SERVICOS",
        "DE", "DA", "DO", "E",
    }
    candidatos = []
    for parte in re.split(r"\s*[-–_|]\s*", nome_documento or ""):
        alvo = normalizar_nome(parte)
        if not alvo:
            continue
        if all(palavra in palavras_de_documento for palavra in alvo.split()):
            continue
        candidatos.append(alvo)
    return candidatos


def pontuacao(nome_a: str, nome_b: str) -> float:
    """0 a 1 — quanto dois nomes se parecem."""
    a, b = normalizar_nome(nome_a), normalizar_nome(nome_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    tokens_a, tokens_b = a.split(), b.split()
    menor, maior = sorted((tokens_a, tokens_b), key=len)
    # "MARIA PEDROSA" dentro de "MARIA PEDROSA DE MORAIS BARROS": mesmo primeiro
    # nome e todos os pedaços presentes — é a mesma pessoa, com nome abreviado.
    if len(menor) >= 2 and set(menor) <= set(maior) and menor[0] == maior[0]:
        return 0.97
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Pastas no disco
# ---------------------------------------------------------------------------

def id_do_drive(caminho: Path):
    """ID real do item no Google Drive (xattr), ou um id local derivado."""
    try:
        saida = subprocess.run(["xattr", "-p", XATTR_DRIVE_ID, str(caminho)],
                               capture_output=True, timeout=10)
        if saida.returncode == 0:
            valor = saida.stdout.decode("utf-8", "ignore").strip()
            if valor:
                return valor
    except (OSError, subprocess.SubprocessError):
        pass
    return "local:" + hashlib.sha1(str(caminho).encode("utf-8")).hexdigest()[:24]


class PastaCliente(object):
    def __init__(self, caminho: Path, mes: str):
        self.caminho = Path(caminho)
        self.mes = mes
        self.nome_pasta = self.caminho.name
        self.nome = nome_provavel_do_cliente(self.nome_pasta)

    @property
    def chave_mes(self):
        return mes_para_chave(self.mes) if self.mes else (0, 0)

    def identidade(self):
        return id_do_drive(self.caminho)

    def __repr__(self):
        return "<PastaCliente %s/%s>" % (self.mes, self.nome_pasta)


def varrer(raiz) -> list:
    """Lista as pastas de cliente, aceitando cliente dentro do mês ou na raiz."""
    raiz = Path(raiz)
    encontradas = []
    if not raiz.exists():
        return encontradas
    for item in sorted(raiz.iterdir()):
        if not item.is_dir() or item.name in IGNORAR or item.name.startswith("."):
            continue
        if eh_pasta_de_mes(item.name):
            for sub in sorted(item.iterdir()):
                if sub.is_dir() and sub.name not in IGNORAR and not sub.name.startswith("."):
                    encontradas.append(PastaCliente(sub, item.name))
        else:
            encontradas.append(PastaCliente(item, ""))
    return encontradas


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------

class Resultado(object):
    """O que a busca achou: pasta (ou None), motivo e as opções consideradas."""

    def __init__(self, pasta=None, situacao="", motivo="", nota=0.0, alternativas=None):
        self.pasta = pasta
        self.situacao = situacao          # achou | ambiguo | nao_achou
        self.motivo = motivo
        self.nota = nota
        self.alternativas = alternativas or []

    @property
    def achou(self):
        return self.pasta is not None


def localizar(candidatas, nomes, limiar: float = 0.88, margem: float = 0.03) -> Resultado:
    """
    Escolhe a pasta do cliente entre `candidatas` a partir dos `nomes` do
    documento (signatários, na ordem de preferência).

    Empate real vira ambiguidade — a automação não chuta pasta de cliente.
    """
    nomes = [n for n in nomes if normalizar_nome(n)]
    if not nomes:
        return Resultado(situacao="nao_achou", motivo="O documento não trouxe nome de signatário.")

    melhores = []
    for pasta in candidatas:
        nota = max(pontuacao(nome, pasta.nome) for nome in nomes)
        if nota >= limiar:
            melhores.append((nota, pasta))
    if not melhores:
        vizinhos = sorted(
            ((max(pontuacao(nome, p.nome) for nome in nomes), p) for p in candidatas),
            key=lambda item: item[0], reverse=True)[:3]
        return Resultado(
            situacao="nao_achou",
            motivo="Nenhuma pasta parecida com \"%s\"." % nomes[0],
            alternativas=["%s (%s) — %d%% parecido" % (p.nome_pasta, p.mes or "raiz", round(n * 100))
                          for n, p in vizinhos if n > 0.5])

    melhores.sort(key=lambda item: (item[0], item[1].chave_mes), reverse=True)
    melhor_nota, melhor = melhores[0]
    empatados = [p for n, p in melhores if melhor_nota - n <= margem]

    if len(empatados) > 1:
        # Mesma pasta vista em dois meses (Drive move o item, o caminho antigo
        # continua aparecendo): não é ambiguidade.
        identidades = {p.identidade() for p in empatados}
        nomes_iguais = {normalizar_nome(p.nome) for p in empatados}
        # Nome igual em meses DIFERENTES é o mesmo cliente que mudou de mês
        # (Andeson em julho e em agosto): vale a mais recente. Nome igual no
        # MESMO mês são duas pastas de verdade — a Sofia dividida em
        # "- CONTRATO 1" e "- CONTRATO 2" (18/09/2026). Aí não se escolhe.
        meses = [p.mes for p in empatados]
        mesmo_mes = len(set(meses)) < len(meses)
        if len(identidades) > 1 and (len(nomes_iguais) > 1 or mesmo_mes):
            return Resultado(
                situacao="ambiguo",
                motivo="Mais de uma pasta parecida com \"%s\" — escolha à mão." % nomes[0],
                nota=melhor_nota,
                alternativas=["%s (%s)" % (p.nome_pasta, p.mes or "raiz") for p in empatados])
        melhor = sorted(empatados, key=lambda p: p.chave_mes, reverse=True)[0]

    return Resultado(pasta=melhor, situacao="achou", nota=melhor_nota,
                     motivo="Casou com a pasta \"%s\" (%s), %d%% de semelhança."
                            % (melhor.nome_pasta, melhor.mes or "raiz", round(melhor_nota * 100)))


# ---------------------------------------------------------------------------
# Criação
# ---------------------------------------------------------------------------

def nome_do_mes(quando: datetime = None) -> str:
    """Nome da pasta de mês no padrão do comercial: 'AGOSTO 2026'."""
    quando = quando or datetime.now()
    return "%s %d" % (MESES[quando.month - 1], quando.year)


def pasta_do_mes(raiz, quando: datetime = None) -> Path:
    """Pasta do mês, reaproveitando a que já existir (mesmo com outra grafia)."""
    raiz = Path(raiz)
    alvo = nome_do_mes(quando)
    chave = mes_para_chave(alvo)
    if raiz.exists():
        for item in raiz.iterdir():
            if item.is_dir() and eh_pasta_de_mes(item.name) and mes_para_chave(item.name) == chave:
                return item
    return raiz / alvo


def criar_pasta_cliente(raiz, nome_cliente: str, quando: datetime = None) -> Path:
    """
    Cria `<MÊS ANO>/<NOME DO CLIENTE>` com as cinco subpastas do padrão novo.

    O nome vem do documento assinado (maiúsculas, como as demais pastas), sem
    prefixo numérico — a numeração é do comercial e não é inventada aqui.
    """
    nome = re.sub(r"[/\\:]+", " ", (nome_cliente or "").strip())
    nome = re.sub(r"\s+", " ", nome).strip().upper()
    if not nome:
        raise ValueError("Sem nome de cliente para criar a pasta.")

    destino = pasta_do_mes(raiz, quando) / nome
    destino.mkdir(parents=True, exist_ok=True)
    for subpasta in SUBPASTAS_PADRAO:
        (destino / subpasta).mkdir(exist_ok=True)
    return destino
