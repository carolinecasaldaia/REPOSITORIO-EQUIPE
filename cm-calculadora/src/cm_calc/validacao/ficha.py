"""Ficha do caso para validação: somente ENTRADAS (contrato e título), nunca resultados da perita.

Planilha com três abas:
- "parametros": chave | valor | fonte | observação
- "parcelas"  : nº | vencimento | valor contratado | tipo (regular / reforçada / extraordinária)
- "pagamentos": nº da parcela | data do pagamento | valor pago | encargos pagos

Cada parâmetro precisa de fonte (contrato, sentença, acórdão ou seção do
parecer que DESCREVE o critério). Parâmetro vazio = não informado; o que for
obrigatório e faltar impede a reconstrução.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from ..documentos.texto import valor_br

PARAMETROS: list[tuple[str, str, bool]] = [
    # chave, descrição / formato, obrigatório
    ("data_liberacao", "Data da liberação do crédito (DD/MM/AAAA)", True),
    ("valor_financiado", "Valor total financiado (R$)", True),
    ("taxa_mensal_contrato", "Taxa de juros mensal contratada (% a.m.)", True),
    ("taxa_anual_contrato", "Taxa anual contratada (% a.a.) — se houver", False),
    ("convencao_contrato", "Capitalização do contrato: meses_civis | meses_30 | dias_base_360 | dias_base_365", True),
    ("taxa_mensal_revisada", "Taxa mensal fixada no título (% a.m.)", True),
    ("taxa_anual_revisada", "Taxa anual fixada no título (% a.a.) — se houver", False),
    ("regime_revisado", "Regime de juros no recálculo: composto | simples", True),
    ("convencao_revisada", "Capitalização no recálculo: meses_civis | meses_30 | dias_base_360 | dias_base_365", True),
    ("valor_excluido_financiado", "Tarifas/seguros financiados excluídos pelo título (R$, soma) — 0 se nenhum", True),
    ("tratamento_reforcadas", "Parcelas reforçadas no recálculo: manter_valor | proporcional (vazio se não houver)", False),
    ("arredondamento", "Arredondamento: casas;modo;quando (por_parcela | final | integral) — ex.: 2;HALF_UP;por_parcela", True),
    ("modalidade_restituicao", "simples | dobro | dobro_a_partir_de", True),
    ("data_corte_dobro", "Data de corte da dobra (DD/MM/AAAA) — só para dobro_a_partir_de", False),
    ("encargos_no_ap03", "Encargos pagos no AP03: excluir (título afastou-os: restituir) | ignorar (fora do cálculo)", False),
    ("data_base", "Data-base da atualização (DD/MM/AAAA)", True),
    ("indice_correcao", "Nome da série de correção (ex.: INPC) — vazio = sem correção", False),
    ("incluir_mes_inicial", "Mês do pagamento entra na correção? sim | não", True),
    ("incluir_mes_final", "Mês da data-base entra na correção? sim | não", True),
    ("juros_mora_mensal", "Juros de mora (% a.m.) — vazio = sem juros", False),
    ("juros_mora_inicio", "Termo inicial dos juros de mora (DD/MM/AAAA)", False),
    ("juros_contagem", "Contagem dos juros: dias_30 | meses_civis", False),
    ("acumulacao_juros", "Acumulação dos juros: soma | produto", False),
]


@dataclass
class ParcelaFicha:
    numero: int
    vencimento: date
    valor: Decimal
    tipo: str          # regular | reforçada | extraordinária


@dataclass
class PagamentoFicha:
    numero: int
    data: date
    valor: Decimal
    encargos: Decimal


@dataclass
class FichaCaso:
    parametros: dict[str, str]
    fontes: dict[str, str]
    parcelas: list[ParcelaFicha]
    pagamentos: list[PagamentoFicha]

    def texto(self, chave: str) -> str | None:
        v = (self.parametros.get(chave) or "").strip()
        return v or None

    def decimal(self, chave: str) -> Decimal | None:
        v = self.texto(chave)
        return None if v is None else _decimal(v, chave)

    def percentual(self, chave: str) -> Decimal | None:
        v = self.decimal(chave)
        return None if v is None else v / Decimal(100)

    def data(self, chave: str) -> date | None:
        v = self.texto(chave)
        return None if v is None else _data(v, chave)

    def sim(self, chave: str) -> bool | None:
        v = self.texto(chave)
        return None if v is None else v.lower() in ("sim", "s", "yes", "true", "1")


def _decimal(v, onde: str) -> Decimal:
    if isinstance(v, (int, Decimal)):
        return Decimal(v)
    if isinstance(v, float):
        return Decimal(repr(v))
    s = str(v).replace("R$", "").replace("%", "").strip()
    try:
        return valor_br(s) if "," in s else Decimal(s)
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"{onde}: número inválido {v!r}") from e


def _data(v, onde: str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v).strip(), "%d/%m/%Y").date()
    except ValueError as e:
        raise ValueError(f"{onde}: data inválida {v!r} (use DD/MM/AAAA)") from e


def gerar_modelo(destino: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "parametros"
    negrito, fundo = Font(bold=True), PatternFill("solid", fgColor="DDE4EE")
    ws.append(["chave", "valor", "fonte (documento e página)", "descrição / formato", "obrigatório"])
    for c in ws[1]:
        c.font, c.fill = negrito, fundo
    for chave, desc, obrig in PARAMETROS:
        ws.append([chave, "", "", desc, "sim" if obrig else "não"])
    for col, larg in zip("ABCDE", (26, 18, 34, 80, 12)):
        ws.column_dimensions[col].width = larg
    for nome, cab in (("parcelas", ["numero", "vencimento", "valor", "tipo"]),
                      ("pagamentos", ["numero", "data_pagamento", "valor_pago", "encargos_pagos"])):
        w = wb.create_sheet(nome)
        w.append(cab)
        for c in w[1]:
            c.font, c.fill = negrito, fundo
        for col in "ABCD":
            w.column_dimensions[col].width = 20
    wb.create_sheet("instrucoes").append(
        ["Preencha só ENTRADAS (contrato e título). Não copie resultados da perita (juros, saldos, diferenças)."])
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def carregar_ficha(dados: bytes) -> FichaCaso:
    wb = load_workbook(io.BytesIO(dados), data_only=True)
    ws = wb["parametros"]
    params, fontes = {}, {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        chave = str(row[0]).strip()
        v = row[1]
        if isinstance(v, (datetime, date)):
            v = (v.date() if isinstance(v, datetime) else v).strftime("%d/%m/%Y")
        elif isinstance(v, float):
            v = str(Decimal(repr(v)))
        params[chave] = "" if v is None else str(v).strip()
        fontes[chave] = str(row[2] or "").strip()

    parcelas = []
    for i, row in enumerate(wb["parcelas"].iter_rows(min_row=2, values_only=True), start=2):
        if not row or row[0] in (None, ""):
            continue
        tipo = str(row[3] or "regular").strip().lower()
        tipo = {"reforcada": "reforçada", "extraordinaria": "extraordinária"}.get(tipo, tipo)
        if tipo not in ("regular", "reforçada", "extraordinária"):
            raise ValueError(f"parcelas, linha {i}: tipo inválido {row[3]!r}")
        parcelas.append(ParcelaFicha(int(_decimal(row[0], f"parcelas L{i}")), _data(row[1], f"parcelas L{i}"),
                                     _decimal(row[2], f"parcelas L{i}"), tipo))
    pagamentos = []
    for i, row in enumerate(wb["pagamentos"].iter_rows(min_row=2, values_only=True), start=2):
        if not row or row[0] in (None, ""):
            continue
        pagamentos.append(PagamentoFicha(int(_decimal(row[0], f"pagamentos L{i}")), _data(row[1], f"pagamentos L{i}"),
                                         _decimal(row[2], f"pagamentos L{i}"),
                                         _decimal(row[3], f"pagamentos L{i}") if row[3] not in (None, "") else Decimal(0)))
    return FichaCaso(params, fontes, parcelas, pagamentos)


def pendencias_ficha(f: FichaCaso, tabelas: set[str]) -> list[str]:
    pend = []
    for chave, desc, obrig in PARAMETROS:
        if obrig and not f.texto(chave):
            pend.append(f"parâmetro obrigatório vazio: {chave} ({desc})")
        if f.texto(chave) and not f.fontes.get(chave):
            pend.append(f"parâmetro sem fonte: {chave}")
    if not f.parcelas:
        pend.append("aba 'parcelas' vazia")
    if "AP03" in tabelas and not f.pagamentos:
        pend.append("aba 'pagamentos' vazia (necessária para o AP03)")
    if f.texto("modalidade_restituicao") == "dobro_a_partir_de" and not f.texto("data_corte_dobro"):
        pend.append("data_corte_dobro obrigatória para dobro_a_partir_de")
    if f.texto("juros_mora_mensal") and not all(f.texto(k) for k in ("juros_mora_inicio", "juros_contagem", "acumulacao_juros")):
        pend.append("juros de mora informados: preencha juros_mora_inicio, juros_contagem e acumulacao_juros")
    if any(p.encargos for p in f.pagamentos) and f.texto("encargos_no_ap03") not in ("excluir", "ignorar"):
        pend.append("há encargos pagos: informe encargos_no_ap03 (excluir | ignorar)")
    if any(p.tipo == "reforçada" for p in f.parcelas) and not f.texto("tratamento_reforcadas"):
        pend.append("há parcelas reforçadas: informe tratamento_reforcadas")
    nums = [p.numero for p in f.parcelas if p.tipo != "extraordinária"]
    if len(nums) != len(set(nums)):
        pend.append("número de parcela repetido na aba 'parcelas'")
    return pend
