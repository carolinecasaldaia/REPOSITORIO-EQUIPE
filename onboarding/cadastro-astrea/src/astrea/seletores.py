#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Onde ficam os "endereços" dos campos na tela do Astrea.

**Calibrado no Astrea real em 13/08/2026**, com a conta do escritório. Não são
palpites: cada seletor abaixo foi lido da tela de contatos e do formulário de
cadastro.

O Astrea é uma aplicação AngularJS, e quase todo campo carrega um atributo
`ng-model` com nome estável (`contact.name`, `address.zipCode`, `contact.job`).
Mirar no `ng-model` é bem mais seguro que mirar em rótulo ou posição: rótulo
muda com tradução e redesenho, `ng-model` só muda se refizerem o formulário.

Toda automação de navegador quebra quando o fornecedor mexe no layout. Para não
precisar programar quando isso acontecer, os seletores podem ser sobrescritos
pelo arquivo:

    ~/.cadastro-astrea/seletores.json

gerado pela calibração (`Cadastrar Clientes.command` → "Calibrar Astrea").

Cada campo tem uma LISTA de estratégias, tentadas em ordem:

    {"tipo": "css",         "valor": "input[ng-model='contact.name']"}
    {"tipo": "rotulo",      "valor": "Nome"}
    {"tipo": "placeholder", "valor": "Digite o nome"}
    {"tipo": "texto",       "valor": "SALVAR"}
