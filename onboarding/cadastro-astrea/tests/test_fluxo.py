#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes de ponta a ponta do fluxo, com pastas de mentira e Astrea de mentira.

Cobrem os cenários pedidos no projeto:
  cliente novo · cliente já existente · CPF inválido · CPF ausente ·
  documentos incompletos · documento ilegível · erro do Astrea · erro do Drive ·
  duas pastas processadas ao mesmo tempo · reinicialização · duplicidade.

Nada aqui toca no Astrea real, no Google Drive real nem no banco real: a
configuração é redirecionada para uma pasta temporária.
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.astrea.base import (AdaptadorAstrea, BuscaIndisponivel, ErroAstrea,  # noqa: E402
                             ResultadoBusca, ResultadoCadastro)
from src.config import settings                                    # noqa: E402
from src.database import controle as St                            # noqa: E402
from src.database.controle import Controle, ExecucaoJaEmAndamento, TravaDeExecucao  # noqa: E402
from src.extractors import contrato_ho, documentos as D            # noqa: E402
from src.drive import scanner                                      # noqa: E402
from src.services import orquestrador                              # noqa: E402
from tests.test_extrator import (COMPLETO, CPF_INVALIDO, OUTRO_CLIENTE,  # noqa: E402
                                 SEM_CPF, texto)


# ---------------------------------------------------------------------------
# Astrea de mentira
# ---------------------------------------------------------------------------

class AstreaFalso(AdaptadorAstrea):
    nome = "falso"
    escreve_no_astrea = True
    verifica_duplicidade = True

    def __init__(self, config, log, existentes=None, falhar_busca=False,
                 falhar_cadastro=False, homonimos=(), grava_sem_confirmar=False):
        AdaptadorAstrea.__init__(self, config, log)
        self.existentes = dict(existentes or {})      # cpf -> id
        self.falhar_busca = falhar_busca
        self.falhar_cadastro = falhar_cadastro
        # Imita o Astrea de verdade quando ele grava e demora a indexar: o
        # contato passa a existir, mas a busca do próprio cadastro não o acha.
        self.grava_sem_confirmar = grava_sem_confirmar
        self.homonimos = set(homonimos)               # nomes já no Astrea sem CPF
        self.cadastrados = []
        self.casos = []
        self.buscas = []

    def buscar_por_documento(self, documento, nome_cliente=""):
        self.buscas.append(documento)
        if self.falhar_busca:
            raise BuscaIndisponivel("Astrea fora do ar (simulado)")
        if documento in self.existentes:
            return ResultadoBusca(True, self.existentes[documento], "Fulano")
        resultado = ResultadoBusca(False)
        if nome_cliente and nome_cliente in self.homonimos:
            resultado.suspeitas.append(
                "Existe contato com nome parecido no Astrea (%s), mas sem este "
                "CPF." % nome_cliente)
        return resultado

    def cadastrar_contato(self, ficha):
        if self.falhar_cadastro:
            return ResultadoCadastro(sucesso=False, erro="Astrea recusou (simulado)")
        if self.grava_sem_confirmar:
            novo_id = "AST%03d" % (len(self.cadastrados) + 1)
            self.cadastrados.append(ficha.cpf)
            self.existentes[ficha.cpf] = novo_id      # gravou de verdade
            return ResultadoCadastro(sucesso=False, a_confirmar=True,
                                     astrea_id=novo_id,
                                     detalhe="gravado, busca ainda não devolveu")
        novo_id = "AST%03d" % (len(self.cadastrados) + 1)
        self.cadastrados.append(ficha.cpf)
        self.existentes[ficha.cpf] = novo_id
        return ResultadoCadastro(True, novo_id, "cadastrado (simulado)")

    def criar_caso(self, ficha, contato_id):
        self.casos.append(contato_id)
        return ResultadoCadastro(True, "CASO%03d" % len(self.casos), "caso criado")


