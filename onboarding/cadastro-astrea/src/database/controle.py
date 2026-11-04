#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Controle de processamento (SQLite).

É o que impede a mesma pasta de ser cadastrada duas vezes. A chave é o
**ID único da pasta no Google Drive** (atributo com.google.drivefs.item-id),
não o nome — renomear "15 - FULANO" para "15 - OK - FULANO" não faz o cliente
ser processado de novo.

Banco em ~/.cadastro-astrea/controle.sqlite3, fora do Drive: banco SQLite
sincronizado por serviço de nuvem corrompe.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# --- Status finais (item 10 do projeto) ------------------------------------
CADASTRADO = "CADASTRADO COM SUCESSO"
JA_CADASTRADO = "JÁ CADASTRADO NO ASTREA"
PENDENTE = "PENDENTE DE INFORMAÇÃO"
DIVERGENTE = "DADOS DIVERGENTES"
ERRO = "ERRO NO CADASTRO"
# Cadastro enviado que o Astrea ainda não devolveu na busca. NÃO é erro e NÃO é
# definitivo: a rodada seguinte confere pelo CPF antes de tentar qualquer coisa.
A_CONFIRMAR = "CADASTRO A CONFIRMAR"

# --- Status internos (não são resultado final) ------------------------------
AGUARDANDO = "AGUARDANDO ESTABILIDADE"     # pasta ainda recebendo arquivos
EM_PROCESSAMENTO = "EM PROCESSAMENTO"      # travado; se ficar preso, é queda
HISTORICO = "IGNORADO (HISTÓRICO)"         # já existia quando a automação subiu
SIMULADO = "SIMULADO (MODO TESTE)"         # TEST_MODE: seria cadastrado
PARCEIRO = "FORA DA AUTOMAÇÃO (PARCEIRO)"  # assunto do escritório parceiro

# Status que permitem nova tentativa numa próxima rodada.
REPROCESSAVEIS = (AGUARDANDO, EM_PROCESSAMENTO, ERRO, PENDENTE, DIVERGENTE, SIMULADO)
# Status definitivos: nunca mais toca.
DEFINITIVOS = (CADASTRADO, JA_CADASTRADO, HISTORICO, PARCEIRO)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS processamentos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_item_id       TEXT    NOT NULL UNIQUE,
    caminho             TEXT    NOT NULL,
    nome_pasta          TEXT    NOT NULL,
    mes_pasta           TEXT,
    nome_cliente        TEXT,
    cpf_cnpj            TEXT,
    status              TEXT    NOT NULL,
    detalhe             TEXT,
    astrea_contato_id   TEXT,
    astrea_caso_id      TEXT,
    status_caso         TEXT,
    confianca           REAL,
    dados_json          TEXT,
    modo                TEXT,
    tentativas          INTEGER NOT NULL DEFAULT 0,
    erro                TEXT,
    visto_em            TEXT    NOT NULL,
    processado_em       TEXT,
    atualizado_em       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_proc_status ON processamentos(status);
CREATE INDEX IF NOT EXISTS ix_proc_cpf    ON processamentos(cpf_cnpj);

CREATE TABLE IF NOT EXISTS execucoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    execucao_id   TEXT NOT NULL,
    modo          TEXT NOT NULL,
    test_mode     INTEGER NOT NULL,
    iniciada_em   TEXT NOT NULL,
    terminada_em  TEXT,
    total         INTEGER DEFAULT 0,
    cadastrados   INTEGER DEFAULT 0,
    ja_existiam   INTEGER DEFAULT 0,
    pendentes     INTEGER DEFAULT 0,
    divergentes   INTEGER DEFAULT 0,
    erros         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS marcos (
    chave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);
