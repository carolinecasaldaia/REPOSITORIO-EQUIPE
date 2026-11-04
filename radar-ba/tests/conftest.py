import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Segredos de teste, fixos, para o resultado ser reproduzível.
os.environ.setdefault("CPF_PEPPER", "pepper-de-teste-nao-usar-em-producao")
os.environ.setdefault("CPF_CHAVE", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")

from src.config import ajustes  # noqa: E402

ajustes.CPF_PEPPER = os.environ["CPF_PEPPER"]
ajustes.CPF_CHAVE = os.environ["CPF_CHAVE"]
