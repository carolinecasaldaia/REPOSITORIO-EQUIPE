#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptador de navegador (Playwright sobre o Google Chrome).

Por que navegador e não API: o Astrea não publica API. O sistema web consome
uma API interna (`app.astrea.net.br/_ah/api/`), mas ela não é documentada nem
contratada. Então a automação faz pela tela o que a advogada faria pela tela,
com a conta dela.

Calibrado no Astrea real em 13/08/2026. Três coisas que só se descobrem olhando
o sistema de verdade, e que estão no código por causa disso:

1. **A busca de contatos só acha CPF com pontuação.** Procurar por
   `39053344705` não devolve nada; `390.533.447-05` devolve. Buscar só com os
   dígitos faria a automação achar que um cliente já cadastrado é novo — e
   criar cadastro duplicado. A busca aqui usa o CPF formatado.

2. **O formulário tem três abas** (Informações pessoais, Informações
   complementares, Documentação) e o **CPF fica na terceira**. Salvar sem
   passar por ela cadastraria o cliente sem CPF.

3. **A tela de novo contato não tem URL estável** — é
   `#/main/contacts/add-edit-merge/%5B,,false,%5B%5D,%5D/personal`. Por isso o
   cadastro entra clicando em ADICIONAR na lista, não pela URL.