class LogMudo(object):
    def __init__(self):
        self.linhas = []

    def _guardar(self, nivel, mensagem):
        self.linhas.append((nivel, str(mensagem)))

    def info(self, m, **k):
        self._guardar("INFO", m)

    def ok(self, m, **k):
        self._guardar("OK", m)

    def alerta(self, m, **k):
        self._guardar("ALERTA", m)

    def erro(self, m, **k):
        self._guardar("ERRO", m)

    def titulo(self, m):
        self._guardar("INFO", m)

    def contexto(self, **k):
        pass

    def limpar_contexto(self):
        pass

    def registrar_resultado(self, *a, **k):
        pass

    def tem(self, trecho):
        return any(trecho.lower() in m.lower() for _, m in self.linhas)


# ---------------------------------------------------------------------------

MES_CORRENTE = "%s %d" % (scanner.NOMES_DO_MES[datetime.now().month - 1],
                          datetime.now().year)


class BaseFluxo(unittest.TestCase):

    # Cada cliente de teste: nome da pasta -> texto do contrato (ou None)
    CONTRATOS = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cadastro-astrea-teste-"))
        self.clientes = self.tmp / "PREPARAÇÃO PARA INGRESSO"
        (self.clientes / MES_CORRENTE).mkdir(parents=True)

        os.environ["PASTA_CLIENTES"] = str(self.clientes)
        os.environ["PASTA_DADOS"] = str(self.tmp / "dados")
        os.environ["PASTA_RELATORIOS"] = str(self.tmp / "relatorios")
        os.environ["TEST_MODE"] = "false"
        os.environ["MINUTOS_ESTABILIDADE"] = "0"
        os.environ["ASTREA_ADAPTADOR"] = "dry-run"
        os.environ.pop("ASTREA_CRIAR_CASO", None)
        self.config = settings.get_config(recarregar=True)
        self.config.preparar_pastas()

        self.textos = {}
        self._original_texto = contrato_ho.texto_do_pdf
        self._original_ler = D._ler_texto
        # A fábrica de adaptadores é trocada por um Astrea de mentira; sem
        # devolver a original no fim, os testes seguintes herdariam o dublê.
        self._original_fabrica = orquestrador._criar_adaptador
        contrato_ho.texto_do_pdf = self._texto_falso
        D._ler_texto = self._ler_falso
        self.log = LogMudo()

    def tearDown(self):
        contrato_ho.texto_do_pdf = self._original_texto
        D._ler_texto = self._original_ler
        orquestrador._criar_adaptador = self._original_fabrica
        for chave in ("PASTA_CLIENTES", "PASTA_DADOS", "PASTA_RELATORIOS",
                      "TEST_MODE", "MINUTOS_ESTABILIDADE", "ASTREA_ADAPTADOR",
                      "ASTREA_CRIAR_CASO"):
            os.environ.pop(chave, None)
        settings.get_config(recarregar=True)
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    # -- montagem das pastas ---------------------------------------------

    # Trava de documentação (25/09/2026): sem estes, nada é cadastrado. Ficam
    # em todo cliente de teste para os cenários antigos continuarem testando
    # o que testavam; a trava em si é coberta por `test_documentacao.py` e
    # por `TestTravaDeDocumentacao`, abaixo.
    DOCUMENTOS_DO_CLIENTE = ("CNH.pdf", "COMPROVANTE DE RESIDÊNCIA.pdf", "CRLV.pdf")

    def criar_cliente(self, nome, texto_contrato=COMPLETO, com_contrato=True,
                      extras=(), com_documentos=True):
        # O mês NÃO pode ser fixo: com MESES=atual no .env, a virada do mês
        # deixaria de varrer a pasta e a suíte inteira quebraria sozinha na
        # madrugada do dia 1º — foi o que houve em 01/09/2026, quando 22 testes
        # falharam de um dia para o outro sem ninguém ter tocado no código.
        pasta = self.clientes / MES_CORRENTE / nome
        (pasta / "CONTRATO HO").mkdir(parents=True)
        (pasta / "DOC CLIENTE").mkdir(parents=True)
        if com_contrato:
            arquivo = pasta / "CONTRATO HO" / "Contrato HO Assinado.pdf"
            arquivo.write_bytes(b"%PDF-1.4 fake")
            if texto_contrato is not None:
                self.textos[str(arquivo)] = texto(texto_contrato)
        documentos = self.DOCUMENTOS_DO_CLIENTE if com_documentos else ()
        for extra in tuple(documentos) + tuple(extras):
            caminho = pasta / "DOC CLIENTE" / extra
            caminho.write_bytes(b"\x89PNG fake" if not extra.endswith(".pdf")
                                else b"%PDF-1.4 fake")
        return pasta

    def _texto_falso(self, caminho, paginas=3):
        chave = str(caminho)
        if chave not in self.textos:
            raise IOError("PDF ilegível (simulado): %s" % Path(caminho).name)
        return self.textos[chave]

    def _ler_falso(self, documento):
        chave = str(documento.caminho)
        if documento.extensao == ".pdf" and chave in self.textos:
            documento.texto = self.textos[chave]
            documento.legivel = True
        elif documento.extensao == ".pdf":
            documento.motivo_ilegivel = "PDF sem camada de texto (simulado)"
        else:
            documento.motivo_ilegivel = "arquivo de imagem (simulado)"

    # -- execução ---------------------------------------------------------

    def rodar(self, adaptador, modo=orquestrador.MODO_NOVOS):
        orquestrador._criar_adaptador = lambda c, l: adaptador
        return orquestrador.executar(self.config, self.log, modo=modo)

    def registro(self, nome_pasta):
        with Controle(self.config.banco) as banco:
            for linha in banco.listar():
                if linha["nome_pasta"] == nome_pasta:
                    return linha
        return None


