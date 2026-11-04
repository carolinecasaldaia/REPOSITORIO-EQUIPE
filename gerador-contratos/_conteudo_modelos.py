# -*- coding: utf-8 -*-
"""
Texto dos quatro modelos mestres do onboarding (contrato, procuração,
declaração de hipossuficiência e declaração de residência).

Este arquivo é a FONTE do texto. Quem o usa é o _construir_modelos.py, que
transforma tudo em .docx com o timbrado, as fontes e as margens dos contratos
reais do escritório.

No dia a dia NÃO é preciso mexer aqui: para corrigir uma cláusula basta abrir
o "MODELO MESTRE - CONTRATO.docx" no Word, editar e salvar. Este arquivo só
serve para reconstruir os modelos do zero.

--------------------------------------------------------------------------
COMO O TEXTO É ESCRITO AQUI
--------------------------------------------------------------------------
  *texto*        -> negrito
  _texto_        -> negrito + sublinhado
  ¶              -> quebra de linha dentro do mesmo parágrafo
  {{CAMPO}}      -> campo preenchido pelo gerador
  {{+TAG}}…{{-TAG}}  -> trecho que entra ou sai NO MEIO da frase
  ('cond','+TAG') / ('cond','-TAG') -> parágrafos inteiros que entram ou saem
  {{#}}          -> número da cláusula (1ª, 2ª, 3ª…), refeito conforme os
                    blocos que sobrarem

TAGS de bloco usadas no contrato
  TIPO_FIN        revisional de financiamento
  TIPO_EMPGAR     revisional de empréstimo com veículo em garantia
  TIPO_EMP        revisional de empréstimo
  TIPO_BUSCA      defesa em busca e apreensão (veículo NÃO apreendido)
  TIPO_APREENDIDO defesa em busca e apreensão com veículo apreendido
  P1MULTI/P1UNI   1ª faixa de parcelas (várias parcelas / parcela única)
  P2              2ª faixa de parcelas (quando o parcelamento tem dois valores)
  GANHO           honorários finais de 20% sobre o ganho
  RECORRENCIA     cláusulas do cartão de crédito na recorrência
  BOLETO          aviso de boletos mensais em nome do escritório
  SO_REVISIONAL   cláusulas que só existem nas revisionais
  RESP_ASSIN      bloco de assinatura do cliente responsável
"""

# ---------------------------------------------------------------- CONTRATO

ESCRITORIO = (
    'Pelo presente Instrumento Particular de Contrato de Prestação de Serviços '
    'Advocatícios que entre si fazem, de um lado, como Advogada Contratada, '
    '*CAROLINE MACEDO SOCIEDADE INDIVIDUAL DE ADVOCACIA*, pessoa jurídica de '
    'direito privado com CNPJ sob o nº 58.173.643/0001-17, inscrita na OAB/AL, '
    'sob o nº 2400582, e sua sócia administradora '
    '*CAROLINE NEIVA CHRISTOFANO MACEDO*, advogada inscrita na *OAB/AL 15.766*, '
    '*OAB/SP 528.725* e *OAB/PE 70.091*, com endereço profissional na Rua Dr. '
    'Luís Pontes de Miranda, nº 36, Centro – *Edifício Delmiro Gouveia – Sala 1107* '
    '- Maceió – AL, CEP: 57.020-140 e do outro lado, como Cliente Contratante '
    '*{{CLI_NOME}}*, {{CLI_NACIONALIDADE}}, {{CLI_ESTADO_CIVIL}}, {{CLI_PROFISSAO}}, '
    '{{CLI_PORTADOR}} do RG sob o nº {{CLI_RG}}, {{CLI_INSCRITO}} no CPF de nº '
    '{{CLI_CPF}}, {{CLI_DOMICILIADO}} {{CLI_PREP}} {{CLI_ENDERECO}}, endereço '
    'eletrônico {{CLI_EMAIL}} e contato telefônico {{CLI_TELEFONE}}'
    '{{+RESP}} e como Cliente Responsável *{{RESP_NOME}}*, {{RESP_NACIONALIDADE}}, '
    '{{RESP_ESTADO_CIVIL}}, {{RESP_PROFISSAO}}, {{RESP_PORTADOR}} do RG sob o nº '
    '{{RESP_RG}}, {{RESP_INSCRITO}} no CPF de nº {{RESP_CPF}}, {{RESP_DOMICILIADO}} '
    '{{RESP_PREP}} {{RESP_ENDERECO}}, endereço eletrônico {{RESP_EMAIL}} e contato '
    'telefônico {{RESP_TELEFONE}}{{-RESP}}, mediante as cláusulas e condições seguintes:'
)

_ABERTURA_CL1 = (
    '*Cláusula {{#}}.* Advogada contratada obriga-se, diante de mandato judicial '
    'que lhe foi outorgado, a prestar seus serviços jurídicos profissionais na '
    'defesa dos direitos do contratante atuando com zelo, diligência e observância '
    'das normas éticas e legais aplicáveis, promovendo o acompanhamento processual '
    'perante qualquer instância, juízo ou tribunal, quando necessário, para '
)

