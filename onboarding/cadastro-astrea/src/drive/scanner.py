#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Varredura da pasta PREPARAÇÃO PARA INGRESSO.

Não usa a API do Google Drive. O Google Drive para Desktop já espelha as pastas
no Mac e — o achado que sustenta este módulo — grava o **ID real do arquivo no
Drive** no atributo estendido `com.google.drivefs.item-id`. É o mesmo ID que a
API devolveria, disponível localmente, sem OAuth, sem credencial da Google e
sem que documento de cliente saia da máquina.

Estrutura real (duas gerações convivem):

    PREPARAÇÃO PARA INGRESSO/
    ├── AGOSTO 2026/
    │   ├── 01 - OK - FULANO DE TAL/        ← nova: com subpastas
    │   │   ├── CONTRATO HO/
    │   │   ├── DOC CLIENTE/ ...
    │   └── SICRANO/
    └── JUNHO 2026/
        └── 11 - BELTRANO/                  ← antiga: arquivos soltos
"""

import hashlib
import re
import subprocess
import time
import unicodedata
from datetime import datetime
from pathlib import Path

XATTR_DRIVE_ID = "com.google.drivefs.item-id#S"

MESES = ("JANEIRO", "FEVEREIRO", "MARÇO", "MARCO", "ABRIL", "MAIO", "JUNHO",
         "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")

# Prefixos e marcações operacionais que o comercial põe no nome da pasta:
# "01 - OK - FULANO", "6 - INDICACAO ISRAEL - FULANO - AGUARDANDO DOC".
_PREFIXO_NUMERO = re.compile(r"^\s*\d{1,3}\s*[-–]\s*")
_MARCACOES = ("OK", "AGUARDANDO DOC", "AGUARDANDO DOCUMENTO", "AGUARDANDO",
              "PENDENTE", "URGENTE", "REVISIONAL", "BUSCA E APREENSAO",
              "BUSCA E APREENSÃO", "VEICULO APREENDIDO", "VEÍCULO APREENDIDO",
              "EMPESTIMO GARANTIA", "EMPRESTIMO GARANTIA", "INDICACAO",
              "INDICAÇÃO")
_UFS = ("ACRE", "ALAGOAS", "AMAPÁ", "AMAPA", "AMAZONAS", "BAHIA", "CEARÁ", "CEARA",
        "DISTRITO FEDERAL", "ESPÍRITO SANTO", "ESPIRITO SANTO", "GOIÁS", "GOIAS",
        "MARANHÃO", "MARANHAO", "MATO GROSSO", "MATO GROSSO DO SUL",
        "MINAS GERAIS", "PARÁ", "PARA", "PARAÍBA", "PARAIBA", "PARANÁ", "PARANA",
        "PERNAMBUCO", "PIAUÍ", "PIAUI", "RIO DE JANEIRO", "RIO GRANDE DO NORTE",
        "RIO GRANDE DO SUL", "RONDÔNIA", "RONDONIA", "RORAIMA", "SANTA CATARINA",
        "SÃO PAULO", "SAO PAULO", "SERGIPE", "TOCANTINS")

# Para NOMEAR o mês corrente. Não dá para usar MESES: ela tem 13 itens, com
# "MARÇO" e "MARCO" separados, porque serve para reconhecer pasta escrita de
# qualquer jeito — usá-la para indexar joga o mês uma casa para trás.
NOMES_DO_MES = ("JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
                "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")

IGNORAR_PASTAS = (".DS_Store", ".git", "__pycache__", "RELATÓRIOS", "RELATORIOS")


def sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c))


def _limpo(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(texto)).strip().upper()


def eh_pasta_de_mes(nome: str) -> bool:
    alvo = _limpo(nome)
    return any(alvo.startswith(_limpo(mes)) for mes in MESES)


def nome_provavel_do_cliente(nome_pasta: str) -> str:
    """
    Tenta adivinhar o nome do cliente a partir do nome da pasta.

    Serve APENAS para exibir na tela e casar pastas — nunca como fonte de
    cadastro. A pasta "01 - OK - ANDESON LOPES DA SILVA" tem um erro de
    digitação que o contrato assinado ("ANDERSON") não tem; quem manda é
    o documento.
    """
    nome = _PREFIXO_NUMERO.sub("", nome_pasta or "").strip()
    partes = [p.strip() for p in re.split(r"\s+[-–]\s+", nome) if p.strip()]
    uteis = []
    for parte in partes:
        alvo = _limpo(parte)
        if alvo in _MARCACOES or alvo in _UFS:
            continue
        if any(alvo.startswith(m + " ") for m in _MARCACOES):
            continue
        uteis.append(parte)
    return re.sub(r"\s+", " ", " ".join(uteis) if uteis else nome).strip()


# ---------------------------------------------------------------------------
# ID da pasta no Google Drive
# ---------------------------------------------------------------------------

def id_do_drive(caminho: Path):
    """
    Devolve (id, origem). origem: 'drive' quando é o ID real do Google Drive;
    'local' quando o atributo não existe (pasta fora do Drive, ou Drive não
    instalado) e caímos num identificador derivado do caminho.
    """
    try:
        saida = subprocess.run(["xattr", "-p", XATTR_DRIVE_ID, str(caminho)],
                               capture_output=True, timeout=10)
        if saida.returncode == 0:
            valor = saida.stdout.decode("utf-8", "ignore").strip()
            if valor:
                return valor, "drive"
    except (OSError, subprocess.SubprocessError):
        pass
    digest = hashlib.sha1(str(caminho).encode("utf-8")).hexdigest()[:24]
    return "local:" + digest, "local"


# ---------------------------------------------------------------------------
# Estabilidade e disponibilidade
# ---------------------------------------------------------------------------

def _mtime_mais_recente(pasta: Path):
    """Modificação mais recente em qualquer arquivo/subpasta (recursivo)."""
    mais_recente = 0.0
    try:
        mais_recente = pasta.stat().st_mtime
    except OSError:
        return 0.0
    for item in pasta.rglob("*"):
        if item.name == ".DS_Store":
            continue
        try:
            mais_recente = max(mais_recente, item.stat().st_mtime)
        except OSError:
            continue
    return mais_recente


def minutos_parada(pasta: Path) -> float:
    ultimo = _mtime_mais_recente(pasta)
    if not ultimo:
        return 0.0
    return max(0.0, (time.time() - ultimo) / 60.0)


def arquivo_disponivel(caminho: Path) -> bool:
    """
    True se o conteúdo do arquivo pode ser lido agora.

    No Google Drive em modo streaming o arquivo aparece na listagem mas o
    conteúdo ainda está na nuvem. Ler dispara o download; se falhar, é melhor
    esperar a próxima rodada do que registrar erro de leitura.
    """
    try:
        with open(str(caminho), "rb") as fh:
            return bool(fh.read(512)) or caminho.stat().st_size == 0
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Varredura
# ---------------------------------------------------------------------------

class PastaCliente(object):
    def __init__(self, caminho: Path, mes: str):
        self.caminho = caminho
        self.mes = mes
        self.nome_pasta = caminho.name
        self.nome_provavel = nome_provavel_do_cliente(caminho.name)
        self.drive_id, self.origem_id = id_do_drive(caminho)
        self._minutos_parada = None

    @property
    def minutos_parada(self) -> float:
        if self._minutos_parada is None:
            self._minutos_parada = minutos_parada(self.caminho)
        return self._minutos_parada

    def estavel(self, minutos: int) -> bool:
        return self.minutos_parada >= minutos

    def criada_em(self) -> datetime:
        try:
            st = self.caminho.stat()
            # st_birthtime existe no macOS; em outros sistemas cai no mtime.
            return datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_mtime))
        except OSError:
            return datetime.fromtimestamp(0)

    def arquivos(self):
        saida = []
        for item in sorted(self.caminho.rglob("*")):
            if item.is_dir() or item.name.startswith("."):
                continue
            saida.append(item)
        return saida

    def vazia(self) -> bool:
        return not self.arquivos()

    def __repr__(self):
        return "<PastaCliente %s/%s>" % (self.mes, self.nome_pasta)


# "A PARTIR DE SETEMBRO 2026" / "DESDE SETEMBRO 2026" (já sem acento, maiúsculo).
_A_PARTIR_DE = re.compile(r"^(?:A PARTIR DE|DESDE)\s+(.+)$")


def _meses_desde(inicio, agora):
    """
    Decisão dela (25/09/2026): a automação cuida de SETEMBRO 2026 em diante
    e nunca dos meses anteriores. Com "atual", a pasta de setembro sairia da
    varredura em 1º de outubro, e cliente de setembro que ainda esperava
    documento nunca seria cadastrado.
    """
    partes = inicio.split()
    nomes = [_limpo(m) for m in NOMES_DO_MES]
    if len(partes) != 2 or partes[0] not in nomes or not partes[1].isdigit():
        raise ValueError("MESES inválido: 'a partir de %s' — use, por exemplo, "
                         "'a partir de SETEMBRO 2026'." % inicio)
    mes, ano = nomes.index(partes[0]) + 1, int(partes[1])
    ultimo = agora.year * 12 + agora.month          # mês que vem, inclusive
    saida = []
    while ano * 12 + mes - 1 <= ultimo:
        saida.append("%s %d" % (NOMES_DO_MES[mes - 1], ano))
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1
    return saida


def meses_aceitos(config_meses):
    """
    Traduz a configuração MESES para uma lista de nomes de pasta de mês.

    "" (vazio)      -> todos os meses
    "atual"         -> só a pasta do mês corrente (AGOSTO 2026, hoje)
    "AGOSTO 2026"   -> só essa, fixa (aceita vários, separados por vírgula)
    "a partir de SETEMBRO 2026"
                    -> esse mês e todos os seguintes, até o mês que vem
                       (o comercial às vezes cria a pasta do mês seguinte
                       antes da virada); nunca os anteriores
    """
    bruto = (config_meses or "").strip()
    if not bruto:
        return None
    pedacos = [p.strip() for p in bruto.split(",") if p.strip()]
    saida = []
    for pedaco in pedacos:
        inicio = _A_PARTIR_DE.match(_limpo(pedaco))
        if inicio:
            saida.extend(_meses_desde(inicio.group(1), datetime.now()))
        elif _limpo(pedaco) in ("ATUAL", "MES ATUAL", "CORRENTE"):
            agora = datetime.now()
            saida.append("%s %d" % (NOMES_DO_MES[agora.month - 1], agora.year))
        else:
            saida.append(pedaco)
    return [_limpo(s) for s in saida]


def varrer(raiz: Path, meses=None):
    """
    Devolve a lista de pastas de cliente encontradas.

    Aceita as duas organizações: pastas de mês contendo clientes, e clientes
    soltos direto na raiz.

    `meses` (opcional) limita a varredura a certas pastas de mês — é o que
    permite a automação cuidar só do mês corrente, sem revisitar o histórico
    que já foi tratado à mão.
    """
    raiz = Path(raiz)
    encontradas = []
    if not raiz.exists():
        return encontradas

    for item in sorted(raiz.iterdir()):
        if not item.is_dir() or item.name in IGNORAR_PASTAS or item.name.startswith("."):
            continue
        if eh_pasta_de_mes(item.name):
            if meses is not None and _limpo(item.name) not in meses:
                continue
            for sub in sorted(item.iterdir()):
                if sub.is_dir() and sub.name not in IGNORAR_PASTAS \
                        and not sub.name.startswith("."):
                    encontradas.append(PastaCliente(sub, item.name))
        elif meses is None:
            encontradas.append(PastaCliente(item, ""))
    return encontradas
