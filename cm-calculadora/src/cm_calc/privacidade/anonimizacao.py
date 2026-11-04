"""Anonimização LOCAL de documentos (PDF, XLSX, CSV) com verificação automática.

PDF — redação real (o texto sob a tarja é apagado do arquivo, não apenas coberto):
1. Detecta identificadores em todo o documento (padrões + nomes por rótulo/qualificação +
   lista de termos informada pela advogada). Valores, percentuais e datas financeiras são
   protegidos: nenhum trecho que seja só número monetário, percentual ou data é removido.
2. Aplica redação em todas as ocorrências, em todas as páginas.
3. Remove imagens incorporadas (assinaturas, QR codes, carimbos), anotações, campos,
   anexos, links, JavaScript, miniaturas, marcadores (sumário) e metadados (Info e XMP).
4. Salva uma CÓPIA (o original nunca é alterado) com limpeza de objetos órfãos.

Verificação (sem exibir dados pessoais):
- original intacto (hash antes = depois);
- nenhum texto removido reaparece na cópia; varredura de resíduos;
- zero imagens, anotações, anexos, metadados e marcadores;
- todos os valores monetários, percentuais e datas preservados (exceto os que integravam
  um dado pessoal removido, como data de nascimento);
- tabelas dos apêndices idênticas às do original.

Camadas tratadas (v0.6.9):
- texto visível, invisível, branco, minúsculo, dentro de XObjects e FORA da área da página;
- identificadores por POSIÇÃO (rótulo de coluna com o valor embaixo ou ao lado — certidões, quadros);
- imagens incorporadas e em linha; desenhos vetoriais com muitas curvas (rubricas, assinaturas e
  logotipos desenhados) — removidos sem apagar o texto;
- estruturas internas: formulários e assinaturas digitais (AcroForm, DSS), árvore de estrutura
  (texto alternativo), rótulos de página, nomes, ações, metadados por objeto, camadas opcionais;
- histórico de revisões (o arquivo é regravado inteiro, sem atualizações incrementais).
A verificação refaz todas as buscas na cópia e varre as cadeias de texto de TODOS os objetos do PDF.

Limitações: dados dentro de imagens (páginas digitalizadas) não são lidos — a página digitalizada
reprova; nome escrito à mão como vetor é removido pela forma (curvas), não pelo conteúdo; texto
convertido em contornos com poucas curvas e identificadores sem rótulo nem formato conhecido não
são reconhecidos — por isso a conferência visual humana continua obrigatória.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

from .pseudonimizacao import NAO_NOMES, NOME, NOME_QUALIFICADO, PADROES, ROTULOS_NOME

TITULOS = r"(?:(?:Dr|Dra|Sr|Sra|Me|Ma|Eng|Prof|Profa)\.?[ \t]+)?"
EXTRAS: list[tuple[str, str]] = [
    ("PROCESSO", r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"),
    # número CNJ quebrado no fim da linha ("0703182-" / "45.2025.8.02.0001")
    ("PROCESSO", r"\b\d{7}-\s*\d{2}\.\s*\d{4}\.\s*\d\.\s*\d{2}\.\s*\d{4}\b"),
    # assinatura digital do Adobe/ICP ("Assinado de forma digital por NOME:CPF")
    ("ASSINATURA", r"(?i:assinado de forma digital por:?[ \t]*)([^\n]{3,80})"),
    # rótulo numa linha e valor na linha seguinte (certidões, quadros de qualificação)
    ("IDENTIFICADOR", r"(?im)^[ \t]*(?:CPF|RG|CNPJ|REGISTRO|MATR[IÍ]CULA|N[º°o]\.?\s*(?:DE\s+)?REGISTRO|"
                      r"CARTEIRA(?: DE IDENTIDADE)?|IDENTIDADE)[ \t]*:?[ \t]*\n[ \t]*(?=[^\n]*\d)([A-Z0-9][\w.\-/ ]{2,30})$"),
    # documentos de identificação com rótulo e valor na mesma linha, com variações de grafia e de formato
    # ("R.G. nº MG-12.345.678", "RG 1234567 SSP/AL", "CTPS 1234567 série 0012", "Matrícula 445566")
    ("IDENTIFICADOR", r"(?i:\b(?:R\.[ \t]?G\b\.?|RG\b|registro geral|carteira de identidade|c[ée]dula de identidade|"
                      r"identidade|n[ºo°]\.?[ \t]*(?:de[ \t]+)?registro|registro|matr[íi]cula|PIS(?:/PASEP)?|PASEP|NIT|"
                      r"CTPS|CNH|t[íi]tulo de eleitor|passaporte))[ \t]*(?:n[ºo°]\.?|n[úu]mero)?[ \t]*[:\-–]?[ \t]*"
                      r"((?:[A-Z]{2}[ \t]*-[ \t]*)?\d[\d.\-/xX]{2,20}[A-Z]?(?:[ \t]*s[ée]rie[ \t]*\d+)?"
                      r"(?:[ \t]*(?:SSP|SDS|SESP|SSPDS|PC|IFP|DETRAN|SJS)[ \t]*[/\-]?[ \t]*[A-Z]{2})?)"),
    ("PROCESSO", r"(?i:(?:processo|autos|apela[çc][ãa]o(?: c[íi]vel)?|recurso)\s*(?:n[ºo°.]*|n[úu]mero)?\s*:?\s*)(\d[\d.\-/]{6,}\d)"),
    ("CONTRATO", r"(?i:(?:contrato|c[ée]dula(?: de cr[ée]dito banc[áa]rio)?|ccb|proposta|opera[çc][ãa]o)\s*(?:n[ºo°.]*|n[úu]mero)\s*:?\s*)([A-Z0-9][\w.\-/]{3,30})"),
    ("ASSINATURA", r"(?i:assinad[oa] (?:digital|eletronica)mente por:?[ \t]*)([^\n,;–]{3,80}?)(?=[ \t]+-[ \t]|[ \t]*\n|,|$)"),
    ("REGISTRO_PROFISSIONAL", r"\b(?:CRC|CREA|CORECON|CRA|CRECI|OAB|CRM)\s*[/-]?\s*[A-Z]{2}\s*(?:n[ºo°.]*\s*)?[\d.\-]{3,12}"),
    ("URL", r"https?://\S+|www\.\S+"),
    ("ID_DOCUMENTO", r"\b\d{15,}\b"),
    ("ID_DOCUMENTO", r"\bNum\.\s*\d{6,}"),
]
FINANCEIRO = [
    r"\d{1,3}(?:\.\d{3})*,\d{2,}",          # 1.234,56
    r"\d+(?:,\d+)?\s?%",                    # 1,99%
    r"\d{1,2}/\d{1,2}/\d{4}",               # 10/02/2023
]
RE_ROTULO_TARJA = re.compile(r"\[[A-Z_]+(?: \(parte\))?\]")
RE_FIN = re.compile("|".join(f"(?:{p})" for p in FINANCEIRO))


def cpf_valido(n: str) -> bool:
    if len(n) != 11 or len(set(n)) == 1:
        return False
    for k in (9, 10):
        s = sum(int(n[i]) * (k + 1 - i) for i in range(k))
        if (s * 10 % 11) % 10 != int(n[k]):
            return False
    return True


def cnpj_valido(n: str) -> bool:
    if len(n) != 14 or len(set(n)) == 1:
        return False
    for k, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        r = sum(int(n[i]) * pesos[i] for i in range(k)) % 11
        if (0 if r < 2 else 11 - r) != int(n[k]):
            return False
    return True


def protegido(s: str) -> bool:
    """Trecho que é só dado financeiro (valor, percentual ou data) — nunca removido."""
    t = s.strip().replace("R$", "").strip()
    return bool(re.fullmatch(r"(?:%s)" % "|".join(FINANCEIRO), t)) or bool(re.fullmatch(r"[\d.,\s]+", t) and "," in t)


@dataclass
class Item:
    tipo: str
    texto: str


def detectar(texto: str, termos: list[str] | None = None, extras: list[Item] | None = None) -> list[Item]:
    """Identificadores pessoais (únicos) no texto. A ordem não importa; duplicatas removidas.
    `extras`: identificadores achados por posição na página (ver `detectar_por_posicao`)."""
    achados: dict[str, str] = {}

    def add(tipo: str, s: str) -> None:
        s = " ".join(s.split()).strip(" .,;:-–")
        if len(s) < 3 or protegido(s) or s in achados:
            return
        if RE_FIN.search(s) and tipo != "NASCIMENTO":
            return        # nunca remover trecho que contenha valor, percentual ou data (integridade financeira)
        if tipo == "IDENTIFICADOR" and len(re.findall(r"\d", s)) < 4:
            return        # número de documento tem ao menos 4 dígitos (evita "registro 1", anos soltos etc.)
        achados[s] = tipo

    texto = RE_ROTULO_TARJA.sub("\n", texto)      # rótulos inseridos pela própria tarja não são dados

    for t in termos or []:
        if t.strip():
            add("TERMO_INFORMADO", t.strip())
    for it in extras or []:
        add(it.tipo, it.texto)
    # CPF/CNPJ sem pontuação e sem rótulo (ex.: ":12345678909" após nome em assinatura digital):
    # só números que passam no dígito verificador — nunca valores financeiros
    for m in re.finditer(r"(?<![\d.,])(\d{11}|\d{14})(?![\d.,])", texto):
        n = m.group(1)
        if (len(n) == 11 and cpf_valido(n)) or (len(n) == 14 and cnpj_valido(n)):
            add("CPF" if len(n) == 11 else "CNPJ", n)
    for tipo, pad in EXTRAS + PADROES:
        for m in re.finditer(pad, texto):
            add(tipo, m.group(m.lastindex or 0) if m.lastindex else m.group(0))
    # endereço de internet / e-mail quebrado no fim da linha: a continuação (1ª palavra da linha seguinte,
    # quando tem cara de endereço) também é identificador — costuma conter números de documento
    for m in re.finditer(r"(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]*\.?[\w.]*", texto):
        if texto[m.end():m.end() + 1] == "\n":
            seguinte = re.match(r"\n\s*(\S+)", texto[m.end():])
            if seguinte and re.search(r"[/?=&%#@]|\.\w{2,}|\d{5,}", seguinte.group(1)):
                add("URL", seguinte.group(1))
    for m in re.finditer(ROTULOS_NOME + TITULOS + NOME, texto):
        nome = m.group(1)
        if not any(p in nome.upper() for p in NAO_NOMES):
            add("NOME", nome)
    for m in re.finditer(NOME_QUALIFICADO, texto):
        if not any(p in m.group(1) for p in NAO_NOMES):
            add("NOME", m.group(1))
    # partes de nomes (primeiro nome e último sobrenome) aparecem isoladas no texto
    for s, tipo in list(achados.items()):
        if tipo in ("NOME", "ASSINATURA", "TERMO_INFORMADO") and not re.search(r"\d", s):
            partes = [p for p in s.split() if len(p) > 3 and p.lower() not in ("dos", "das", "de", "da", "do")]
            if len(partes) >= 2:
                for p in (partes[0], partes[-1]):
                    if re.search(rf"\b{re.escape(p)}\b", texto, re.I) and p not in achados:
                        achados[p] = "NOME (parte)"
    return [Item(tipo=t, texto=s) for s, t in achados.items()]


def tokens_financeiros(texto: str) -> Counter:
    return Counter(m.group(0).replace(" ", "") for m in RE_FIN.finditer(texto))


@dataclass
class Remocao:
    pagina: int
    tipo: str
    texto: str


@dataclass
class Verificacao:
    original_intacto: bool
    residuos_removidos: int
    residuos_padrao: dict[str, int]
    imagens: int
    anotacoes: int
    anexos: int
    metadados_vazios: bool
    marcadores: int
    tokens_financeiros_original: int
    tokens_financeiros_preservados: int
    tokens_ausentes: list[str]
    tabelas_identicas: bool | None
    paginas_digitalizadas: list[int]
    nao_localizados: list[str] = field(default_factory=list)
    reaparecendo_por_tipo: dict[str, int] = field(default_factory=dict)
    nao_localizados_por_tipo: dict[str, int] = field(default_factory=dict)
    residuos_estruturais: dict[str, int] = field(default_factory=dict)
    vetores_suspeitos: int = 0
    estruturas_internas: int = 0
    revisoes: int = 1
    texto_fora_da_pagina: int = 0
    imagens_detalhe: list[dict] = field(default_factory=list)

    @property
    def aprovada(self) -> bool:
        return (self.original_intacto and self.residuos_removidos == 0 and self.imagens == 0 and self.anotacoes == 0
                and self.anexos == 0 and self.metadados_vazios and self.marcadores == 0 and not self.tokens_ausentes
                and self.tabelas_identicas is not False and not self.paginas_digitalizadas and not self.nao_localizados
                and not self.residuos_padrao     # qualquer identificador residual reprova (não é só informativo)
                and not self.residuos_estruturais and self.vetores_suspeitos == 0 and self.estruturas_internas == 0
                and self.revisoes <= 1 and self.texto_fora_da_pagina == 0)


@dataclass
class Resultado:
    origem: Path
    destino: Path
    sha256_original: str
    sha256_anonimizado: str
    remocoes: list[Remocao]
    imagens_removidas: int
    verificacao: Verificacao
    vetores_removidos: int = 0
    camadas_opcionais: int = 0
    imagens_neutralizadas: int = 0
    imagens_retidas: list[dict] = field(default_factory=list)
    imagens_por_funcao: dict[str, int] = field(default_factory=dict)

    def resumo(self) -> dict:
        """Sem dados pessoais: só tipos, quantidades e páginas."""
        por_tipo = Counter(r.tipo for r in self.remocoes)
        paginas = sorted({r.pagina for r in self.remocoes})
        v = self.verificacao
        return {
            "versao_rotina": _versao(), "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "arquivo_original": self.origem.name, "arquivo_anonimizado": self.destino.name,
            "sha256_original": self.sha256_original, "sha256_anonimizado": self.sha256_anonimizado,
            "remocoes_por_tipo": dict(sorted(por_tipo.items())), "paginas_com_remocao": paginas,
            "imagens_removidas": self.imagens_removidas, "desenhos_vetoriais_removidos": self.vetores_removidos,
            "camadas_opcionais_reveladas": self.camadas_opcionais,
            "imagens_no_original_por_funcao_provavel": self.imagens_por_funcao,
            "imagens_removidas_pela_rede_de_seguranca": self.imagens_neutralizadas,
            "imagens_retidas_para_conferencia_humana": self.imagens_retidas,
            "verificacao": {
                "aprovada": v.aprovada, "original_intacto": v.original_intacto,
                "textos_removidos_reaparecendo": v.residuos_removidos,
                "residuos_por_tipo": v.residuos_padrao, "imagens_restantes": v.imagens,
                "anotacoes_restantes": v.anotacoes, "anexos_restantes": v.anexos, "metadados_vazios": v.metadados_vazios,
                "marcadores_restantes": v.marcadores,
                "dados_financeiros": f"{v.tokens_financeiros_preservados}/{v.tokens_financeiros_original} preservados",
                "dados_financeiros_ausentes": len(v.tokens_ausentes),
                "tabelas_identicas": v.tabelas_identicas, "paginas_digitalizadas": v.paginas_digitalizadas,
                "termos_nao_localizados_no_pdf": len(v.nao_localizados),
                "reaparecendo_por_tipo": v.reaparecendo_por_tipo,
                "nao_localizados_por_tipo": v.nao_localizados_por_tipo,
                "residuos_em_estruturas_internas": v.residuos_estruturais,
                "desenhos_vetoriais_restantes": v.vetores_suspeitos,
                "estruturas_internas_restantes": v.estruturas_internas,
                "revisoes_no_arquivo": v.revisoes, "texto_fora_da_pagina": v.texto_fora_da_pagina,
                "imagens_restantes_detalhe": v.imagens_detalhe,
            },
        }


def _versao() -> str:
    from .. import __version__
    return __version__


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- PDF ------------------------------------------------------------------------------------

def _norm_char(c: str) -> str:
    """Caractere sem acento e em minúscula; ligaduras (ﬁ, ﬂ) expandidas."""
    d = unicodedata.normalize("NFKD", c)
    return "".join(x for x in d if unicodedata.category(x) != "Mn").lower()


def normalizar_busca(s: str) -> str:
    return "".join(_norm_char(c) for c in s)


def padrao_busca(texto: str) -> re.Pattern:
    """Padrão sem diferença de maiúsculas/acentos; entre palavras aceita espaço, quebra de linha e hífen."""
    hifen_de_quebra = r"(?:[\-‐‑­]\s+)?"     # "ALBU-" + quebra de linha + "QUERQUE"
    toks = [hifen_de_quebra.join(re.escape(c) for c in normalizar_busca(t)) for t in texto.split()]
    return re.compile(r"[\s\-‐‑­]*".join(toks))


def _flags(modo: str) -> int:
    """Flags de extração SEM recorte pela área da página: texto posicionado fora da página
    (invisível ao leitor, mas presente no arquivo) também é lido, tarjado e verificado."""
    import pymupdf
    base = {"text": pymupdf.TEXTFLAGS_TEXT, "words": pymupdf.TEXTFLAGS_WORDS, "rawdict": pymupdf.TEXTFLAGS_RAWDICT}[modo]
    return base & ~pymupdf.TEXT_MEDIABOX_CLIP


def texto_pagina(pg) -> str:
    import pymupdf
    return pg.get_text("text", flags=_flags("text"), clip=pymupdf.INFINITE_RECT())


def palavras_fora_da_pagina(pg) -> list:
    import pymupdf
    return [pymupdf.Rect(w[:4]) for w in pg.get_text("words", flags=_flags("words"), clip=pymupdf.INFINITE_RECT())
            if not pymupdf.Rect(w[:4]).intersects(pg.rect)]


# --- identificadores por posição (rótulo de coluna com valor embaixo ou ao lado) -------------------

RE_ROTULO_ID = re.compile(
    r"(?i)^(?:r\.?\s?g\.?|registro(?: geral| profissional)?|n[ºo°]?\.?\s*(?:de\s+)?registro|identidade|"
    r"carteira de identidade|c[ée]dula de identidade|doc(?:umento)?\.? de identidade|cpf|cnpj|cpf\s*/\s*cnpj|cnh|"
    r"matr[íi]cula|pis(?:\s*/\s*pasep)?|pasep|nit|ctps|t[íi]tulo de eleitor|passaporte|inscri[çc][ãa]o)"
    r"(?:\s*n[ºo°]\.?)?\s*:?$")
RE_ROTULO_NOME = re.compile(r"(?i)^(?:nome(?: completo)?|perit[oa]|titular|profissional|interessad[oa])\s*:?$")


def _celulas(pg) -> list[tuple]:
    """Palavras agrupadas em células: mesma linha do PDF e distância horizontal pequena."""
    import pymupdf
    linhas: dict[tuple, list] = {}
    for w in pg.get_text("words", flags=_flags("words"), clip=pymupdf.INFINITE_RECT()):
        linhas.setdefault((w[5], w[6]), []).append(w)
    celulas = []
    for ws in linhas.values():
        ws.sort(key=lambda w: w[0])
        atual = [ws[0]]
        for w in ws[1:]:
            altura = max(1.0, atual[-1][3] - atual[-1][1])
            if w[0] - atual[-1][2] > 1.5 * altura:
                celulas.append(atual)
                atual = [w]
            else:
                atual.append(w)
        celulas.append(atual)
    return [(pymupdf.Rect(min(w[0] for w in c), min(w[1] for w in c), max(w[2] for w in c), max(w[3] for w in c)),
             " ".join(w[4] for w in c)) for c in celulas]


def detectar_por_posicao(pg) -> list[Item]:
    """Certidões e quadros de qualificação: o rótulo ("RG", "REGISTRO", "NOME") fica numa célula e o valor
    na célula de BAIXO (mesma coluna) ou à DIREITA (mesma linha). A ordem do texto extraído não importa."""
    cels = [(r, t) for r, t in _celulas(pg) if not RE_ROTULO_TARJA.fullmatch(t.strip())]
    eh_rotulo = [bool(RE_ROTULO_ID.match(t.strip()) or RE_ROTULO_NOME.match(t.strip())) for _, t in cels]
    achados: list[Item] = []
    for i, (r, t) in enumerate(cels):
        rotulo = t.strip()
        if not eh_rotulo[i]:
            continue
        h = max(1.0, r.height)
        abaixo = [(c.y0, j) for j, (c, _) in enumerate(cels) if j != i and not eh_rotulo[j]
                  and r.y1 - 1 <= c.y0 <= r.y1 + 2.5 * h and (min(r.x1, c.x1) - max(r.x0, c.x0) > 0 or abs(c.x0 - r.x0) < 15)]
        direita = [(c.x0, j) for j, (c, _) in enumerate(cels) if j != i and not eh_rotulo[j]
                   and abs((c.y0 + c.y1) / 2 - (r.y0 + r.y1) / 2) < 0.5 * h and r.x1 <= c.x0 <= r.x1 + 220]
        for cand in (min(abaixo) if abaixo else None, min(direita) if direita else None):
            if cand is None:
                continue
            valor = cels[cand[1]][1].strip()
            if len(valor) > 60 or RE_FIN.search(valor) or protegido(valor):
                continue
            if RE_ROTULO_ID.match(rotulo) and len(re.findall(r"\d", valor)) >= 4:
                achados.append(Item("IDENTIFICADOR", valor))
            elif RE_ROTULO_NOME.match(rotulo) and re.fullmatch(NOME, valor) \
                    and not any(p in valor.upper() for p in NAO_NOMES):
                achados.append(Item("NOME", valor))
    return achados


def detectar_pdf(pdf, termos: list[str] | None = None) -> list[Item]:
    extras = [it for pg in pdf for it in detectar_por_posicao(pg)]
    return detectar("\n".join(texto_pagina(pg) for pg in pdf), termos, extras)


# --- desenhos vetoriais (rubricas, assinaturas, logotipos e textos convertidos em contorno) ------

MIN_CURVAS = 10


def vetores_suspeitos(pg) -> list:
    """Grupos de desenhos com muitas curvas e área pequena. Linhas e retângulos de tabela não contam."""
    import pymupdf
    grupos: list[list] = []          # [retângulo, nº de curvas]
    for p in pg.get_drawings():
        curvas = sum(1 for it in p["items"] if it[0] == "c")
        if not curvas:
            continue
        r = pymupdf.Rect(p["rect"])
        grupos.append([r, curvas])
    mudou = True
    while mudou:                     # une grupos próximos (traços da mesma rubrica)
        mudou = False
        for i in range(len(grupos)):
            for j in range(i + 1, len(grupos)):
                if (grupos[i][0] + (-6, -6, 6, 6)).intersects(grupos[j][0]):
                    grupos[i] = [grupos[i][0] | grupos[j][0], grupos[i][1] + grupos[j][1]]
                    del grupos[j]
                    mudou = True
                    break
            if mudou:
                break
    area = abs(pg.rect)
    return [r for r, n in grupos if n >= MIN_CURVAS and abs(r) < 0.3 * area]


# --- inventário técnico de imagens (sem conteúdo) ------------------------------------------------

def _funcao_provavel(area_pct: float, larg: float, alt: float, zona: str, cs: str, mascara: bool, na_pagina: bool) -> str:
    """Hipótese pela forma e posição — NUNCA pelo conteúdo (os pixels não são lidos)."""
    if not na_pagina or larg * alt == 0:
        return "elemento invisível (fora da página ou sem área)"
    if min(larg, alt) < 3:
        return "elemento decorativo (fio/linha)"
    if area_pct > 25:
        return "possível gráfico, tabela ou fotografia (grande) — conferência humana"
    razao = larg / alt
    if 0.8 <= razao <= 1.25 and area_pct < 3:
        return "possível QR code, selo ou carimbo"
    if zona == "cabeçalho":
        return "possível logotipo/timbre"
    if razao > 2.5 and (mascara or zona == "rodapé"):
        return "possível assinatura ou rubrica"
    if cs.startswith(("DeviceRGB", "ICCBased(RGB")) and area_pct > 5:
        return "possível fotografia ou gráfico"
    return "indeterminada — conferência humana"


def inventario_imagens(pdf) -> list[dict]:
    """Para cada imagem desenhada (inclusive em linha e dentro de XObjects) e cada imagem só referenciada
    nos recursos: página, origem, tamanho, posição e função provável. Só METADADOS — nenhum pixel."""
    import pymupdf
    itens = []
    for pg in pdf:
        area, alt_pg = abs(pg.rect), pg.rect.height
        desenhadas = set()
        for info in pg.get_image_info(xrefs=True):
            r = pymupdf.Rect(info["bbox"])
            xref = info.get("xref", 0)
            desenhadas.add(xref)
            ref = next((im[-1] for im in pg.get_images(full=True) if im[0] == xref), 0) if xref else 0
            vis = r & pg.rect
            zona = ("cabeçalho" if r.y1 <= 0.18 * alt_pg else "rodapé" if r.y0 >= 0.75 * alt_pg else "corpo")
            cs = str(info.get("cs-name") or "")
            mascara = bool(info.get("colorspace") == 0 or info.get("bpc") == 1)
            na_pag = not vis.is_empty
            pct = round(100 * abs(vis) / area, 2) if na_pag else 0.0
            itens.append({
                "pagina": pg.number + 1,
                "origem": "em linha (no fluxo da página)" if not xref else ("dentro de XObject de formulário" if ref else "XObject da página"),
                "pixels": f"{info['width']}x{info['height']}", "bits": info.get("bpc"), "cores": cs.split("(")[0] or "?",
                "mascara_ou_1bit": mascara, "posicao_pt": [round(c, 1) for c in r], "area_pct_pagina": pct,
                "zona": zona, "dentro_da_pagina": na_pag,
                "funcao_provavel": _funcao_provavel(pct, r.width, r.height, zona, cs, mascara, na_pag),
            })
        for im in pg.get_images(full=True):
            if im[0] not in desenhadas:
                itens.append({"pagina": pg.number + 1, "origem": "só referenciada nos recursos (não desenhada)",
                              "pixels": f"{im[2]}x{im[3]}", "bits": im[4], "cores": im[5] or "?", "mascara_ou_1bit": im[4] == 1,
                              "posicao_pt": None, "area_pct_pagina": 0.0, "zona": "—", "dentro_da_pagina": False,
                              "funcao_provavel": "objeto residual nos recursos (invisível, mas presente no arquivo)"})
    return itens


# --- remoção de imagens que resistem à redação -----------------------------------------------------

_DELIM = b"()<>[]{}/%"
_ESPACO = b" \t\r\n\f\x00"
_COMPONENTES = {b"G": 1, b"DeviceGray": 1, b"RGB": 3, b"DeviceRGB": 3, b"CMYK": 4, b"DeviceCMYK": 4, b"I": 1, b"Indexed": 1}


def _pular_string(b: bytes, i: int) -> int:
    """i aponta para '('; devolve a posição após o ')' correspondente (com escapes e aninhamento)."""
    nivel, i = 0, i
    while i < len(b):
        c = b[i]
        if c == 0x5C:              # barra invertida
            i += 2
            continue
        if c == 0x28:
            nivel += 1
        elif c == 0x29:
            nivel -= 1
            if nivel == 0:
                return i + 1
        i += 1
    return i


def _fim_imagem_em_linha(b: bytes, ini: int, dic: bytes) -> int | None:
    """Fim (após 'EI') dos dados de uma imagem em linha que começam em `ini`."""
    m = re.search(rb"/(?:L|Length)\s+(\d+)", dic)
    filtro = re.search(rb"/(?:F|Filter)\b", dic)
    if m:
        cand = ini + int(m.group(1))
    elif not filtro:
        w = re.search(rb"/(?:W|Width)\s+(\d+)", dic)
        h = re.search(rb"/(?:H|Height)\s+(\d+)", dic)
        bpc = re.search(rb"/(?:BPC|BitsPerComponent)\s+(\d+)", dic)
        cs = re.search(rb"/(?:CS|ColorSpace)\s*/(\w+)", dic)
        mascara = re.search(rb"/(?:IM|ImageMask)\s+true", dic)
        if not (w and h):
            return None
        comp = 1 if mascara else _COMPONENTES.get(cs.group(1) if cs else b"G", 1)
        bits = 1 if mascara else int(bpc.group(1)) if bpc else 8
        cand = ini + ((int(w.group(1)) * comp * bits + 7) // 8) * int(h.group(1))
    else:
        cand = None
    if cand is not None:
        m2 = re.compile(rb"\s*EI(?=[\s]|$)").match(b, cand)
        if m2:
            return m2.end()
    # dados comprimidos sem comprimento: o primeiro "EI" isolado seguido de conteúdo de página plausível
    for m3 in re.finditer(rb"[\s]EI(?=[\s]|$)", b[ini:]):
        fim = ini + m3.end()
        resto = b[fim:fim + 32]
        if all(32 <= c < 127 or c in b"\t\r\n" for c in resto):
            return fim
    return None


def _operador_id(b: bytes, i: int) -> tuple[int, int] | None:
    """Após 'BI', localiza o operador ID lendo o dicionário token a token (o MuPDF grava sem espaços:
    '/F[/AHx/Fl]ID'). Devolve (início do ID, início dos dados)."""
    n = len(b)
    while i < n:
        c = b[i]
        if c in _ESPACO or c in b"[]":
            i += 1
            continue
        if c == 0x28:
            i = _pular_string(b, i)
            continue
        if c == 0x3C:                                   # <hex> ou <<
            j = b.find(b">", i)
            i = n if j < 0 else j + 1
            continue
        nome = c == 0x2F
        j = i + 1 if nome else i
        while j < n and b[j] not in _ESPACO and b[j] not in _DELIM:
            j += 1
        if not nome and b[i:j] == b"ID":
            return i, j + 1                             # um único espaço separa ID dos dados
        i = j
    return None


def remover_imagens_em_linha(fluxo: bytes) -> tuple[bytes, int]:
    """Apaga do fluxo de conteúdo todos os blocos BI … ID … EI (imagens em linha), com leitura léxica
    (cadeias de texto, comentários e hexadecimais não são confundidos com operadores)."""
    out, i, n, removidas = bytearray(), 0, len(fluxo), 0
    while i < n:
        c = fluxo[i]
        if c == 0x28:                                   # cadeia literal
            j = _pular_string(fluxo, i)
            out += fluxo[i:j]
            i = j
            continue
        if c == 0x25:                                   # comentário
            j = fluxo.find(b"\n", i)
            j = n if j < 0 else j
            out += fluxo[i:j]
            i = j
            continue
        if c in _ESPACO or c in _DELIM:
            out.append(c)
            i += 1
            continue
        j = i
        while j < n and fluxo[j] not in _ESPACO and fluxo[j] not in _DELIM:
            j += 1
        tok = fluxo[i:j]
        if tok == b"BI":
            k = _operador_id(fluxo, j)
            if k:
                fim = _fim_imagem_em_linha(fluxo, k[1], fluxo[j:k[0]])
                if fim:
                    removidas += 1
                    i = fim
                    continue
        out += tok
        i = j
    return bytes(out), removidas


def _fluxos_de_conteudo(pdf) -> set[int]:
    """Fluxos de conteúdo das páginas e de todos os XObjects de formulário do documento."""
    xs = {x for pg in pdf for x in pg.get_contents()}
    for x in range(1, pdf.xref_length()):
        try:
            if pdf.xref_is_stream(x) and pdf.xref_get_key(x, "Subtype") == ("name", "/Form"):
                xs.add(x)
        except Exception:
            continue
    return xs


def neutralizar_imagens_restantes(pdf, manter: set[tuple[int, tuple]] | None = None) -> int:
    """Rede de segurança após a redação: remove imagens em linha diretamente do fluxo e desliga dos
    recursos as imagens que continuarem presentes (desenhadas ou não). `manter`: (página, bbox) de imagens
    retidas para conferência humana — essas não são tocadas aqui."""
    manter = manter or set()
    removidas = 0
    def retida(pg, info) -> bool:
        return (pg.number + 1, tuple(round(c, 1) for c in info["bbox"])) in manter

    em_linha = [(pg, i) for pg in pdf for i in pg.get_image_info(xrefs=True) if i.get("xref", 0) == 0]
    # imagem em linha retida para conferência: não mexe nos fluxos (o documento já fica reprovado)
    if em_linha and not any(retida(pg, i) for pg, i in em_linha):
        for x in _fluxos_de_conteudo(pdf):
            novo, k = remover_imagens_em_linha(pdf.xref_stream(x))
            if k:
                pdf.update_stream(x, novo)
                removidas += k
    retidas = {xr for pg in pdf for i in pg.get_image_info(xrefs=True)
               for (p, bb) in manter if p == pg.number + 1 and tuple(round(c, 1) for c in i["bbox"]) == bb
               for xr in [i.get("xref", 0)]}
    for pg in pdf:
        for im in pg.get_images(full=True):
            xref, nome, dono = im[0], im[7], im[-1]
            if xref in retidas or not nome:
                continue
            alvo = dono or pg.xref
            chave = f"Resources/XObject/{nome}"
            if pdf.xref_get_key(alvo, chave)[0] == "null" and dono == 0:
                continue
            pdf.xref_set_key(alvo, chave, "null")
            removidas += 1
    return removidas


# --- estruturas internas -------------------------------------------------------------------------

CHAVES_CATALOGO = ("AcroForm", "DSS", "Perms", "StructTreeRoot", "MarkInfo", "PageLabels", "Names", "OpenAction", "AA",
                   "Outlines", "Metadata", "PieceInfo", "Threads", "SpiderInfo", "Legal", "Collection", "URI",
                   "OCProperties", "AF")
CHAVES_PAGINA = ("Annots", "Thumb", "Metadata", "PieceInfo", "AA", "B", "StructParents", "AF")


def _chaves_presentes(pdf) -> int:
    cat = pdf.pdf_catalog()
    n = sum(1 for k in CHAVES_CATALOGO if pdf.xref_get_key(cat, k)[0] != "null")
    n += sum(1 for pg in pdf for k in CHAVES_PAGINA if pdf.xref_get_key(pg.xref, k)[0] != "null")
    return n


def _limpar_estruturas(pdf) -> None:
    cat = pdf.pdf_catalog()
    for k in CHAVES_CATALOGO:
        pdf.xref_set_key(cat, k, "null")
    for pg in pdf:
        for k in CHAVES_PAGINA:
            pdf.xref_set_key(pg.xref, k, "null")
    for x in range(1, pdf.xref_length()):        # metadados XMP ligados a imagens, fontes e XObjects
        try:
            if pdf.xref_get_key(x, "Metadata")[0] != "null":
                pdf.xref_set_key(x, "Metadata", "null")
        except Exception:
            continue


RE_STR_LITERAL = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
RE_STR_HEX = re.compile(rb"(?<!<)<([0-9A-Fa-f\s]{4,})>(?!>)")
RE_PROPRIEDADE_MC = re.compile(rb"/(?:ActualText|Alt|E|T|TU|Contents|Name|Reason|Location|ContactInfo)\s*"
                               rb"(\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>)", re.S)


def _decodificar(b: bytes) -> str:
    if b.startswith(b"(") and b.endswith(b")"):
        corpo = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"", b"f": b""}
                       .get(m.group(1), m.group(1)), b[1:-1])
        corpo = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 255]), corpo)
    else:
        try:
            corpo = bytes.fromhex(re.sub(rb"\s", b"", b.strip(b"<>")).decode())
        except ValueError:
            return ""
    if corpo.startswith(b"\xfe\xff"):
        return corpo[2:].decode("utf-16-be", "replace")
    return corpo.decode("latin-1")


def texto_estrutural(pdf) -> str:
    """Todas as cadeias de texto guardadas FORA do conteúdo visível: dicionários de todos os objetos,
    metadados XML e propriedades de conteúdo marcado (ActualText/Alt) dentro dos fluxos de página."""
    partes: list[str] = []
    conteudos = {x for pg in pdf for x in pg.get_contents()}
    for x in range(1, pdf.xref_length()):
        try:
            obj = pdf.xref_object(x, compressed=False).encode("latin-1", "replace")
        except Exception:
            continue
        partes += [_decodificar(m.group(0)) for m in RE_STR_LITERAL.finditer(obj)]
        partes += [_decodificar(b"<" + m.group(1) + b">") for m in RE_STR_HEX.finditer(obj)]
        if pdf.xref_is_stream(x):
            try:
                fluxo = pdf.xref_stream(x)
            except Exception:
                continue
            if b"/XML" in obj or b"/Metadata" in obj:
                partes.append(fluxo.decode("utf-8", "replace"))
            elif x in conteudos or b"/Form" in obj:
                partes += [_decodificar(m.group(1)) for m in RE_PROPRIEDADE_MC.finditer(fluxo)]
    partes.append(pdf.get_xml_metadata() or "")
    return "\n".join(p for p in partes if p.strip())


def mapa_caracteres(pg) -> tuple[str, list[tuple]]:
    """Texto normalizado da página e, para cada caractere, (retângulo, nº da linha).
    Linhas são separadas por espaço (o separador não tem retângulo)."""
    import pymupdf
    chars: list[str] = []
    info: list[tuple] = []
    linha = 0
    for bloco in pg.get_text("rawdict", flags=_flags("rawdict"), clip=pymupdf.INFINITE_RECT())["blocks"]:
        for ln in bloco.get("lines", []):
            for span in ln["spans"]:
                for ch in span["chars"]:
                    for e in _norm_char(ch["c"]):
                        chars.append(e)
                        info.append((ch["bbox"], linha))
            chars.append(" ")
            info.append((None, linha))
            linha += 1
    return "".join(chars), info


MAX_PASSADAS = 4


def _redigir_texto(pg, itens: list[Item]) -> list["Remocao"]:
    """Marca para redação todas as ocorrências de cada identificador na página, caractere a caractere
    (sem diferença de maiúsculas/minúsculas/acentos e atravessando quebras de linha e hifenização)."""
    import pymupdf

    norm, info = mapa_caracteres(pg)
    feitos = []
    for it in itens:
        rects = []
        for m in padrao_busca(it.texto).finditer(norm):
            por_linha: dict[int, object] = {}
            for bbox, linha in info[m.start():m.end()]:
                if bbox is None:
                    continue
                r = pymupdf.Rect(bbox)
                por_linha[linha] = r if linha not in por_linha else por_linha[linha] | r
            rects += por_linha.values()
        for r in rects:
            if r.intersects(pg.rect):
                pg.add_redact_annot(r, text=f"[{it.tipo.split()[0]}]", fill=(0.92, 0.92, 0.92), fontsize=5)
            else:                       # fora da página: apaga sem deixar rótulo (nada é exibido ali)
                pg.add_redact_annot(r, fill=False)
        if rects:
            feitos.append(Remocao(pagina=pg.number + 1, tipo=it.tipo, texto=it.texto))
    return feitos


LIMIAR_IMAGEM_GRANDE = 25.0     # % da página: acima disso pode ser gráfico/tabela/foto -> conferência humana


def anonimizar_pdf(origem: Path, destino: Path, termos: list[str] | None = None, remover_imagens_grandes: bool = False,
                   pasta_revisao: Path | None = None) -> Resultado:
    """`remover_imagens_grandes`: só depois da conferência humana. Sem ele, imagens grandes (possíveis gráficos ou
    tabelas) NÃO são removidas: ficam retidas, são exportadas para `pasta_revisao` (local, protegida) e a
    verificação reprova até a decisão da advogada."""
    import pymupdf

    if destino.resolve() == origem.resolve():
        raise ValueError("o destino não pode ser o próprio original")
    h0 = _sha(origem)
    pdf = pymupdf.open(origem)
    # camadas opcionais ocultas: o conteúdo escondido continua no arquivo. Sem a definição de camadas
    # tudo fica visível — e, portanto, detectável e tarjável. O fato é registrado para a conferência visual.
    camadas = int(pdf.xref_get_key(pdf.pdf_catalog(), "OCProperties")[0] != "null")
    pdf.xref_set_key(pdf.pdf_catalog(), "OCProperties", "null")
    itens = detectar_pdf(pdf, termos)
    remocoes: list[Remocao] = []
    nao_localizados: list[str] = []
    imagens = 0
    vetores = 0
    fora = 0
    digitalizadas = []
    retidas: list[dict] = []
    inventario_original = inventario_imagens(pdf)

    for pg in pdf:
        n = pg.number + 1
        area = abs(pg.rect)
        # desenhos vetoriais com muitas curvas (rubricas e assinaturas desenhadas): remove só o desenho,
        # nunca o texto por cima ou ao lado
        rv = vetores_suspeitos(pg)
        for r in rv:
            # margem: o MuPDF mede o traço pela espessura e pelos pontos de controle das curvas
            pg.add_redact_annot(r + (-12, -12, 12, 12), fill=False)
        if rv:
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                text=pymupdf.PDF_REDACT_TEXT_NONE)
            for r in rv:
                pg.draw_rect(r, color=None, fill=(0.92, 0.92, 0.92))
                pg.insert_text(r.tl + (2, 7), "[DESENHO REMOVIDO]", fontsize=5)
            vetores += len(rv)
        # texto fora da área da página: nunca aparece ao leitor, mas fica no arquivo — removido por inteiro
        for r in palavras_fora_da_pagina(pg):
            pg.add_redact_annot(r, fill=False)
            fora += 1
        # imagens (inclusive as em linha no fluxo da página): assinaturas, carimbos, QR codes, logotipos
        for info in pg.get_image_info():
            r = pymupdf.Rect(info["bbox"])
            if r.is_empty:
                continue
            # imagem de página inteira = página digitalizada (com ou sem OCR): o dado pessoal pode estar
            # na imagem e a página ficaria em branco -> a verificação reprova e o procedimento para
            if abs(r & pg.rect) > 0.8 * area:
                digitalizadas.append(n)
            elif 100 * abs(r & pg.rect) / area > LIMIAR_IMAGEM_GRANDE and not remover_imagens_grandes:
                # possível gráfico/tabela com dados financeiros: não remove sem decisão humana
                bb = tuple(round(c, 1) for c in r)
                ref = {"pagina": n, "bbox": bb, "area_pct_pagina": round(100 * abs(r & pg.rect) / area, 1)}
                if pasta_revisao is not None:
                    pasta_revisao.mkdir(parents=True, exist_ok=True)
                    arq = pasta_revisao / f"pag{n:02d}-imagem{len(retidas) + 1}.png"
                    pg.get_pixmap(clip=r & pg.rect, dpi=150).save(arq)      # só no disco local, para a advogada
                    ref["arquivo_para_conferencia"] = arq.name
                retidas.append(ref)
                continue
            pg.add_redact_annot(r, text="[IMAGEM REMOVIDA]", fill=(0.92, 0.92, 0.92), fontsize=6)
            imagens += 1
        remocoes += _redigir_texto(pg, itens)
        pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                            text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    for it in itens:
        if not any(r.texto == it.texto for r in remocoes):
            nao_localizados.append(it.texto)

    # Passadas adicionais: a remoção pode "aproximar" rótulo e valor que antes estavam separados
    # (ex.: certidão com rótulos numa linha e valores na seguinte). Procura de novo no resultado
    # e remove o que restou, até não sobrar identificador ou atingir o limite.
    for _ in range(MAX_PASSADAS - 1):
        novos = [i for i in detectar_pdf(pdf) if i.texto not in {r.texto for r in remocoes}]
        if not novos:
            break
        for pg in pdf:
            achados = _redigir_texto(pg, novos)
            if achados:
                remocoes += achados
                pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                    text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        itens = itens + novos

    # rede de segurança: imagens que a redação não removeu (ex.: imagem em linha com delimitação incomum)
    neutralizadas = neutralizar_imagens_restantes(pdf, {(x["pagina"], x["bbox"]) for x in retidas})

    pdf.set_toc([])
    pdf.scrub(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=False, javascript=True,
              metadata=True, redactions=True, remove_links=True, reset_fields=True, reset_responses=True,
              thumbnails=True, xml_metadata=True)
    for pg in pdf:
        for a in list(pg.annots() or []):
            pg.delete_annot(a)
        for w in list(pg.widgets() or []):
            pg.delete_widget(w)
    pdf.set_metadata({})
    pdf.del_xml_metadata()
    _limpar_estruturas(pdf)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # gravação completa (nunca incremental): revisões anteriores e objetos órfãos não vão para a cópia
    pdf.save(destino, garbage=4, deflate=True, clean=True, incremental=False)
    pdf.close()

    tipos = {it.texto: it.tipo for it in itens}
    v = verificar_pdf(origem, destino, h0, list(dict.fromkeys(r.texto for r in remocoes)), digitalizadas,
                      nao_localizados, tipos, termos)
    return Resultado(origem=origem, destino=destino, sha256_original=h0, sha256_anonimizado=_sha(destino),
                     remocoes=remocoes, imagens_removidas=imagens, verificacao=v, vetores_removidos=vetores,
                     camadas_opcionais=camadas, imagens_neutralizadas=neutralizadas, imagens_retidas=retidas,
                     imagens_por_funcao=dict(Counter(i["funcao_provavel"] for i in inventario_original)))


def verificar_pdf(origem: Path, destino: Path, h0: str, removidos: list[str], digitalizadas: list[int],
                  nao_localizados: list[str], tipos: dict[str, str] | None = None,
                  termos: list[str] | None = None) -> Verificacao:
    import pymupdf
    from ..validacao.leitura_parecer import ler_parecer_pdf

    tipos = tipos or {}
    with pymupdf.open(origem) as o:
        visivel_o = "\n".join(p.get_text("text") for p in o)       # valores financeiros: só os da área da página
    with pymupdf.open(destino) as d:
        texto_d = "\n".join(texto_pagina(p) for p in d)
        visivel_d = "\n".join(p.get_text("text") for p in d)
        fora = sum(len(palavras_fora_da_pagina(p)) for p in d)
        # mesma busca da redação: sem diferença de maiúsculas/acentos, atravessando linhas
        norm_d = re.sub(r"\[[a-z_]+(?: \(parte\))?\]", " ", " ".join(mapa_caracteres(p)[0] for p in d))
        detalhe = inventario_imagens(d)                  # metadados das imagens que restaram (sem pixels)
        imagens = len(detalhe)
        anot = sum(len(list(p.annots() or [])) + len(list(p.widgets() or [])) for p in d)
        anexos = d.embfile_count()
        meta_vazio = not any((v or "").strip() for k, v in d.metadata.items() if k not in ("format", "encryption")) \
            and not (d.get_xml_metadata() or "").strip()
        marcadores = len(d.get_toc())
        extras = [it for p in d for it in detectar_por_posicao(p)]
        vetores = sum(len(vetores_suspeitos(p)) for p in d)
        estruturas = _chaves_presentes(d)
        estrutural = texto_estrutural(d)
    revisoes = destino.read_bytes().count(b"%%EOF")
    sobras = [s for s in removidos if padrao_busca(s).search(norm_d)]
    # cadeias internas (dicionários, XMP, ActualText): nenhum texto removido nem identificador pode estar lá
    norm_e = normalizar_busca(estrutural)
    sobras_e = [s for s in removidos + list(termos or []) if s.strip() and padrao_busca(s).search(norm_e)]
    reaparecem = len(sobras)
    por_tipo = dict(Counter(tipos.get(s, "?") for s in sobras))
    nao_loc_tipo = dict(Counter(tipos.get(s, "?") for s in nao_localizados))
    residuos = Counter(i.tipo for i in detectar(texto_d, extras=extras) if not i.tipo.startswith("NOME (parte)"))
    residuos_e = Counter(i.tipo for i in detectar(estrutural) if not i.tipo.startswith("NOME (parte)"))
    residuos_e.update({"TEXTO_REMOVIDO": len(sobras_e)} if sobras_e else {})
    # dados financeiros: tudo o que não estava dentro de um dado pessoal removido deve permanecer
    tok_o, tok_d = tokens_financeiros(visivel_o), tokens_financeiros(visivel_d)
    # estrito: só a data de nascimento pode "sumir" (é dado pessoal); qualquer outro valor/data/percentual deve permanecer
    dentro_removidos = sum((tokens_financeiros(s) for s in removidos if tipos.get(s) == "NASCIMENTO"), Counter())
    esperado = tok_o - dentro_removidos
    faltam = esperado - tok_d
    po, pd_ = ler_parecer_pdf(origem.read_bytes(), origem.name), ler_parecer_pdf(destino.read_bytes(), destino.name)
    tabelas = None
    if po.tabelas:
        tabelas = {k: [(l.numero, l.data, l.valores) for l in t.linhas] for k, t in po.tabelas.items()} == \
                  {k: [(l.numero, l.data, l.valores) for l in t.linhas] for k, t in pd_.tabelas.items()}
    return Verificacao(
        original_intacto=_sha(origem) == h0, residuos_removidos=reaparecem, residuos_padrao=dict(residuos),
        imagens=imagens, anotacoes=anot, anexos=anexos, metadados_vazios=meta_vazio, marcadores=marcadores,
        tokens_financeiros_original=sum(esperado.values()),
        tokens_financeiros_preservados=sum((esperado & tok_d).values()),
        tokens_ausentes=sorted(faltam.elements()), tabelas_identicas=tabelas,
        paginas_digitalizadas=sorted(set(digitalizadas)), nao_localizados=nao_localizados,
        reaparecendo_por_tipo=por_tipo, nao_localizados_por_tipo=nao_loc_tipo,
        residuos_estruturais=dict(residuos_e), vetores_suspeitos=vetores, estruturas_internas=estruturas,
        revisoes=revisoes, texto_fora_da_pagina=fora, imagens_detalhe=detalhe)


# --- Planilhas e CSV ---------------------------------------------------------------------------

def _substituir(texto: str, itens: list[Item]) -> tuple[str, list[Item]]:
    usados = []
    for it in sorted(itens, key=lambda i: -len(i.texto)):
        novo = re.sub(re.escape(it.texto), f"[{it.tipo.split()[0]}]", texto, flags=re.I)
        if novo != texto:
            usados.append(it)
            texto = novo
    return texto, usados


def anonimizar_csv(origem: Path, destino: Path, termos: list[str] | None = None) -> tuple[list[Remocao], int]:
    texto = origem.read_text(encoding="utf-8-sig")
    # rótulo e nome costumam estar em células vizinhas: a detecção lê a linha com as células unidas por ': '
    sep = ";" if ";" in texto else ","
    itens = detectar(texto.replace(sep, ": "), termos)
    novo, usados = _substituir(texto, itens)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(novo, encoding="utf-8")
    faltam = tokens_financeiros(texto) - sum((tokens_financeiros(i.texto) for i in usados), Counter()) - tokens_financeiros(novo)
    return [Remocao(pagina=1, tipo=i.tipo, texto=i.texto) for i in usados], sum(faltam.values())


def anonimizar_xlsx(origem: Path, destino: Path, termos: list[str] | None = None) -> tuple[list[Remocao], int]:
    """Substitui identificadores nas células de texto; remove comentários, imagens e propriedades do arquivo.
    Células numéricas e datas não são tocadas."""
    from openpyxl import load_workbook
    from openpyxl.packaging.core import DocumentProperties

    wb = load_workbook(origem)          # imagens não são carregadas pelo openpyxl -> não são regravadas
    # cada linha da planilha vira um texto com as células unidas por ': ' (rótulo e nome em células vizinhas)
    textos = [": ".join(str(c.value) for c in row if c.value is not None) for ws in wb.worksheets for row in ws.iter_rows()]
    textos += [ws.title for ws in wb.worksheets]
    itens = detectar("\n".join(textos), termos)
    remocoes: list[Remocao] = []
    for i, ws in enumerate(wb.worksheets, start=1):
        for row in ws.iter_rows():
            for c in row:
                c.comment = None
                if isinstance(c.value, str):
                    novo, usados = _substituir(c.value, itens)
                    if usados:
                        c.value = novo
                        remocoes += [Remocao(pagina=i, tipo=u.tipo, texto=u.texto) for u in usados]
        ws.oddHeader.center.text = ws.oddFooter.center.text = None
    wb.properties = DocumentProperties()
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return remocoes, 0


# --- Relatórios ---------------------------------------------------------------------------------

def relatorio_detalhado(nome: str, remocoes: list[Remocao], v: Verificacao | None) -> str:
    """CONTÉM os dados removidos — para conferência da advogada, somente local."""
    L = [f"# Relatório DETALHADO de anonimização — {nome}", "",
         "**Confidencial: contém os dados pessoais removidos. Não compartilhar.**", "",
         "| Página | Tipo | Texto removido |", "|---|---|---|"]
    vistos = set()
    for r in sorted(remocoes, key=lambda x: (x.pagina, x.tipo)):
        if (r.pagina, r.texto) in vistos:
            continue
        vistos.add((r.pagina, r.texto))
        L.append(f"| {r.pagina} | {r.tipo} | {r.texto.replace('|', '/')} |")
    if v is not None:
        if v.tokens_ausentes:
            L += ["", "## Dados financeiros ausentes na cópia (verificar!)", ""] + [f"- {t}" for t in v.tokens_ausentes]
        if v.nao_localizados:
            L += ["", "## Identificadores detectados mas não localizados graficamente no PDF (conferir manualmente)", ""]
            L += [f"- {t}" for t in v.nao_localizados]
    return "\n".join(L) + "\n"


def relatorio_verificacao(resumos: list[dict]) -> str:
    """Sem dados pessoais."""
    L = ["# Verificação da anonimização", "", "Relatório sem dados pessoais (tipos, quantidades e páginas).", ""]
    for r in resumos:
        v = r.get("verificacao", {})
        L += [f"## {r['arquivo_original']} → {r['arquivo_anonimizado']}", "",
              f"- **Resultado da verificação automática: {'APROVADA' if v.get('aprovada') else 'REPROVADA — conferir'}**",
              f"- Remoções por tipo: {r.get('remocoes_por_tipo')}",
              f"- Páginas com remoção: {r.get('paginas_com_remocao')}",
              f"- Imagens removidas: {r.get('imagens_removidas', 0)}",
              f"- Imagens removidas pela rede de segurança: {r.get('imagens_removidas_pela_rede_de_seguranca', 0)}",
              f"- Desenhos vetoriais removidos: {r.get('desenhos_vetoriais_removidos', 0)}",
              f"- Camadas opcionais reveladas: {r.get('camadas_opcionais_reveladas', 0)}",
              f"- Imagens no original por função provável (só forma e posição): "
              f"{r.get('imagens_no_original_por_funcao_provavel', {})}"]
        for x in r.get("imagens_retidas_para_conferencia_humana") or []:
            L.append(f"- **Imagem RETIDA para conferência humana:** pág. {x['pagina']}, {x['area_pct_pagina']}% da página"
                     + (f", arquivo anonimizados/revisao-imagens/…/{x['arquivo_para_conferencia']}" if x.get("arquivo_para_conferencia") else ""))
        L += [f"- {k.replace('_', ' ')}: {val}" for k, val in v.items() if k != "aprovada"]
        L.append("")
    return "\n".join(L) + "\n"