BLOCOS_CONTRATO = [
    ('titulo', 'CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS'),
    ('vazio',), ('vazio',), ('vazio',), ('vazio',),

    ('cab', ESCRITORIO),
    ('vazio',), ('vazio',),

    # ------------------------------------------------ Cláusula 1ª (objeto)
    ('cond', '+TIPO_FIN'),
    ('p', _ABERTURA_CL1 +
        'realizar o ingresso da *Ação Revisional em desfavor do {{BANCO}}*, '
        'referente ao contrato de financiamento do veículo *{{VEICULO}}*.'),
    ('cond', '-TIPO_FIN'),

    ('cond', '+TIPO_EMPGAR'),
    ('p', _ABERTURA_CL1 +
        'realizar o ingresso da *Ação Revisional de Empréstimo com garantia de '
        'veículo em desfavor do {{BANCO}}*, referente ao contrato sob garantia do '
        'veículo *{{VEICULO}}*.'),
    ('cond', '-TIPO_EMPGAR'),

    ('cond', '+TIPO_EMP'),
    ('p', _ABERTURA_CL1 +
        'realizar o ingresso da *Ação Revisional de Empréstimo em desfavor do '
        '{{BANCO}}*, referente ao contrato de empréstimo{{+CONTRATO_NUM}} '
        'nº *{{CONTRATO_NUM}}*{{-CONTRATO_NUM}} firmado entre as partes.'),
    ('cond', '-TIPO_EMP'),

    ('cond', '+TIPO_BUSCA'),
    ('p', _ABERTURA_CL1 +
        'realizar a defesa na *Ação de Busca e Apreensão sob o nº {{PROCESSO}}*'
        '{{+VARA}} distribuída na *{{VARA}}*{{+COMARCA}} da Comarca de '
        '*{{COMARCA}}*{{-COMARCA}}{{-VARA}}, Estado {{ESTADO}}, referente ao '
        'contrato de financiamento do veículo *{{VEICULO}}* – '
        '*Veículo não se encontra apreendido*.'),
    ('cond', '-TIPO_BUSCA'),

    ('cond', '+TIPO_APREENDIDO'),
    ('p', _ABERTURA_CL1 +
        'realizar a defesa da *Ação de Busca e Apreensão sob o nº {{PROCESSO}}*'
        '{{+VARA}} distribuída na *{{VARA}}*{{+COMARCA}} da Comarca de '
        '*{{COMARCA}}*{{-COMARCA}}{{-VARA}} – *veículo apreendido no Estado '
        '{{ESTADO}}{{+DATA_APREENSAO}}, na data de {{DATA_APREENSAO}}{{-DATA_APREENSAO}}*, '
        'referente ao contrato do veículo *{{VEICULO}}*.'),
    ('cond', '-TIPO_APREENDIDO'),

    ('vazio',),

    # ------------------------------------------------ Cláusula 2ª (honorários)
    ('p', '*Cláusula {{#}}.* Em remuneração, o cliente pagará à advogada a título '
          'de _honorários advocatícios_, a importância de *R$ {{TOTAL}}* '
          '({{TOTAL_EXTENSO}}), sendo este cobrado da seguinte maneira:'),
    ('vazio',),
    ('p', '- Entrada no valor de *R$ {{ENTRADA}}* ({{ENTRADA_EXTENSO}}) na data de '
          '*{{DATA_ENTRADA}}*;'),
    ('vazio',),

    ('cond', '+P1MULTI'),
    ('p', '- *{{QTD1}}* ({{QTD1_EXTENSO}}) parcelas de *R$ {{VALOR1}}* '
          '({{VALOR1_EXTENSO}}) com início em *{{INICIO1}}* e a última em *{{FIM1}}*'
          '{{+REC}} - *CARTÃO DE CRÉDITO NA RECORRÊNCIA*{{-REC}}.'),
    ('cond', '-P1MULTI'),
    ('cond', '+P1UNI'),
    ('p', '- *{{QTD1}}* ({{QTD1_EXTENSO}}) parcela de *R$ {{VALOR1}}* '
          '({{VALOR1_EXTENSO}}) na data de *{{INICIO1}}*.'),
    ('cond', '-P1UNI'),

    ('cond', '+P2'),
    ('vazio',),
    ('p', '- *{{QTD2}}* ({{QTD2_EXTENSO}}) parcelas de *R$ {{VALOR2}}* '
          '({{VALOR2_EXTENSO}}) com início em *{{INICIO2}}* e a última em *{{FIM2}}*'
          '{{+REC}} - *CARTÃO DE CRÉDITO NA RECORRÊNCIA*{{-REC}}.'),
    ('cond', '-P2'),

    ('cond', '+GANHO'),
    ('vazio',),
    ('p', '- A título de honorários advocatícios finais, pagará a importância '
          'correspondente a *{{PCT_GANHO}}% ({{PCT_GANHO_EXTENSO}} por cento) '
          'sob o ganho*.'),
    ('cond', '-GANHO'),

    ('vazio',),
    ('p', 'O contratante fica ciente que o pagamento da entrada deverá ser '
          'realizado por meio de *BOLETO*, emitido pelo escritório, pelo sistema '
          '*{{SISTEMA}}*, de titularidade do Contratado: '
          '*CAROLINE MACEDO SOCIEDADE INDIVIDUAL DE ADVOCACIA*, e ser realizado o '
          'envio do respectivo comprovante de pagamento.'),
    ('vazio',),

    ('cond', '+BOLETO'),
    ('p', 'Os boletos referentes aos honorários, correspondente ao parcelamento, '
          'serão gerados *EM NOME DO ESCRITÓRIO* e encaminhados de forma automática '
          'no *E-MAIL, WHATSAPP E SMS* de cadastro do contratante mês a mês, devendo '
          'o contratante verificar mensalmente o e-mail para ter acesso aos boletos '
          'para realização do pagamento.'),
    ('vazio',),
    ('cond', '-BOLETO'),

    ('cond', '+RECORRENCIA'),
    ('p', 'O(a) CONTRATANTE obriga-se a manter ativo, válido e apto o meio de '
          'pagamento indicado para cobrança recorrente dos honorários advocatícios, '
          'devendo assegurar a existência de saldo, crédito ou limite suficiente na '
          'data de vencimento de cada parcela.'),
    ('vazio',),
    ('p', 'Em caso de cancelamento, bloqueio, troca, substituição, vencimento, '
          'perda, roubo, contestação indevida da cobrança ou qualquer outro fato que '
          'impeça a efetivação do pagamento, o(a) CONTRATANTE deverá comunicar o '
          'ESCRITÓRIO de forma imediata, indicando novo meio de pagamento válido.'),
    ('vazio',),
    ('p', 'A falta de comunicação imediata e/ou a ausência de regularização do '
          'pagamento no vencimento caracterizará mora automática, independentemente '
          'de aviso, notificação ou interpelação, autorizando o ESCRITÓRIO a aplicar '
          'as penalidades contratuais cabíveis, inclusive multa, juros, correção '
          'monetária, vencimento antecipado das parcelas restantes, suspensão da '
          'atuação em atos não urgentes e adoção das medidas de cobrança pertinentes.'),
    ('vazio',),
    ('p', 'Fica expressamente estabelecido que problemas relacionados ao cartão, '
          'limite, banco emissor, cancelamento, bloqueio ou alteração do meio de '
          'pagamento não afastam a obrigação do(a) CONTRATANTE de quitar pontualmente '
          'os honorários contratados.'),
    ('vazio',),
    ('cond', '-RECORRENCIA'),

    ('p', '*Parágrafo 1º.* O lembrete da cobrança será encaminhado '
          'OBRIGATÓRIAMENTE no _E-MAIL,_ com *05 (CINCO) DIAS DE ANTECEDÊNCIA* pelo '
          'sistema *{{SISTEMA}}*;'),
    ('vazio',),
    ('p', '*Parágrafo 2º.* O atraso no pagamento dos honorários advocatícios seja '
          'em única ou em mais parcelas, será cobrada multa de *10%* e juros de *1%* '
          'ao mês a partir do vencimento;'),
    ('vazio',),
    ('p', '*Parágrafo 3º.* Sem prejuízo da cobrança de multa e juros apontados no '
          'parágrafo anterior, o CONTRATANTE anui que, em caso de inadimplência '
          'correspondente a *01 (uma) parcela*, a CONTRATADA irá realizar a '
          '*NEGATIVAÇÃO* junto aos órgãos de proteção ao crédito *(SPC/SERASA)*;'),
    ('vazio',),
    ('p', '*Parágrafo 4º.* Sem prejuízo da cobrança de multa e juros apontados no '
          'parágrafo 2º, o CONTRATANTE anui que, em caso de inadimplência '
          'correspondente a *02 (duas) parcelas ou mais*, a CONTRATADA irá suspender '
          'os trabalhos processuais, requerendo a renúncia do processo, sem prejuízo '
          'dos valores vencidos e vincendos, bem como, sendo encaminhado para '
          'cartório de protesto, para que o título seja protestado;'),
    ('vazio',),
    ('p', '*Parágrafo 5º.* Em caso de inadimplência de *03 (três) parcelas ou mais* '
          'em atraso, poderá a CONTRATADA requerer a penhora de até *30% (trinta por '
          'cento)* do salário em sede de execução processual;'),
    ('vazio',),
    ('p', '*Parágrafo 6º.* Ao CONTRATANTE caberá o pagamento das custas processuais '
          '(no caso de não enquadramento da Justiça Gratuita), deslocamento, '
          'alojamento, alimentação e demais despesas que forem necessárias ao bom '
          'andamento da ação, devendo a CONTRATADA prestar contas de forma '
          'transparente, bem como o fornecimento de documentos e informações que o '
          'contratado solicitar.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* A CONTRATANTE autoriza desde já o destaque contratual '
          'dos honorários advocatícios quando legalmente possível.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* Os atendimentos e comunicações ocorrerão em horário '
          'comercial, de segunda a sexta-feira, das *08h às 17h*, por meio de '
          'telefone, WhatsApp, e-mail ou atendimento presencial mediante agendamento '
          'prévio. Mensagens encaminhadas fora do horário comercial poderão ser '
          'respondidas no próximo dia útil. Deixando claro que, as mensagens pelo '
          'Whatsapp serão respondidas por ordem de chegada.'),
    ('vazio',),
    ('p', '*Parágrafo único.* A CONTRATANTE declara estar ciente de que não há '
          'obrigação de envio individualizado de todas as movimentações processuais, '
          'comprometendo-se a CONTRATADA a comunicar os atos relevantes que exijam '
          'providências ou possam impactar diretamente o andamento da demanda.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* É de inteira responsabilidade do contratante as '
          'informações prestadas ao contratado para propositura da presente ação, '
          'confirmando pelo presente instrumento a sua veracidade.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* A CONTRATANTE declara ter recebido orientação jurídica '
          'prévia acerca dos serviços contratados e compromete-se a fornecer à '
          'CONTRATADA todos os documentos, informações e meios necessários à adequada '
          'defesa de seus interesses. Compromete-se ainda a:'),
    ('lista', 'a) Prestar informações verídicas, completas e atualizadas, '
              'presumindo-se autênticos e verdadeiros os documentos e informações '
              'fornecidos;'),
    ('lista', 'b) Entregar todos os documentos, provas e informações necessárias ao '
              'ajuizamento e regular andamento da demanda;'),
    ('lista', 'c) Comunicar imediatamente qualquer alteração de endereço, telefone, '
              'e-mail ou outro meio de contato;'),
    ('lista', 'd) Comparecer pontualmente às audiências, reuniões ou demais atos '
              'processuais para os quais for convocada;'),
    ('lista', 'e) O não comparecimento injustificado ou atraso da CONTRATANTE poderá '
              'acarretar arquivamento do processo, revelia, perda de direitos ou '
              'demais prejuízos processuais, não podendo a CONTRATADA ser '
              'responsabilizada por tais consequências;'),
    ('lista', 'f) A ausência de documentos indispensáveis, à prestação de informações '
              'falsas, a apresentação de documentos inidôneos ou falsificados, bem '
              'como a omissão de fatos relevantes, poderão comprometer o andamento da '
              'demanda, não podendo a CONTRATADA ser responsabilizada por eventual '
              'prejuízo decorrente dessas condutas;'),
    ('lista', 'g) A CONTRATANTE declara estar ciente de que a utilização de '
              'documentos falsos, poderá ensejar sua responsabilização civil, '
              'administrativa e criminal, nos termos da legislação vigente, '
              'respondendo exclusivamente pelos danos e consequências decorrentes de '
              'sua conduta, inclusive perante autoridades judiciais, administrativas '
              'e órgãos de classe eventualmente envolvidos.'),
    ('vazio',),
    ('p', '*Parágrafo único.* Ocorrendo ausência injustificada da CONTRATANTE em '
          'audiência previamente agendada, após ter sido regularmente cientificada da '
          'data, horário, local e demais orientações necessárias, ficará obrigada ao '
          'pagamento de honorários compensatórios correspondentes ao valor de '
          '*R$ 750,00 (setecentos e cinquenta reais)*, destinados a ressarcir o tempo '
          'profissional disponibilizado, preparação do ato processual, deslocamento e '
          'comparecimento da CONTRATADA ao compromisso judicial frustrado por fato '
          'exclusivamente atribuível à CONTRATANTE. O referido valor não substitui '
          'nem afasta os honorários contratuais já pactuados neste instrumento.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* Fica entendido que os honorários de condenação da parte '
          'contrária (honorários de sucumbência), se houverem, pertencerão a '
          'advogada, independentemente dos ora contratados, nos termos da lei.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* O total dos honorários poderá ser exigido imediatamente, '
          'se houver composição amigável realizada por qualquer das partes litigantes, '
          'ou no caso de não prosseguimento da ação por qualquer circunstância não '
          'determinada pela advogada contratada, ou ainda, se lhe for cassado o '
          'mandato sem culpa.'),
    ('vazio',),
    ('p', '*Parágrafo Único.* Em caso de rescisão do presente contrato por parte do '
          'CONTRATANTE para contratação de outro advogado para realização do mesmo '
          'serviço, o CONTRATANTE se compromete em pagar ao CONTRATADO o valor total '
          'devido dos honorários.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* Em caso de rescisão do presente contrato por iniciativa '
          'do(a) CONTRATANTE, após o pagamento da entrada, ou antes do vencimento da '
          'primeira parcela, ficará o(a) CONTRATANTE obrigado(a) ao pagamento de '
          '*multa rescisória equivalente a 02 (dois) salários mínimos vigentes*, em '
          'razão dos serviços já iniciados e/ou disponibilizados pelo escritório, '
          'incluindo, mas não se limitando à consultoria jurídica, análise técnica do '
          'caso, estudo documental, elaboração de estratégia, confecção de petição '
          'inicial, utilização dos sistemas internos do escritório, cadastro, '
          'organização administrativa e demais providências necessárias ao início da '
          'atuação profissional.'),
    ('vazio',),
    ('p', '*Parágrafo 1º.* A multa prevista nesta cláusula possui natureza '
          'compensatória, considerando o tempo técnico despendido, a reserva da agenda '
          'profissional, a mobilização da equipe jurídica e administrativa, bem como a '
          'impossibilidade de restituição integral dos atos já praticados pelo '
          'escritório.'),
    ('vazio',),
    ('p', '*Parágrafo 2º.* Caso já tenha havido protocolo de petição, distribuição da '
          'ação, realização de audiência, manifestação processual, negociação '
          'extrajudicial, acordo, atendimento estratégico ou qualquer outro ato '
          'jurídico relevante, os honorários correspondentes aos serviços efetivamente '
          'prestados serão devidos de forma proporcional, sem prejuízo da multa '
          'rescisória aqui prevista.'),
    ('vazio',),
    ('p', '*Parágrafo 3º.* A desistência, arrependimento, abandono da demanda, '
          'ausência de envio de documentos, não colaboração do(a) CONTRATANTE, mudança '
          'de advogado ou tentativa de solução direta com a parte contrária não '
          'afastam a obrigação de pagamento dos valores devidos ao escritório, quando '
          'já iniciada a prestação dos serviços contratados.'),
    ('vazio',),
    ('p', '*Parágrafo 4º.* A rescisão deverá ser formalizada por escrito, por meio '
          'físico ou eletrônico, somente produzindo efeitos após a ciência expressa do '
          'escritório, permanecendo exigíveis os valores vencidos, vincendos e/ou '
          'proporcionais até a data da comunicação formal.'),
    ('vazio',),
    ('p', '*Parágrafo 5º.* A ausência de pagamento dos valores previstos nesta '
          'cláusula autoriza o escritório a promover a cobrança extrajudicial ou '
          'judicial do débito, acrescido de correção monetária, juros, multa, custas e '
          'honorários advocatícios de cobrança, quando cabíveis.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* São *OBRIGAÇÕES DO CONTRATADO*: promover a defesa dos '
          'interesses do Contratante na ação já mencionada, até segunda instância, com '
          'diligência e dedicação.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* A CONTRATANTE declara estar ciente de que plataformas de '
          'consulta processual de terceiros, incluindo *Jusbrasil* e similares, podem '
          'apresentar informações desatualizadas, incompletas, automatizadas ou '
          'divergentes dos sistemas oficiais dos Tribunais.'),
    ('vazio',),
    ('p', '*Parágrafo 1º.* Qualquer informação relacionada ao processo deverá ser '
          'confirmada diretamente com a CONTRATADA por meio dos canais oficiais '
          'informados neste contrato.'),
    ('vazio',),
    ('p', '*Parágrafo 2º.* A CONTRATADA não se responsabiliza por interpretações '
          'equivocadas, alarmismos, conclusões precipitadas ou prejuízos decorrentes '
          'da consulta exclusiva a plataformas de terceiros. O acompanhamento '
          'processual oficial será realizado por meio dos sistemas dos Tribunais '
          'competentes e das informações prestadas diretamente pela CONTRATADA.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* A CONTRATANTE declara estar ciente de que informações '
          'obtidas por meio do *ChatGPT, TikTok, Instagram, YouTube, Jusbrasil* e '
          'demais plataformas digitais possuem caráter meramente informativo e não '
          'substituem a análise jurídica individualizada realizada pela CONTRATADA, '
          'prevalecendo, para a condução do caso, exclusivamente a orientação '
          'profissional da CONTRATADA.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* Em observância ao sigilo profissional previsto no '
          'Estatuto da Advocacia, no Código de Ética e Disciplina da OAB e na '
          'legislação vigente, a CONTRATADA prestará informações sobre o processo '
          '*exclusivamente à CONTRATANTE*. Nenhuma informação processual, estratégia '
          'jurídica, documento, cópia de autos, andamento processual ou dado '
          'relacionado à demanda será fornecido a familiares, cônjuges, companheiros, '
          'namorados, amigos, representantes ou quaisquer terceiros, ainda que possuam '
          'vínculo de parentesco com a CONTRATANTE.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* O Contratante fica obrigado a, sempre que houver mudança '
          'de endereço, telefone ou e-mail, comunicar imediatamente ao Contratado.'),
    ('vazio',),
    ('p', '*Parágrafo 1º.* A falta de contato com o CONTRATANTE, ensejará em renúncia '
          'processual, sem prejuízo dos honorários vencidos e vincendos. Tendo em vista '
          'que, a comunicação com o CONTRATANTE é extremamente importante para o bom '
          'andamento da Ação. Por meio da comunicação será realizada informações '
          'processuais, solicitação de documentos para juntada no processo e afins.'),
    ('vazio',),
    ('p', '*Parágrafo 2º.* No caso de perca de prazo processual por falta de contato '
          'com o CONTRATANTE, ensejando em extinção da Ação, ou prejuízos ao processo, '
          'a CONTRATADA renunciará o mandato, sem prejuízo dos honorários vencidos e '
          'vincendos.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* Toda comunicação do CONTRATADO com o CONTRATANTE será '
          'única e exclusivamente realizada pelos telefones oficiais do escritório – '
          '*(82) 99321-3032* e *(82) 99604-7676*.'),
    ('vazio',),
    ('p', '*Parágrafo 1º.* No caso de outro contato que não seja diretamente dos '
          'números apontados acima, deverá ser comunicado imediatamente ao CONTRATADO.'),
    ('vazio',),
    ('p', '*Parágrafo 2º.* O escritório Caroline Macedo *não exige nenhum pagamento '
          'via PIX ou Boleto para liberação de Alvará*, nem pede senhas bancárias aos '
          'clientes.'),
    ('vazio',),
    ('p', '*Parágrafo 3º.* Em virtude da grande quantidade de golpes e fraudes, fica o '
          'CONTRATANTE informado que, nem o Fórum e nem o Tribunal de Justiça entram em '
          'contato via Whatsapp para fazer reconhecimento facial para liberação de '
          'Alvará.'),
    ('vazio',),
    ('p', '*Parágrafo 4º.* Em caso de clonagem de WhatsApp, invasão de contas, '
          'vazamento de dados, falhas de segurança em aplicativos, plataformas '
          'digitais, serviços de correio eletrônico, operadoras de telefonia, '
          'provedores de internet ou quaisquer sistemas de terceiros utilizados para '
          'comunicação, a CONTRATADA não poderá ser responsabilizada pelos danos '
          'eventualmente suportados pela CONTRATANTE.'),
    ('vazio',),
    ('p', '*Parágrafo 5º.* As medidas previstas nesta cláusula constituem mecanismos '
          'preventivos adotados pela CONTRATADA para proteção das partes, não '
          'representando garantia absoluta contra a ocorrência de fraudes praticadas '
          'por terceiros.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* A relação profissional entre as partes deverá ser pautada '
          'pela boa-fé, confiança, urbanidade e respeito mútuo. A prática de ofensas, '
          'ameaças, agressões verbais, exposição indevida da imagem profissional da '
          'CONTRATADA, injúria, calúnia, difamação ou qualquer conduta incompatível com '
          'a relação profissional poderá ensejar a rescisão imediata deste contrato, '
          'sem prejuízo da cobrança dos honorários devidos e da adoção das medidas '
          'judiciais cabíveis.'),
    ('vazio',),

    # ------------------------------- cláusulas exclusivas das revisionais
    ('cond', '+SO_REVISIONAL'),
    ('p', '*Cláusula {{#}}.* As guias judiciais para depósito do valor incontroverso '
          'e/ou integral serão encaminhadas pelos canais oficiais do escritório, '
          'descritas na cláusula anterior.'),
    ('vazio',),
    ('p', '*Parágrafo Único.* Na Ação Revisional onde o magistrado não conceder a '
          'liminar de depósito incontroverso, e o contratante ainda assim, quiser '
          'realizar os depósitos, as guias serão emitidas pelo escritório, tendo o '
          'contratante ciência de que poderão não surtir efeitos jurídicos, sendo por '
          'sua conta e risco.'),
    ('vazio',),
    ('cond', '-SO_REVISIONAL'),

    ('p', '*Cláusula {{#}}.* Caso o CONTRATANTE receba alguma minuta de acordo e/ou '
          'boleto de pagamento que não seja enviada diretamente do escritório '
          '(CONTRATADO), deverá *IMEDIATAMENTE* comunicar ao escritório, sob pena do '
          'CONTRATADO não se responsabilizar em caso de possíveis fraudes e/ou golpes.'),
    ('vazio',),

    ('cond', '+SO_REVISIONAL'),
    ('p', '*Cláusula {{#}}.* Caso a instituição financeira ingresse com Ação de Busca '
          'e Apreensão e, em decorrência da atuação da CONTRATADA, advenha qualquer '
          'proveito econômico, retorno financeiro, redução de saldo devedor ou '
          'recebimento de valores em favor do CONTRATANTE, este pagará ao escritório o '
          'percentual de *{{PCT_GANHO}}% ({{PCT_GANHO_EXTENSO}} por cento)* incidente '
          'sobre o valor total do benefício obtido.'),
    ('vazio',),
    ('p', '*Parágrafo Único.* Os honorários previstos nesta cláusula são independentes '
          'dos honorários fixados na Cláusula 2ª e serão devidos no momento da '
          'liquidação do proveito econômico ou da homologação de eventual acordo que '
          'gere o referido retorno financeiro.'),
    ('vazio',),
    ('cond', '-SO_REVISIONAL'),

    ('p', '*Cláusula {{#}}.* O CONTRATANTE declara estar ciente de que a atividade '
          'advocatícia constitui *obrigação de meio, e não de resultado*, '
          'comprometendo-se a CONTRATADA a empregar toda a técnica, diligência, zelo e '
          'conhecimento jurídico necessários à melhor defesa dos interesses do '
          'CONTRATANTE, nos termos do artigo 32 da Lei nº 8.906/1994 (Estatuto da '
          'Advocacia) e da pacífica orientação do Superior Tribunal de Justiça. A '
          'prestação dos serviços ora contratados não importa, por sua natureza, '
          'garantia ou promessa de êxito, de procedência da ação, de determinado '
          'resultado econômico ou de qualquer provimento judicial específico, uma vez '
          'que a decisão final compete exclusivamente ao Poder Judiciário.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* O CONTRATANTE outorga à CONTRATADA poderes amplos para '
          'atuação extrajudicial, autorizando-a a promover tratativas, negociações, '
          'propor e receber propostas, transigir, firmar acordos, dar e receber '
          'quitação e praticar todos os atos necessários à composição do litígio '
          'perante a instituição financeira e/ou parte contrária, em defesa dos '
          'interesses do CONTRATANTE.'),
    ('vazio',),
    ('p', '*Parágrafo 1º.* Sempre que a celebração do acordo depender de desembolso, '
          'aporte ou disponibilidade de valores por parte do CONTRATANTE, este deverá '
          'confirmar, de forma expressa e prévia, que dispõe dos recursos financeiros '
          'necessários ao cumprimento das condições pactuadas, isentando a CONTRATADA '
          'de qualquer responsabilidade pela frustração do acordo decorrente da '
          'ausência de tais recursos.'),
    ('vazio',),
    ('p', '*Parágrafo 2º.* Os valores eventualmente recebidos em nome do CONTRATANTE '
          'serão a este repassados, deduzidos os honorários e despesas contratualmente '
          'devidos, mediante prestação de contas transparente.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* Os valores das parcelas dos honorários advocatícios '
          'previstos na Cláusula 2ª serão reajustados anualmente pela variação '
          'acumulada do *Índice Nacional de Preços ao Consumidor Amplo (IPCA)*, apurado '
          'pelo IBGE, a contar da data de assinatura do presente instrumento, '
          'incidindo o reajuste sobre as parcelas vincendas a cada período de 12 '
          '(doze) meses. Na hipótese de extinção ou substituição do referido índice, '
          'será adotado o índice oficial que vier a substituí-lo.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* As partes reconhecem a validade jurídica da assinatura '
          'eletrônica do presente contrato, realizada por meio da plataforma '
          '*Autentique*, declarando-a autêntica, íntegra e plenamente eficaz entre os '
          'contratantes, nos termos do artigo 10, § 2º, da Medida Provisória nº '
          '2.200-2/2001 e da Lei nº 14.063/2020. As partes reconhecem como válida a '
          'manifestação de vontade exteriorizada por tal meio, dispensando a '
          'assinatura física e/ou o reconhecimento de firma para todos os efeitos '
          'legais.'),
    ('vazio',),

    ('p', '*Cláusula {{#}}.* As partes elegem o foro da comarca de *Maceió-AL*, para '
          'dirimir quaisquer dúvidas provenientes da execução do presente contrato, à '
          'exceção de qualquer outro, por mais privilegiado que seja.'),
    ('vazio',), ('vazio',),

    ('p', 'E, por estarem assim, justos e contratados, firmam o presente em 02 (duas) '
          'vias de igual teor e forma para que produza seus efeitos legais.'),
    ('vazio',), ('vazio',),

    ('centro', '{{LOCAL_CONTRATO}}, {{DATA_EXTENSO}}.'),
    ('vazio',), ('vazio',), ('vazio',), ('vazio',),

    ('assin', '*CAROLINE NEIVA CHRISTOFANO MACEDO*¶ADVOGADA¶*OAB/AL 15.766*'
              '¶*OAB/SP 528.725*¶*OAB/PE 70.091*'),
    ('vazio',), ('vazio',), ('vazio',), ('vazio',), ('vazio',),

    ('assin', '*{{CLI_NOME}}*¶CLIENTE/CONTRATANTE'),

    ('cond', '+RESP_ASSIN'),
    ('vazio',), ('vazio',), ('vazio',), ('vazio',), ('vazio',),
    ('assin', '*{{RESP_NOME}}*¶CLIENTE/RESPONSÁVEL'),
    ('cond', '-RESP_ASSIN'),
]