Perfil próprio (padrão): a sessão fica salva num perfil do Chrome criado só
para a automação, em `~/.cadastro-astrea/chrome-perfil`. Você entra uma vez à
mão (`executar.py entrar`) e **a senha não precisa ser guardada em lugar
nenhum** — nem no .env. É o desenho mais seguro para dado de escritório.
"""

import re
import time
from datetime import datetime
from pathlib import Path

from ..validators import campos as V
from . import seletores as S
from .base import (AdaptadorAstrea, BuscaIndisponivel, ErroAstrea,
                   ErroAutenticacao, ErroSessaoPerdida, ResultadoBusca,
                   ResultadoCadastro, payload_caso, payload_contato)

_ID_NA_URL = re.compile(S.PADRAO_ID_CONTATO)
_CONTAGEM = re.compile(S.PADRAO_CONTAGEM, re.I)
_ID_CASO_NA_URL = re.compile(r"(?:cases?|folders?)[-/]detail/(\d+)")


class CampoNaoEncontrado(ErroAstrea):
    pass


def marcar_tipo_pessoa(alvo, juridica: bool):
    """
    Marca Pessoa física/jurídica — o botão de opção do Astrea é INVISÍVEL.

    O desenho da tela cobre o <input> de verdade, então clique normal espera
    30 s e desiste: foi o que travou o cadastro da Vektor Pharma, primeiro
    cliente empresa (18/09/2026). O `force` é o mesmo remédio do botão de
    "caso público". Para empresa, confere que a marcação pegou: preencher
    dados de empresa num formulário de pessoa física seria pior que falhar.
    """
    try:
        alvo.check(force=True)
    except Exception:
        alvo.click(force=True)
    if juridica and not alvo.is_checked():
        raise ErroAstrea("Não consegui marcar 'Pessoa jurídica' no formulário do "
                         "Astrea — o cadastro da empresa não foi feito.")


def perfil_ocupado(pasta_perfil):
    """
    PID do Chrome que está usando o perfil, ou "" se ninguém está.

    O Chrome marca o perfil em uso com o link SingletonLock -> "máquina-PID".
    Link que sobrou de um Chrome que morreu não conta: confere se o PID vive.
    """
    import os
    trava = Path(pasta_perfil) / "SingletonLock"
    try:
        alvo = os.readlink(str(trava))
    except OSError:
        return ""
    pid = alvo.rsplit("-", 1)[-1]
    if not pid.isdigit():
        return ""
    try:
        os.kill(int(pid), 0)          # sinal 0: só pergunta se o processo existe
    except ProcessLookupError:
        return ""
    except PermissionError:
        return pid                    # existe, só é de outro usuário
    return pid


class AdaptadorNavegador(AdaptadorAstrea):

    nome = "navegador"
    escreve_no_astrea = True
    verifica_duplicidade = True

    def __init__(self, config, log, somente_leitura=None):
        AdaptadorAstrea.__init__(self, config, log)
        # Em TEST_MODE o adaptador entra, consulta duplicidade de verdade,
        # mas se recusa a gravar.
        self.somente_leitura = (config.test_mode if somente_leitura is None
                                else somente_leitura)
        self._playwright = None
        self._navegador = None
        self._contexto = None
        self.pagina = None
        self.seletores, self.rotas, self.origem_seletores = S.carregar(
            config.pasta_dados)

    # -- ciclo de vida ---------------------------------------------------

    def conectar(self, forcar_visivel=False):
        # Perfil ocupado: NÃO tentar abrir o Chrome. Abrir o Chrome num perfil
        # em uso manda um sinal para a janela que já está aberta — e em
        # 18/09/2026, logo depois que o agendador das 12:40 fez isso, o lote
        # que estava rodando parou de conseguir clicar no ADICIONAR.
        dono = perfil_ocupado(self.config.pasta_perfil_chrome)
        if dono:
            raise ErroAstrea("O perfil do Chrome da automação está em uso por "
                             "outra execução (processo %s). Rodada adiada." % dono)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ErroAstrea(
                "O Playwright não está instalado. Rode o atalho "
                "'Cadastrar Clientes' uma vez — ele instala sozinho — ou:\n"
                "    python3 -m pip install playwright && python3 -m playwright "
                "install chromium")

        visivel = forcar_visivel or self.config.astrea_navegador_visivel
        self.log.info("Abrindo o Astrea no %s (%s)."
                      % (self.config.astrea_navegador.title(),
                         self.origem_seletores))
        self._playwright = sync_playwright().start()

        argumentos = {"headless": not visivel}
        if self.config.astrea_navegador == "chrome":
            # Usa o Google Chrome instalado, não o Chromium baixado.
            argumentos["channel"] = "chrome"

        if self.config.astrea_perfil_proprio:
            perfil = self.config.pasta_perfil_chrome
            perfil.mkdir(parents=True, exist_ok=True)
            try:
                self._contexto = self._playwright.chromium.launch_persistent_context(
                    str(perfil), locale="pt-BR",
                    viewport={"width": 1440, "height": 900}, **argumentos)
            except Exception as erro:
                raise ErroAstrea(
                    "Não foi possível abrir o Chrome com o perfil da automação "
                    "(%s).\nSe o Chrome estiver aberto com esse mesmo perfil, "
                    "feche-o e tente de novo." % erro)
            self.pagina = (self._contexto.pages[0] if self._contexto.pages
                           else self._contexto.new_page())
        else:
            self._navegador = self._playwright.chromium.launch(**argumentos)
            self._contexto = self._navegador.new_context(
                locale="pt-BR", viewport={"width": 1440, "height": 900})
            self.pagina = self._contexto.new_page()

        self._contexto.set_default_timeout(self.config.astrea_timeout_ms)
        self._garantir_sessao()

    def encerrar(self):
        for fechar in (self._contexto, self._navegador):
            try:
                if fechar:
                    fechar.close()
            except Exception:
                pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = self._navegador = self._contexto = self.pagina = None

    # -- sessão -----------------------------------------------------------

    def _sessao_valida(self, navegar=True) -> bool:
        """
        Entrou mesmo?

        A checagem é em dois níveis de propósito. O forte é a lista de contatos
        aparecer; mas o Astrea às vezes demora a desenhar, e exigir só isso
        fazia a espera pelo login ficar em looping (navega, não achou, navega de
        novo) mesmo com a sessão já aberta. Então estar em `#/main` sem campo de
        senha na tela também conta como sessão válida.
        """
        try:
            if navegar:
                self.pagina.goto(self.rotas["contatos"], wait_until="domcontentloaded")
            self.pagina.wait_for_timeout(2000)

            if self.pagina.locator("input[type=password]").count() > 0:
                return False
            url = self.pagina.url or ""
            if "#/login" in url or "/login" in url:
                return False

            try:
                self.pagina.wait_for_selector(
                    "input[ng-model='$ctrl.data.filter.input']", timeout=8000)
                return True
            except Exception:
                pass
            return "#/main" in url
        except Exception:
            return False

    def _caiu_a_sessao(self) -> bool:
        """A tela atual é a de login? (campo de senha ou URL de login)"""
        try:
            if self.pagina.locator("input[type=password]").count() > 0:
                return True
            return "#/login" in (self.pagina.url or "")
        except Exception:
            return False

    def _garantir_sessao(self):
        if self._sessao_valida():
            self.log.ok("Sessão do Astrea já estava aberta no perfil da automação.")
            return

        senha = self.config.astrea_senha
        if not senha or not self.config.astrea_email:
            raise ErroAutenticacao(
                "Não há sessão salva no perfil da automação e não há senha no "
                ".env.\nRode 'python3 executar.py entrar' (ou o menu do atalho) "
                "para entrar uma vez à mão — depois disso a automação reaproveita "
                "a sessão e a senha não precisa ser guardada.")
        self._entrar(self.config.astrea_email, senha)

    def _entrar(self, email, senha):
        # "domcontentloaded", nunca "networkidle": o Astrea é um sistema que
        # fica conversando com o servidor o tempo todo (mensagens, telemetria),
        # então a rede nunca fica ociosa e a espera estourava em 30 s. Quem
        # garante que a tela está pronta é a espera por campo, em _achar.
        self.pagina.goto(self.rotas["login"], wait_until="domcontentloaded")
        self.pagina.wait_for_timeout(1500)
        self._preencher("login_email", email)
        self._preencher("login_senha", senha)
        self._clicar("login_entrar")
        try:
            self.pagina.wait_for_url(re.compile(r"#/main"),
                                     timeout=self.config.astrea_timeout_ms)
        except Exception:
            url = self.pagina.url or ""
            if "two-factor" in url or "two_factor" in url:
                raise ErroAutenticacao(
                    "O Astrea pediu o código de verificação em duas etapas (2FA). "
                    "A automação não guarda esse código. Use "
                    "'executar.py entrar' para entrar à mão uma vez: a sessão "
                    "fica salva no perfil e as rodadas seguintes não pedem 2FA.")
            self._evidencia("login-falhou")
            raise ErroAutenticacao(
                "Não foi possível entrar no Astrea. Confira e-mail e senha. "
                "(URL final: %s)" % url)
        self.log.ok("Sessão aberta no Astrea.")

    def entrar_manualmente(self, espera_segundos=300):
        """
        Abre o Chrome visível no perfil da automação e espera você entrar.

        A automação não digita, não vê e não guarda a senha: quem entra é você,
        na tela do Astrea. Depois disso a sessão fica salva no perfil e as
        rodadas automáticas reaproveitam.
        """
        self.pagina.goto(self.rotas["login"], wait_until="domcontentloaded")
        print("\n  Entre no Astrea na janela que abriu (a senha é digitada por "
              "você, não pela automação).")
        print("  Assim que a tela de contatos aparecer, esta janela fecha "
              "sozinha.\n")
        limite = time.time() + espera_segundos
        while time.time() < limite:
            try:
                if "#/main" in (self.pagina.url or ""):
                    self.pagina.wait_for_timeout(3000)
                    if self._sessao_valida():
                        return True
            except Exception:
                pass
            time.sleep(2)
        return False

    # -- localização de elementos ---------------------------------------

    def _tentativas(self, chave):
        estrategias = self.seletores.get(chave)
        if not estrategias:
            raise CampoNaoEncontrado("Campo %r não está mapeado nos seletores." % chave)
        for estrategia in estrategias:
            tipo, valor = estrategia.get("tipo"), estrategia.get("valor")
            try:
                if tipo == "rotulo":
                    alvo = self.pagina.get_by_label(valor, exact=False)
                elif tipo == "placeholder":
                    alvo = self.pagina.get_by_placeholder(valor, exact=False)
                elif tipo == "texto":
                    alvo = self.pagina.get_by_role("button", name=valor,
                                                   exact=False)
                    if alvo.count() == 0:
                        alvo = self.pagina.get_by_text(valor, exact=False)
                elif tipo == "css":
                    alvo = self.pagina.locator(valor)
                else:
                    continue
                if alvo.count() > 0:
                    yield alvo.first, estrategia
            except Exception:
                continue

    def _achar(self, chave, obrigatorio=True):
        """
        Procura o campo ESPERANDO ele aparecer.

        Antes a procura era instantânea (`count() > 0` uma única vez): se o
        Astrea ainda estivesse montando a tela, a automação desistia na hora e
        dizia que o campo não existe. A tela de login leva ~8 s para montar e a
        rodada morria em 7 s — e os erros de 17/08 no campo de busca de
        contatos eram a mesma coisa. Agora insiste até o tempo configurado
        (ASTREA_TIMEOUT_MS); campo opcional espera pouco, para não arrastar a
        rodada inteira.
        """
        # Guia de primeiro acesso na frente = clique nenhum funciona (Wladson,
        # 08/09/2026). Tira antes de procurar qualquer campo.
        try:
            from .casos import fechar_guia_inicial
            fechar_guia_inicial(self.pagina)
        except Exception:
            pass

        limite_ms = self.config.astrea_timeout_ms if obrigatorio else 2000
        fim = time.monotonic() + limite_ms / 1000.0
        while True:
            for alvo, _ in self._tentativas(chave):
                return alvo
            if time.monotonic() >= fim:
                break
            try:
                self.pagina.wait_for_timeout(300)
            except Exception:
                break
        if obrigatorio:
            raise CampoNaoEncontrado(
                "Campo %r não foi encontrado na tela do Astrea. A tela pode ter "
                "mudado — rode a calibração (menu 'Calibrar Astrea')." % chave)
        return None

    def _preencher(self, chave, valor, obrigatorio=True):
        """
        Escreve no campo e CONFERE o que ficou lá.

        A conferência não é preciosismo: o Astrea preenche bairro e cidade
        sozinho quando o CEP é digitado, e isso atropelava o que a automação
        estava escrevendo — o Felipe foi cadastrado em 18/08/2026 com o bairro
        "Cidade Universitáriaade Universitária", metade dele e metade do
        preenchimento automático. Se o que ficou no campo não for o que
        mandamos, escreve de uma vez só (fill) e confere de novo.
        """
        if valor in (None, ""):
            return False
        alvo = self._achar(chave, obrigatorio)
        if alvo is None:
            return False
        valor = str(valor)
        alvo.click()
        alvo.fill("")
        alvo.type(valor, delay=15)
        for _ in range(2):
            try:
                self.pagina.wait_for_timeout(250)
                if (alvo.input_value() or "").strip() == valor.strip():
                    return True
                alvo.fill(valor)
            except Exception:
                break
        try:
            final = (alvo.input_value() or "").strip()
            if final != valor.strip():
                self.log.alerta("Campo %s ficou como %r em vez de %r — confira na tela."
                               % (chave, final, valor))
        except Exception:
            pass
        return True

    def _selecionar(self, chave, texto, obrigatorio=False):
        if not texto:
            return False
        alvo = self._achar(chave, obrigatorio)
        if alvo is None:
            return False
        try:
            alvo.select_option(label=texto)
            return True
        except Exception:
            return False

    def _clicar(self, chave, obrigatorio=True):
        alvo = self._achar(chave, obrigatorio)
        if alvo is None:
            return False
        alvo.click()
        return True

    def _evidencia(self, rotulo):
        """
        Captura de tela para diagnóstico.

        Só é chamada quando algo deu errado, e só grava se a configuração
        permitir. A tela pode conter dado de cliente, então o padrão é guardar
        apenas em falha (SALVAR_EVIDENCIA=erro) e dá para desligar de vez
        (=nunca). Fica em ~/.cadastro-astrea/evidencias, fora do Drive.
        """
        if self.config.salvar_evidencia == "nunca" or self.pagina is None:
            return None
        self.config.pasta_evidencias.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        arquivo = self.config.pasta_evidencias / ("%s_%s.png" % (carimbo, rotulo))
        try:
            self.pagina.screenshot(path=str(arquivo), full_page=False)
            return arquivo
        except Exception:
            return None

    # -- duplicidade -----------------------------------------------------

    def _filtrar_lista(self, termo):
        """Digita na busca da lista de contatos e devolve (achou, id, nome)."""
        campo = self._achar("busca_contato")
        campo.click()
        campo.fill("")
        if termo:
            campo.type(str(termo), delay=25)
        self.pagina.wait_for_timeout(2800)

        texto = ""
        try:
            texto = self.pagina.inner_text("body")
        except Exception:
            pass

        achado_contagem = _CONTAGEM.search(texto or "")
        total = int(achado_contagem.group(2)) if achado_contagem else 0

        link = None
        for alvo, _ in self._tentativas("linha_resultado"):
            if alvo.count() > 0:
                link = alvo
                break

        if total == 0 and link is None:
            return False, None, ""

        astrea_id, nome = None, ""
        if link is not None:
            try:
                achado = _ID_NA_URL.search(link.get_attribute("href") or "")
                if achado:
                    astrea_id = achado.group(1)
                nome = (link.inner_text() or "").strip().split("\n")[0]
            except Exception:
                pass
        return True, astrea_id, nome

    def buscar_por_documento(self, documento, nome_cliente=""):
        """
        Procura o CPF/CNPJ na lista de contatos.

        O CPF vai **formatado** de propósito: medido no Astrea real, a busca
        acha `390.533.447-05` e NÃO acha `39053344705`.

        Quando o CPF não aparece, ainda procura pelo nome. Se existir alguém
        com o mesmo nome, devolve uma suspeita — pode ser a mesma pessoa
        cadastrada sem CPF, e aí quem decide é gente, não a automação.
        """
        digitos = V.so_digitos(documento)
        if not digitos:
            raise BuscaIndisponivel("Sem CPF/CNPJ para consultar.")
        formatado = (V.formatar_cnpj(digitos) if len(digitos) == 14
                     else V.formatar_cpf(digitos))

        try:
            self.pagina.goto(self.rotas["contatos"], wait_until="domcontentloaded")
            self.pagina.wait_for_timeout(1500)
            achou, astrea_id, nome = self._filtrar_lista(formatado)
        except CampoNaoEncontrado as erro:
            # Antes de culpar a tela, ver se o que aconteceu foi a sessão cair:
            # o Astrea derruba a sessão quando a mesma conta entra em outro
            # lugar, e aí a tela de contatos vira a tela de login.
            if self._caiu_a_sessao():
                self._evidencia("sessao-caiu")
                raise ErroSessaoPerdida(
                    "A sessão do Astrea caiu no meio da rodada (a tela voltou "
                    "para o login). Isso costuma acontecer quando a mesma conta "
                    "entra em outro navegador — o Astrea derruba a sessão "
                    "anterior.")
            self._evidencia("busca-falhou")
            raise BuscaIndisponivel(
                "Não foi possível usar a busca de contatos do Astrea: %s" % erro)
        except Exception as erro:
            self._evidencia("busca-falhou")
            raise BuscaIndisponivel("Falha ao consultar o Astrea: %s" % erro)

        if achou:
            return ResultadoBusca(True, astrea_id, nome,
                                  detalhe="CPF/CNPJ já existe no Astrea")

        resultado = ResultadoBusca(False, detalhe="CPF não encontrado no Astrea")
        if nome_cliente:
            try:
                achou_nome, id_nome, nome_achado = self._filtrar_lista(nome_cliente)
                if achou_nome:
                    resultado.suspeitas.append(
                        "Existe contato com nome parecido no Astrea (%s%s), mas "
                        "sem este CPF. Conferir para não duplicar."
                        % (nome_achado or nome_cliente,
                           (", id %s" % id_nome) if id_nome else ""))
            except Exception:
                pass                      # a suspeita é um extra, não pode quebrar
        return resultado

    # -- cadastro --------------------------------------------------------

    def cadastrar_contato(self, ficha):
        dados = payload_contato(ficha)

        if self.somente_leitura:
            self.log.info("[TEST MODE] CLIENTE SERIA CADASTRADO")
            for rotulo, valor, confianca in ficha.resumo_para_tela():
                self.log.info("            %-18s %s   (confiança %.2f)"
                              % (rotulo + ":", valor, confianca))
            return ResultadoCadastro(
                sucesso=False,
                detalhe="TEST_MODE ativo: duplicidade verificada no Astrea real, "
                        "cadastro não gravado")

        try:
            self._abrir_formulario()
            self._preencher_formulario(dados)
            self._clicar("salvar_contato")
            self.pagina.wait_for_timeout(3500)
        except Exception as erro:
            self._evidencia("cadastro-erro")
            return ResultadoCadastro(
                sucesso=False, erro="Falha ao preencher o cadastro: %s" % erro)

        # Confirmação: só é sucesso se o Astrea devolver o cliente na busca.
        #
        # A busca é tentada mais de uma vez: em 18/08/2026 o João Roberto foi
        # cadastrado corretamente e mesmo assim a conferência falhou — o
        # Astrea leva alguns segundos para o contato novo aparecer na busca, e
        # a automação perguntava rápido demais. Marcar erro num cadastro que
        # deu certo é pior do que esperar: assusta e convida a cadastrar de
        # novo à mão.
        documento = dados.get("cpf") or dados.get("cnpj")
        astrea_id = self._id_da_url()
        try:
            confirmacao = self.buscar_por_documento(documento)
            for _ in range(3):
                if confirmacao.encontrado:
                    break
                self.pagina.wait_for_timeout(4000)
                confirmacao = self.buscar_por_documento(documento)
        except ErroAstrea as erro:
            return ResultadoCadastro(
                sucesso=False, a_confirmar=True, astrea_id=astrea_id,
                detalhe="Cadastro enviado; a busca no Astrea falhou (%s). "
                        "A próxima rodada confere antes de tentar de novo." % erro)

        if confirmacao.encontrado:
            return ResultadoCadastro(
                sucesso=True,
                astrea_id=confirmacao.astrea_id or astrea_id,
                detalhe="cadastro confirmado pela busca do CPF no Astrea")

        self._evidencia("cadastro-nao-confirmado")
        # O endereço da tela depois de salvar carrega o id do contato novo. Se
        # ele está lá, o Astrea GRAVOU — só ainda não indexou para a busca.
        # Esse id era descartado, e era exatamente a informação que teria
        # evitado o cadastro repetido do Wladson (08/09/2026).
        if astrea_id:
            return ResultadoCadastro(
                sucesso=False, a_confirmar=True, astrea_id=astrea_id,
                detalhe="Cadastro gravado (id %s pela tela), mas a busca ainda "
                        "não o devolveu. A próxima rodada confirma — não "
                        "cadastre de novo à mão." % astrea_id)
        return ResultadoCadastro(
            sucesso=False, a_confirmar=True,
            detalhe="Cadastro enviado, sem confirmação e sem id na tela. A "
                    "próxima rodada procura pelo CPF antes de tentar de novo.")

    def _abrir_formulario(self):
        """
        A tela de novo contato não tem URL estável: entra pelo botão.

        Mudou em 18/08/2026: o ADICIONAR deixou de abrir o formulário direto e
        passou a abrir um MENU (Processo, Caso, Atendimento, Tarefa, Evento,
        Prazo, Audiência, Contato). Agora é preciso escolher "Contato" nesse
        menu. Se um dia voltar a abrir direto, o passo extra simplesmente não
        encontra nada e segue em frente.
        """
        self.pagina.goto(self.rotas["contatos"], wait_until="domcontentloaded")
        self.pagina.wait_for_timeout(1800)
        self._clicar("botao_novo_contato")
        self.pagina.wait_for_timeout(1500)
        if self._achar("nome", obrigatorio=False) is None:
            item = self._achar("menu_novo_contato", obrigatorio=False)
            if item is not None:
                item.click()
                self.pagina.wait_for_timeout(2500)
        if self._achar("nome", obrigatorio=False) is None:
            raise CampoNaoEncontrado(
                "O formulário de novo contato não abriu depois de clicar em "
                "ADICIONAR.")

    # Conectivos ficam em minúsculo: é como o manual do escritório manda
    # escrever o nome no Astrea ("Maria Nizete Santos do Nascimento Araújo").
    _CONECTIVOS = ("de", "da", "do", "das", "dos", "e", "di", "du", "del")

    @classmethod
    def nome_no_padrao(cls, nome):
        """
        MAIÚSCULAS do contrato -> padrão do manual: primeira letra maiúscula,
        resto minúsculo, conectivos em minúsculo.

        O contrato é escrito todo em caixa alta; o manual "ABRIR TAREFA DE
        CLIENTE NOVO NO ASTREA" pede o nome como nome próprio. Os 10 primeiros
        cadastros foram corrigidos à mão em 18/08/2026 e daqui em diante sai
        pronto daqui.
        """
        import re as _re
        pedacos = _re.split(r"(\s+|-)", (nome or "").strip().lower())
        saida, primeiro = [], True
        for pedaco in pedacos:
            if not pedaco.strip() or pedaco == "-":
                saida.append(pedaco)
                continue
            if pedaco in cls._CONECTIVOS and not primeiro:
                saida.append(pedaco)
            else:
                saida.append(pedaco[0].upper() + pedaco[1:])
            primeiro = False
        return "".join(saida)

    def _preencher_formulario(self, dados):
        # Tipo de pessoa e perfil ficam na primeira aba.
        chave_tipo = ("tipo_pessoa_juridica" if dados.get("tipo_pessoa") == "juridica"
                      else "tipo_pessoa_fisica")
        alvo = self._achar(chave_tipo, obrigatorio=False)
        if alvo is not None:
            marcar_tipo_pessoa(alvo, dados.get("tipo_pessoa") == "juridica")
        self._selecionar("perfil", S.OPCOES["perfil_cliente"])
        self._selecionar("telefone_tipo", S.OPCOES["telefone_tipo"])
        self._selecionar("email_tipo", S.OPCOES["email_tipo"])
        self._selecionar("endereco_tipo", S.OPCOES["endereco_tipo"])

        # RG vai num campo livre que pede "Número/emissão/emissor".
        rg = dados.get("rg", "")
        if rg and dados.get("orgao_expedidor"):
            rg = "%s %s" % (rg, dados["orgao_expedidor"])

        valores = dict(dados)
        valores["rg"] = rg
        if valores.get("nome"):
            valores["nome"] = self.nome_no_padrao(valores["nome"])

        for chave_aba, campos in S.ABAS:
            if chave_aba != "aba_pessoais":
                self._clicar(chave_aba, obrigatorio=False)
                self.pagina.wait_for_timeout(1200)
            for campo in campos:
                self._preencher(campo, valores.get(campo), obrigatorio=False)

    def _id_da_url(self):
        try:
            achado = _ID_NA_URL.search(self.pagina.url or "")
            return achado.group(1) if achado else None
        except Exception:
            return None

    # -- caso ------------------------------------------------------------

    def criar_caso(self, ficha, contato_id):
        """
        A tela de casos ainda NÃO foi calibrada.

        Enquanto não for, isto falha de propósito e de forma controlada: o
        contato continua cadastrado e o caso vira pendência no relatório, em vez
        de a automação sair clicando às cegas numa tela que não conhece.
        """
        dados = payload_caso(ficha)
        if not dados.get("tipo_acao"):
            return ResultadoCadastro(
                sucesso=False,
                detalhe="tipo de ação não identificado no contrato — caso não criado")

        if self.somente_leitura:
            self.log.info("[TEST MODE] CASO SERIA CRIADO: %s" % dados.get("titulo"))
            return ResultadoCadastro(sucesso=False, detalhe="TEST_MODE: caso não criado")

        return ResultadoCadastro(
            sucesso=False,
            detalhe="criação de caso ainda não calibrada na tela do Astrea — "
                    "abrir o caso à mão (dados no relatório: %s / %s)"
                    % (dados.get("tipo_acao"), dados.get("parte_contraria") or "—"))

    # -- calibração ------------------------------------------------------

    def calibrar(self):
        """
        Anota como os campos aparecem hoje. Não cadastra nada: abre o
        formulário, lê a tela aba por aba e sai sem salvar.
        """
        achados = {}
        self.pagina.goto(self.rotas["contatos"], wait_until="domcontentloaded")
        self.pagina.wait_for_timeout(2500)
        achados["contatos"] = self._mapear_tela()

        try:
            self._abrir_formulario()
            for chave_aba, _ in S.ABAS:
                if chave_aba != "aba_pessoais":
                    self._clicar(chave_aba, obrigatorio=False)
                    self.pagina.wait_for_timeout(1500)
                achados[chave_aba] = self._mapear_tela()
        except Exception as erro:
            achados["formulario"] = {"erro": str(erro)}
        finally:
            # Sai do formulário sem salvar.
            try:
                self.pagina.goto(self.rotas["contatos"], wait_until="domcontentloaded")
            except Exception:
                pass
        return achados

    def _mapear_tela(self):
        """Lista campos e botões visíveis, com rótulo, placeholder e ng-model."""
        script = """
        () => {
          const visivel = (e) => {
            const r = e.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const rotulo = (e) => {
            if (e.id) {
              const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]');
              if (l) return l.innerText.trim();
            }
            const p = e.closest('.form-group, .field, label, md-input-container, .ga-field');
            if (p) {
              const l = p.querySelector('label');
              if (l) return l.innerText.trim();
            }
            return '';
          };
          const campos = [...document.querySelectorAll('input,select,textarea')]
            .filter(visivel).filter(e => e.id !== 'search').map(e => ({
              tag: e.tagName.toLowerCase(), type: e.type || '', name: e.name || '',
              id: e.id || '', placeholder: e.placeholder || '',
              ngModel: e.getAttribute('ng-model') || '', rotulo: rotulo(e),
              opcoes: e.tagName === 'SELECT'
                ? [...e.options].map(o => o.text).slice(0, 12) : undefined
            }));
          const botoes = [...document.querySelectorAll('button,a[role=button],.btn')]
            .filter(visivel).map(e => ({
              texto: (e.innerText || '').trim().slice(0, 60)
            })).filter(b => b.texto);
          const abas = [...document.querySelectorAll('li.tabs-item, [role=tab]')]
            .filter(visivel).map(e => (e.innerText || '').trim()).filter(Boolean);
          return {url: location.href, campos, botoes, abas};
        }
        """
        try:
            return self.pagina.evaluate(script)
        except Exception as erro:
            return {"erro": str(erro)}

    # -- ritmo -----------------------------------------------------------

    def pausar(self):
        if self.config.astrea_pausa_entre_clientes_s > 0:
            time.sleep(self.config.astrea_pausa_entre_clientes_s)