# ---------------------------------------------------------------------------

class TestAtivacaoEHistorico(BaseFluxo):

    def test_primeira_execucao_nao_cadastra_pastas_antigas(self):
        self.criar_cliente("01 - FULANO DE TAL")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        self.assertEqual(astrea.cadastrados, [],
                         "a ativação não pode cadastrar quem já estava na pasta")
        self.assertEqual(self.registro("01 - FULANO DE TAL")["status"], St.HISTORICO)

    def test_apos_ativacao_cliente_novo_e_cadastrado(self):
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)                              # ativação, pasta vazia
        self.criar_cliente("02 - CLIENTE NOVO")
        self.rodar(astrea)
        self.assertEqual(len(astrea.cadastrados), 1)
        self.assertEqual(self.registro("02 - CLIENTE NOVO")["status"], St.CADASTRADO)

    def test_modo_importacao_traz_as_antigas(self):
        self.criar_cliente("03 - ANTIGO")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)                              # vira histórico
        self.assertEqual(astrea.cadastrados, [])
        self.rodar(astrea, modo=orquestrador.MODO_IMPORTACAO)
        self.assertEqual(len(astrea.cadastrados), 1)


class TestCadastro(BaseFluxo):

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))   # ativa a automação

    def test_cliente_novo(self):
        self.criar_cliente("10 - NOVO")
        astrea = AstreaFalso(self.config, self.log)
        resumo = self.rodar(astrea)
        registro = self.registro("10 - NOVO")
        self.assertEqual(registro["status"], St.CADASTRADO)
        self.assertEqual(registro["astrea_contato_id"], "AST001")
        self.assertEqual(registro["nome_cliente"], "ANDERSON LOPES DA SILVA")
        self.assertEqual(resumo.cadastrados, 1)

    def test_escopo_atual_nao_cria_caso_mas_guarda_o_que_abrir(self):
        """Só o contato é cadastrado; o caso fica anotado para abertura à mão."""
        self.criar_cliente("10b - SEM CASO")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("10b - SEM CASO")
        self.assertEqual(registro["status"], St.CADASTRADO)
        self.assertEqual(astrea.casos, [], "o caso não deve ser criado por ora")
        self.assertIn("Ação Revisional", registro["status_caso"] or "")
        self.assertIn("Banco Santander", registro["status_caso"] or "")

    def test_caso_e_criado_quando_ligado(self):
        os.environ["ASTREA_CRIAR_CASO"] = "true"
        self.config = settings.get_config(recarregar=True)
        self.criar_cliente("10c - COM CASO")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        self.assertEqual(astrea.casos, ["AST001"])
        self.assertEqual(self.registro("10c - COM CASO")["status_caso"],
                         "CASO CRIADO")

    def test_cliente_ja_existente_nao_duplica(self):
        self.criar_cliente("11 - JA EXISTE")
        astrea = AstreaFalso(self.config, self.log,
                             existentes={"529.982.247-25": "AST999"})
        self.rodar(astrea)
        registro = self.registro("11 - JA EXISTE")
        self.assertEqual(registro["status"], St.JA_CADASTRADO)
        self.assertEqual(registro["astrea_contato_id"], "AST999")
        self.assertEqual(astrea.cadastrados, [], "não pode criar segundo cadastro")

    def test_cpf_invalido_vira_pendencia(self):
        self.criar_cliente("12 - CPF INVALIDO", texto_contrato=CPF_INVALIDO)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("12 - CPF INVALIDO")
        self.assertEqual(registro["status"], St.PENDENTE)
        self.assertIn("dígito verificador", registro["detalhe"])
        self.assertEqual(astrea.cadastrados, [])

    def test_cpf_ausente_vira_pendencia_dizendo_o_que_falta(self):
        self.criar_cliente("13 - SEM CPF", texto_contrato=SEM_CPF)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("13 - SEM CPF")
        self.assertEqual(registro["status"], St.PENDENTE)
        self.assertIn("CPF", registro["detalhe"])
        self.assertEqual(astrea.cadastrados, [])

    def test_pasta_sem_documentos(self):
        pasta = self.clientes / MES_CORRENTE / "14 - PASTA VAZIA"
        pasta.mkdir(parents=True)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("14 - PASTA VAZIA")
        self.assertEqual(registro["status"], St.PENDENTE)
        self.assertIn("sem documento", registro["detalhe"].lower())

    def test_contrato_ilegivel_nao_e_adivinhado(self):
        self.criar_cliente("15 - ILEGIVEL", texto_contrato=None)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("15 - ILEGIVEL")
        self.assertEqual(registro["status"], St.PENDENTE)
        self.assertEqual(astrea.cadastrados, [])

    def test_documento_ilegivel_e_registrado_mas_nao_impede(self):
        self.criar_cliente("16 - COM FOTO", extras=("RG.jpg", "CNH.pdf"))
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("16 - COM FOTO")
        self.assertEqual(registro["status"], St.CADASTRADO)
        self.assertTrue(self.log.tem("DOCUMENTO NÃO INTERPRETADO"))

    def test_homonimo_sem_cpf_vai_para_conferencia(self):
        """
        Alguém com o mesmo nome já no Astrea, mas sem o CPF preenchido.

        Pode ser a mesma pessoa cadastrada pela metade. Cadastrar seria
        arriscar duplicidade, então quem decide é gente.
        """
        self.criar_cliente("19 - HOMONIMO")
        astrea = AstreaFalso(self.config, self.log,
                             homonimos={"ANDERSON LOPES DA SILVA"})
        self.rodar(astrea)
        registro = self.registro("19 - HOMONIMO")
        self.assertEqual(registro["status"], St.DIVERGENTE)
        self.assertIn("nome parecido", registro["detalhe"])
        self.assertEqual(astrea.cadastrados, [])

    def test_sessao_caida_interrompe_a_rodada_sem_culpar_clientes(self):
        """
        Se a sessão do Astrea cai no meio, os clientes que faltam não podem
        virar uma fila de erros: a rodada para e eles voltam para a fila.
        """
        from src.astrea.base import ErroSessaoPerdida

        class AstreaQueCai(AstreaFalso):
            def buscar_por_documento(self, documento, nome_cliente=""):
                self.buscas.append(documento)
                if len(self.buscas) > 1:
                    raise ErroSessaoPerdida("sessão caiu (simulado)")
                return ResultadoBusca(False)

        for nome, contrato in (("40 - CLIENTE A", COMPLETO),
                               ("41 - CLIENTE B", OUTRO_CLIENTE),
                               ("42 - CLIENTE C", OUTRO_CLIENTE)):
            self.criar_cliente(nome, texto_contrato=contrato)

        astrea = AstreaQueCai(self.config, self.log)
        self.rodar(astrea)

        self.assertEqual(len(astrea.cadastrados), 1, "só o primeiro é cadastrado")
        self.assertEqual(self.registro("41 - CLIENTE B")["status"], St.AGUARDANDO)
        self.assertEqual(self.registro("42 - CLIENTE C")["status"], St.AGUARDANDO)
        self.assertTrue(self.log.tem("RODADA INTERROMPIDA"))

        # E na rodada seguinte, com a sessão de volta, eles são processados.
        astrea2 = AstreaFalso(self.config, self.log)
        self.rodar(astrea2)
        self.assertEqual(self.registro("41 - CLIENTE B")["status"], St.CADASTRADO)

    def test_erro_do_astrea_no_cadastro(self):
        self.criar_cliente("17 - ERRO ASTREA")
        astrea = AstreaFalso(self.config, self.log, falhar_cadastro=True)
        self.rodar(astrea)
        registro = self.registro("17 - ERRO ASTREA")
        self.assertEqual(registro["status"], St.ERRO)
        self.assertIn("recusou", registro["erro"])

    def test_sem_consulta_de_duplicidade_nao_cadastra(self):
        self.criar_cliente("18 - ASTREA FORA")
        astrea = AstreaFalso(self.config, self.log, falhar_busca=True)
        self.rodar(astrea)
        registro = self.registro("18 - ASTREA FORA")
        self.assertEqual(registro["status"], St.ERRO)
        self.assertEqual(astrea.cadastrados, [],
                         "sem poder conferir duplicidade, não pode cadastrar")

    def test_um_erro_nao_derruba_os_outros_clientes(self):
        self.criar_cliente("20 - CLIENTE A")
        self.criar_cliente("21 - CLIENTE B", texto_contrato=None)     # ilegível
        self.criar_cliente("22 - CLIENTE C", texto_contrato=OUTRO_CLIENTE)
        astrea = AstreaFalso(self.config, self.log)
        resumo = self.rodar(astrea)
        self.assertEqual(self.registro("20 - CLIENTE A")["status"], St.CADASTRADO)
        self.assertEqual(self.registro("21 - CLIENTE B")["status"], St.PENDENTE)
        self.assertEqual(self.registro("22 - CLIENTE C")["status"], St.CADASTRADO)
        self.assertEqual(resumo.cadastrados, 2)

    def test_nao_reprocessa_cliente_ja_cadastrado(self):
        self.criar_cliente("23 - UMA VEZ SO")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        self.rodar(astrea)
        self.rodar(astrea)
        self.assertEqual(len(astrea.cadastrados), 1,
                         "a mesma pasta não pode ser cadastrada de novo")

    def test_renomear_a_pasta_nao_faz_recadastrar(self):
        pasta = self.criar_cliente("24 - FULANO")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        novo = pasta.parent / "24 - OK - FULANO"
        # O texto do contrato acompanha o arquivo renomeado.
        antigo_arquivo = str(pasta / "CONTRATO HO" / "Contrato HO Assinado.pdf")
        pasta.rename(novo)
        self.textos[str(novo / "CONTRATO HO" / "Contrato HO Assinado.pdf")] = \
            self.textos.pop(antigo_arquivo)
        self.rodar(astrea)
        self.assertEqual(len(astrea.cadastrados), 1,
                         "o controle é pelo ID da pasta, não pelo nome")

    def test_modo_teste_nao_cadastra(self):
        self.criar_cliente("25 - EM TESTE")
        os.environ["TEST_MODE"] = "true"
        self.config = settings.get_config(recarregar=True)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("25 - EM TESTE")
        self.assertEqual(registro["status"], St.SIMULADO)