"""


class Controle(object):
    def __init__(self, caminho_banco: Path):
        self.caminho = Path(caminho_banco)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.caminho), timeout=30.0,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(ESQUEMA)
        try:
            os.chmod(str(self.caminho), 0o600)
        except OSError:
            pass

    def fechar(self):
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    @contextmanager
    def transacao(self):
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # -- consultas -------------------------------------------------------

    def buscar(self, drive_item_id: str):
        cur = self._conn.execute(
            "SELECT * FROM processamentos WHERE drive_item_id = ?", (drive_item_id,))
        return cur.fetchone()

    def buscar_por_cpf(self, cpf: str):
        if not cpf:
            return []
        cur = self._conn.execute(
            "SELECT * FROM processamentos WHERE cpf_cnpj = ? ORDER BY id", (cpf,))
        return cur.fetchall()

    def ja_finalizado(self, drive_item_id: str) -> bool:
        linha = self.buscar(drive_item_id)
        return bool(linha) and linha["status"] in DEFINITIVOS

    def listar(self, status=None, limite: int = 500):
        if status:
            marcas = ",".join("?" * len(status))
            cur = self._conn.execute(
                "SELECT * FROM processamentos WHERE status IN (%s) "
                "ORDER BY atualizado_em DESC LIMIT ?" % marcas,
                tuple(status) + (limite,))
        else:
            cur = self._conn.execute(
                "SELECT * FROM processamentos ORDER BY atualizado_em DESC LIMIT ?",
                (limite,))
        return cur.fetchall()

    def contagem_por_status(self):
        cur = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM processamentos GROUP BY status "
            "ORDER BY n DESC")
        return [(l["status"], l["n"]) for l in cur.fetchall()]

    # -- escrita ---------------------------------------------------------

    def registrar_visto(self, drive_item_id, caminho, nome_pasta, mes_pasta,
                        status, modo="novos", detalhe=""):
        """Primeiro contato com a pasta. Não sobrescreve resultado definitivo."""
        agora = datetime.now().isoformat(timespec="seconds")
        with self.transacao() as conn:
            existente = conn.execute(
                "SELECT id, status FROM processamentos WHERE drive_item_id = ?",
                (drive_item_id,)).fetchone()
            if existente is None:
                conn.execute(
                    "INSERT INTO processamentos (drive_item_id, caminho, nome_pasta,"
                    " mes_pasta, status, detalhe, modo, visto_em, atualizado_em)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (drive_item_id, str(caminho), nome_pasta, mes_pasta, status,
                     detalhe, modo, agora, agora))
                return "novo"
            if existente["status"] in DEFINITIVOS:
                return "definitivo"
            conn.execute(
                "UPDATE processamentos SET caminho=?, nome_pasta=?, mes_pasta=?,"
                " atualizado_em=? WHERE drive_item_id=?",
                (str(caminho), nome_pasta, mes_pasta, agora, drive_item_id))
            return "conhecido"

    def reabrir(self, drive_item_id: str, motivo: str) -> bool:
        """
        Devolve à fila uma pasta que estava com resultado definitivo.

        Só o modo importação (e o reprocessamento forçado) usam isto, e ambos
        exigem confirmação de quem chama — é a válvula que impede a automação
        de reabrir cadastro sozinha.
        """
        agora = datetime.now().isoformat(timespec="seconds")
        with self.transacao() as conn:
            cur = conn.execute(
                "UPDATE processamentos SET status=?, detalhe=?, atualizado_em=?"
                " WHERE drive_item_id=?",
                (AGUARDANDO, motivo, agora, drive_item_id))
            return bool(cur.rowcount)

    def marcar_em_processamento(self, drive_item_id: str) -> bool:
        """
        Reserva a pasta para esta execução. Devolve False se outra execução
        já pegou — é assim que duas rodadas simultâneas não colidem.
        """
        agora = datetime.now().isoformat(timespec="seconds")
        with self.transacao() as conn:
            linha = conn.execute(
                "SELECT status FROM processamentos WHERE drive_item_id=?",
                (drive_item_id,)).fetchone()
            if linha is None:
                return False
            if linha["status"] == EM_PROCESSAMENTO:
                return False
            if linha["status"] in DEFINITIVOS:
                return False
            conn.execute(
                "UPDATE processamentos SET status=?, tentativas=tentativas+1,"
                " atualizado_em=? WHERE drive_item_id=?",
                (EM_PROCESSAMENTO, agora, drive_item_id))
        return True

    def concluir(self, drive_item_id, status, nome_cliente=None, cpf=None,
                 detalhe="", astrea_contato_id=None, astrea_caso_id=None,
                 status_caso=None, confianca=None, dados=None, erro=None):
        agora = datetime.now().isoformat(timespec="seconds")
        with self.transacao() as conn:
            conn.execute(
                "UPDATE processamentos SET status=?, nome_cliente=?, cpf_cnpj=?,"
                " detalhe=?, astrea_contato_id=?, astrea_caso_id=?, status_caso=?,"
                " confianca=?, dados_json=?, erro=?, processado_em=?, atualizado_em=?"
                " WHERE drive_item_id=?",
                (status, nome_cliente, cpf, detalhe, astrea_contato_id,
                 astrea_caso_id, status_caso, confianca,
                 json.dumps(dados, ensure_ascii=False) if dados else None,
                 erro, agora, agora, drive_item_id))

    def atualizar_status_caso(self, drive_item_id: str, status_caso: str,
                              astrea_caso_id: str = None):
        """
        Atualiza só o status do caso (e o id do caso, se veio), sem tocar em
        mais nada do registro. `concluir()` não serve aqui: ela regrava nome,
        CPF e os demais campos com o que for passado (ou None, apagando o que
        já estava lá) — usá-la para só anotar o caso apagaria dado do cliente.
        """
        agora = datetime.now().isoformat(timespec="seconds")
        with self.transacao() as conn:
            if astrea_caso_id:
                conn.execute(
                    "UPDATE processamentos SET status_caso=?, astrea_caso_id=?,"
                    " atualizado_em=? WHERE drive_item_id=?",
                    (status_caso, astrea_caso_id, agora, drive_item_id))
            else:
                conn.execute(
                    "UPDATE processamentos SET status_caso=?, atualizado_em=?"
                    " WHERE drive_item_id=?",
                    (status_caso, agora, drive_item_id))

    def destravar_presos(self, log=None) -> int:
        """
        Recuperação de queda: se a automação morreu no meio, sobrou pasta em
        EM PROCESSAMENTO. Na próxima execução elas voltam à fila.
        """
        agora = datetime.now().isoformat(timespec="seconds")
        with self.transacao() as conn:
            cur = conn.execute(
                "UPDATE processamentos SET status=?, detalhe=?, atualizado_em=?"
                " WHERE status=?",
                (ERRO, "Execução anterior foi interrompida antes de concluir "
                       "este cliente. Recolocado na fila.", agora, EM_PROCESSAMENTO))
            n = cur.rowcount or 0
        if n and log:
            log.alerta("%d cliente(s) tinham ficado presos de uma execução "
                       "interrompida e voltaram para a fila." % n)
        return n

    # -- marcos (linha de corte do MODO NOVOS) ---------------------------

    def marco(self, chave: str, padrao=None):
        cur = self._conn.execute("SELECT valor FROM marcos WHERE chave=?", (chave,))
        linha = cur.fetchone()
        return linha["valor"] if linha else padrao

    def definir_marco(self, chave: str, valor: str):
        with self.transacao() as conn:
            conn.execute("INSERT INTO marcos (chave, valor) VALUES (?,?) "
                         "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                         (chave, valor))

    def automacao_ativada(self) -> bool:
        return self.marco("ativada_em") is not None

    def ativar(self, quando: str = None) -> str:
        quando = quando or datetime.now().isoformat(timespec="seconds")
        self.definir_marco("ativada_em", quando)
        return quando

    # -- execuções -------------------------------------------------------

    def abrir_execucao(self, execucao_id: str, modo: str, test_mode: bool) -> int:
        with self.transacao() as conn:
            cur = conn.execute(
                "INSERT INTO execucoes (execucao_id, modo, test_mode, iniciada_em)"
                " VALUES (?,?,?,?)",
                (execucao_id, modo, 1 if test_mode else 0,
                 datetime.now().isoformat(timespec="seconds")))
            return cur.lastrowid

    def fechar_execucao(self, rowid: int, contagens: dict):
        with self.transacao() as conn:
            conn.execute(
                "UPDATE execucoes SET terminada_em=?, total=?, cadastrados=?,"
                " ja_existiam=?, pendentes=?, divergentes=?, erros=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"),
                 contagens.get("total", 0), contagens.get("cadastrados", 0),
                 contagens.get("ja_existiam", 0), contagens.get("pendentes", 0),
                 contagens.get("divergentes", 0), contagens.get("erros", 0), rowid))


# ---------------------------------------------------------------------------
# Trava de execução única (impede duas rodadas ao mesmo tempo)
# ---------------------------------------------------------------------------

class TravaDeExecucao(object):
    """
    Trava por arquivo. A automação roda pelo agendador de tempos em tempos;
    se uma rodada demorar mais que o intervalo, a seguinte simplesmente desiste
    em vez de processar as mesmas pastas em paralelo.
    """

    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self._fh = None

    def __enter__(self):
        import fcntl
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(str(self.caminho), "w")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            self._fh.close()
            self._fh = None
            raise ExecucaoJaEmAndamento(
                "Já existe uma execução em andamento (trava: %s)." % self.caminho)
        self._fh.write("%d\n%s\n" % (os.getpid(), datetime.now().isoformat()))
        self._fh.flush()
        return self

    def __exit__(self, *_):
        import fcntl
        if self._fh:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None


class ExecucaoJaEmAndamento(RuntimeError):
    pass
