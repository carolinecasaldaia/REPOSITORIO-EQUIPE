#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Separador de documentos assinados no Autentique.

Recebe o PDF único baixado do Autentique (contrato + procuração + declaração de
hipossuficiência + relatório de auditoria) e grava cada documento em um arquivo
separado, com o relatório de assinaturas anexado ao final de cada um.

Substitui o passo manual no iLovePDF (split-range + merge).

Uso:
    python3 separar_autentique.py                      # pega o PDF mais recente da pasta Downloads
    python3 separar_autentique.py ARQUIVO.pdf
    python3 separar_autentique.py ARQUIVO.pdf --destino "/caminho/da/pasta/do/cliente"
    python3 separar_autentique.py ARQUIVO.pdf --sem-relatorio   # não anexa o relatório de auditoria
    python3 separar_autentique.py ARQUIVO.pdf --listar          # só mostra a estrutura detectada
"""

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    sys.exit("Falta a biblioteca pypdf. Rode:  python3 -m pip install --user pypdf")


DOWNLOADS = Path.home() / "Downloads"

# Subpastas da pasta do cliente. O primeiro nome é o padrão (criado se não
# existir); os demais são variações já usadas em pastas antigas.
PASTA_CONTRATO = ["CONTRATO HO", "CONTRATO DE HONORÁRIOS", "CONTRATO HONORÁRIOS", "CONTRATO"]
PASTA_ESCRITORIO = ["DOC ESCRITÓRIO", "DOCS ESCRITÓRIO", "DOC ESCRITORIO", "DOC CLIENTE", "DOCS CLIENTE"]

# ---------------------------------------------------------------------------
# Tipos de documento reconhecidos.
#   padrao      -> regex casada com a 1ª linha da página (sem acento, maiúscula)
#   arquivo     -> nome do PDF gerado
#   subpasta    -> nomes aceitos de subpasta dentro da pasta do cliente
# ---------------------------------------------------------------------------
TIPOS = [
    {
        "chave": "contrato",
        "padrao": r"^CONTRATO (DE )?(PRESTACAO DE SERVICOS?|HONORARIOS?)\b",
        "rotulo": "Contrato de Prestação de Serviços",
        "arquivo": "Contrato HO Assinado.pdf",
        "subpasta": PASTA_CONTRATO,
    },
    {
        "chave": "procuracao",
        "padrao": r"^PROCURACAO\b",
        "rotulo": "Procuração",
        "arquivo": "Procuracao Assinada.pdf",
        "subpasta": PASTA_ESCRITORIO,
    },
    {
        "chave": "hipossuficiencia",
        "padrao": r"^DECLARACAO DE HIPOSSUFICIENCIA\b",
        "rotulo": "Declaração de Hipossuficiência",
        "arquivo": "Declaracao de Hipo Assinada.pdf",
        "subpasta": PASTA_ESCRITORIO,
    },
    {
        "chave": "residencia",
        "padrao": r"^DECLARACAO DE (COMPROVANTE DE )?(RESIDENCIA|ENDERECO)\b",
        "rotulo": "Declaração de Residência",
        "arquivo": "Declaracao de Residencia Assinada.pdf",
        "subpasta": PASTA_ESCRITORIO,
    },
]

# Fallback: contrato genérico ("CONTRATO ..." sem os complementos acima).
TIPO_CONTRATO_GENERICO = TIPOS[0]

# Em alguns PDFs o pypdf junta o título com o parágrafo seguinte numa única
# linha; por isso o título é procurado só no começo da primeira linha da página.
JANELA_TITULO = 120


def normalizar(texto: str) -> str:
    """Maiúsculas, sem acento, espaços colapsados — para casar títulos com segurança."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def primeira_linha(pagina) -> str:
    texto = pagina.extract_text() or ""
    for linha in texto.splitlines():
        if linha.strip():
            return linha.strip()
    return ""