"""

import json
from pathlib import Path

ARQUIVO_OVERRIDES = "seletores.json"

# Rotas internas (AngularJS, navegação por hash).
#
# Atenção: a tela de novo contato NÃO tem URL estável — ela é
# `#/main/contacts/add-edit-merge/%5B,,false,%5B%5D,%5D/personal`, com um
# parâmetro serializado. Por isso o cadastro entra clicando em ADICIONAR na
# lista, e não pela URL.
ROTAS = {
    "base": "https://astrea.net.br",
    "login": "https://astrea.net.br/#/login/BR",
    "contatos": "https://astrea.net.br/#/main/contacts",
    "contato_novo": "https://astrea.net.br/#/main/contacts",
    "casos": "https://astrea.net.br/#/main/cases",
}

# Texto que a lista de contatos mostra com o total filtrado:
#   "Mostrando 1 de 1 contato(s)"
PADRAO_CONTAGEM = r"Mostrando\s+(\d+)\s+de\s+(\d+)\s+contato"

# Padrão do link de detalhe: #/main/contacts/detail/5446980264558592/data
PADRAO_ID_CONTATO = r"contacts?[-/]detail/(\d+)"

PADRAO = {
    # --- login --------------------------------------------------------
    "login_email": [
        {"tipo": "css", "valor": "input[type=email]"},
        {"tipo": "css", "valor": "input[name=email]"},
        {"tipo": "placeholder", "valor": "E-mail"},
    ],
    "login_senha": [
        {"tipo": "css", "valor": "input[type=password]"},
        {"tipo": "placeholder", "valor": "Senha"},
    ],
    "login_entrar": [
        {"tipo": "texto", "valor": "ENTRAR"},
        {"tipo": "texto", "valor": "Entrar"},
        {"tipo": "css", "valor": "button[type=submit]"},
    ],

    # --- lista de contatos --------------------------------------------
    # A busca da LISTA (não a busca global do topo, que é #search).
    "busca_contato": [
        {"tipo": "css", "valor": "input[ng-model='$ctrl.data.filter.input']"},
        {"tipo": "placeholder", "valor": "Procure por nome, apelido ou nome fantasia"},
    ],
    "botao_novo_contato": [
        {"tipo": "texto", "valor": "ADICIONAR"},
        {"tipo": "texto", "valor": "Adicionar"},
    ],
    "linha_resultado": [
        {"tipo": "css", "valor": "a[href*='contacts/detail/']"},
        {"tipo": "css", "valor": "a[href*='contacts-detail']"},
    ],

    # --- abas do formulário -------------------------------------------
    "aba_pessoais": [
        {"tipo": "css", "valor": "li.tabs-item:has-text('Informações pessoais')"},
        {"tipo": "texto", "valor": "Informações pessoais"},
    ],
    "aba_complementares": [
        {"tipo": "css", "valor": "li.tabs-item:has-text('Informações complementares')"},
        {"tipo": "texto", "valor": "Informações complementares"},
    ],
    "aba_documentacao": [
        {"tipo": "css", "valor": "li.tabs-item:has-text('Documentação')"},
        {"tipo": "texto", "valor": "Documentação"},
    ],

    # --- aba "Informações pessoais" -----------------------------------
    "tipo_pessoa_fisica": [
        {"tipo": "css", "valor": "input#person"},
    ],
    "tipo_pessoa_juridica": [
        {"tipo": "css", "valor": "input#company"},
    ],
    "perfil": [
        {"tipo": "css", "valor": "select[ng-model='contact.classification']"},
    ],
    "nome": [
        {"tipo": "css", "valor": "input[ng-model='contact.name']"},
        {"tipo": "css", "valor": "input#contactName"},
        {"tipo": "placeholder", "valor": "Digite o nome"},
    ],
    "apelido": [
        {"tipo": "css", "valor": "input[ng-model='contact.nickname']"},
    ],
    "telefone_tipo": [
        {"tipo": "css", "valor": "select[ng-model='telephone.typeEnum']"},
    ],
    "telefone": [
        {"tipo": "css", "valor": "input[ng-model='telephone.number']"},
        {"tipo": "placeholder", "valor": "Digite o telefone"},
    ],
    "email_tipo": [
        {"tipo": "css", "valor": "select[ng-model='email.typeEnum']"},
    ],
    "email": [
        {"tipo": "css", "valor": "input[ng-model='email.address']"},
        {"tipo": "placeholder", "valor": "Digite o email"},
    ],
    "endereco_tipo": [
        {"tipo": "css", "valor": "select[ng-model='address.typeEnum']"},
    ],
    "cep": [
        {"tipo": "css", "valor": "input[ng-model='address.zipCode']"},
        {"tipo": "placeholder", "valor": "Digite o CEP"},
    ],
    "logradouro": [
        {"tipo": "css", "valor": "input[ng-model='address.street']"},
        {"tipo": "placeholder", "valor": "Digite a rua"},
    ],
    "numero": [
        {"tipo": "css", "valor": "input[ng-model='address.number']"},
        {"tipo": "placeholder", "valor": "Digite o número"},
    ],
    "bairro": [
        {"tipo": "css", "valor": "input[ng-model='address.district']"},
        {"tipo": "placeholder", "valor": "Digite o bairro"},
    ],
    "complemento": [
        {"tipo": "css", "valor": "input[ng-model='address.complement']"},
        {"tipo": "placeholder", "valor": "Digite o complemento"},
    ],
    "cidade": [
        {"tipo": "css", "valor": "input[ng-model='address.city']"},
        {"tipo": "placeholder", "valor": "Digite a cidade"},
    ],
    "uf": [
        {"tipo": "css", "valor": "input[ng-model='address.state']"},
        {"tipo": "placeholder", "valor": "Digite o estado"},
    ],

    # --- aba "Informações complementares" ------------------------------
    "profissao": [
        {"tipo": "css", "valor": "input[ng-model='contact.job']"},
        {"tipo": "placeholder", "valor": "Digite a profissão"},
    ],
    "estado_civil": [
        {"tipo": "css", "valor": "input[ng-model='contact.maritalStatus']"},
        {"tipo": "placeholder", "valor": "Digite o estado civil"},
    ],
    "nacionalidade": [
        {"tipo": "css", "valor": "input[ng-model='contact.nationality']"},
    ],

    # --- aba "Documentação" --------------------------------------------
    # O CPF não tem ng-model próprio (é 'model', de um componente genérico):
    # aqui o placeholder é a âncora confiável.
    "cpf": [
        {"tipo": "placeholder", "valor": "Digite o CPF"},
    ],
    "cnpj": [
        {"tipo": "placeholder", "valor": "Digite o CNPJ"},
    ],
    # O campo do RG é livre e pede "Número/emissão/emissor" num só lugar.
    "rg": [
        {"tipo": "css", "valor": "input[ng-model='contact.idDocumentNumber']"},
    ],

    "salvar_contato": [
        {"tipo": "texto", "valor": "SALVAR"},
        {"tipo": "css", "valor": "button[type=submit].ga--is-primary"},
    ],

    # --- caso / pasta ---------------------------------------------------
    # NÃO calibrado ainda: a tela de casos não foi mapeada. Enquanto isso, a
    # criação do caso falha de forma controlada (o contato continua cadastrado
    # e o caso vira pendência no relatório).
    "botao_novo_caso": [
        {"tipo": "texto", "valor": "ADICIONAR"},
    ],
    "caso_cliente": [
        {"tipo": "rotulo", "valor": "Cliente"},
    ],
    "caso_titulo": [
        {"tipo": "rotulo", "valor": "Título"},
    ],
    "caso_parte_contraria": [
        {"tipo": "rotulo", "valor": "Parte contrária"},
    ],
    "salvar_caso": [
        {"tipo": "texto", "valor": "SALVAR"},
    ],
}

# Opções dos menus suspensos, como aparecem hoje na tela.
OPCOES = {
    "perfil_cliente": "Cliente",
    "telefone_tipo": "Celular pessoal",
    "email_tipo": "Pessoal",
    "endereco_tipo": "Pessoal",
}

# Campos que ficam em cada aba, na ordem de preenchimento.
ABAS = (
    ("aba_pessoais", ("nome", "telefone", "email", "cep", "logradouro",
                      "numero", "complemento", "bairro", "cidade", "uf")),
    ("aba_documentacao", ("cpf", "cnpj", "rg")),
    ("aba_complementares", ("profissao", "estado_civil", "nacionalidade")),
)


def carregar(pasta_dados: Path):
    """Padrões do arquivo, sobrescritos pelo que a calibração descobriu."""
    seletores = {chave: list(valor) for chave, valor in PADRAO.items()}
    rotas = dict(ROTAS)

    arquivo = Path(pasta_dados) / ARQUIVO_OVERRIDES
    if arquivo.exists():
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except ValueError:
            return seletores, rotas, "arquivo de seletores inválido (JSON)"
        for chave, valor in (dados.get("rotas") or {}).items():
            rotas[chave] = valor
        for chave, valor in (dados.get("seletores") or {}).items():
            if isinstance(valor, dict):
                valor = [valor]
            # O que veio da calibração é tentado ANTES do padrão.
            seletores[chave] = list(valor) + seletores.get(chave, [])
        return seletores, rotas, "calibrado em %s" % dados.get("calibrado_em", "?")
    return seletores, rotas, "seletores calibrados em 13/08/2026 (embutidos)"


def salvar_calibracao(pasta_dados: Path, seletores: dict, rotas: dict = None,
                      quando: str = ""):
    arquivo = Path(pasta_dados) / ARQUIVO_OVERRIDES
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {"calibrado_em": quando, "seletores": seletores,
                "rotas": rotas or {}}
    arquivo.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return arquivo
