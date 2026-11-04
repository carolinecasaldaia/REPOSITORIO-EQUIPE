#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventário dos documentos da pasta do cliente.

Faz três coisas:

1. **Classifica** cada arquivo pelo nome e pela subpasta (CNH, comprovante de
   residência, contrato de honorários, contrato bancário, CRLV, holerite...).

2. **Registra o que não deu para interpretar**, sem chutar conteúdo. Foi
   verificado nas pastas reais que as CNH-e em PDF trazem os dados dentro de uma
   imagem (o PDF só tem o texto do carimbo do SERPRO) e as fotos de RG são
   imagem pura. Como não há OCR instalado nesta máquina — e mandar documento de
   cliente para OCR na nuvem seria exposição desnecessária — esses arquivos são
   marcados como DOCUMENTO NÃO INTERPRETADO, com nome, tipo e motivo.

3. **Confere** o que dá para conferir. A conta de luz usada como comprovante de
   residência costuma ter camada de texto com nome, CEP e endereço; ela vira
   segunda fonte para checar o endereço do contrato.
"""

import re
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:                                    # pragma: no cover
    PdfReader = None

from .. import ocr, pdf_protegido
from ..validators import campos as V

# Tipos reconhecidos, na ordem em que são testados (o primeiro que casar vence).
TIPOS = (
    ("contrato_honorarios", re.compile(
        r"contrato\s*ho\b|contrato\s+de\s+presta|honor[áa]rio|"
        r"contrato\s*-\s*procura", re.I)),
    ("procuracao", re.compile(r"procura[çc][ãa]o", re.I)),
    ("hipossuficiencia", re.compile(r"hipossufici", re.I)),
    ("onboarding", re.compile(r"onboarding|on\s*board", re.I)),
    ("calculo", re.compile(r"c[áa]lculo|calculo|planilha\s+revis", re.I)),
    ("cnh", re.compile(r"\bcnh\b|habilita[çc][ãa]o|carteira\s+de\s+motorista", re.I)),
    ("rg", re.compile(r"\brg\b|identidade|\brg[,\s]", re.I)),
    ("cpf", re.compile(r"\bcpf\b", re.I)),
    # Declaração de residência assinada no escritório (Lei 7.115/83), para
    # quem não tem comprovante no próprio nome. Vem ANTES do comprovante: o
    # nome do arquivo diz "residência" nos dois, e confundir os dois faria a
    # declaração ser lida como conta de luz.
    ("declaracao_residencia", re.compile(
        r"declara[çc][ãa]o\s*(de)?\s*resid|declara[çc]ao\s*resid", re.I)),
    ("comprovante_residencia", re.compile(
        r"comprovante\s*(de)?\s*resid|comp\s*resid|conta\s+de\s+(luz|energia|[áa]gua)|"
        r"fatura", re.I)),
    ("contrato_bancario", re.compile(
        r"contrato\s+banc|contrato\s+de\s+financiamento|c[ée]dula|financiamento", re.I)),
    ("veiculo", re.compile(r"crlv|crv\b|documento\s+do\s+ve[íi]culo|ve[íi]culo", re.I)),
    ("renda", re.compile(r"holerite|contracheque|contra-cheque|extrato\s+banc|"
                         r"comprovante\s+de\s+renda|declara[çc][ãa]o\s+de\s+renda", re.I)),
    ("boleto", re.compile(r"boleto|carn[êe]|parcela|comprovante\s+de\s+pagamento|"
                          r"comprovante\s+pix|entrada\s+ho", re.I)),
    ("ficha", re.compile(r"ficha\s*cadastral|ficha\s+do\s+cliente|cadastro", re.I)),
)

EXTENSOES_IMAGEM = (".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff", ".bmp")
EXTENSOES_TEXTO = (".txt", ".csv", ".md")
MIN_CARACTERES_UTEIS = 120     # abaixo disso o PDF é digitalização, não texto


class Documento(object):
    def __init__(self, caminho: Path, tipo: str):
        self.caminho = caminho
        self.tipo = tipo
        self.texto = ""
        self.legivel = False
        self.motivo_ilegivel = ""
        self.por_ocr = False           # texto veio do OCR, não da camada do PDF

    @property
    def nome(self):
        return self.caminho.name

    @property
    def extensao(self):
        return self.caminho.suffix.lower()

    def como_dict(self):
        return {"arquivo": self.nome, "tipo": self.tipo,
                "legivel": self.legivel, "motivo": self.motivo_ilegivel}

    def __repr__(self):
        return "<Documento %s %s>" % (self.tipo, self.nome)


def classificar(caminho: Path) -> str:
    """Tipo do documento, pelo nome do arquivo e pela subpasta onde está."""
    alvo = "%s %s" % (caminho.parent.name, caminho.name)
    for tipo, padrao in TIPOS:
        if padrao.search(alvo):
            return tipo
    return "outros"


def _ler_texto(documento: Documento):
    caminho = documento.caminho
    extensao = documento.extensao

    if extensao in EXTENSOES_IMAGEM:
        # Foto de documento é rotina: o cliente manda pelo WhatsApp e o arquivo
        # cai na pasta como .jpeg. O OCR do macOS lê imagem tão bem quanto PDF.
        reconhecido = re.sub(r"\s+", " ", ocr.ler(caminho)).strip()
        if len(reconhecido) >= MIN_CARACTERES_UTEIS:
            documento.texto = reconhecido
            documento.legivel = True
            documento.por_ocr = True
            return
        documento.motivo_ilegivel = (
            "imagem (%s) sem texto reconhecível — foto tremida, escura ou "
            "cortada" % extensao.lstrip(".")
            if ocr.disponivel() else
            "arquivo de imagem (%s) — leitura exigiria OCR, que não está "
            "instalado" % extensao.lstrip("."))
        return

    if extensao in EXTENSOES_TEXTO:
        try:
            documento.texto = caminho.read_text(encoding="utf-8", errors="ignore")
            documento.legivel = bool(documento.texto.strip())
        except OSError as erro:
            documento.motivo_ilegivel = "não foi possível abrir o arquivo: %s" % erro
        return

    if extensao != ".pdf":
        documento.motivo_ilegivel = "formato não suportado para leitura (%s)" % extensao
        return

    if PdfReader is None:
        documento.motivo_ilegivel = "biblioteca de leitura de PDF indisponível"
        return

    # PDF com senha: tenta a senha vazia e a que estiver escrita no nome do
    # arquivo ("CONTRATO, SENHA: 448.pdf"). Autorizado por ela em 08/09/2026.
    leitor_protegido, senha_usada = pdf_protegido.abrir(caminho, PdfReader)
    if leitor_protegido is None and senha_usada is None:
        try:
            if PdfReader(str(caminho)).is_encrypted:
                documento.motivo_ilegivel = (
                    "PDF protegido por senha — nem a senha vazia nem a escrita "
                    "no nome do arquivo abriram")
                return
        except Exception:
            pass

    try:
        leitor = leitor_protegido or PdfReader(str(caminho))
        pedacos = []
        for pagina in leitor.pages[:4]:
            try:
                pedacos.append(pagina.extract_text() or "")
            except Exception:
                continue
        texto = re.sub(r"\s+", " ", " ".join(pedacos)).strip()
    except Exception as erro:
        documento.motivo_ilegivel = "PDF não pôde ser aberto: %s" % erro
        return

    if len(texto) < MIN_CARACTERES_UTEIS:
        # Digitalização: cai no OCR do macOS. Metade dos documentos que os
        # clientes mandam é foto de papel — CNH, CRLV, comprovante, mandado.
        # O OCR usa o PDFKit, que não abre arquivo protegido: quando a senha
        # foi necessária, ele lê uma cópia aberta e temporária, fora do Drive.
        if senha_usada:
            with pdf_protegido.copia_aberta(leitor) as aberto:
                bruto = ocr.ler(aberto) if aberto else ""
        else:
            bruto = ocr.ler(caminho)
        reconhecido = re.sub(r"\s+", " ", bruto).strip()
        if len(reconhecido) >= MIN_CARACTERES_UTEIS:
            documento.texto = reconhecido
            documento.legivel = True
            documento.por_ocr = True      # quem usa o texto merece saber a origem
            return
        documento.motivo_ilegivel = (
            "PDF sem camada de texto (%d caracteres) e o OCR também não "
            "reconheceu nada legível" % len(texto)
            if ocr.disponivel() else
            "PDF sem camada de texto (%d caracteres) — é digitalização ou "
            "imagem; o OCR não está instalado" % len(texto))
        return

    documento.texto = texto
    documento.legivel = True


def inventariar(pasta: Path, ler_conteudo=True):
    """Lista os documentos da pasta do cliente, já classificados."""
    documentos = []
    for caminho in sorted(Path(pasta).rglob("*")):
        if caminho.is_dir() or caminho.name.startswith("."):
            continue
        documento = Documento(caminho, classificar(caminho))
        if ler_conteudo:
            _ler_texto(documento)
        documentos.append(documento)
    return documentos


def do_tipo(documentos, *tipos):
    return [d for d in documentos if d.tipo in tipos]


def ilegiveis(documentos):
    return [d for d in documentos if not d.legivel and d.motivo_ilegivel]


# ---------------------------------------------------------------------------
# Escolha do contrato de honorários
# ---------------------------------------------------------------------------

_PREFERENCIA_CONTRATO = (
    re.compile(r"^contrato\s*ho\s*assinado", re.I),       # nome padronizado novo
    re.compile(r"assinado", re.I),                        # qualquer assinado
    re.compile(r"completo", re.I),
)


def escolher_contrato(documentos):
    """
    Qual PDF usar como contrato de honorários.

    Uma pasta pode ter o envelope inteiro do Autentique, o contrato separado e
    ainda uma cópia do modelo. A ordem de preferência é: 'Contrato HO
    Assinado.pdf' (nome padronizado pelo separador do Autentique), depois
    qualquer um com 'assinado' no nome, depois o resto — sempre exigindo que o
    arquivo tenha camada de texto.
    """
    candidatos = [d for d in do_tipo(documentos, "contrato_honorarios")
                  if d.extensao == ".pdf"]
    if not candidatos:
        return None
    legiveis = [d for d in candidatos if d.legivel] or candidatos
    for padrao in _PREFERENCIA_CONTRATO:
        for documento in legiveis:
            if padrao.search(documento.nome):
                return documento
    return legiveis[0]


# ---------------------------------------------------------------------------
# Conferência pelo comprovante de residência
# ---------------------------------------------------------------------------

_CEP_NO_TEXTO = re.compile(r"CEP\s*[:.]?\s*(\d{5}\s*-?\s*\d{3})", re.I)
_CEP_SOLTO = re.compile(r"\b(\d{5}-\d{3})\b")
_CPF_MASCARADO = re.compile(r"CPF\s*[:.]?\s*([\*\d]{3}\.[\*\d]{3}\.[\*\d]{3}-[\*\d]{2})", re.I)


# Numa conta de luz o CEP da distribuidora vem encostado no CNPJ dela
# ("CEP: 57052-902 ... CNPJ: 12.272.084/0001-00"). O cliente é pessoa física,
# então CNPJ ali é sempre de quem emitiu a conta — e o CEP ao lado é o
# endereço da empresa, não o dele. Sem esta regra, a conta da Equatorial
# acusou divergência de endereço no Leanderson (13/10/2026) comparando o CEP
# da avenida da própria distribuidora com o do contrato.
_CNPJ_NO_TEXTO = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}")
VIZINHANCA_DO_EMISSOR = 150     # caracteres para cada lado


def _e_do_emissor(texto: str, posicao: int) -> bool:
    inicio = max(0, posicao - VIZINHANCA_DO_EMISSOR)
    janela = texto[inicio:posicao + VIZINHANCA_DO_EMISSOR]
    return bool(_CNPJ_NO_TEXTO.search(janela))


def ceps_da_declaracao(documentos) -> list:
    """CEPs da declaração de residência assinada no escritório."""
    achados = []
    for documento in do_tipo(documentos, "declaracao_residencia"):
        if not documento.legivel:
            continue
        for padrao in (_CEP_NO_TEXTO, _CEP_SOLTO):
            for achado in padrao.finditer(documento.texto or ""):
                cep, ok, _ = V.validar_cep(achado.group(1))
                if ok and cep not in achados:
                    achados.append(cep)
    return achados


class ConferenciaEndereco(object):
    def __init__(self):
        self.ceps = []          # CEPs que podem ser do cliente
        self.ceps_do_emissor = []   # CEPs que são de quem emitiu a conta
        self.cpf_mascarado = ""
        self.arquivo = ""
        self.texto = ""

    @property
    def cep(self):
        return self.ceps[0] if self.ceps else ""

    def confere_cep(self, cep_do_contrato: str) -> bool:
        """
        Uma conta de luz traz vários CEPs: o do cliente e o da distribuidora
        (normalmente um CEP de grande usuário, terminado em 9xx). Por isso a
        conferência é "algum deles bate?", e não "o primeiro bate?" — senão a
        automação acusaria divergência em quase todo mundo.
        """
        return (not self.ceps) or (cep_do_contrato in self.ceps)


def conferir_no_comprovante(documentos):
    """
    Lê o comprovante de residência, quando ele tiver texto (conta de luz, água
    ou telefone costumam ter), e devolve o que serve de segunda fonte.
    """
    for documento in do_tipo(documentos, "comprovante_residencia"):
        if not documento.legivel:
            continue
        conferencia = ConferenciaEndereco()
        conferencia.arquivo = documento.nome
        conferencia.texto = documento.texto
        for padrao in (_CEP_NO_TEXTO, _CEP_SOLTO):
            for achado in padrao.finditer(documento.texto):
                cep, ok, _ = V.validar_cep(achado.group(1))
                if not ok or cep in conferencia.ceps:
                    continue
                if _e_do_emissor(documento.texto, achado.start()):
                    if cep not in conferencia.ceps_do_emissor:
                        conferencia.ceps_do_emissor.append(cep)
                    continue
                conferencia.ceps.append(cep)
        achado = _CPF_MASCARADO.search(documento.texto)
        if achado:
            conferencia.cpf_mascarado = achado.group(1)
        if conferencia.ceps or conferencia.ceps_do_emissor or conferencia.cpf_mascarado:
            return conferencia
    return None


def cpf_compativel_com_mascara(cpf: str, mascarado: str) -> bool:
    """
    A conta de luz traz o CPF parcialmente escondido ('***.734.60*-**').
    Confere só as posições visíveis. Devolve True quando não há conflito.
    """
    digitos = V.so_digitos(cpf)
    visivel = re.sub(r"[^\d\*]", "", mascarado or "")
    if len(digitos) != 11 or len(visivel) != 11:
        return True
    for esperado, real in zip(visivel, digitos):
        if esperado != "*" and esperado != real:
            return False
    return True

# CPF escrito logo depois do rótulo. Na CNH o rótulo e o número são separados
# por traço, espaço ou quebra de linha, e o OCR às vezes come a pontuação.
_CPF_ROTULADO = re.compile(r"CPF[^0-9]{0,20}(\d{3}\D?\d{3}\D?\d{3}\D?\d{2})", re.I)


def cpfs_rotulados(documento) -> list:
    """
    CPFs que aparecem ESCRITOS COM O RÓTULO num documento de identidade.

    Só o que vem depois de "CPF" entra: uma CNH tem vários números longos
    (registro, nº da carteira, código de segurança) que, lidos por OCR,
    passariam por CPF se a busca fosse por formato solto. Devolve já
    formatado e sem repetição, apenas os que passam no dígito verificador.
    """
    from ..validators.campos import validar_cpf

    achados = []
    for bruto in _CPF_ROTULADO.findall(documento.texto or ""):
        formatado, valido, _motivo = validar_cpf(bruto)
        if valido and formatado not in achados:
            achados.append(formatado)
    return achados