def eh_pagina_de_relatorio(pagina) -> bool:
    """Primeira página do relatório de auditoria do Autentique."""
    texto = pagina.extract_text() or ""
    norm = normalizar(texto)
    return norm.startswith("IDENTIFICADOR:") and "AUTENTIQUE.COM.BR" in norm


def eh_pagina_de_validacao(pagina) -> bool:
    """Folha avulsa 'Assinado com Assinatura Eletrônica / Hash SHA256 / Validador'.

    O Autentique intercala essa folha em alguns modelos. O conteúdo dela já está
    no relatório de auditoria, por isso ela é descartada por padrão (é o mesmo
    critério usado nos documentos separados manualmente até hoje).
    """
    norm = normalizar(pagina.extract_text() or "")
    return norm.startswith("ASSINADO COM ASSINATURA ELETRONICA") and "HASH SHA256 DO ORIGINAL" in norm


def classificar_titulo(linha: str, primeira_pagina: bool = False):
    norm = normalizar(linha)[:JANELA_TITULO]
    if not norm:
        return None
    for tipo in TIPOS:
        if re.search(tipo["padrao"], norm):
            return tipo
    # Na 1ª página, qualquer "CONTRATO ..." vale como início do contrato.
    if primeira_pagina and norm.startswith("CONTRATO"):
        return TIPO_CONTRATO_GENERICO
    return None


def analisar(reader: PdfReader):
    """Devolve (secoes, paginas_do_relatorio, paginas_de_validacao).

    secoes: lista de dicts {tipo, paginas} com índices de página 0-based.
    """
    total = len(reader.pages)

    inicio_relatorio = total
    for i in range(total):
        if eh_pagina_de_relatorio(reader.pages[i]):
            inicio_relatorio = i
            break

    validacao = []
    secoes = []
    for i in range(inicio_relatorio):
        pagina = reader.pages[i]
        if eh_pagina_de_validacao(pagina):
            validacao.append(i)
            if secoes:
                secoes[-1]["validacao"].append(i)
            continue
        tipo = classificar_titulo(primeira_linha(pagina), primeira_pagina=(i == 0))
        if tipo is not None and (not secoes or secoes[-1]["tipo"]["chave"] != tipo["chave"]):
            secoes.append({"tipo": tipo, "paginas": [i], "validacao": [], "presumido": False})
        elif secoes:
            secoes[-1]["paginas"].append(i)
        else:
            # Páginas antes de qualquer título reconhecido: assume contrato.
            secoes.append({"tipo": TIPO_CONTRATO_GENERICO, "paginas": [i], "validacao": [], "presumido": True})

    relatorio = list(range(inicio_relatorio, total))
    return secoes, relatorio, validacao


def nome_unico(caminho: Path) -> Path:
    if not caminho.exists():
        return caminho
    base, sufixo = caminho.stem, caminho.suffix
    n = 2
    while True:
        alt = caminho.with_name(f"{base} ({n}){sufixo}")
        if not alt.exists():
            return alt
        n += 1


def gravar(reader: PdfReader, paginas, destino: Path, sobrescrever: bool) -> Path:
    writer = PdfWriter()
    for i in paginas:
        writer.add_page(reader.pages[i])
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not sobrescrever:
        destino = nome_unico(destino)
    with open(destino, "wb") as f:
        writer.write(f)
    return destino


def candidatos_downloads(limite: int = 8):
    """PDFs recentes da pasta Downloads, os assinados primeiro."""
    pdfs = [p for p in DOWNLOADS.glob("*.pdf") if p.is_file()]
    assinados = [p for p in pdfs if "assinado" in p.name.lower()]
    lista = assinados or pdfs
    return sorted(lista, key=lambda p: p.stat().st_mtime, reverse=True)[:limite]


def pdf_mais_recente() -> Path:
    lista = candidatos_downloads(1)
    if not lista:
        sys.exit("Nenhum PDF encontrado na pasta Downloads.")
    return lista[0]