class TestConcorrenciaEQueda(BaseFluxo):

    def test_duas_execucoes_ao_mesmo_tempo(self):
        trava = TravaDeExecucao(self.config.pasta_dados / "execucao.lock")
        trava.__enter__()
        try:
            self.criar_cliente("30 - CONCORRENTE")
            astrea = AstreaFalso(self.config, self.log)
            self.rodar(astrea)
            self.assertEqual(astrea.cadastrados, [])
            self.assertTrue(self.log.tem("em andamento"))
        finally:
            trava.__exit__(None, None, None)

    def test_reinicializacao_destrava_pasta_presa(self):
        """Simula a automação morrendo no meio de um cliente."""
        with Controle(self.config.banco) as banco:
            banco.ativar()
            banco.registrar_visto("id-preso", "/tmp/preso", "31 - PRESO",
                                  "AGOSTO 2026", St.AGUARDANDO)
            self.assertTrue(banco.marcar_em_processamento("id-preso"))
            self.assertEqual(banco.buscar("id-preso")["status"], St.EM_PROCESSAMENTO)

        # Nova execução: a pasta presa volta para a fila em vez de ficar travada.
        with Controle(self.config.banco) as banco:
            self.assertEqual(banco.destravar_presos(), 1)
            self.assertEqual(banco.buscar("id-preso")["status"], St.ERRO)
            self.assertTrue(banco.marcar_em_processamento("id-preso"))

    def test_pasta_reservada_por_outra_execucao_e_pulada(self):
        with Controle(self.config.banco) as banco:
            banco.ativar()
            banco.registrar_visto("id-x", "/tmp/x", "X", "AGOSTO 2026",
                                  St.AGUARDANDO)
            self.assertTrue(banco.marcar_em_processamento("id-x"))
            self.assertFalse(banco.marcar_em_processamento("id-x"),
                             "a segunda execução não pode pegar a mesma pasta")


