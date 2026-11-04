#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regras do adaptador de navegador que vieram de medição no Astrea real.

Estes testes existem por causa de um erro concreto: a primeira versão buscava o
CPF só com os dígitos (`39053344705`). Medido no Astrea em 13/08/2026, a busca
de contatos **não acha** assim — só acha com pontuação (`390.533.447-05`). Um
cliente já cadastrado apareceria como novo, e a automação criaria cadastro
duplicado logo no primeiro cliente.

Não precisam de navegador nem de rede: o adaptador é montado sem `conectar()`
e a parte que fala com a tela é substituída.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.astrea.navegador import AdaptadorNavegador   # noqa: E402
from src.config import settings                       # noqa: E402


class PaginaFalsa(object):
    """O mínimo que buscar_por_documento usa da página."""

    def __init__(self):
        self.url = "https://astrea.net.br/#/main/contacts"
        self.visitou = []

    def goto(self, url, **_):
        self.visitou.append(url)

    def wait_for_timeout(self, _ms):
        pass


class NavegadorDeTeste(AdaptadorNavegador):
    """Troca só a digitação na lista; o resto da lógica é a de produção."""

    def __init__(self, config, log, achados=None):
        AdaptadorNavegador.__init__(self, config, log, somente_leitura=True)
        self.pagina = PaginaFalsa()
        self.termos = []
        # termo digitado -> (achou, id, nome)
        self.achados = dict(achados or {})

    def _filtrar_lista(self, termo):
        self.termos.append(termo)
        return self.achados.get(termo, (False, None, ""))


class LogMudo(object):
    def _nada(self, *a, **k):
        pass
    info = ok = alerta = erro = titulo = registrar_resultado = _nada

    def contexto(self, **k):
        pass

    def limpar_contexto(self):
        pass


class TestBuscaDeDuplicidade(unittest.TestCase):

    def setUp(self):
        self.config = settings.get_config(recarregar=True)
        self.log = LogMudo()

    def test_busca_usa_o_cpf_com_pontuacao(self):
        # É o achado que motiva este arquivo: o Astrea só acha assim.
        nav = NavegadorDeTeste(
            self.config, self.log,
            achados={"390.533.447-05": (True, "5446980264558592", "Cliente Teste")})
        resultado = nav.buscar_por_documento("39053344705")
        self.assertEqual(nav.termos[0], "390.533.447-05")
        self.assertTrue(resultado.encontrado)
        self.assertEqual(resultado.astrea_id, "5446980264558592")

    def test_aceita_cpf_ja_formatado(self):
        nav = NavegadorDeTeste(self.config, self.log,
                               achados={"529.982.247-25": (True, "1", "Fulano")})
        resultado = nav.buscar_por_documento("529.982.247-25")
        self.assertEqual(nav.termos[0], "529.982.247-25")
        self.assertTrue(resultado.encontrado)

    def test_cnpj_tambem_vai_formatado(self):
        nav = NavegadorDeTeste(self.config, self.log)
        nav.buscar_por_documento("58173643000117")
        self.assertEqual(nav.termos[0], "58.173.643/0001-17")

    def test_cliente_novo_nao_e_confundido(self):
        nav = NavegadorDeTeste(self.config, self.log)
        resultado = nav.buscar_por_documento("529.982.247-25", "FULANO DE TAL")
        self.assertFalse(resultado.encontrado)
        self.assertEqual(resultado.suspeitas, [])

    def test_homonimo_sem_cpf_vira_suspeita(self):
        nav = NavegadorDeTeste(
            self.config, self.log,
            achados={"FULANO DE TAL": (True, "77", "Fulano de Tal")})
        resultado = nav.buscar_por_documento("529.982.247-25", "FULANO DE TAL")
        self.assertFalse(resultado.encontrado)
        self.assertEqual(len(resultado.suspeitas), 1)
        self.assertIn("77", resultado.suspeitas[0])

    def test_sem_documento_nao_deixa_seguir(self):
        from src.astrea.base import BuscaIndisponivel
        nav = NavegadorDeTeste(self.config, self.log)
        with self.assertRaises(BuscaIndisponivel):
            nav.buscar_por_documento("")


