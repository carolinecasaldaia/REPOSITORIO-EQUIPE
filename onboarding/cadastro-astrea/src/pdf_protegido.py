#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF com senha: abrir quando dá, sem adivinhação selvagem.

Arquivo compartilhado, como o ocr.py: a fonte fica aqui e cada projeto tem uma
cópia em src/.

Dois casos aparecem nas pastas dela (08/09/2026):

- **Senha só de dono**: o PDF é protegido contra edição, mas abre com senha
  vazia. É o caso mais comum e o pypdf resolve sozinho.
- **Senha no nome do arquivo**: o banco manda o contrato protegido e o cliente
  renomeia para "CONTRATO, SENHA: 448.pdf". A senha está ali, escrita por quem
  tem direito ao documento — usá-la é ler o que o cliente já entregou aberto.

O que este módulo **não** faz: tentar lista de senhas comuns, CPF, data de
nascimento. Isso seria quebrar a proteção, não ler o que foi entregue.
"""

import contextlib
import os
import re
import tempfile
from pathlib import Path

# "SENHA: 448", "senha 1234", "SENHA-abc12"
_SENHA_NO_NOME = re.compile(r"SENHA\s*[:\-=]?\s*([A-Za-z0-9]{3,20})", re.I)


def senha_no_nome(nome: str) -> str:
    """Devolve a senha escrita no nome do arquivo, ou ""."""
    achado = _SENHA_NO_NOME.search(nome or "")
    return achado.group(1) if achado else ""


def senhas_possiveis(caminho) -> list:
    """Senhas a tentar, na ordem. A vazia vem primeiro: é a que mais resolve."""
    senhas = [""]
    escrita = senha_no_nome(Path(caminho).name)
    if escrita:
        senhas.append(escrita)
    return senhas


def abrir(caminho, PdfReader=None):
    """
    Devolve (leitor, senha_usada) de um PDF, protegido ou não.

    (None, None) quando não abre. Nunca levanta exceção.
    """
    if PdfReader is None:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None, None
    caminho = Path(caminho)
    try:
        leitor = PdfReader(str(caminho))
    except Exception:
        return None, None

    if not getattr(leitor, "is_encrypted", False):
        return leitor, None

    for senha in senhas_possiveis(caminho):
        try:
            if leitor.decrypt(senha):
                return leitor, senha
        except Exception:
            continue
    return None, None


@contextlib.contextmanager
def copia_aberta(leitor, PdfWriter=None):
    """
    Grava uma cópia SEM senha, para quem não sabe lidar com PDF protegido.

    Existe por causa do OCR: o contrato do Gildovan abre com a senha do nome do
    arquivo, mas é digitalização — só que o programa de OCR usa o PDFKit, que
    não abre arquivo protegido. A cópia é temporária, fica FORA do Google Drive
    e some ao fim do bloco.

        with copia_aberta(leitor) as aberto:
            texto = ocr.ler(aberto)
    """
    if PdfWriter is None:
        try:
            from pypdf import PdfWriter
        except ImportError:
            yield None
            return

    pasta = Path.home() / ".ocr-escritorio" / "temporarios"
    pasta.mkdir(parents=True, exist_ok=True)
    os.chmod(str(pasta), 0o700)          # documento de cliente não fica exposto
    alvo = None
    try:
        escritor = PdfWriter()
        for pagina in leitor.pages:
            escritor.add_page(pagina)
        descritor, caminho = tempfile.mkstemp(suffix=".pdf", dir=str(pasta))
        os.close(descritor)
        alvo = Path(caminho)
        with open(str(alvo), "wb") as saida:
            escritor.write(saida)
        yield alvo
    except Exception:
        yield None
    finally:
        if alvo is not None:
            try:
                alvo.unlink()
            except OSError:
                pass