class TestControleBanco(BaseFluxo):

    def test_nao_sobrescreve_resultado_definitivo(self):
        with Controle(self.config.banco) as banco:
            banco.registrar_visto("id-1", "/tmp/a", "A", "AGOSTO 2026", St.AGUARDANDO)
            banco.concluir("id-1", St.CADASTRADO, "Fulano", "529.982.247-25",
                           astrea_contato_id="AST1")
            self.assertEqual(banco.registrar_visto("id-1", "/tmp/a", "A",
                                                   "AGOSTO 2026", St.AGUARDANDO),
                             "definitivo")
            self.assertTrue(banco.ja_finalizado("id-1"))
            self.assertFalse(banco.marcar_em_processamento("id-1"))

    def test_trava_de_execucao_impede_duas_ao_mesmo_tempo(self):
        caminho = self.config.pasta_dados / "teste.lock"
        primeira = TravaDeExecucao(caminho)
        primeira.__enter__()
        try:
            with self.assertRaises(ExecucaoJaEmAndamento):
                TravaDeExecucao(caminho).__enter__()
        finally:
            primeira.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCadastroAConfirmar(BaseFluxo):
    """
    Cadastro gravado que o Astrea ainda não devolve na busca.

    O caso real: em 08/09/2026 o Wladson ficou com DOIS contatos. O primeiro
    cadastro gravou e a conferência, feita segundos depois, não achou — a
    automação chamou de erro, e a tentativa seguinte cadastrou de novo. O certo
    é anotar "a confirmar" e deixar a rodada seguinte conferir.
    """

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))    # ativa a automação

    def test_gravado_sem_confirmacao_nao_vira_erro(self):
        self.criar_cliente("30 - A CONFIRMAR")
        astrea = AstreaFalso(self.config, self.log, grava_sem_confirmar=True)
        resumo = self.rodar(astrea)
        registro = self.registro("30 - A CONFIRMAR")
        self.assertEqual(registro["status"], St.A_CONFIRMAR)
        self.assertEqual(registro["astrea_contato_id"], "AST001")
        self.assertEqual(resumo.erros, 0, "não é erro: o contato foi gravado")

    def test_a_rodada_seguinte_confirma_em_vez_de_cadastrar_de_novo(self):
        """O coração do conserto: nada de segundo contato."""
        self.criar_cliente("31 - WLADSON")
        primeira = AstreaFalso(self.config, self.log, grava_sem_confirmar=True)
        self.rodar(primeira)
        self.assertEqual(len(primeira.cadastrados), 1)

        segunda = AstreaFalso(self.config, self.log)      # Astrea já indexou
        segunda.existentes = dict(primeira.existentes)
        resumo = self.rodar(segunda)

        self.assertEqual(segunda.cadastrados, [],
                         "não pode cadastrar de novo o que já estava gravado")
        registro = self.registro("31 - WLADSON")
        self.assertEqual(registro["status"], St.JA_CADASTRADO)
        self.assertEqual(registro["astrea_contato_id"], "AST001")
        self.assertEqual(resumo.erros, 0)

    def test_sem_id_na_tela_a_rodada_seguinte_procura_pelo_cpf(self):
        """
        Sem id, a decisão é da busca por CPF — que é o primeiro passo do fluxo.
        Se o Astrea disser que existe, vira JÁ CADASTRADO; nada é criado.
        """
        self.criar_cliente("32 - SEM ID")
        astrea = AstreaFalso(self.config, self.log)
        astrea.cadastrar_contato = lambda ficha: ResultadoCadastro(
            sucesso=False, a_confirmar=True, detalhe="sem id na tela")
        self.rodar(astrea)
        self.assertEqual(self.registro("32 - SEM ID")["status"], St.A_CONFIRMAR)

        cpf = self.registro("32 - SEM ID")["cpf_cnpj"]
        segunda = AstreaFalso(self.config, self.log, existentes={cpf: "AST900"})
        self.rodar(segunda)
        self.assertEqual(segunda.cadastrados, [])
        self.assertEqual(self.registro("32 - SEM ID")["status"], St.JA_CADASTRADO)

    def test_recusa_de_verdade_continua_sendo_erro(self):
        """O conserto não pode engolir falha real de cadastro."""
        self.criar_cliente("33 - RECUSADO")
        astrea = AstreaFalso(self.config, self.log, falhar_cadastro=True)
        resumo = self.rodar(astrea)
        self.assertEqual(self.registro("33 - RECUSADO")["status"], St.ERRO)
        self.assertEqual(resumo.erros, 1)


