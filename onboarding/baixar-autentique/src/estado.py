#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memória da automação: o que já foi baixado, o que ficou pendente.

É um JSON simples em ~/.baixar-autentique/estado.json — fora do Google Drive,
porque arquivo de controle sincronizado dá conflito (a mesma lição do banco do
CADASTRO ASTREA). A gravação é atômica: escreve num temporário e troca, para
não deixar arquivo pela metade se a máquina dormir no meio da rodada.

Situações de um documento:
    baixado    — arquivado na pasta do cliente (o caso feliz)
    historico  — já estava assinado quando a automação foi ligada; não baixa
    pendente   — assinado, mas falta decisão humana (sem pasta, pasta ambígua)
    ignorado   — assinado, mas não é envelope de onboarding
    erro       — deu problema; a próxima rodada tenta de novo
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

VERSAO = 1
SITUACOES_FINAIS = ("baixado", "historico", "ignorado")


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Estado(object):
    def __init__(self, caminho, dados=None):
        self.caminho = Path(caminho)
        self.dados = dados or {"versao": VERSAO, "documentos": {},
                               "ultima_rodada": "", "ligada_em": ""}

    # -- carga e gravação -------------------------------------------------

    @classmethod
    def carregar(cls, caminho):
        caminho = Path(caminho)
        if not caminho.exists():
            return cls(caminho)
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # Arquivo ilegível não pode travar a automação nem apagar histórico:
            # guarda uma cópia e começa do zero.
            try:
                caminho.replace(caminho.with_suffix(".json.quebrado"))
            except OSError:
                pass
            return cls(caminho)
        dados.setdefault("documentos", {})
        dados.setdefault("versao", VERSAO)
        return cls(caminho, dados)

    def salvar(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(".json.tmp")
        temporario.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        os.replace(str(temporario), str(self.caminho))
        try:
            os.chmod(str(self.caminho), 0o600)
        except OSError:
            pass

    # -- consultas --------------------------------------------------------

    @property
    def documentos(self):
        return self.dados["documentos"]

    def vazio(self) -> bool:
        return not self.documentos

    def conhecido(self, doc_id: str) -> bool:
        """Já resolvido? Pendência e erro NÃO contam — a próxima rodada retenta."""
        registro = self.documentos.get(doc_id)
        return bool(registro) and registro.get("situacao") in SITUACOES_FINAIS

    def situacao(self, doc_id: str) -> str:
        return (self.documentos.get(doc_id) or {}).get("situacao", "")

    def por_situacao(self, *situacoes):
        return {i: r for i, r in self.documentos.items() if r.get("situacao") in situacoes}

    def contagem(self) -> dict:
        contas = {}
        for registro in self.documentos.values():
            chave = registro.get("situacao", "?")
            contas[chave] = contas.get(chave, 0) + 1
        return contas

    # -- escrita ----------------------------------------------------------

    def anotar(self, doc_id: str, **campos):
        registro = self.documentos.get(doc_id, {})
        registro.update(campos)
        registro["quando"] = agora()
        self.documentos[doc_id] = registro
        return registro

    def marcar_rodada(self):
        self.dados["ultima_rodada"] = agora()

    def marcar_ligada(self):
        if not self.dados.get("ligada_em"):
            self.dados["ligada_em"] = agora()


class Tranca(object):
    """
    Impede duas rodadas ao mesmo tempo (o agendador e o clique dela).

    Trava velha (processo que morreu) é ignorada depois de `validade_s`.
    """

    def __init__(self, caminho, validade_s: int = 1800):
        self.caminho = Path(caminho)
        self.validade_s = validade_s
        self.minha = False

    def __enter__(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        if self.caminho.exists():
            idade = time.time() - self.caminho.stat().st_mtime
            if idade < self.validade_s:
                raise RuntimeError(
                    "A automação já está rodando (começou há %d minuto(s)). "
                    "Espere terminar." % int(idade / 60))
            self.caminho.unlink(missing_ok=True)
        self.caminho.write_text("%d %s\n" % (os.getpid(), agora()), encoding="utf-8")
        self.minha = True
        return self

    def __exit__(self, *_):
        if self.minha:
            self.caminho.unlink(missing_ok=True)
        return False
