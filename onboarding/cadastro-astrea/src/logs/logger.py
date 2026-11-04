#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Log da automação.

Duas saídas ao mesmo tempo:
  - texto legível  (execucao-AAAA-MM-DD.log)  — para você ler
  - JSON por linha (eventos-AAAA-MM-DD.jsonl) — para o relatório e auditoria

Regras que este módulo garante sozinho, sem depender de quem chama:
  - CPF sai mascarado (049.***.***-56);
  - senha, token e cabeçalho de autenticação NUNCA são gravados — mesmo que
    alguém passe por engano, o filtro apaga antes de escrever no arquivo.
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..config.settings import get_config, mascarar_cpf

# Padrões que jamais podem ir para o disco.
_SEGREDOS = [
    (re.compile(r"(senha|password|passwd|pwd)\s*[=:]\s*\S+", re.I), r"\1=***"),
    (re.compile(r"(token|api[_-]?key|secret|authorization|bearer)\s*[=:]?\s*[\w\-\.]{6,}", re.I),
     r"\1=***"),
]

_CPF_SOLTO = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def _limpar(texto: str, mascarar_cpf_tambem: bool) -> str:
    if not isinstance(texto, str):
        texto = str(texto)
    for padrao, troca in _SEGREDOS:
        texto = padrao.sub(troca, texto)
    if mascarar_cpf_tambem:
        texto = _CPF_SOLTO.sub(lambda m: mascarar_cpf(m.group(0)), texto)
    return texto


class Log(object):
    """Log de uma execução. Use `Log.abrir()`."""

    def __init__(self, pasta: Path, mascarar: bool, execucao_id: str):
        self.pasta = pasta
        self.mascarar = mascarar
        self.execucao_id = execucao_id
        hoje = datetime.now().strftime("%Y-%m-%d")
        self.arquivo_texto = pasta / ("execucao-%s.log" % hoje)
        self.arquivo_json = pasta / ("eventos-%s.jsonl" % hoje)
        self._contexto = {}

    @classmethod
    def abrir(cls, execucao_id: str = None) -> "Log":
        cfg = get_config()
        cfg.preparar_pastas()
        if execucao_id is None:
            execucao_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        log = cls(cfg.pasta_logs, cfg.mascarar_cpf_no_log, execucao_id)
        log.limpar_antigos(cfg.dias_retencao_log)
        return log

    # -- contexto do cliente em processamento ---------------------------

    def contexto(self, **campos):
        """Campos repetidos em todo evento seguinte (pasta, cliente, cpf)."""
        self._contexto = {k: v for k, v in campos.items() if v not in (None, "")}

    def limpar_contexto(self):
        self._contexto = {}

    # -- escrita ---------------------------------------------------------

    def _escrever(self, nivel: str, mensagem: str, extra: dict = None):
        agora = datetime.now()
        mensagem = _limpar(mensagem, self.mascarar)

        dados = {"quando": agora.isoformat(timespec="seconds"),
                 "execucao": self.execucao_id,
                 "nivel": nivel,
                 "mensagem": mensagem}
        dados.update(self._contexto)
        if extra:
            for chave, valor in extra.items():
                if isinstance(valor, str):
                    valor = _limpar(valor, self.mascarar)
                dados[chave] = valor
        if self.mascarar and dados.get("cpf"):
            dados["cpf"] = mascarar_cpf(str(dados["cpf"]))

        linha_txt = "%s  %-7s %s" % (agora.strftime("%d/%m/%Y %H:%M:%S"), nivel, mensagem)
        alvo = dados.get("cliente") or dados.get("pasta")
        if alvo and nivel != "INFO":
            linha_txt += "   [%s]" % alvo

        try:
            with open(str(self.arquivo_texto), "a", encoding="utf-8") as fh:
                fh.write(linha_txt + "\n")
            with open(str(self.arquivo_json), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(dados, ensure_ascii=False) + "\n")
        except OSError as erro:                       # disco cheio, permissão…
            print("[log indisponível: %s]" % erro, file=sys.stderr)

        cor = {"ERRO": "\033[31m", "ALERTA": "\033[33m", "OK": "\033[32m"}.get(nivel, "")
        fim = "\033[0m" if cor else ""
        print(cor + linha_txt + fim)

    def info(self, mensagem, **extra):
        self._escrever("INFO", mensagem, extra)

    def ok(self, mensagem, **extra):
        self._escrever("OK", mensagem, extra)

    def alerta(self, mensagem, **extra):
        self._escrever("ALERTA", mensagem, extra)

    def erro(self, mensagem, **extra):
        self._escrever("ERRO", mensagem, extra)

    def titulo(self, texto: str):
        print("\n" + "─" * 72)
        print(texto)
        print("─" * 72)
        self._escrever("INFO", "== %s ==" % texto)

    # -- registro formal exigido pelo item 11 do projeto -----------------

    def registrar_resultado(self, pasta, cliente, cpf, acao, resultado,
                            astrea_id=None, erro=None, **extra):
        """DATA/HORA, PASTA, CLIENTE, CPF, AÇÃO, RESULTADO, ID ASTREA, ERRO."""
        dados = {"pasta": pasta, "cliente": cliente, "cpf": cpf, "acao": acao,
                 "resultado": resultado, "astrea_id": astrea_id, "erro": erro}
        dados.update(extra)
        nivel = "ERRO" if erro else ("OK" if "SUCESSO" in (resultado or "") else "INFO")
        self._escrever(nivel, "%s → %s" % (acao, resultado), dados)

    # -- manutenção ------------------------------------------------------

    def limpar_antigos(self, dias: int):
        """Remove logs além do prazo de retenção (minimização de dados, LGPD)."""
        if dias <= 0:
            return
        limite = time.time() - dias * 86400
        for arquivo in list(self.pasta.glob("execucao-*.log")) + \
                       list(self.pasta.glob("eventos-*.jsonl")):
            try:
                if arquivo.stat().st_mtime < limite:
                    arquivo.unlink()
            except OSError:
                pass

    def eventos_do_dia(self, dia: datetime = None):
        """Lê de volta os eventos JSON de um dia (usado pelo relatório)."""
        dia = dia or datetime.now()
        arquivo = self.pasta / ("eventos-%s.jsonl" % dia.strftime("%Y-%m-%d"))
        if not arquivo.exists():
            return []
        eventos = []
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            try:
                eventos.append(json.loads(linha))
            except ValueError:
                continue
        return eventos


def data_hora_br(quando: datetime = None) -> str:
    return (quando or datetime.now()).strftime("%d/%m/%Y %H:%M:%S")


def ontem() -> datetime:
    return datetime.now() - timedelta(days=1)