class TestRodadaSemAcesso(BaseFluxo):
    """
    Rodada que não conseguiu entrar no Astrea tem que FALHAR, não passar batido.

    Em 09/09/2026 a senha foi trocada, o login passou a ser recusado e o
    agendador marcou "ok" cinco vezes seguidas. Ninguém foi cadastrado e nada
    avisou — a falha só apareceu porque fui atrás de um cliente específico.
    """

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))     # ativa a automação

    def test_login_recusado_marca_a_rodada_como_sem_acesso(self):
        from src.astrea.base import ErroAutenticacao

        class NaoEntra(AstreaFalso):
            def conectar(self, *a, **k):
                raise ErroAutenticacao("Não foi possível entrar no Astrea.")

        self.criar_cliente("40 - ESPERANDO")
        resumo = self.rodar(NaoEntra(self.config, self.log))
        self.assertTrue(resumo.sem_acesso, "a rodada precisa dizer que não entrou")
        self.assertIn("entrar no Astrea", resumo.sem_acesso)
        self.assertEqual(resumo.cadastrados, 0)

    def test_a_fila_continua_intacta_para_a_proxima_rodada(self):
        """Não entrar não pode queimar o cliente: ele espera a senha nova."""
        from src.astrea.base import ErroAutenticacao

        class NaoEntra(AstreaFalso):
            def conectar(self, *a, **k):
                raise ErroAutenticacao("Não foi possível entrar no Astrea.")

        self.criar_cliente("41 - NA FILA")
        self.rodar(NaoEntra(self.config, self.log))
        registro = self.registro("41 - NA FILA")
        self.assertTrue(registro is None or registro["status"] not in
                        (St.CADASTRADO, St.ERRO),
                        "cliente não pode ser dado como resolvido nem como erro dele")

        astrea = AstreaFalso(self.config, self.log)        # senha nova, entra
        self.rodar(astrea)
        self.assertEqual(self.registro("41 - NA FILA")["status"], St.CADASTRADO)

    def test_senha_recusada_e_chrome_ocupado_sao_motivos_diferentes(self):
        """
        Chrome ocupado não é senha errada. Um aviso só mandaria você trocar a
        senha certa toda vez que o perfil estivesse em uso (18/09/2026).
        """
        from src.astrea.base import ErroAstrea, ErroAutenticacao

        class SenhaErrada(AstreaFalso):
            def conectar(self, *a, **k):
                raise ErroAutenticacao("Não foi possível entrar no Astrea.")

        class ChromeOcupado(AstreaFalso):
            def conectar(self, *a, **k):
                raise ErroAstrea("Failed to create a ProcessSingleton")

        self.criar_cliente("43 - MOTIVO")
        self.assertEqual(self.rodar(SenhaErrada(self.config, self.log)).motivo_sem_acesso,
                         "senha")
        self.assertEqual(self.rodar(ChromeOcupado(self.config, self.log)).motivo_sem_acesso,
                         "conexao")

    def test_rodada_normal_nao_marca_sem_acesso(self):
        self.criar_cliente("42 - NORMAL")
        resumo = self.rodar(AstreaFalso(self.config, self.log))
        self.assertFalse(resumo.sem_acesso)


