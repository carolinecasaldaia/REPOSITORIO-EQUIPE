#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abertura de casos e tarefas em lote.

O que estes testes protegem é uma coisa só, aprendida na tela: o Astrea leva
algumas dezenas de segundos para indexar um caso recém-salvo, e a primeira
tarefa desse caso falha se for pedida logo em seguida. Aconteceu com quatro
clientes em 18/08, com o Djacy em 24/08 e com o Adeson em 01/09/2026.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.astrea import casos as C                                   # noqa: E402


class PaginaFalsa(object):
    """Registra a ordem dos acontecimentos; não desenha tela nenhuma."""

    def __init__(self):
        self.roteiro = []


class TestLote(unittest.TestCase):

    def setUp(self):
        self.roteiro = []
        self._caso, self._tarefa, self._entrar = C.abrir_caso, C.abrir_tarefa, C._entrar_no_caso
        self._quem_criou = C.quem_criou_o_caso
        C.abrir_caso = self._abrir_caso
        C.abrir_tarefa = self._abrir_tarefa
        C._entrar_no_caso = self._entrar_no_caso
        C.quem_criou_o_caso = lambda pagina: self.criado_por.get(
            self.contato_atual, C.USUARIO_AUTOMACAO)
        self._existentes = C.tarefas_existentes
        self.ja_existentes = {}
        C.tarefas_existentes = lambda pagina, url, tarefas: {
            t for t in tarefas if t in self.ja_existentes.get(url, set())}
        self.casos_que_falham = set()
        self.tarefas_que_falham = set()
        self.casos_ja_existentes = set()   # nomes de cliente cujo caso "já existia"
        self.casos_bloqueados_historico = set()  # cliente com processo/caso anterior
        self.criado_por = {}               # contato_id -> quem criou (default: a automação)
        self.contato_atual = None

    def tearDown(self):
        C.abrir_caso, C.abrir_tarefa, C._entrar_no_caso = self._caso, self._tarefa, self._entrar
        C.tarefas_existentes = self._existentes
        C.quem_criou_o_caso = self._quem_criou

    def _abrir_caso(self, pagina, contato_id, cliente, tipo, descricao, observacao="",
                    espera=None, materia_nova="", **_):
        # `materia_nova` chega vazia nos testes antigos; o teste da autorização
        # a usa para checar que o bloqueio histórico é contornado.
        if materia_nova and cliente in self.casos_bloqueados_historico:
            self.roteiro.append(("caso", cliente))
            return "COMERCIAL - " + tipo, True, ""
        if cliente in self.casos_que_falham:
            raise RuntimeError("SALVAR não respondeu")
        self.roteiro.append(("caso", cliente))
        if cliente in self.casos_bloqueados_historico:
            return "COMERCIAL - " + tipo, None, "resumo do que já existe"
        return "COMERCIAL - " + tipo, cliente not in self.casos_ja_existentes, None

    def _entrar_no_caso(self, pagina, contato_id, titulo):
        self.contato_atual = contato_id
        return "url/%s" % contato_id

    def _abrir_tarefa(self, pagina, url, titulo, cliente, tarefa, responsavel, data,
                      tentativas=None):
        if (cliente, tarefa) in self.tarefas_que_falham:
            raise RuntimeError("O Astrea não sugeriu %r" % titulo)
        self.roteiro.append(("tarefa", cliente, tarefa))

    def _itens(self, *nomes):
        return [{"id": "ID%d" % n, "cliente": nome, "tipo": "REVISIONAL VEICULAR"}
                for n, nome in enumerate(nomes, 1)]

    def test_todos_os_casos_saem_antes_de_qualquer_tarefa(self):
        """O conserto: a fila de casos é a espera que a indexação pedia."""
        C.abrir_lote(None, self._itens("Ana", "Bruno", "Carla"), "01/09/2026")
        tipos = [linha[0] for linha in self.roteiro]
        self.assertEqual(tipos[:3], ["caso", "caso", "caso"])
        self.assertNotIn("caso", tipos[3:])

    def test_cada_cliente_recebe_as_cinco_tarefas(self):
        resultado = C.abrir_lote(None, self._itens("Ana", "Bruno"), "01/09/2026")
        for linha in resultado:
            self.assertEqual(len(linha["tarefas"]), 5)
            self.assertEqual(linha["falhas"], [])

    def test_veiculo_apreendido_ganha_o_agravo(self):
        itens = self._itens("Ana")
        itens[0]["tipo"] = "BUSCA E APREENSÃO"
        itens[0]["apreendido"] = True
        resultado = C.abrir_lote(None, itens, "01/09/2026")
        self.assertIn(C.TAREFA_AGRAVO, resultado[0]["tarefas"])
        self.assertEqual(len(resultado[0]["tarefas"]), 6)

    def test_um_caso_que_falha_nao_derruba_os_outros(self):
        self.casos_que_falham.add("Bruno")
        resultado = C.abrir_lote(None, self._itens("Ana", "Bruno", "Carla"), "01/09/2026")
        por_cliente = {l["cliente"]: l for l in resultado}
        self.assertEqual(por_cliente["Bruno"]["tarefas"], [])
        self.assertEqual(por_cliente["Bruno"]["falhas"][0][0], "(caso)")
        self.assertEqual(len(por_cliente["Ana"]["tarefas"]), 5)
        self.assertEqual(len(por_cliente["Carla"]["tarefas"]), 5)

    def test_caso_que_ja_tinha_tarefas_so_recebe_as_que_faltam(self):
        """
        Cliente de mês anterior pode já ter caso e tarefas (Eber, 18/09/2026).
        O lote não pode criar de novo o que já está lá.
        """
        self.ja_existentes["url/ID1"] = {"ENVIAR ONBOARDING", "PROTOCOLAR INICIAL"}
        resultado = C.abrir_lote(None, self._itens("Eber"), "18/09/2026")
        criadas = [r[2] for r in self.roteiro if r[0] == "tarefa"]
        self.assertNotIn("ENVIAR ONBOARDING", criadas)
        self.assertNotIn("PROTOCOLAR INICIAL", criadas)
        self.assertEqual(len(criadas), 3)
        self.assertEqual(sorted(resultado[0]["ja_tinha"]),
                         ["ENVIAR ONBOARDING", "PROTOCOLAR INICIAL"])

    def test_caso_de_outra_pessoa_nao_recebe_tarefa_nenhuma(self):
        """
        Caso que já existia por conta de uma PESSOA (não da automação) não
        pode receber tarefa nenhuma — foi mexer nisso, sem saber em que fase
        o caso estava, que gerou retrabalho e transtorno para a equipe em
        22/09/2026 (34 tarefas de "início de caso" caíram em cima de casos já
        com até 10 tarefas concluídas).
        """
        self.casos_ja_existentes.add("Ana")
        self.criado_por["ID1"] = "Caroline Macedo"
        resultado = C.abrir_lote(None, self._itens("Ana"), "22/09/2026")
        self.assertEqual([r for r in self.roteiro if r[0] == "tarefa"], [])
        self.assertEqual(resultado[0]["tarefas"], [])
        self.assertEqual(resultado[0]["falhas"], [])
        self.assertTrue(resultado[0]["nao_mexido"])
        self.assertEqual(resultado[0]["criado_por"], "Caroline Macedo")

    def test_caso_da_propria_automacao_continua_completando_o_que_falta(self):
        """
        Caso que já existia mas foi A PRÓPRIA AUTOMAÇÃO quem criou — sobrou
        de uma rodada anterior que caiu no meio, como o Eber em 18/09/2026 —
        continua entrando e completando a tarefa que faltou.
        """
        self.casos_ja_existentes.add("Ana")
        self.criado_por["ID1"] = C.USUARIO_AUTOMACAO
        resultado = C.abrir_lote(None, self._itens("Ana"), "22/09/2026")
        self.assertEqual(len(resultado[0]["tarefas"]), 5)
        self.assertNotIn("nao_mexido", resultado[0])

    def test_cliente_com_processo_anterior_nao_recebe_caso_nem_tarefa(self):
        """
        Cliente antigo, com defesa já protocolada num Processo de antes desta
        automação, mas sem "Caso COMERCIAL" ainda — não pode receber um caso
        novo do zero. Foi isso que aconteceu com o Bruno Helder Gomes
        Teofilo em 22/09/2026: matéria antiga, kit de início duplicado.
        """
        self.casos_bloqueados_historico.add("Bruno")
        resultado = C.abrir_lote(None, self._itens("Bruno"), "22/09/2026")
        self.assertEqual([r for r in self.roteiro if r[0] == "tarefa"], [])
        self.assertEqual(resultado[0]["tarefas"], [])
        self.assertEqual(resultado[0]["falhas"], [])
        self.assertTrue(resultado[0]["nao_mexido"])
        self.assertTrue(resultado[0]["bloqueado_historico"])
        self.assertEqual(resultado[0]["processos_e_casos_anteriores"],
                         "resumo do que já existe")

    def test_caso_completo_nao_recebe_nada(self):
        self.ja_existentes["url/ID1"] = set(C.tarefas_do_caso("REVISIONAL VEICULAR"))
        C.abrir_lote(None, self._itens("Completo"), "18/09/2026")
        self.assertEqual([r for r in self.roteiro if r[0] == "tarefa"], [])

    def test_tarefa_que_falha_vira_pendencia_e_o_resto_continua(self):
        self.tarefas_que_falham.add(("Ana", "ENVIAR ONBOARDING"))
        resultado = C.abrir_lote(None, self._itens("Ana", "Bruno"), "01/09/2026")
        por_cliente = {l["cliente"]: l for l in resultado}
        self.assertEqual(len(por_cliente["Ana"]["tarefas"]), 4)
        self.assertEqual(por_cliente["Ana"]["falhas"][0][0], "ENVIAR ONBOARDING")
        self.assertEqual(len(por_cliente["Bruno"]["tarefas"]), 5)