def limpar_caminho(texto: str) -> str:
    """Normaliza caminho colado ou arrastado para dentro do Terminal."""
    texto = texto.strip()
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in "\"'":
        return texto[1:-1]
    return re.sub(r"\\(.)", r"\1", texto)


def subpastas_existentes(destino: Path):
    if not destino.is_dir():
        return {}
    return {normalizar(p.name): p for p in destino.iterdir() if p.is_dir()}


def pasta_de_cliente(destino: Path) -> bool:
    """Pasta do cliente = já tem CONTRATO HO e/ou DOC ESCRITÓRIO dentro."""
    existentes = set(subpastas_existentes(destino))
    aceitos = {normalizar(n) for n in PASTA_CONTRATO + PASTA_ESCRITORIO}
    return bool(existentes & aceitos)


def resolver_subpasta(destino: Path, nomes) -> Path:
    """Usa a subpasta que já existe (qualquer grafia da lista); senão cria a padrão."""
    existentes = subpastas_existentes(destino)
    for nome in nomes:
        achada = existentes.get(normalizar(nome))
        if achada is not None:
            return achada
    return destino / nomes[0]


def faixa(paginas) -> str:
    if not paginas:
        return "-"
    return str(paginas[0] + 1) if len(paginas) == 1 else f"{paginas[0]+1}-{paginas[-1]+1}"


def descrever(origem: Path, total: int, secoes, relatorio, validacao, manter_validacao: bool):
    linhas = [
        (s["paginas"], s["tipo"]["rotulo"] + ("   <- título não reconhecido, salvo como contrato" if s.get("presumido") else ""))
        for s in secoes
    ]
    if validacao:
        marca = "mantida" if manter_validacao else "descartada"
        linhas += [([p], f"Folha de validação/hash do Autentique  [{marca}]") for p in validacao]
    if relatorio:
        linhas.append((relatorio, "Relatório de assinaturas (Autentique)"))

    print(f"\nArquivo: {origem.name}  ({total} páginas)")
    print("-" * 70)
    for paginas, rotulo in sorted(linhas, key=lambda x: x[0][0]):
        print(f"  pág. {faixa(paginas):<8} {rotulo}")
    if not relatorio:
        print("  [aviso] Relatório de auditoria do Autentique não encontrado.")
    print("-" * 70)


def executar(reader, secoes, relatorio, destino: Path, sem_relatorio: bool,
             manter_validacao: bool, sobrescrever: bool):
    destino.mkdir(parents=True, exist_ok=True)
    usar_subpastas = pasta_de_cliente(destino)
    anexar = bool(relatorio) and not sem_relatorio

    gerados = []
    for s in secoes:
        paginas = list(s["paginas"])
        if manter_validacao:
            paginas = sorted(paginas + s["validacao"])
        if anexar:
            paginas += relatorio
        tipo = s["tipo"]
        pasta = resolver_subpasta(destino, tipo["subpasta"]) if usar_subpastas else destino
        gerados.append((tipo["rotulo"], gravar(reader, paginas, pasta / tipo["arquivo"], sobrescrever), len(paginas)))

    print(f"\nDestino: {destino}")
    if anexar:
        print("Relatório de assinaturas anexado ao final de cada documento.")
    if usar_subpastas:
        print("Arquivos gravados nas subpastas CONTRATO HO / DOC ESCRITÓRIO.")
    print()
    for rotulo, caminho, n in gerados:
        print(f"  ✓ {rotulo:<34} -> {caminho.relative_to(destino)}  ({n} pág.)")
    print()
    return destino