# -------------------------------------------------------------- PROCURAÇÃO

QUALIF_OUTORGANTE = (
    '*{{CLI_NOME}}*, {{CLI_NACIONALIDADE}}, {{CLI_ESTADO_CIVIL}}, {{CLI_PROFISSAO}}, '
    '{{CLI_INSCRITO}} no CPF de nº {{CLI_CPF}}, {{CLI_PORTADOR}} do RG sob o nº '
    '{{CLI_RG}}, {{CLI_DOMICILIADO}} {{CLI_PREP}} {{CLI_ENDERECO}}.'
)

BLOCOS_PROCURACAO = [
    ('pr_titulo', 'PROCURAÇÃO'),
    ('pr_vazio',),
    ('pr_sub', 'OUTORGANTE:'),
    ('pr_vazio',),
    ('pr_corpo', QUALIF_OUTORGANTE),
    ('pr_vazio',),
    ('pr_sub', 'OUTORGADA:'),
    ('pr_vazio',),
    ('pr_corpo',
     '*CAROLINE MACEDO SOCIEDADE INDIVIDUAL DE ADVOCACIA*, pessoa jurídica de direito '
     'privado com CNPJ sob o nº 58.173.643/0001-17, inscrita na OAB/AL, sob o nº '
     '2400582, e sua sócia administradora *CAROLINE NEIVA CHRISTOFANO MACEDO*, '
     'brasileira, divorciada, advogada inscrita na OAB/AL sob o nº 15.766, OAB/SP sob '
     'o nº 528.725 e OAB/PE sob o nº 70.091, com endereço profissional na Rua Dr. Luís '
     'Pontes de Miranda, nº 36, Centro – Edifício Delmiro Gouveia – Sala 1107 - Maceió '
     '– AL, CEP: 57.020-140, onde deverá receber as intimações e notificações de praxe.'),
    ('pr_corpo',
     'Pelo presente instrumento particular de mandato, são conferidos pelo OUTORGANTE, '
     'a dita outorgada, procuradora e advogada deste instrumento, os poderes da '
     'Cláusula *“Ad Judicia et Extra”*, além de poderes especiais, podendo para tanto, '
     'acordar, discordar, transigir, dar e receber quitação, receber alvará, renunciar, '
     'desistir, reconvir, inclusive substabelecer com ou sem reserva de poderes, tudo '
     'em fim para o bom e fiel cumprimento do presente mandato.'),
    ('pr_vazio',),
    ('pr_sub', 'FINALIDADE'),
    ('pr_vazio',),
    ('pr_centro', 'Promover os interesses do Outorgante em demanda judicial e extrajudicial.'),
    ('pr_vazio',),
    ('pr_centro', '{{CIDADE_UF}}, {{DATA_EXTENSO}}.'),
    ('pr_vazio',), ('pr_vazio',), ('pr_vazio',), ('pr_vazio',),
    ('pr_centro_b', '{{CLI_NOME}}'),
]