class TestSeletoresCalibrados(unittest.TestCase):
    """Garante que os seletores medidos na tela real não se percam."""

    def setUp(self):
        self.config = settings.get_config(recarregar=True)
        self.nav = NavegadorDeTeste(self.config, LogMudo())

    def test_id_do_contato_sai_da_url_com_barra(self):
        # A URL real é #/main/contacts/detail/5446980264558592/data
        from src.astrea.navegador import _ID_NA_URL
        achado = _ID_NA_URL.search(
            "https://astrea.net.br/#/main/contacts/detail/5446980264558592/data")
        self.assertIsNotNone(achado)
        self.assertEqual(achado.group(1), "5446980264558592")

    def test_contador_da_lista_e_lido(self):
        from src.astrea.navegador import _CONTAGEM
        achado = _CONTAGEM.search("Mostrando 1 de 1 contato(s)")
        self.assertIsNotNone(achado)
        self.assertEqual(achado.group(2), "1")

    def test_cpf_e_procurado_pelo_placeholder(self):
        # O campo de CPF não tem ng-model próprio; o placeholder é a âncora.
        estrategias = self.nav.seletores["cpf"]
        self.assertTrue(any(e["tipo"] == "placeholder" and "CPF" in e["valor"]
                            for e in estrategias))

    def test_campos_principais_miram_no_ng_model(self):
        for chave, modelo in (("nome", "contact.name"),
                              ("cep", "address.zipCode"),
                              ("logradouro", "address.street"),
                              ("profissao", "contact.job"),
                              ("estado_civil", "contact.maritalStatus"),
                              ("rg", "contact.idDocumentNumber")):
            estrategias = self.nav.seletores[chave]
            self.assertTrue(
                any(modelo in e.get("valor", "") for e in estrategias),
                "%s deveria mirar em ng-model=%s" % (chave, modelo))

    def test_cpf_esta_na_aba_de_documentacao(self):
        from src.astrea import seletores as S
        abas = dict(S.ABAS)
        self.assertIn("cpf", abas["aba_documentacao"])
        self.assertNotIn("cpf", abas["aba_pessoais"])