def perguntar(texto: str) -> str:
    try:
        return input(texto).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def escolher_pdf() -> Path:
    lista = candidatos_downloads()
    print("\n=== SEPARADOR DE DOCUMENTOS DO AUTENTIQUE ===")
    if lista:
        print("\nPDFs recentes na pasta Downloads:\n")
        for n, p in enumerate(lista, 1):
            print(f"  {n}. {p.name}")
        print("\nDigite o número, ou arraste outro PDF para esta janela.")
        padrao = "  [Enter = opção 1] > "
    else:
        print("\nNenhum PDF na pasta Downloads. Arraste o arquivo para esta janela.")
        padrao = "  > "

    while True:
        resposta = perguntar(padrao)
        if not resposta and lista:
            return lista[0]
        if resposta.isdigit() and lista and 1 <= int(resposta) <= len(lista):
            return lista[int(resposta) - 1]
        caminho = Path(limpar_caminho(resposta)).expanduser()
        if caminho.is_file() and caminho.suffix.lower() == ".pdf":
            return caminho
        print("  Não encontrei esse PDF. Tente de novo.")


def escolher_destino(origem: Path) -> Path:
    print("\nOnde salvar os documentos separados?")
    print("  Arraste a pasta do cliente para esta janela")
    print(f"  [Enter = criar 'SEPARADOS - {origem.stem}' na pasta Downloads]")
    while True:
        resposta = perguntar("  > ")
        if not resposta:
            return DOWNLOADS / f"SEPARADOS - {origem.stem}"
        caminho = Path(limpar_caminho(resposta)).expanduser()
        if caminho.is_dir():
            return caminho
        print("  Pasta não encontrada. Tente de novo.")


def interativo(args):
    origem = escolher_pdf()
    reader = PdfReader(str(origem))
    secoes, relatorio, validacao = analisar(reader)
    descrever(origem, len(reader.pages), secoes, relatorio, validacao, args.manter_validacao)

    if not secoes:
        print("Nenhum documento reconhecido. Confira se é o PDF assinado baixado do Autentique.\n")
        return

    destino = escolher_destino(origem)
    if perguntar(f"\nConfirma a separação? [Enter = sim / n = cancelar] > ").lower().startswith("n"):
        print("Cancelado.\n")
        return

    pasta = executar(reader, secoes, relatorio, destino, args.sem_relatorio,
                     args.manter_validacao, args.sobrescrever)
    if perguntar("Abrir a pasta no Finder? [Enter = sim / n = não] > ").lower().startswith("n"):
        return
    os.system(f'open "{pasta}"')


def main():
    ap = argparse.ArgumentParser(description="Separa o PDF assinado do Autentique em documentos individuais.")
    ap.add_argument("pdf", nargs="?", help="PDF baixado do Autentique (padrão: mais recente em Downloads)")
    ap.add_argument("--destino", "-d", help="Pasta de destino (padrão: pasta 'SEPARADOS - <arquivo>' em Downloads)")
    ap.add_argument("--sem-relatorio", action="store_true", help="Não anexar o relatório de auditoria a cada documento")
    ap.add_argument("--manter-validacao", action="store_true",
                    help="Manter as folhas avulsas 'Assinado com Assinatura Eletrônica / Hash SHA256'")
    ap.add_argument("--listar", "-l", action="store_true", help="Apenas mostrar a estrutura detectada")
    ap.add_argument("--sobrescrever", action="store_true", help="Sobrescrever arquivos existentes no destino")
    ap.add_argument("--interativo", "-i", action="store_true", help="Modo pergunta-e-resposta (usado pelo atalho)")
    args = ap.parse_args()

    if args.interativo:
        interativo(args)
        return

    origem = Path(args.pdf).expanduser() if args.pdf else pdf_mais_recente()
    if not origem.is_file():
        sys.exit(f"Arquivo não encontrado: {origem}")

    reader = PdfReader(str(origem))
    secoes, relatorio, validacao = analisar(reader)
    descrever(origem, len(reader.pages), secoes, relatorio, validacao, args.manter_validacao)

    if args.listar:
        return
    if not secoes:
        sys.exit("Nenhum documento reconhecido neste PDF. Confira se é o arquivo assinado do Autentique.")

    destino = Path(args.destino).expanduser() if args.destino else DOWNLOADS / f"SEPARADOS - {origem.stem}"
    executar(reader, secoes, relatorio, destino, args.sem_relatorio,
             args.manter_validacao, args.sobrescrever)


if __name__ == "__main__":
    main()