class TestTravaDeDocumentacao(BaseFluxo):
    """Sem a documentação completa na pasta, não cadastra (25/09/2026)."""

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))   # ativa a automação

    def test_sem_comprovante_fica_pendente_e_nao_cadastra(self):
        self.criar_cliente("50 - INCOMPLETO", com_documentos=False,
                           extras=("CNH.pdf", "CRLV.pdf"))
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("50 - INCOMPLETO")
        self.assertEqual(registro["status"], St.PENDENTE)
        self.assertIn("DOCUMENTAÇÃO INCOMPLETA", registro["detalhe"])
        self.assertIn("COMPROVANTE DE RESIDÊNCIA", registro["detalhe"])
        self.assertEqual(astrea.cadastrados, [])

    def test_completar_a_pasta_libera_na_rodada_seguinte(self):
        pasta = self.criar_cliente("51 - COMPLETA DEPOIS", com_documentos=False,
                                   extras=("CNH.pdf", "CRLV.pdf"))
        self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("51 - COMPLETA DEPOIS")["status"], St.PENDENTE)

        for nome in ("COMPROVANTE DE RESIDÊNCIA.pdf",):
            (pasta / "DOC CLIENTE" / nome).write_bytes(b"%PDF-1.4 fake")
        self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("51 - COMPLETA DEPOIS")["status"], St.CADASTRADO)