class TestContagemDeProcessosECasos(unittest.TestCase):
    """
    `_contar_processos_e_casos` é o que impede abrir um "Caso COMERCIAL" do
    zero num cliente que já tem matéria em andamento sob outro título — foi
    o que faltou e gerou o caso do Bruno Helder Gomes Teofilo (22/09/2026).
    """

    class Pagina(object):
        def __init__(self, texto):
            self.texto = texto

        def evaluate(self, _script):
            return self.texto

    def test_cliente_realmente_novo_tem_zero(self):
        self.assertEqual(
            C._contar_processos_e_casos(self.Pagina("Nenhum processo ou caso encontrado.")),
            0)

    def test_le_o_numero_de_processos_e_casos_existentes(self):
        texto = "ATIVOS\n\n3 de 3 processos e casos\n\nTÍTULO\tCLIENTE / PASTA"
        self.assertEqual(C._contar_processos_e_casos(self.Pagina(texto)), 3)

    def test_singular_tambem_e_reconhecido(self):
        self.assertEqual(
            C._contar_processos_e_casos(self.Pagina("1 de 1 processo e caso")), 1)

    def test_texto_sem_o_padrao_esperado_nao_estoura(self):
        self.assertEqual(C._contar_processos_e_casos(self.Pagina("qualquer coisa")), 0)

    def test_resumo_traz_o_trecho_da_lista_para_conferencia_manual(self):
        """
        A automação não decide sozinha se é a mesma matéria ou uma nova —
        regra dela (23/09/2026): "se houver dúvidas, sempre questionar". O
        resumo só entrega o que já existe, para leitura humana.
        """
        texto = ("cabeçalho qualquer\n\n2 de 2 processos e casos\n\n"
                 "COMERCIAL - BUSCA E APREENSÃO\nCaso ativo\n22/09/2026")
        resumo = C._resumo_processos_e_casos(self.Pagina(texto))
        self.assertIn("2 de 2 processos e casos", resumo)
        self.assertIn("COMERCIAL - BUSCA E APREENSÃO", resumo)

    def test_resumo_sem_a_lista_devolve_vazio(self):
        self.assertEqual(C._resumo_processos_e_casos(self.Pagina("nada aqui")), "")


