#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de onboarding do cliente.

Lê o contrato de prestação de serviços assinado (o mesmo PDF que fica em
CONTRATO HO), preenche sozinho o formulário do gerador_pdf.html e grava o PDF
de onboarding dentro da subpasta ONBOARDING do cliente.

O desenho do PDF continua sendo o do arquivo gerador_pdf.html: este programa
apenas abre aquela página num navegador invisível, preenche os campos e recolhe
o PDF pronto. Se o gerador_pdf.html mudar, o resultado daqui muda junto.

Uso:
    python3 gerar_onboarding.py                                 # modo pergunta-e-resposta
    python3 gerar_onboarding.py "/caminho/da/pasta/do/cliente"
    python3 gerar_onboarding.py PASTA --listar                  # só mostra o que foi lido do contrato
    python3 gerar_onboarding.py PASTA --sobrescrever
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    sys.exit("Falta a biblioteca pypdf. Rode:  python3 -m pip install --user pypdf")


AQUI = Path(__file__).resolve().parent
GERADOR_HTML = AQUI.parent / "gerador_pdf.html"
JSPDF = AQUI / "jspdf.umd.min.js"
PASTA_CLIENTES = AQUI.parent.parent / "PREPARAÇÃO PARA INGRESSO"

# Subpastas da pasta do cliente (a primeira é o padrão; as demais são grafias antigas).
PASTA_CONTRATO = ["CONTRATO HO", "CONTRATO DE HONORÁRIOS", "CONTRATO HONORÁRIOS", "CONTRATO"]
PASTA_ONBOARDING = ["ONBOARDING", "ON BOARDING"]

NAVEGADORES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]

# Opções dos dois menus suspensos do gerador_pdf.html.
SERVICOS = ["Ação Revisional", "Busca e Apreensão (Defesa)", "Ação de Danos Morais",
            "Negativação Indevida", "Fraude Bancária"]
FORMAS = ["Boleto", "Cartão de Crédito (Recorrência)"]

# (chave usada no formulário, rótulo na tela, obrigatório)
CAMPOS = [
    ("nome",  "Primeiro nome",      True),
    ("serv",  "Serviço",            True),
    ("banco", "Banco adverso",      True),
    ("veic",  "Veículo",            False),
    ("ent",   "Valor da entrada",   False),
    ("dte",   "Data da entrada",    False),
    ("qtd",   "Qtd. de parcelas",   False),
    ("par",   "Valor da parcela",   False),
    ("d1",    "1ª parcela",         False),
    ("df",    "Última parcela",     False),
    ("tot",   "Total honorários",   False),
    ("forma", "Forma de pagamento", True),
]


# ---------------------------------------------------------------------------
# Leitura do contrato
# ---------------------------------------------------------------------------

DINHEIRO = r"R\$\s*\d[\d.\s]*,\s?\d{2}"
DATA = r"\d{2}\s*[./-]\s*\d{2}\s*[./-]\s*\d{4}"