# --------------------------------------------- DECLARAÇÃO DE HIPOSSUFICIÊNCIA

QUALIF_DECLARANTE = (
    '*{{CLI_NOME}}*, {{CLI_NACIONALIDADE}}, {{CLI_ESTADO_CIVIL}}, {{CLI_PROFISSAO}}, '
    '{{CLI_PORTADOR}} do RG sob o nº {{CLI_RG}}, {{CLI_INSCRITO}} no CPF de nº '
    '{{CLI_CPF}}, {{CLI_DOMICILIADO}} {{CLI_PREP}} {{CLI_ENDERECO}}, '
)

BLOCOS_HIPOSSUFICIENCIA = [
    ('dc_vazio',),
    ('dc_titulo', 'DECLARAÇÃO DE HIPOSSUFICIÊNCIA'),
    ('dc_vazio',), ('dc_vazio',), ('dc_vazio',),
    ('dc_corpo', QUALIF_DECLARANTE +
     '*DECLARO* para todos os fins de direito e sob as penas da lei, que não possuo '
     'condições de arcar com as despesas inerentes ao presente processo, sem prejuízo '
     'do meu sustento e de minha família, necessitando, portanto, da *Gratuidade da '
     'Justiça*, nos termos do art. 98 e seguintes da Lei 13.105/2015 (Código de '
     'Processo Civil). Requerendo, ainda, que o benefício abranja a todos os atos do '
     'processo.'),
    ('dc_vazio',),
    ('dc_corpo', 'Declaro, também, que assumo inteira responsabilidade pela veracidade '
                 'do conteúdo da presente declaração, sob as penas da lei.'),
    ('dc_vazio',), ('dc_vazio',),
    ('dc_centro', '{{CIDADE}}, {{DATA_EXTENSO}}.'),
    ('dc_vazio',),
    ('dc_assin', '*{{CLI_NOME}}*¶CPF sob o nº {{CLI_CPF}}'),
]