class TestInsistencia(unittest.TestCase):
    """A tarefa insiste enquanto o Astrea não indexou o caso."""

    def setUp(self):
        self._interna, self._dormir = C._abrir_tarefa, C.time.sleep
        C.time.sleep = lambda _s: None
        self.chamadas = []

    def tearDown(self):
        C._abrir_tarefa, C.time.sleep = self._interna, self._dormir

    def _interna_falha(self, quantas):
        def interna(*args, **kwargs):
            self.chamadas.append(1)
            if len(self.chamadas) <= quantas:
                raise RuntimeError("O Astrea não sugeriu 'COMERCIAL - X'")
            return None
        return interna

    def test_insiste_e_consegue_na_segunda(self):
        C._abrir_tarefa = self._interna_falha(1)
        C.abrir_tarefa(_PaginaSemPainel(), "url", "COMERCIAL - X", "Ana",
                       "ENVIAR ONBOARDING", "Emerson Medeiros", "01/09/2026")
        self.assertEqual(len(self.chamadas), 2)

    def test_desiste_depois_do_limite_e_conta_o_motivo(self):
        C._abrir_tarefa = self._interna_falha(99)
        with self.assertRaises(RuntimeError):
            C.abrir_tarefa(_PaginaSemPainel(), "url", "COMERCIAL - X", "Ana",
                           "ENVIAR ONBOARDING", "Emerson Medeiros", "01/09/2026")
        self.assertEqual(len(self.chamadas), C.TENTATIVAS_DA_TAREFA)


