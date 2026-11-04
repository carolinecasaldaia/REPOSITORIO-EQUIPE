"""Configuração do RADAR B&A.

Tudo que é segredo (chave da API, pepper do hash, chave de criptografia) vem do
arquivo .env, nunca do código. O .env fica em ~/.radar-ba/.env, fora do Drive,
para não ser sincronizado nem versionado.
"""
import os
from pathlib import Path

CASA = Path(os.path.expanduser("~/.radar-ba"))
ENV = CASA / ".env"
RAIZ = Path(__file__).resolve().parents[2]


def _carregar_env():
    """Lê o .env sem depender do pacote python-dotenv."""
    if not ENV.exists():
        return
    for linha in ENV.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()


def _txt(nome, padrao=""):
    return os.environ.get(nome, padrao).strip()


def _int(nome, padrao):
    try:
        return int(os.environ.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao


def _bool(nome, padrao=False):
    v = os.environ.get(nome)
    if v is None:
        return padrao
    return v.strip().lower() in ("1", "true", "sim", "yes", "on")


# --- DataJud (CNJ) ------------------------------------------------------
# A chave é pública e divulgada pelo próprio CNJ, mas mesmo assim fica no .env:
# o CNJ pode rotacioná-la a qualquer momento e não queremos editar código por isso.
DATAJUD_API_KEY = _txt("DATAJUD_API_KEY")
DATAJUD_BASE = _txt("DATAJUD_BASE", "https://api-publica.datajud.cnj.jus.br")
DATAJUD_RPM = _int("DATAJUD_RPM", 60)

# --- DJEN / API Comunica (CNJ) -----------------------------------------
DJEN_BASE = _txt("DJEN_BASE", "https://comunicaapi.pje.jus.br/api/v1")
# O header anuncia x-ratelimit-limit=20, mas 20/min NÃO se sustenta: medido em
# 18/08/2026, 18/min derrubou todas as consultas em 429 e insistir só renovava o
# castigo. A 10/min: 15 requisições seguidas, zero erro. Ficamos em 10.
DJEN_RPM = _int("DJEN_RPM", 10)
DJEN_ITENS_POR_PAGINA = _int("DJEN_ITENS_POR_PAGINA", 1000)

# --- e-SAJ --------------------------------------------------------------
# DESLIGADO POR PADRÃO. Só ligar após análise dos Termos de Uso de cada
# tribunal (ver docs/mapeamento-tribunais.md §4). A ausência de CAPTCHA é um
# fato técnico, não uma autorização.
ESAJ_HABILITADO = _bool("ESAJ_HABILITADO", False)
# Ritmo deliberadamente lento: 1 requisição a cada 5 segundos.
ESAJ_INTERVALO_S = _int("ESAJ_INTERVALO_S", 5)

# --- Segurança ----------------------------------------------------------
CPF_PEPPER = _txt("CPF_PEPPER")          # sal fixo do hash determinístico
CPF_CHAVE = _txt("CPF_CHAVE")            # chave AES-GCM (base64, 32 bytes)
RETENCAO_DIAS = _int("RETENCAO_DIAS", 1825)   # 5 anos

# --- Operação -----------------------------------------------------------
LOG_NIVEL = _txt("LOG_NIVEL", "INFO")
PASTA_RELATORIOS = RAIZ / "RELATÓRIOS"
PASTA_DADOS = CASA / "dados"
TENTATIVAS_MAX = _int("TENTATIVAS_MAX", 4)