class TestEscolhaDoAdaptador(unittest.TestCase):
    """
    Qual adaptador entra em campo.

    Existe por um erro real: com a sessão salva no perfil do Chrome (e nenhuma
    senha no .env), a automação caía em dry-run e o teste passava "verde" sem
    nunca ter consultado o Astrea — o cliente que já estava cadastrado saiu como
    novo. A escolha tem que olhar os DOIS caminhos de acesso.
    """

    def setUp(self):
        import shutil
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="cadastro-astrea-adapt-"))
        self._limpar = lambda: shutil.rmtree(str(self.tmp), ignore_errors=True)
        import os
        self.env_antigo = {c: os.environ.get(c) for c in
                           ("PASTA_DADOS", "TEST_MODE", "ASTREA_ADAPTADOR",
                            "ASTREA_EMAIL", "ASTREA_SENHA",
                            "ASTREA_PERFIL_PROPRIO")}
        os.environ["PASTA_DADOS"] = str(self.tmp)
        os.environ["TEST_MODE"] = "true"
        os.environ["ASTREA_ADAPTADOR"] = "navegador"
        os.environ["ASTREA_PERFIL_PROPRIO"] = "true"
        # Vazio, e não pop: a variável de ambiente vence o .env, e apagá-la
        # deixava o e-mail/senha REAIS do .env valerem no teste. Depois que ela
        # gravou a senha do Astrea (18/08/2026), "sem acesso nenhum" deixou de
        # ser sem acesso nenhum e dois testes passaram a falhar.
        for chave in ("ASTREA_EMAIL", "ASTREA_SENHA"):
            os.environ[chave] = ""

    def tearDown(self):
        import os
        for chave, valor in self.env_antigo.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor
        settings.get_config(recarregar=True)
        self._limpar()

    def _adaptador(self):
        from src.services.orquestrador import _criar_adaptador
        config = settings.get_config(recarregar=True)
        return _criar_adaptador(config, LogMudo())

    def test_com_sessao_salva_usa_o_navegador(self):
        (self.tmp / "chrome-perfil" / "Default").mkdir(parents=True)
        self.assertEqual(self._adaptador().nome, "navegador")

    def test_com_email_e_senha_usa_o_navegador(self):
        import os
        os.environ["ASTREA_EMAIL"] = "alguem@exemplo.com"
        os.environ["ASTREA_SENHA"] = "x"
        self.assertEqual(self._adaptador().nome, "navegador")

    def test_sem_acesso_nenhum_cai_para_dry_run(self):
        self.assertEqual(self._adaptador().nome, "dry-run")

    def test_sessao_salva_conta_como_acesso(self):
        config = settings.get_config(recarregar=True)
        self.assertFalse(config.tem_acesso_astrea())
        (self.tmp / "chrome-perfil" / "Default").mkdir(parents=True)
        config = settings.get_config(recarregar=True)
        self.assertTrue(config.tem_acesso_astrea())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPerfilOcupado(unittest.TestCase):
    """
    O agendador não pode abrir o Chrome num perfil que já está em uso.

    Em 18/09/2026, a tentativa do agendador das 12:40 coincidiu com o lote que
    estava rodando no mesmo perfil deixar de conseguir clicar no ADICIONAR.
    Conferir antes, sem abrir nada, tira a chance de mexer na janela aberta.
    """

    def setUp(self):
        import tempfile
        self.pasta = Path(tempfile.mkdtemp(prefix="perfil-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.pasta), ignore_errors=True)

    def _travar(self, alvo):
        import os
        os.symlink(alvo, str(self.pasta / "SingletonLock"))

    def test_perfil_livre(self):
        from src.astrea.navegador import perfil_ocupado
        self.assertEqual(perfil_ocupado(self.pasta), "")

    def test_perfil_em_uso_por_processo_vivo(self):
        import os
        from src.astrea.navegador import perfil_ocupado
        self._travar("MinhaMaquina-%d" % os.getpid())      # este teste está vivo
        self.assertEqual(perfil_ocupado(self.pasta), str(os.getpid()))

    def test_trava_que_sobrou_de_chrome_morto_nao_conta(self):
        from src.astrea.navegador import perfil_ocupado
        self._travar("MinhaMaquina-999999")                 # PID que não existe
        self.assertEqual(perfil_ocupado(self.pasta), "")

    def test_trava_estranha_nao_estoura(self):
        from src.astrea.navegador import perfil_ocupado
        self._travar("sem-numero-aqui")
        self.assertEqual(perfil_ocupado(self.pasta), "")


class TestTipoDePessoa(unittest.TestCase):
    """
    O botão Pessoa jurídica do Astrea é invisível: só aceita clique forçado.

    Descoberto na tela em 18/09/2026, com o primeiro cliente empresa (Vektor
    Pharma): clique normal esperou 30 s e o cadastro inteiro falhou.
    """

    class Radio(object):
        def __init__(self, aceita_check=True, fica_marcado=True):
            self.aceita_check, self.fica_marcado = aceita_check, fica_marcado
            self.chamadas = []
            self.marcado = False

        def check(self, force=False):
            self.chamadas.append(("check", force))
            if not self.aceita_check:
                raise RuntimeError("Timeout 30000ms exceeded")
            self.marcado = self.fica_marcado

        def click(self, force=False):
            self.chamadas.append(("click", force))
            self.marcado = self.fica_marcado

        def is_checked(self):
            return self.marcado

    def test_marca_sempre_com_force(self):
        from src.astrea.navegador import marcar_tipo_pessoa
        radio = self.Radio()
        marcar_tipo_pessoa(radio, juridica=True)
        self.assertEqual(radio.chamadas, [("check", True)])

    def test_se_o_check_falhar_clica_forcado(self):
        from src.astrea.navegador import marcar_tipo_pessoa
        radio = self.Radio(aceita_check=False)
        marcar_tipo_pessoa(radio, juridica=True)
        self.assertIn(("click", True), radio.chamadas)

    def test_empresa_que_nao_ficou_marcada_para_o_cadastro(self):
        """Dados de empresa num formulário de pessoa física: melhor parar."""
        from src.astrea.base import ErroAstrea
        from src.astrea.navegador import marcar_tipo_pessoa
        with self.assertRaises(ErroAstrea):
            marcar_tipo_pessoa(self.Radio(fica_marcado=False), juridica=True)

    def test_pessoa_fisica_nao_exige_conferencia(self):
        """Pessoa física já vem marcada por padrão no formulário."""
        from src.astrea.navegador import marcar_tipo_pessoa
        marcar_tipo_pessoa(self.Radio(fica_marcado=False), juridica=False)