class _PaginaSemPainel(object):
    """Só o suficiente para o fechar_paineis() não estourar."""

    def locator(self, _seletor):
        return self

    def count(self):
        return 0


if __name__ == "__main__":
    unittest.main()


class TestObjetoDoContrato(unittest.TestCase):
    """
    Descrição do caso e apreensão, lidas da cláusula 1ª.

    Existe porque o comando em lote lia um campo `objeto` que nunca existiu no
    extrator: `getattr(resultado, "objeto", "")` devolvia "" sempre, e todo caso
    aberto pelo menu saía com a descrição em branco (descoberto em 01/09/2026).
    """

    def _extrair(self, texto):
        from src.extractors import contrato_ho
        resultado = contrato_ho.ResultadoContrato(Path("contrato.pdf"))
        contrato_ho._parse_objeto(texto, resultado, "contrato.pdf")
        return resultado

    def test_le_a_clausula_primeira_a_partir_do_para_realizar(self):
        r = self._extrair(
            "Cláusula 1ª. Advogada contratada obriga-se, diante de mandato judicial, "
            "para realizar o ingresso da Ação Revisional em desfavor do Banco BV, "
            "referente ao contrato de financiamento do veículo ONIX - PLACA: IVA9H35. "
            "Cláusula 2ª. Em remuneração...")
        self.assertTrue(r.objeto.valor.startswith("O ingresso da Ação Revisional"))
        self.assertNotIn("Cláusula 2", r.objeto.valor)
        self.assertNotIn("obriga-se", r.objeto.valor)

    def test_separador_do_veiculo_nao_e_colado(self):
        """'SPORTLINE - COR: VERMELHA' é separador de verdade, não palavra partida."""
        r = self._extrair("Cláusula 1ª. para realizar o ingresso da Ação Revisional, "
                          "referente ao veículo VW/GOLF 1.6 SPORTLINE - COR: VERMELHA "
                          "- PLACA: MIY3E40 - ANO: 2010/2010. Cláusula 2ª.")
        self.assertIn("SPORTLINE - COR: VERMELHA", r.objeto.valor)

    def test_veiculo_apreendido_e_reconhecido_com_estado_data_e_processo(self):
        r = self._extrair(
            "Cláusula 1ª. para realizar a defesa da Ação de Busca e Apreensão sob o "
            "nº 5092826 -32.2026.8.24.0930 – veículo apreendido no Estado de Santa "
            "Catarina, na data de 19.08.2026, referente ao contrato do veículo VW/GOLF. "
            "Cláusula 2ª.")
        self.assertEqual(r.apreensao["estado"], "SANTA CATARINA")
        self.assertEqual(r.apreensao["data"], "19.08.2026")
        self.assertEqual(r.apreensao["processo"], "5092826-32.2026.8.24.0930")

    def test_ano_partido_pelo_pdf_e_remendado(self):
        """'25.08.202 6' — o PDF parte o ano; a data tem que sair inteira."""
        r = self._extrair("Cláusula 1ª. para realizar a defesa da Ação de Busca e "
                          "Apreensão – veículo apreendido no Estado de Sergipe, na "
                          "data de 25.08.202 6, referente ao contrato. Cláusula 2ª.")
        self.assertEqual(r.apreensao["data"], "25.08.2026")

    def test_sem_apreensao_nao_inventa(self):
        r = self._extrair("Cláusula 1ª. para realizar o ingresso da Ação Revisional em "
                          "desfavor do Banco BV, referente ao financiamento. Cláusula 2ª.")
        self.assertIsNone(r.apreensao)

    def test_contrato_sem_clausula_primeira_diz_o_motivo(self):
        r = self._extrair("Contrato de prestação de serviços advocatícios. Fim.")
        self.assertEqual(r.objeto.valor, "")
        self.assertIn("cláusula 1", r.objeto.motivo.lower())


