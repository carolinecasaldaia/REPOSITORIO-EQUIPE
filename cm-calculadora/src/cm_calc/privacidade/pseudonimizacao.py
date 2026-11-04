"""Pseudonimização local de dados pessoais.

Substitui por marcadores estáveis ([CPF_1], [NOME_2]...) e guarda a tabela
de correspondência SOMENTE localmente (nunca vai no pacote). Valores,
datas, taxas e índices são mantidos — são necessários à interpretação.

Limitação: detecção por padrões. Nomes só são reconhecidos quando aparecem
após rótulos (Autor, Réu, Emitente, Nome...) ou em CAIXA ALTA seguida de
qualificação ("brasileiro", "inscrito no CPF"...). Depois de descobertos,
são substituídos em todas as ocorrências. Por isso há a verificação
residual: se sobrar padrão de dado pessoal, o pacote é bloqueado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PADROES: list[tuple[str, str]] = [
    ("PROCESSO", r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"),
    ("CNPJ", r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    ("CPF", r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\bCPF[^\d\n]{0,15}\d{11}\b"),
    ("EMAIL", r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    ("TELEFONE", r"\(?\b\d{2}\)?\s?9?\d{4}-\d{4}\b"),
    ("CEP", r"\b\d{5}-\d{3}\b"),
    ("PLACA", r"\b[A-Z]{3}-?\d[A-Z0-9]\d{2}\b"),
    ("CHASSI", r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    ("RENAVAM", r"(?i:renavam)[^\d\n]{0,10}\d{9,11}"),
    ("RG", r"(?i:\bRG\b|carteira de identidade)[^\d\n]{0,10}[\d.\-xX]{5,15}"),
    ("OAB", r"(?i:OAB)\s*/?\s*[A-Z]{2}\s*(?:n[ºo°]\.?\s*)?[\d.]{3,8}"),
    ("CONTA", r"(?i:ag[eê]ncia|conta(?: corrente)?)\s*(?:n[ºo°]\.?\s*)?:?\s*[\d\-]{3,15}"),
    ("ENDERECO", r"(?i:\b(?:rua|avenida|av\.|travessa|alameda|rodovia|estrada|pra[çc]a)\s+[^,\n]{2,60}(?:,\s*(?:n[ºo°]\.?\s*)?\d+)?)"),
    ("NASCIMENTO", r"(?i:nascid[oa] em)\s*\d{1,2}/\d{1,2}/\d{4}"),
]

ROTULOS_NOME = (r"(?i:\b(?:nome|autor[a]?|r[ée]u|requerente|requerid[oa]|emitente|devedor[a]?|cliente|fiduciante|"
                r"apelante|apelad[oa]|embargante|embargad[oa]|advogad[oa]|procurador[a]?|perit[oa]|juiz[a]?|"
                r"relator[a]?|desembargador[a]?|exequente|executad[oa]|avalista|benefici[aá]rio)\b)\s*[:\-–]?\s*")
# nomes nunca atravessam a quebra de linha (senão capturam o rótulo da linha seguinte)
NOME = r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç']+(?:[ \t]+(?:d[aeo]s?|e)?[ \t]*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç']+){1,6})"
NOME_QUALIFICADO = (r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:[ \t]+(?:D[AEO]S?|E)?[ \t]*[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,6}),?\s+"
                    r"(?i:brasileir[oa]|portador[a]? d|inscrit[oa] no cpf|casad[oa]|solteir[oa]|divorciad[oa]|vi[uú]v[oa])")
NAO_NOMES = {"BANCO", "S.A", "LTDA", "CÉDULA", "CONTRATO", "SENTENÇA", "ACÓRDÃO", "TRIBUNAL", "PODER JUDICIÁRIO"}


@dataclass
class Pseudonimizador:
    mapa: dict[str, str] = field(default_factory=dict)   # original -> marcador (fica local)
    contagem: dict[str, int] = field(default_factory=dict)

    def _marcador(self, tipo: str, original: str) -> str:
        chave = original.strip()
        if chave not in self.mapa:
            self.contagem[tipo] = self.contagem.get(tipo, 0) + 1
            self.mapa[chave] = f"[{tipo}_{self.contagem[tipo]}]"
        return self.mapa[chave]

    def descobrir_nomes(self, texto: str) -> None:
        for m in re.finditer(ROTULOS_NOME + NOME, texto):
            nome = m.group(1).strip()
            if not any(p in nome.upper() for p in NAO_NOMES):
                self._marcador("NOME", nome)
        for m in re.finditer(NOME_QUALIFICADO, texto):
            nome = m.group(1).strip()
            if not any(p in nome for p in NAO_NOMES):
                self._marcador("NOME", nome)

    def aplicar(self, texto: str) -> str:
        self.descobrir_nomes(texto)
        for tipo, pad in PADROES:
            texto = re.sub(pad, lambda m, t=tipo: self._marcador(t, m.group(0)), texto)
        nomes = sorted(((o, m) for o, m in self.mapa.items() if m.startswith("[NOME_")), key=lambda kv: -len(kv[0]))
        # fase 1: nomes completos (do mais longo ao mais curto)
        for original, marcador in nomes:
            texto = re.sub(re.escape(original), marcador, texto, flags=re.IGNORECASE)
        # fase 2: primeiro nome e último sobrenome isolados ("a autora Joana")
        for original, marcador in nomes:
            partes = [p for p in original.split() if len(p) > 3 and p.lower() not in ("dos", "das", "de", "da", "do")]
            if len(partes) >= 2:
                for p in (partes[0], partes[-1]):
                    texto = re.sub(rf"\b{re.escape(p)}\b", marcador, texto, flags=re.IGNORECASE)
        return texto


def residuos(texto: str, nomes_conhecidos: list[str] | None = None) -> list[str]:
    """Dados pessoais que ainda restam no texto (deve ser vazio para liberar o pacote)."""
    achados = []
    for tipo, pad in PADROES:
        if tipo in ("ENDERECO",):
            continue
        for m in re.finditer(pad, texto):
            achados.append(f"{tipo}: {m.group(0)[:4]}…")
    for m in re.finditer(NOME_QUALIFICADO, texto):
        achados.append(f"NOME: {m.group(1)[:3]}…")
    for n in nomes_conhecidos or []:
        if re.search(re.escape(n), texto, flags=re.IGNORECASE):
            achados.append(f"NOME conhecido: {n[:3]}…")
    return achados
