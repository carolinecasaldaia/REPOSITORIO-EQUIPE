#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrato comum dos adaptadores do Astrea.

Todo o resto da automação (varredura, extração, validação, controle, logs)
conversa só com esta interface. Trocar o jeito de entrar no Astrea — navegador
hoje, API oficial no dia em que a Aurum publicar uma — é trocar um arquivo,
sem mexer em mais nada.

Adaptadores disponíveis:
    navegador  → Playwright, com a conta da própria advogada (padrão)
    planilha   → não toca no Astrea; gera planilha de conferência/importação
    dry-run    → não toca em nada; só mostra o que seria enviado
"""


class ErroAstrea(RuntimeError):
    """Falha ao falar com o Astrea. Vira status ERRO NO CADASTRO."""


class ErroAutenticacao(ErroAstrea):
    """Login recusado, sessão expirada ou 2FA no caminho."""


class ErroSessaoPerdida(ErroAutenticacao):
    """
    A sessão caiu NO MEIO da rodada — o Astrea voltou para a tela de login.

    Não é problema do cliente que estava sendo processado, e insistir nos
    próximos só produziria uma fila de erros falsos. Quem receber isto deve
    parar a rodada inteira e devolver os clientes para a fila.
    """


class BuscaIndisponivel(ErroAstrea):
    """
    O adaptador não consegue verificar duplicidade.

    Erro de propósito: sem poder conferir se o CPF já existe, a automação
    NÃO cadastra — o risco de duplicar cadastro é maior que o ganho.
    """


class ResultadoBusca(object):
    def __init__(self, encontrado=False, astrea_id=None, nome="", detalhe="",
                 suspeitas=None):
        self.encontrado = encontrado
        self.astrea_id = astrea_id
        self.nome = nome
        self.detalhe = detalhe
        # Não é duplicidade confirmada, mas é motivo para gente olhar antes de
        # cadastrar — ex.: existe alguém com o mesmo nome, sem CPF preenchido.
        self.suspeitas = list(suspeitas or [])

    def __repr__(self):
        return "<ResultadoBusca encontrado=%s id=%s>" % (self.encontrado,
                                                         self.astrea_id)


class ResultadoCadastro(object):
    """
    O que aconteceu na tentativa de cadastro.

    `a_confirmar` é o terceiro estado, entre o sucesso e o erro: o cadastro foi
    ENVIADO e provavelmente gravado, mas o Astrea ainda não o devolveu na busca.
    Existe porque tratar isso como erro custou caro — em 08/09/2026 o Wladson
    acabou com dois contatos, já que a rodada seguinte cadastrou de novo o que
    já estava lá.
    """

    def __init__(self, sucesso=False, astrea_id=None, detalhe="", erro="",
                 a_confirmar=False):
        self.sucesso = sucesso
        self.astrea_id = astrea_id
        self.detalhe = detalhe
        self.erro = erro
        self.a_confirmar = a_confirmar

    def __repr__(self):
        return "<ResultadoCadastro sucesso=%s id=%s>" % (self.sucesso,
                                                         self.astrea_id)


class AdaptadorAstrea(object):
    """Interface. Todo adaptador implementa estes cinco métodos."""

    nome = "base"
    escreve_no_astrea = False
    verifica_duplicidade = False

    def __init__(self, config, log):
        self.config = config
        self.log = log

    # -- ciclo de vida ---------------------------------------------------

    def conectar(self):
        """Abre sessão. Deve falhar cedo e com mensagem clara."""

    def encerrar(self):
        """Fecha tudo. Chamado sempre, inclusive quando deu erro."""

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, *_):
        self.encerrar()

    # -- operações -------------------------------------------------------

    def buscar_por_documento(self, documento: str,
                             nome_cliente: str = "") -> ResultadoBusca:
        raise BuscaIndisponivel(
            "O adaptador %r não sabe consultar CPF/CNPJ no Astrea." % self.nome)

    def cadastrar_contato(self, ficha) -> ResultadoCadastro:
        raise NotImplementedError

    def criar_caso(self, ficha, contato_id) -> ResultadoCadastro:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Tradução da ficha para os campos do Astrea
# ---------------------------------------------------------------------------

def payload_contato(ficha):
    """
    Só o que foi encontrado nos documentos entra aqui.

    Campo não localizado simplesmente não aparece no dicionário — nunca vai
    string vazia "para preencher", nunca vai valor presumido.
    """
    dados = {}

    def por(chave, nome_campo):
        campo = ficha.campo(nome_campo)
        if campo.preenchido:
            dados[chave] = campo.valor

    dados["tipo_pessoa"] = "juridica" if ficha.pessoa_juridica else "fisica"
    dados["perfil"] = "cliente"

    por("nome", "nome")
    por("cpf", "cpf")
    por("cnpj", "cnpj")
    por("rg", "rg")
    por("orgao_expedidor", "orgao_expedidor")
    por("nacionalidade", "nacionalidade")
    por("estado_civil", "estado_civil")
    por("profissao", "profissao")
    por("data_nascimento", "data_nascimento")
    por("email", "email")
    por("telefone", "telefone")
    por("cep", "cep")
    por("logradouro", "logradouro")
    por("numero", "numero")
    por("complemento", "complemento")
    por("bairro", "bairro")
    por("cidade", "cidade")
    por("uf", "uf")
    return dados


def payload_caso(ficha):
    dados = {}
    if ficha.tipo_acao.preenchido:
        dados["tipo_acao"] = ficha.tipo_acao.valor
    if ficha.banco_adverso.preenchido:
        dados["parte_contraria"] = ficha.banco_adverso.valor
    if ficha.veiculo.preenchido:
        dados["objeto"] = ficha.veiculo.valor
    if ficha.nome:
        dados["titulo"] = "%s — %s" % (ficha.nome,
                                       ficha.tipo_acao.valor or "Ação")
    return dados