class TestTentativasDeBusca(unittest.TestCase):
    """
    Em que ordem o campo de sugestão é preenchido.

    O primeiro nome sozinho não basta: em 01/09/2026 as cinco tarefas da Juliana
    Lisboa de Oliveira falharam porque "Juliana" trazia outras clientes do mesmo
    primeiro nome e a lista curta de sugestões engolia o caso dela.
    """

    def setUp(self):
        self.tentado = []
        self._esperar, self._limpar, self._dormir = (
            C._esperar_sugestao, C._limpar_campo, C.time.sleep)
        C.time.sleep = lambda _s: None
        C._limpar_campo = lambda _p: None

    def tearDown(self):
        C._esperar_sugestao, C._limpar_campo, C.time.sleep = (
            self._esperar, self._limpar, self._dormir)

    def _rodar(self, texto, acha_em=None, preferir_completo=False):
        class Teclado(object):
            def __init__(self, registro):
                self.registro, self.atual = registro, []

            def type(self, letra):
                self.atual.append(letra)

        class Pagina(object):
            def __init__(self):
                self.keyboard = Teclado(None)

        pagina = Pagina()

        def esperar(pg, alvo, segundos=25):
            digitado = "".join(pg.keyboard.atual)
            pg.keyboard.atual = []
            self.tentado.append(digitado)
            if acha_em is not None and digitado == acha_em:
                class Opcao(object):
                    def click(self_):
                        pass
                return Opcao()
            return None

        C._esperar_sugestao = esperar
        try:
            C._sugerir(pagina, texto, "COMERCIAL - CÍVEL",
                       preferir_completo=preferir_completo)
        except RuntimeError:
            pass
        return self.tentado

    def test_tenta_os_sobrenomes_quando_o_primeiro_nome_nao_resolve(self):
        tentado = self._rodar("Juliana Lisboa de Oliveira")
        self.assertIn("Lisboa", tentado)
        self.assertIn("Oliveira", tentado)

    def test_particulas_nao_viram_busca(self):
        """Procurar por 'de' devolveria meio escritório."""
        self.assertNotIn("de", self._rodar("Juliana Lisboa de Oliveira"))

    def test_para_assim_que_encontra(self):
        tentado = self._rodar("Juliana Lisboa de Oliveira", acha_em="Juliana")
        self.assertEqual(tentado, ["Juliana"])

    def test_nao_repete_a_mesma_busca(self):
        tentado = self._rodar("Adeson")
        self.assertEqual(len(tentado), len(set(tentado)))


class TestGuiaDedPrimeiroAcesso(unittest.TestCase):
    """
    O guia de primeiro acesso do Astrea cobre a tela e engole os cliques.

    Não é hipótese: em 08/09/2026 o `first-xp-module-react` derrubou duas vezes
    o cadastro do Wladson, com o Playwright dizendo "subtree intercepts pointer
    events". Ele não some sozinho.
    """

    class PaginaComGuia(object):
        def __init__(self, botao_funciona=True, quantos=1):
            self.botao_funciona, self.quantos = botao_funciona, quantos
            self.removeu = False
            self.clicou = None

        def locator(self, seletor):
            self._ultimo = seletor
            return self

        def count(self):
            return self.quantos

        def first_text(self):
            return self

        def get_by_text(self, rotulo, exact=False):
            self._rotulo = rotulo
            return self

        @property
        def first(self):
            return self

        def is_visible(self):
            return True

        def click(self, timeout=None):
            if not self.botao_funciona:
                raise RuntimeError("botão não responde")
            self.clicou = self._rotulo
            self.quantos = 0

        def wait_for_timeout(self, _ms):
            pass

        def evaluate(self, _script, _seletor=None):
            self.removeu = True
            self.quantos = 0

    def test_fecha_pelo_botao_quando_da(self):
        pagina = self.PaginaComGuia()
        self.assertTrue(C.fechar_guia_inicial(pagina))
        self.assertEqual(pagina.clicou, "Fechar")
        self.assertFalse(pagina.removeu)

    def test_sem_botao_que_funcione_tira_do_caminho_pelo_dom(self):
        pagina = self.PaginaComGuia(botao_funciona=False)
        self.assertTrue(C.fechar_guia_inicial(pagina))
        self.assertTrue(pagina.removeu)

    def test_tela_sem_guia_nao_mexe_em_nada(self):
        pagina = self.PaginaComGuia(quantos=0)
        self.assertFalse(C.fechar_guia_inicial(pagina))
        self.assertFalse(pagina.removeu)
        self.assertIsNone(pagina.clicou)