# --------------------------------------------- DECLARAÇÃO DE RESIDÊNCIA

BLOCOS_RESIDENCIA = [
    ('dc_vazio',), ('dc_vazio',),
    ('dc_titulo', 'DECLARAÇÃO DE RESIDÊNCIA'),
    ('dc_vazio',), ('dc_vazio',), ('dc_vazio',),
    ('dc_corpo',
     '*{{CLI_NOME}}*, {{CLI_NACIONALIDADE}}, {{CLI_ESTADO_CIVIL}}, {{CLI_PROFISSAO}}, '
     '{{CLI_PORTADOR}} do RG sob o nº {{CLI_RG}}, {{CLI_INSCRITO}} no CPF de nº '
     '{{CLI_CPF}}, na falta de documentos para comprovação de residência, em '
     'conformidade com o disposto na Lei 7.115, de 29 de agosto de 1983, *DECLARO* '
     'para os devidos fins, sob penas da Lei, ser {{CLI_DOMICILIADO}} '
     '{{CLI_PREP_CRASE}} {{CLI_ENDERECO}}.'),
    ('dc_corpo',
     'Por ser verdade, firmo a presente declaração para que produza os efeitos legais, '
     'ciente de que a falsidade de seu conteúdo pode implicar na imputação de sanções '
     'civis, administrativas, bem como na sanção penal prevista no art. 299 do Código '
     'Penal, conforme transcrição abaixo:'),
    ('dc_vazio',),
    ('dc_cita',
     '*Art. 299* – Omitir, em documento público ou particular, declaração que nele '
     'deveria constar, ou nele inserir ou fazer inserir declaração falsa ou diversa da '
     'que devia ser escrita, com o fim de prejudicar direito, criar obrigação ou '
     'alterar a verdade sobre o fato juridicamente relevante. *Pena:* reclusão de 1 '
     '(um) a 5 (cinco) anos e multa, se o documento é público e reclusão de 1 (um) a 3 '
     '(três) anos, se o documento é particular.'),
    ('dc_vazio',), ('dc_vazio',),
    ('dc_centro', '{{CIDADE}}, {{DATA_EXTENSO}}.'),
    ('dc_vazio',),
    ('dc_assin', '*{{CLI_NOME}}*¶CPF sob o nº {{CLI_CPF}}'),
]
