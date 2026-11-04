"""Reexporta o parecer fictício (definido em cm_calc.demonstracao.parecer_ficticio; independente do motor)."""

from cm_calc.demonstracao.parecer_ficticio import *  # noqa: F401,F403
from cm_calc.demonstracao.parecer_ficticio import (  # noqa: F401
    ap01, ap02, ap03, csv_indice, gerar_pdf, pagamentos, parcelas_contrato, preencher_ficha, P_CONTRATO, P_REVISADA,
)