class TestInsistenciaDoCaso(unittest.TestCase):
    """
    Abrir caso insiste — e repetir não pode duplicar.

    O Astrea travou no botão ADICIONAR duas vezes em dois dias (Rafael Wagner,
    09/09/2026). Insistir só é seguro porque a função olha antes se o caso já
    está na ficha do contato.
    """

    def setUp(self):
        self._interno, self._dormir, self._fechar = (
            C._abrir_caso, C.time.sleep, C.fechar_paineis)
        C.time.sleep = lambda _s: None
        C.fechar_paineis = lambda _p: None
        self.chamadas = []

    def tearDown(self):
        C._abrir_caso, C.time.sleep, C.fechar_paineis = (
            self._interno, self._dormir, self._fechar)

    def test_insiste_e_consegue_na_segunda(self):
        def interno(*args, **kwargs):
            self.chamadas.append(1)
            if len(self.chamadas) == 1:
                raise RuntimeError("Timeout no ADICIONAR")
            return "COMERCIAL - CÍVEL", True
        C._abrir_caso = interno
        titulo, criado = C.abrir_caso(None, "ID1", "Fulano", "CÍVEL", "descrição")
        self.assertEqual(titulo, "COMERCIAL - CÍVEL")
        self.assertEqual(len(self.chamadas), 2)

    def test_caso_que_ja_existe_nao_e_criado_de_novo(self):
        """A segunda tentativa encontra o caso da primeira e devolve criado=False."""
        def interno(*args, **kwargs):
            self.chamadas.append(1)
            if len(self.chamadas) == 1:
                raise RuntimeError("travou depois de salvar")
            return "COMERCIAL - CÍVEL", False        # achou o que já existia
        C._abrir_caso = interno
        titulo, criado = C.abrir_caso(None, "ID1", "Fulano", "CÍVEL", "descrição")
        self.assertFalse(criado, "não pode contar como criado duas vezes")

    def test_desiste_e_conta_o_motivo(self):
        def interno(*args, **kwargs):
            self.chamadas.append(1)
            raise RuntimeError("Astrea fora do ar")
        C._abrir_caso = interno
        with self.assertRaises(RuntimeError):
            C.abrir_caso(None, "ID1", "Fulano", "CÍVEL", "descrição")
        self.assertEqual(len(self.chamadas), 2)


class TestSessaoCaida(unittest.TestCase):
    """
    Tela de login reconhecida como tal.

    Em 09/09/2026 a sessão caiu e TODO clique passou a falhar por "Timeout
    30000ms exceeded" — mensagem que não diz nada. Consertei duas vezes o que
    não estava quebrado antes de olhar a tela e ver o formulário de login.
    """

    class Pagina(object):
        def __init__(self, texto):
            self.texto = texto

        def evaluate(self, _script):
            return self.texto

    TELA_DE_LOGIN = ("ENTRAR\nESQUECEU SUA SENHA?\n"
                     "Ainda não tem conta no Astrea? Cadastre-se")

    def test_tela_de_login_vira_erro_que_se_entende(self):
        with self.assertRaises(C.SessaoCaiu) as caso:
            C.conferir_sessao(self.Pagina(self.TELA_DE_LOGIN))
        self.assertIn("sessão do Astrea caiu", str(caso.exception))

    def test_tela_normal_passa_direto(self):
        C.conferir_sessao(self.Pagina("COMERCIAL - CÍVEL\nCaso ativo\nADICIONAR"))

    def test_pagina_que_nao_responde_nao_estoura(self):
        class Muda(object):
            def evaluate(self, _script):
                raise RuntimeError("página fechada")
        C.conferir_sessao(Muda())

    def test_sessao_caida_nao_faz_a_tarefa_insistir(self):
        """Insistir com a sessão caída é só perder tempo."""
        chamadas = []

        def interna(*args, **kwargs):
            chamadas.append(1)
            raise C.SessaoCaiu("caiu")

        original, dormir = C._abrir_tarefa, C.time.sleep
        C._abrir_tarefa, C.time.sleep = interna, lambda _s: None
        try:
            with self.assertRaises(C.SessaoCaiu):
                C.abrir_tarefa(_PaginaSemPainel(), "url", "T", "Fulano",
                               "ENVIAR ONBOARDING", "Emerson Medeiros", "09/09/2026")
        finally:
            C._abrir_tarefa, C.time.sleep = original, dormir
        self.assertEqual(len(chamadas), 1, "não pode insistir com a sessão caída")