def normalizar(texto: str) -> str:
    """Sem acento, maiúscula, espaços colapsados — para comparar nomes de pasta."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


def texto_do_contrato(caminho: Path, paginas: int = 4) -> str:
    """Texto das primeiras páginas, sem os rodapés de assinatura, numa linha só."""
    reader = PdfReader(str(caminho))
    bruto = "\n".join(p.extract_text() or "" for p in reader.pages[:paginas])
    bruto = re.sub(r"Assinado com Assinatura Eletrônica.*?Validador", " ", bruto, flags=re.S)
    bruto = bruto.replace(" ", " ").replace("–", "–")
    return re.sub(r"\s+", " ", bruto).strip()


def limpar_dinheiro(txt: str) -> str:
    """'R$4.499, 95' -> 'R$ 4.499,95'"""
    if not txt:
        return ""
    valor = re.sub(r"\s+", "", txt).replace("R$", "")
    return "R$ " + valor


def limpar_data(txt: str) -> str:
    """'14.08.2026' / '14 . 08 . 2026' -> '14/08/2026'"""
    if not txt:
        return ""
    return re.sub(r"[.\-]", "/", re.sub(r"\s+", "", txt))


def trecho_clausula2(texto: str) -> str:
    """Só o pedaço da Cláusula 2ª que descreve entrada e parcelas."""
    m = re.search(r"Cl[áa]usula 2", texto)
    inicio = m.start() if m else 0
    fim = len(texto)
    for marca in ("O contratante fica ciente", "Parágrafo 1", "Paragrafo 1",
                  "Cláusula 3", "Clausula 3"):
        p = texto.find(marca, inicio + 10)
        if p > 0:
            fim = min(fim, p)
    return texto[inicio:min(fim, inicio + 6000)]


def ler_nome(texto: str) -> str:
    m = re.search(r"(?:Cliente\s+)?Contratante[:,]?\s+([A-ZÀ-Ú][A-ZÀ-Ú\s.]{4,70}?)\s*,", texto)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def primeiro_nome(nome_completo: str) -> str:
    if not nome_completo:
        return ""
    return nome_completo.split()[0].title()


def frouxa(palavra: str) -> str:
    """
    Regex que aguenta a palavra partida pelo PDF.

    'Obrigação' vira O\s*b\s*r\s*i\s*g\s*a\s*[çc]... porque o extrator de
    texto enfia espaço em qualquer ponto da palavra: o contrato do Lucas traz
    "Obrigação" inteiro e o da Juliana, "Obri gação" — a mesma frase, o mesmo
    modelo, dois PDFs diferentes.
    """
    equivalentes = {"ç": "[çc]", "ã": "[ãa]", "á": "[áa]", "é": "[ée]", "í": "[íi]",
                    "ó": "[óo]", "ú": "[úu]", "â": "[âa]", "ê": "[êe]", "õ": "[õo]"}
    return r"\s*".join(equivalentes.get(letra, re.escape(letra))
                       for letra in palavra if not letra.isspace())


def ler_servico(texto: str) -> str:
    if re.search(frouxa("Busca") + r"\s*e\s*" + frouxa("Apreensão"), texto, re.I):
        return "Busca e Apreensão (Defesa)"
    if re.search(frouxa("Ação") + r"\s+" + frouxa("Revisional"), texto, re.I):
        return "Ação Revisional"
    # Vem antes de "Danos Morais" porque o contrato escreve a ação inteira:
    # "Ação de Obrigação de Fazer c/c Dano Moral" (contrato do Felipe, 17/08/2026).
    # Os \s* no meio da palavra são por causa do PDF, que parte palavra ao meio:
    # o contrato da Juliana traz "Obri gação de Fazer" (01/09/2026).
    if re.search(frouxa("Obrigação") + r"\s+de\s+" + frouxa("Fazer"), texto, re.I):
        return "Ação de Obrigação de Fazer c/c Dano Moral"
    # "Morais?" não pega "Moral" — era esse o erro que deixava o contrato da
    # Juliana sem serviço nenhum, mesmo dizendo "Dano Moral".
    if re.search(r"Danos?\s+Mora(l|is)", texto, re.I):
        return "Ação de Danos Morais"
    if re.search(r"Negativa[çc][ãa]o\s+Indevida", texto, re.I):
        return "Negativação Indevida"
    if re.search(r"Fraude\s+Banc[áa]ria", texto, re.I):
        return "Fraude Bancária"
    return ""


def ler_banco(texto: str) -> str:
    """
    A parte adversa. Nas revisionais é o banco ("em desfavor do Banco X").

    Nas ações de obrigação de fazer a adversa não é banco nenhum — é a loja ou
    a escola, e o contrato escreve de outro jeito: "firmado com a empresa: MEGA
    MOTOS..." (Lucas), "na empresa, COLÉGIO INÊS MENDES..." (Juliana). O campo
    do onboarding é o mesmo; só a frase muda.
    """
    padroes = (
        r"em\s+desfavor\s+d[oa]\s+(.{3,70}?)\s*,\s*referente",
        r"em\s+desfavor\s+d[oa]\s+(.{3,70}?)\s*(?:,|\.|\breferente\b)",
        r"firmado\s+com\s+a\s+empresa\s*[:,]?\s*(.{3,70}?)\s*(?:[–-]\s*CNPJ|,|\.\s|$)",
        r"na\s+empresa\s*[:,]\s*(.{3,70}?)\s*(?:[–-]\s*CNPJ|,|\.\s|$)",
        # Sofia (01/09/2026): "com a instituição: NU PAGAMENTOS S.A." e
        # "com o: MUNICÍPIO DE JEQUIÁ DA PRAIA - AL." — adversa que não é banco
        # nem loja. Os dois pedem os dois pontos logo depois, o que evita casar
        # com qualquer "com o" solto do texto.
        r"com\s+[oa]s?\s+institui[çc][ãa]o\s*[:,]\s*(.{3,70}?)\s*(?:[–-]\s*CNPJ|,|\.\s|$)",
        r"com\s+[oa]s?\s*[:,]\s*(.{3,70}?)\s*(?:[–-]\s*CNPJ|,|\.\s|$)",
    )
    for padrao in padroes:
        m = re.search(padrao, texto, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" ,;.–-")
    return ""


def ler_veiculo(texto: str) -> str:
    # O ';' corta: no contrato do Lucas o veículo é seguido de "; firmado com a
    # empresa: MEGA MOTOS…", que é a parte adversa, não o carro.
    m = re.search(r"referente\s+ao\s+contrato\b.{0,40}?\bve[íi]culo\s*[:,]?\s*([^;]+?)\s*"
                  r"(?:Cl[áa]usula\s*2|;|$)", texto, re.I)
    if not m:
        return ""
    veic = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(" .;,")
    veic = re.sub(r"\s+([,;:])", r"\1", veic)          # 'START , PLACA' -> 'START, PLACA'
    return re.sub(r"^MARCA:\s*", "", veic, flags=re.I)


def ler_entrada(trecho: str):
    m = re.search(r"Entrada\s+no\s+valor\s+de\s*(" + DINHEIRO + r")", trecho, re.I)
    if not m:
        return "", ""
    valor = limpar_dinheiro(m.group(1))
    d = re.search(r"na\s+data\s+de\s*(" + DATA + r")", trecho[m.end():], re.I)
    return valor, limpar_data(d.group(1)) if d else ""


def ler_parcelas(trecho: str):
    """
    Devolve (qtd, valor, data da 1ª, data da última).

    Quase sempre há um único bloco ('15 (quinze) parcelas de R$ 273,33 com
    início em ... e a última em ...'). Quando o contrato divide em dois blocos
    com valores diferentes, soma as quantidades e descreve os dois valores —
    do mesmo jeito que era preenchido à mão.
    """
    rx = re.compile(r"(\d{1,3})\s*\([^)]{0,60}\)\s*parcelas?\s+de\s*(" + DINHEIRO + r")", re.I)
    achados = list(rx.finditer(trecho))
    if not achados:
        return "", "", "", ""

    blocos = []
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(trecho)
        blocos.append({
            "qtd": int(m.group(1)),
            "valor": limpar_dinheiro(m.group(2)),
            "datas": [limpar_data(d) for d in re.findall(DATA, trecho[m.end():fim])],
        })

    qtd = sum(b["qtd"] for b in blocos)
    if len(blocos) == 1:
        valor = blocos[0]["valor"]
    else:
        valor = " e ".join("%02d de %s" % (b["qtd"], b["valor"]) for b in blocos)

    primeira = next((b["datas"][0] for b in blocos if b["datas"]), "")
    ultima = next((b["datas"][-1] for b in reversed(blocos) if b["datas"]), "")
    return str(qtd), valor, primeira, ultima


def ler_forma(trecho: str) -> str:
    if re.search(r"CART[ÃA]O\s+DE\s+CR[ÉE]DITO\s+NA\s+RECORR[ÊE]NCIA", trecho, re.I):
        return "Cartão de Crédito (Recorrência)"
    return "Boleto"


def ler_total(trecho: str) -> str:
    m = re.search(r"import[âa]ncia\s+de\s*(" + DINHEIRO + r")", trecho, re.I)
    return limpar_dinheiro(m.group(1)) if m else ""


def extrair(contrato: Path) -> dict:
    texto = texto_do_contrato(contrato)
    trecho = trecho_clausula2(texto)
    ent, dte = ler_entrada(trecho)
    qtd, par, d1, df = ler_parcelas(trecho)
    nome_completo = ler_nome(texto)
    return {
        "nome": primeiro_nome(nome_completo),
        "nome_completo": nome_completo,
        "serv": ler_servico(texto),
        "banco": ler_banco(texto),
        "veic": ler_veiculo(texto),
        "ent": ent, "dte": dte,
        "qtd": qtd, "par": par, "d1": d1, "df": df,
        "tot": ler_total(trecho),
        "forma": ler_forma(trecho),
        "_vazio": len(texto) < 200,
    }


# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------

def limpar_caminho(texto: str) -> str:
    """Normaliza caminho colado ou arrastado para dentro do Terminal."""
    texto = texto.strip()
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in "\"'":
        return texto[1:-1]
    return re.sub(r"\\(.)", r"\1", texto)


def subpastas(pasta: Path) -> dict:
    if not pasta.is_dir():
        return {}
    return {normalizar(p.name): p for p in pasta.iterdir() if p.is_dir()}


def achar_subpasta(pasta: Path, nomes):
    existentes = subpastas(pasta)
    for nome in nomes:
        achada = existentes.get(normalizar(nome))
        if achada is not None:
            return achada
    return None


def eh_pasta_de_cliente(pasta: Path) -> bool:
    return achar_subpasta(pasta, PASTA_CONTRATO) is not None or \
           achar_subpasta(pasta, PASTA_ONBOARDING) is not None


def resolver_pasta_cliente(caminho: Path):
    """Aceita a pasta do cliente, a subpasta CONTRATO HO ou o próprio PDF do contrato."""
    caminho = caminho.expanduser()
    if caminho.is_file():
        pai = caminho.parent
        return pai.parent if normalizar(pai.name) in {normalizar(n) for n in PASTA_CONTRATO} else pai
    if caminho.is_dir():
        if normalizar(caminho.name) in {normalizar(n) for n in PASTA_CONTRATO + PASTA_ONBOARDING}:
            return caminho.parent
        return caminho
    return None


def achar_contrato(pasta_cliente: Path):
    """PDF do contrato dentro da pasta do cliente. Prefere o assinado em CONTRATO HO."""
    pasta = achar_subpasta(pasta_cliente, PASTA_CONTRATO)
    candidatos = sorted(pasta.glob("*.pdf")) if pasta else []
    if not candidatos:
        candidatos = sorted(p for p in pasta_cliente.glob("*.pdf")
                            if "contrato" in normalizar(p.name).lower())
    if not candidatos:
        return None

    def peso(p: Path):
        n = normalizar(p.name)
        return (0 if "ASSINAD" in n else 1, 0 if "CONTRATO" in n else 1, len(n))

    return sorted(candidatos, key=peso)[0]


def clientes_recentes(limite: int = 10):
    """Pastas de cliente mais mexidas recentemente, dentro de PREPARAÇÃO PARA INGRESSO."""
    if not PASTA_CLIENTES.is_dir():
        return []
    achadas = []
    for mes in PASTA_CLIENTES.iterdir():
        if not mes.is_dir() or mes.name.startswith("."):
            continue
        for cliente in mes.iterdir():
            if cliente.is_dir() and not cliente.name.startswith(".") and eh_pasta_de_cliente(cliente):
                achadas.append(cliente)
    return sorted(achadas, key=lambda p: p.stat().st_mtime, reverse=True)[:limite]


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


# ---------------------------------------------------------------------------
# Geração do PDF (navegador invisível rodando o gerador_pdf.html)
# ---------------------------------------------------------------------------

DRIVER = """
<script>
function __gerar(){
  var D = __DADOS__;
  function enviar(o){
    try{ var x=new XMLHttpRequest(); x.open('POST','/resultado',true);
         x.setRequestHeader('Content-Type','application/json'); x.send(JSON.stringify(o)); }catch(e){}
  }
  window.alert = function(m){ enviar({erro: m}); };
  window.onerror = function(m){ enviar({erro: m}); };
  function texto(id,v){ var e=document.getElementById(id); if(e) e.value = v||''; }
  function menu(id,v){
    var s=document.getElementById(id); if(!s||!v) return;
    for(var i=0;i<s.options.length;i++){ if(s.options[i].text.trim()===v.trim()){ s.selectedIndex=i; return; } }
    for(var i=0;i<s.options.length;i++){
      if(s.options[i].text.toLowerCase().indexOf(v.toLowerCase().slice(0,8))>=0){ s.selectedIndex=i; return; }
    }
  }
  texto('f_nome',D.nome); texto('f_banco',D.banco); texto('f_veic',D.veic);
  texto('f_ent',D.ent); texto('f_dte',D.dte); texto('f_qtd',D.qtd); texto('f_par',D.par);
  texto('f_d1',D.d1); texto('f_df',D.df); texto('f_tot',D.tot);
  menu('f_serv',D.serv); menu('f_forma',D.forma);

  var botao = document.getElementById('bGerar');
  if(!botao){ enviar({erro:'não encontrei o botão Gerar PDF na página'}); return; }
  botao.click();

  var t0 = Date.now();
  var relogio = setInterval(function(){
    if(window.blob){
      clearInterval(relogio);
      var leitor = new FileReader();
      leitor.onload = function(){ enviar({pdf: leitor.result.split(',')[1]}); };
      leitor.readAsDataURL(window.blob);
    } else if(Date.now()-t0 > 90000){
      clearInterval(relogio); enviar({erro:'o gerador demorou demais para responder'});
    }
  }, 150);
}
if(document.readyState === 'complete') __gerar();
else window.addEventListener('load', __gerar);
</script>
"""


def achar_navegador():
    for caminho in NAVEGADORES:
        if os.path.exists(caminho):
            return caminho
    return shutil.which("chromium") or shutil.which("google-chrome")


def montar_pagina(dados: dict) -> bytes:
    html = GERADOR_HTML.read_text(encoding="utf-8")
    html, trocas = re.subn(r'<script src="https://cdnjs[^"]*jspdf[^"]*"></script>',
                           '<script src="/jspdf.js"></script>', html, count=1)
    if not trocas:
        raise RuntimeError("não achei a linha do jsPDF dentro de gerador_pdf.html")
    html = re.sub(r'<link[^>]+href="https://fonts[^"]*"[^>]*>', "", html)
    driver = DRIVER.replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
    return html.replace("</body>", driver + "</body>").encode("utf-8")


def gerar_pdf(dados: dict) -> bytes:
    if not GERADOR_HTML.is_file():
        raise RuntimeError("não encontrei o arquivo:\n  %s" % GERADOR_HTML)
    if not JSPDF.is_file():
        raise RuntimeError("não encontrei o arquivo jspdf.umd.min.js na pasta do programa.")
    navegador = achar_navegador()
    if not navegador:
        raise RuntimeError("não encontrei o Google Chrome nesta máquina.\n"
                           "Instale o Chrome (gratuito) em https://www.google.com/chrome e tente de novo.")

    pagina = montar_pagina(dados)
    biblioteca = JSPDF.read_bytes()
    resultado, pronto = {}, threading.Event()

    class Alca(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _responder(self, corpo, tipo):
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            if self.path.startswith("/jspdf.js"):
                self._responder(biblioteca, "application/javascript; charset=utf-8")
            elif self.path in ("/", "/index.html"):
                self._responder(pagina, "text/html; charset=utf-8")
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                resultado.update(json.loads(self.rfile.read(n)))
            except Exception:
                resultado["erro"] = "resposta ilegível do navegador"
            self.send_response(204)
            self.end_headers()
            pronto.set()

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Alca)
    porta = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    perfil = tempfile.mkdtemp(prefix="onboarding-")
    processo = subprocess.Popen(
        [navegador, "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--disable-extensions", "--mute-audio",
         "--user-data-dir=" + perfil, "--window-size=900,700",
         "http://127.0.0.1:%d/" % porta],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        pronto.wait(120)
    finally:
        processo.terminate()
        try:
            processo.wait(10)
        except Exception:
            processo.kill()
        servidor.shutdown()
        shutil.rmtree(perfil, ignore_errors=True)

    if "pdf" in resultado:
        return base64.b64decode(resultado["pdf"])
    raise RuntimeError(resultado.get("erro") or
                       "o navegador não respondeu. Tente de novo; se persistir, confira se o "
                       "Chrome abre normalmente.")


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------

def perguntar(texto: str) -> str:
    try:
        return input(texto).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def mostrar(dados: dict, cliente: Path, contrato: Path):
    print()
    print("  Cliente:  %s" % cliente.name)
    if dados.get("nome_completo"):
        print("            %s" % dados["nome_completo"].title())
    print("  Contrato: %s" % contrato.name)
    print()
    print("  ─── DADOS PARA O ONBOARDING " + "─" * 30)
    for i, (chave, rotulo, obrigatorio) in enumerate(CAMPOS, 1):
        valor = dados.get(chave) or ""
        if len(valor) > 62:
            valor = valor[:59] + "..."
        marca = "  " if valor else ("!!" if obrigatorio else "··")
        print("  %s %2d. %-20s %s" % (marca, i, rotulo, valor or "(vazio)"))
    print("  " + "─" * 58)
    faltando = [r for c, r, o in CAMPOS if o and not dados.get(c)]
    if faltando:
        print("  !! Falta preencher: %s" % ", ".join(faltando))
    print()


def editar_campo(dados: dict, indice: int):
    chave, rotulo, _ = CAMPOS[indice]
    if chave == "serv":
        opcoes = SERVICOS
    elif chave == "forma":
        opcoes = FORMAS
    else:
        opcoes = None

    if opcoes:
        print("\n  %s:" % rotulo)
        for n, o in enumerate(opcoes, 1):
            print("    %d. %s" % (n, o))
        resposta = perguntar("  Digite o número [Enter = manter] > ")
        if resposta.isdigit() and 1 <= int(resposta) <= len(opcoes):
            dados[chave] = opcoes[int(resposta) - 1]
        return

    atual = dados.get(chave) or ""
    print("\n  %s%s" % (rotulo, (" (atual: %s)" % atual) if atual else ""))
    resposta = perguntar("  Novo valor [Enter = manter] > ")
    if resposta:
        dados[chave] = resposta


def escolher_cliente() -> Path:
    lista = clientes_recentes()
    print("\n=== GERADOR DE ONBOARDING ===")
    if lista:
        print("\nClientes mexidos recentemente:\n")
        for n, p in enumerate(lista, 1):
            print("  %2d. %s   (%s)" % (n, p.name, p.parent.name))
        print("\nDigite o número, ou arraste a pasta do cliente para esta janela.")
        padrao = "  [Enter = opção 1] > "
    else:
        print("\nArraste a pasta do cliente para esta janela.")
        padrao = "  > "

    while True:
        resposta = perguntar(padrao)
        if not resposta and lista:
            return lista[0]
        if resposta.isdigit() and lista and 1 <= int(resposta) <= len(lista):
            return lista[int(resposta) - 1]
        pasta = resolver_pasta_cliente(Path(limpar_caminho(resposta)))
        if pasta and pasta.is_dir():
            return pasta
        print("  Não encontrei essa pasta. Tente de novo.")


def revisar(dados: dict, cliente: Path, contrato: Path) -> bool:
    """Mostra os dados e deixa corrigir campo a campo. False = cancelado."""
    # O banco não consta no contrato de busca e apreensão: pergunta logo.
    if not dados.get("banco"):
        print("\n  O contrato não diz qual é o banco adverso (é o caso das buscas e apreensões).")
        dados["banco"] = perguntar("  Banco adverso > ")

    while True:
        mostrar(dados, cliente, contrato)
        faltando = [r for c, r, o in CAMPOS if o and not dados.get(c)]
        if faltando:
            print("  Digite o número do campo para preencher (ou 'c' para cancelar).")
            resposta = perguntar("  > ")
        else:
            print("  Digite o número do campo para corrigir, 'c' para cancelar,")
            resposta = perguntar("  ou Enter para gerar o PDF > ")
            if not resposta:
                return True
        if resposta.lower() == "c":
            return False
        if resposta.isdigit() and 1 <= int(resposta) <= len(CAMPOS):
            editar_campo(dados, int(resposta) - 1)
        else:
            print("  Não entendi.")


def salvar(pdf: bytes, cliente: Path, nome: str, sobrescrever: bool) -> Path:
    pasta = achar_subpasta(cliente, PASTA_ONBOARDING) or (cliente / PASTA_ONBOARDING[0])
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / ("onboarding_%s.pdf" % (nome or "cliente").lower().replace(" ", "_"))
    if not sobrescrever:
        arquivo = nome_unico(arquivo)
    arquivo.write_bytes(pdf)
    return arquivo


# ---------------------------------------------------------------------------

def preparar(pasta_informada, listar):
    """Devolve (cliente, contrato, dados) ou encerra com mensagem."""
    if pasta_informada:
        cliente = resolver_pasta_cliente(Path(limpar_caminho(pasta_informada)))
        if not cliente or not cliente.is_dir():
            sys.exit("Pasta não encontrada: %s" % pasta_informada)
    else:
        cliente = escolher_cliente()

    contrato = achar_contrato(cliente)
    if not contrato:
        sys.exit("Não achei o PDF do contrato em:\n  %s\n"
                 "Confira se o arquivo está na subpasta CONTRATO HO." % cliente)

    dados = extrair(contrato)
    if dados.pop("_vazio", False):
        print("\n  Atenção: não consegui ler o texto deste contrato (PDF digitalizado?).")
        print("  Os campos vêm em branco; preencha à mão abaixo.\n")
    if not dados.get("nome"):
        dados["nome"] = primeiro_nome(re.sub(r"^[\d\s\-]*(OK\s*-\s*)?", "", cliente.name).strip())
    return cliente, contrato, dados


def interativo(args):
    cliente, contrato, dados = preparar(args.pasta, False)
    if not revisar(dados, cliente, contrato):
        print("Cancelado.\n")
        return

    print("\n  Gerando o PDF...")
    try:
        pdf = gerar_pdf(dados)
    except RuntimeError as e:
        print("\n  Não deu certo: %s\n" % e)
        return
    arquivo = salvar(pdf, cliente, dados["nome"], args.sobrescrever)
    print("  ✓ %s" % arquivo.name)
    print("    em %s\n" % arquivo.parent)

    if perguntar("Abrir a pasta no Finder? [Enter = sim / n = não] > ").lower().startswith("n"):
        return
    subprocess.run(["open", "-R", str(arquivo)])


def main():
    ap = argparse.ArgumentParser(
        description="Gera o PDF de onboarding a partir do contrato de prestação de serviços.")
    ap.add_argument("pasta", nargs="?", help="Pasta do cliente (ou o PDF do contrato)")
    ap.add_argument("--listar", "-l", action="store_true",
                    help="Apenas mostrar o que foi lido do contrato, sem gerar nada")
    ap.add_argument("--sobrescrever", action="store_true",
                    help="Substituir o onboarding já existente em vez de criar '(2)'")
    ap.add_argument("--saida", help="Gravar o PDF neste caminho em vez da subpasta ONBOARDING")
    ap.add_argument("--banco", help="Banco adverso (as buscas e apreensões não trazem no contrato)")
    ap.add_argument("--veiculo", help="Veículo, quando o contrato não descrever")
    ap.add_argument("--interativo", "-i", action="store_true",
                    help="Modo pergunta-e-resposta (usado pelo atalho)")
    args = ap.parse_args()

    if args.interativo:
        interativo(args)
        return

    cliente, contrato, dados = preparar(args.pasta, args.listar)
    # Preenchimento vindo de fora: é assim que a automação informa o banco que
    # achou no contrato de financiamento do cliente (busca e apreensão não traz
    # esse dado no contrato de honorários).
    if getattr(args, "banco", None):
        dados["banco"] = args.banco.strip()
    if getattr(args, "veiculo", None):
        dados["veic"] = args.veiculo.strip()
    mostrar(dados, cliente, contrato)
    if args.listar:
        return

    faltando = [r for c, r, o in CAMPOS if o and not dados.get(c)]
    if faltando:
        sys.exit("Falta preencher: %s. Rode sem argumentos para preencher na tela." % ", ".join(faltando))

    pdf = gerar_pdf(dados)
    if args.saida:
        destino = Path(args.saida).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(pdf)
    else:
        destino = salvar(pdf, cliente, dados["nome"], args.sobrescrever)
    print("  ✓ %s\n    em %s\n" % (destino.name, destino.parent))


if __name__ == "__main__":
    main()