class TestNumeroCnj(unittest.TestCase):

    def test_digitos_colados_ganham_a_mascara(self):
        self.assertEqual(C.numero_cnj("00356759220268160001"), "0035675-92.2026.8.16.0001")

    def test_numero_ja_formatado_continua_igual(self):
        self.assertEqual(C.numero_cnj("5771353-33.2026.8.09.0067"), "5771353-33.2026.8.09.0067")

    def test_o_que_nao_e_cnj_volta_como_veio(self):
        self.assertEqual(C.numero_cnj("123/2026"), "123/2026")

    def test_observacao_usa_o_numero_formatado(self):
        self.assertIn("0035675-92.2026.8.16.0001",
                      C.observacao_de_apreensao("PARANÁ", "09.09.2026", "00356759220268160001"))


class TestArquivoDeResponsaveis(unittest.TestCase):

    def test_arquivo_manda_e_ignora_comentarios(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as arq:
            arq.write("# comentário = ignorar\n\ncível = Fulana Nova\nlinha sem igual\n")
        tabela = C.ler_responsaveis(arq.name)
        os.remove(arq.name)
        self.assertEqual(tabela["CÍVEL"], "Fulana Nova")
        self.assertEqual(tabela["REVISIONAL VEICULAR"], "Emerson Medeiros")
        self.assertNotIn("# COMENTÁRIO", tabela)

    def test_sem_arquivo_usa_o_padrao(self):
        tabela = C.ler_responsaveis("/caminho/que/nao/existe.txt")
        self.assertEqual(tabela, C.RESPONSAVEIS_PADRAO)

    def test_ninguem_mais_recebe_para_o_pablo(self):
        self.assertNotIn("Pablo Cabral", C.RESPONSAVEIS.values())


class TestCorrecaoDeTipo(unittest.TestCase):
    """
    O contrato de honorários nem sempre descreve o caso que será aberto
    (Dione, 19/10/2026: contrato de revisional, caso de busca e apreensão).
    """

    def tabela(self, texto):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as arq:
            arq.write(texto)
        tabela = C.ler_correcoes_de_tipo(arq.name)
        os.remove(arq.name)
        return tabela

    def test_le_o_arquivo_ignorando_acento_e_caixa(self):
        tabela = self.tabela("# nota\ndione ferreira lucas = busca e apreensao\n")
        self.assertEqual(tabela["DIONE FERREIRA LUCAS"], "BUSCA E APREENSÃO")

    def test_tipo_desconhecido_e_descartado(self):
        self.assertEqual(self.tabela("Fulano = AÇÃO QUALQUER\n"), {})

    def test_corrige_quem_esta_na_lista(self):
        tabela = {"DIONE FERREIRA LUCAS": "BUSCA E APREENSÃO"}
        self.assertEqual(
            C.tipo_corrigido("REVISIONAL VEICULAR", "Dione Ferreira Lucas",
                             correcoes=tabela), "BUSCA E APREENSÃO")

    def test_nao_mexe_em_quem_nao_esta(self):
        tabela = {"DIONE FERREIRA LUCAS": "BUSCA E APREENSÃO"}
        self.assertEqual(
            C.tipo_corrigido("REVISIONAL VEICULAR", "Outro Cliente",
                             correcoes=tabela), "REVISIONAL VEICULAR")

    def test_serve_tambem_pelo_nome_da_pasta(self):
        tabela = {"01 - OK - DIONE FERREIRA LUCAS": "CÍVEL"}
        self.assertEqual(
            C.tipo_corrigido("REVISIONAL VEICULAR", "Dione Ferreira Lucas",
                             "01 - OK - DIONE FERREIRA LUCAS",
                             correcoes=tabela), "CÍVEL")

    def test_corrigir_muda_tarefa_e_responsavel(self):
        tipo = C.tipo_corrigido("REVISIONAL VEICULAR", "Dione Ferreira Lucas",
                                correcoes={"DIONE FERREIRA LUCAS": "BUSCA E APREENSÃO"})
        self.assertEqual(C.TIPOS[tipo], "PETICIONAR DEFESA - BUSCA E APREENSÃO")
        self.assertEqual(C.RESPONSAVEIS[tipo], "Ana Carolina")


class TestMateriaNovaAutorizada(unittest.TestCase):
    """
    Cliente com processo/caso anterior só recebe caso novo quando ela autoriza
    (Daniel Cedrim, 20/10/2026: superendividamento ativo + busca e apreensão
    nova).
    """

    def tabela(self, texto):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as arq:
            arq.write(texto)
        tabela = C.ler_materias_novas(arq.name)
        os.remove(arq.name)
        return tabela

    def test_le_nome_e_motivo(self):
        tabela = self.tabela("# nota\nDANIEL CEDRIM OLIVEIRA = busca nova\n")
        self.assertEqual(tabela["DANIEL CEDRIM OLIVEIRA"], "busca nova")

    def test_sem_arquivo_ninguem_autorizado(self):
        self.assertEqual(C.ler_materias_novas("/nao/existe.txt"), {})

    def test_autorizado_ignora_acento_e_caixa(self):
        tabela = {"DANIEL CEDRIM OLIVEIRA": "busca nova"}
        self.assertEqual(C.materia_nova("Daniel Cedrim Oliveira",
                                        autorizacoes=tabela), "busca nova")

    def test_quem_nao_esta_na_lista_continua_bloqueado(self):
        tabela = {"DANIEL CEDRIM OLIVEIRA": "busca nova"}
        self.assertEqual(C.materia_nova("Bruno Helder Gomes Teofilo",
                                        autorizacoes=tabela), "")


class TestLoteComMateriaNova(TestLote):
    """O lote abre o caso de quem ela autorizou, mesmo com histórico."""

    def test_autorizada_passa_pelo_bloqueio_historico(self):
        original = C.ler_materias_novas
        C.ler_materias_novas = lambda *a, **k: {"FULANO DE TAL": "matéria nova"}
        try:
            self.casos_bloqueados_historico = {"Fulano de Tal"}
            saida = C.abrir_lote(None, [{"id": "ID1", "cliente": "Fulano de Tal",
                                         "tipo": "CÍVEL"}], "20/10/2026")
        finally:
            C.ler_materias_novas = original
        self.assertTrue(saida[0]["criado"])
        self.assertFalse(saida[0].get("bloqueado_historico"))


class TestPadraoTolerante(unittest.TestCase):
    """
    Partícula a mais ou a menos não pode impedir o clique na sugestão
    (Daniel Cedrim, 20/10/2026: contrato sem o "de", Astrea com).
    """

    def test_aceita_particula_a_mais_no_astrea(self):
        padrao = C.padrao_tolerante("Daniel Cedrim Oliveira")
        self.assertTrue(padrao.search("Daniel Cedrim de Oliveira"))

    def test_aceita_particula_a_menos(self):
        padrao = C.padrao_tolerante("Maria Lima de Jesus")
        self.assertTrue(padrao.search("Maria Lima Jesus"))

    def test_nao_casa_outra_pessoa(self):
        padrao = C.padrao_tolerante("Daniel Cedrim Oliveira")
        for outro in ("Daniel Souza Cruz", "Daniela Cedrim de Oliveira Santos",
                      "Cedrim Daniel Oliveira"):
            self.assertIsNone(padrao.search(outro), outro)

    def test_exige_todos_os_nomes_na_ordem(self):
        padrao = C.padrao_tolerante("Maria Lima de Jesus")
        self.assertIsNone(padrao.search("Maria Jesus Lima"))
        self.assertIsNone(padrao.search("Maria Lima"))

    def test_nome_vazio_nao_gera_padrao(self):
        self.assertIsNone(C.padrao_tolerante(""))
        self.assertIsNone(C.padrao_tolerante("de da do"))
