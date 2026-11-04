# -*- coding: utf-8 -*-
"""
CONTEÚDO DO MODELO MESTRE - AÇÃO REVISIONAL DE CONTRATO BANCÁRIO
Escritório Caroline Macedo Sociedade Individual de Advocacia

Fonte: petições reais do escritório
  - ELIEZER CICERO VASCONCELOS DA SILVA (BV / TJ-AL)  -> padrão atual
  - JULIANA DE CÁSSIA ALVES RODRIGUES (PAN / TJ-MG)
  - GABRIELLE WESTPHAL DOS SANTOS (Volkswagen / TJ-SP)
  - MODELO REVISIONAL NOVO - APLICAR NOS CASOS CONCRETOS

Tipos de bloco:
  ('bar',  texto)  -> faixa cinza de seção (título principal)
  ('h',    texto)  -> subtítulo em negrito (usa {{§}} para numeração romana automática)
  ('p',    texto)  -> parágrafo justificado 12pt
  ('pb',   texto)  -> parágrafo justificado 12pt em NEGRITO
  ('c',    texto)  -> parágrafo centralizado em negrito
  ('q',    texto)  -> citação / ementa (recuo 4cm, 10pt)
  ('qf',   texto)  -> fonte da citação (recuo 4cm, 10pt)
  ('lista',texto)  -> item de lista com recuo
  ('vazio', '')    -> linha em branco
  ('tabela_contrato', '') -> quadro do contrato (montado pelo gerador)
  ('img',  texto)  -> marcador para a advogada colar o print da cláusula
  ('+X' / '-X')    -> abre / fecha bloco condicional da tese X
"""

BLOCOS = [
    # ------------------------------------------------------------------ ENDEREÇAMENTO
    ('pb', 'EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA {{VARA}} VARA CÍVEL DA COMARCA DE {{COMARCA_MAI}}, ESTADO DE {{ESTADO}}.'),
    ('vazio', ''),
    ('vazio', ''),
    ('vazio', ''),
    ('c', 'TUTELA DE URGÊNCIA'),
    ('+JUROSMORA',),
    ('c', 'JUROS MORATÓRIOS ACIMA DE 1% AO MÊS'),
    ('-JUROSMORA',),
    ('+DEPINTEGRAL',),
    ('c', 'DEPÓSITO INTEGRAL'),
    ('-DEPINTEGRAL',),
    ('+DEPINCONTROVERSO',),
    ('c', 'DEPÓSITO DO VALOR INCONTROVERSO'),
    ('-DEPINCONTROVERSO',),
    ('vazio', ''),
    ('vazio', ''),

    # ------------------------------------------------------------------ QUALIFICAÇÃO
    ('p', '{{AUTOR_NOME}}, {{AUTOR_NACIONALIDADE}}, {{AUTOR_ESTADO_CIVIL}}, {{AUTOR_PROFISSAO}}, {{AUTOR_RG}}inscrit{{O_A}} no CPF de nº {{AUTOR_CPF}}, residente e domiciliad{{O_A}} na {{AUTOR_ENDERECO}}, vem por meio de sua advogada, procuração em anexo com todas as qualificações necessárias e endereço profissional, respeitosamente perante V. Exa., propor:'),
    ('vazio', ''),
    ('c', 'AÇÃO DE REVISÃO DE CONTRATO DE FINANCIAMENTO DE VEÍCULO COM PEDIDO DE TUTELA DE URGÊNCIA'),
    ('vazio', ''),
    ('p', 'Em face de {{REU_NOME}}, instituição financeira {{REU_ENDERECO}}, inscrita no CNPJ/MF sob o n.° {{REU_CNPJ}}, {{REU_EMAIL}}, pelos motivos de fato e de direito a seguir aduzidos:'),
    ('vazio', ''),

    # ------------------------------------------------------------------ GRATUIDADE
    ('bar', 'DA GRATUIDADE DE JUSTIÇA'),
    ('p', '{{O_A_REQUERENTE}}, com fundamento no artigo 98 do CPC, requer que sejam concedidos os benefícios da Gratuidade da Justiça, visto que se encontra em estado de insuficiência de recursos para pagar as custas, as despesas processuais e os honorários advocatícios em quaisquer graus de processamento.'),
    ('q', 'Art. 98. A pessoa natural ou jurídica, brasileira ou estrangeira, com insuficiência de recursos para pagar as custas, as despesas processuais e os honorários advocatícios tem direito à gratuidade da justiça, na forma da lei.'),
    ('p', 'Isto posto, o destinatário da gratuidade da justiça é todo aquele que não pode arcar com os custos de um processo no momento da propositura do mesmo, que serão beneficiados com a isenção de pagamento das despesas inerentes ao processo judicial para a solução do litígio.'),
    ('p', 'A lei determina expressamente que seja concedido este benefício em caso de juntada de declaração de pobreza e simples pedido, o que foi feito, conforme reza o art. 4º da Lei nº 1.060 de 05 de fevereiro de 1950 (o qual foi alterado pela Lei nº 7.510/86) e o art. 1º da Lei nº 7.115, de 29 de agosto de 1983:'),
    ('q', 'Art. 4º. A parte gozará dos benefícios da assistência judiciária, mediante simples afirmação, na própria petição inicial, de que não está em condições de pagar as custas do processo e os honorários de advogado, sem prejuízo próprio ou de sua família. (Redação dada pela Lei nº 7.510, de 1986)'),
    ('q', 'Art. 1º. A declaração destinada a fazer prova de vida, residência, pobreza, dependência econômica, homonímia ou bons antecedentes, quando firmada pelo próprio interesse ou por procurador bastante, e sob as penas da Lei, presume-se verdadeira.'),
    ('qf', '(Grifos Nossos)'),
    ('p', 'Nesse contexto, cumpre destacar que o entendimento consolidado pelos Tribunais Pátrios corrobora integralmente a pretensão ora deduzida, reconhecendo que a simples declaração de hipossuficiência, quando acompanhada de elementos que demonstrem a impossibilidade de arcar com as custas sem prejuízo do próprio sustento, é suficiente para o deferimento do benefício. In verbis:'),
    ('q', 'DIREITO PROCESSUAL CIVIL. AGRAVO DE INSTRUMENTO. JUSTIÇA GRATUITA. DEFERIMENTO. PRESUNÇÃO DE VERACIDADE DA DECLARAÇÃO DE HIPOSSUFICIÊNCIA. RECURSO CONHECIDO E PROVIDO. DECISÃO UNÂNIME. I. Caso em exame 1. Agravo de Instrumento interposto contra decisão que indeferiu o pedido de justiça gratuita em ação de origem não especificada. A agravante alega não possuir condições de arcar com as custas processuais sem prejuízo do próprio sustento. II. Questão em discussão 2. A questão em discussão consiste em saber se estão presentes os requisitos para a concessão da gratuidade da justiça à agravante. III. Razões de decidir 3. A declaração de hipossuficiência goza de presunção relativa de veracidade, conforme art. 99, § 3º do CPC. 4. A renda líquida da agravante, devidamente comprovada nos autos, é insuficiente para arcar com custas processuais sem comprometer sua subsistência. 5. Não se exige estado de miserabilidade absoluta para a concessão do benefício da justiça gratuita, bastando a comprovação da impossibilidade de litigar sem prejuízo do próprio sustento ou da família. 6. A ausência de elementos nos autos que contradigam a declaração e comprovação de hipossuficiência da agravante corrobora o deferimento do benefício. IV. Dispositivo e tese 7. Tese de julgamento: "É cabível a concessão de justiça gratuita quando a declaração de hipossuficiência é corroborada por elementos que demonstrem a impossibilidade de a parte arcar com as custas processuais sem prejuízo de seu sustento, não se exigindo estado de miserabilidade absoluta." 8. Recurso conhecido e provido. Decisão unânime.'),
    ('qf', '(TJ-AL - Agravo de Instrumento: 08052423620248020000 Maceió, Relator.: Des. Carlos Cavalcanti de Albuquerque Filho, Data de Julgamento: 24/10/2024, 2ª Câmara Cível, Data de Publicação: 25/10/2024)'),
    ('p', 'Cumpre ressaltar que a parte autora não apenas declarou sua hipossuficiência, gozando da presunção legal de veracidade estabelecida pelo art. 99, § 3º, do CPC, mas também robusteceu tal alegação com documentos que demonstram sua situação de vulnerabilidade financeira.'),
    ('p', 'Conforme a jurisprudência do Superior Tribunal de Justiça (STJ - REsp: 2055899/MG), o afastamento da presunção de insuficiência de recursos que milita em favor da pessoa natural exige a indicação de elementos concretos constantes dos autos que evidenciem a falta dos pressupostos legais para a concessão do benefício, vejamos:'),
    ('q', 'RECURSO ESPECIAL. PROCESSUAL CIVIL. GRATUIDADE DA JUSTIÇA. ALEGAÇÃO DE INSUFICIÊNCIA DE RECURSOS. PRESUNÇÃO RELATIVA. AFASTAMENTO. NECESSIDADE DE INDICAÇÃO DE ELEMENTOS CONCRETOS CONSTANTE DOS AUTOS. [...] 3. De acordo com o § 3º, do art. 99, do CPC, presume-se verdadeira a alegação de insuficiência deduzida exclusivamente por pessoa natural. 4. Diante da presunção estabelecida pela lei, o ônus da prova na impugnação à gratuidade é, em regra, do impugnante, podendo, ainda, o próprio juiz afastar a presunção à luz de elementos constantes dos autos que evidenciem a falta de preenchimento dos pressupostos autorizadores da concessão do benefício, nos termos do § 2º, do art. 99, do CPC. 5. De acordo com o § 2º, do art. 99 do CPC/2015, o juiz somente poderá indeferir o pedido se houver nos autos elementos que evidenciem a falta dos pressupostos legais para a concessão de gratuidade, devendo, antes de indeferir o pedido, determinar à parte a comprovação do preenchimento dos referidos pressupostos. [...] 7. Recurso especial conhecido e provido.'),
    ('qf', '(STJ - REsp: 2055899 MG 2023/0060553-8, Relator.: NANCY ANDRIGHI, Data de Julgamento: 20/06/2023, T3 - TERCEIRA TURMA, Data de Publicação: DJe 27/06/2023)'),
    ('p', 'Portanto, em consonância com o entendimento do STJ, e inexistindo nos autos elementos que, de forma inequívoca e concreta, demonstrem a capacidade financeira d{{O_A}} Autor{{A}} para arcar com as custas sem prejuízo do seu sustento, requer-se o deferimento do BENEFÍCIO DA ASSISTÊNCIA JUDICIÁRIA GRATUITA, prestigiando-se a presunção legal e a efetiva comprovação da condição de vulnerabilidade da parte.'),
    ('vazio', ''),

    # ------------------------------------------------------------------ CONCILIAÇÃO
    ('bar', 'DA AUDIÊNCIA DE CONCILIAÇÃO'),
    ('p', 'A parte Autora já buscou resolver a questão de forma extrajudicial, não obtendo sucesso, razão pela qual entende infrutífera, neste momento, qualquer marcação de audiência conciliatória, nos termos do art. 319, inc. VII do CPC.'),
    ('vazio', ''),

    # ------------------------------------------------------------------ COMPETÊNCIA (opcional)
    ('+COMPETENCIA',),
    ('bar', 'DA COMPETÊNCIA'),
    ('p', 'A parte Autora, ora consumidor{{A}}, TEM A POSSIBILIDADE DE ESCOLHER SE AJUIZARÁ SUA AÇÃO NO FORO DO DOMICÍLIO DO RÉU ou em seu próprio domicílio, pois é uma faculdade pertencente somente àquela pessoa física ou jurídica destinatária final do bem ou serviço na relação de consumo.'),
    ('q', 'CONFLITO NEGATIVO DE COMPETÊNCIA. AÇÃO DECLARATÓRIA DE INEXISTÊNCIA DE DÉBITO. RELAÇÃO DE CONSUMO. AJUIZAMENTO DA AÇÃO FORA DO DOMICÍLIO DO CONSUMIDOR. POSSIBILIDADE. É FACULTADO AO CONSUMIDOR OPTAR PELO FORO DE SEU DOMICÍLIO, DE ELEIÇÃO OU DO DOMICÍLIO DO RÉU. ART. 101, INCISO I, DO CÓDIGO DE DEFESA DO CONSUMIDOR. DECLÍNIO EX OFFICIO DE COMPETÊNCIA. NÃO CABIMENTO. INTELIGÊNCIA DA SÚMULA Nº 33 DO STJ. COMPETÊNCIA RELATIVA. CONFLITO DE COMPETÊNCIA CONHECIDO.'),
    ('qf', '(TJ-AL - CC: 05010001520218020000 Joaquim Gomes, Relator: Desa. Elisabeth Carvalho Nascimento, Data de Julgamento: 26/05/2022, 2ª Câmara Cível, Data de Publicação: 26/05/2022)'),
    ('q', 'EMENTA. CONFLITO NEGATIVO DE COMPETÊNCIA. AÇÃO DE NATUREZA CONSUMERISTA. PROPOSITURA DA AÇÃO. POLO ATIVO OCUPADO PELO CONSUMIDOR. OPÇÃO DO CONSUMIDOR - AUSÊNCIA DE PREJUÍZO AO CONSUMIDOR. COMPETÊNCIA RELATIVA – CONFLITO JULGADO PROCEDENTE. 1. Quando o consumidor ajuíza ação de responsabilidade civil contra fornecedor de produtos e serviços, poderá optar pelo foro do seu domicílio, pelo de domicílio do réu ou pelo foro de eleição. [...] 4. Nos termos do artigo 101, I, do CDC, deve prevalecer o foro eleito pelo consumidor, posto que a legislação consumerista traz ao consumidor a opção de foro, não obrigando-o a propor a ação em seu domicílio, mas, sim, possibilitando que escolha dentre o foro do seu domicílio, o de domicílio do réu ou o foro de eleição, aquele que melhor facilita a defesa dos seus interesses.'),
    ('qf', '(TJ-PI - CC: 07051143720198180000, Relator: Luiz Gonzaga Brandão De Carvalho, Data de Julgamento: 29/07/2022, 2ª CÂMARA DE DIREITO PÚBLICO)'),
    ('p', 'Dito isso, cumpre transcrever o que prescreve a REGRA GERAL do art. 46 do Código de Processo Civil, o qual rege as regras de competência, notadamente conferindo plena possibilidade de ingresso desta ação no foro do domicílio do réu:'),
    ('q', 'Art. 46. A ação fundada em direito pessoal e a ação fundada em direito real sobre bens móveis serão propostas, em regra, no foro do domicílio do réu. § 1º Tendo mais de um domicílio, o réu será demandado no foro de qualquer deles.'),
    ('p', 'Diante disto, requer que seja mantida a competência nesta Comarca de {{COMARCA}}/{{UF}}.'),
    ('vazio', ''),
    ('-COMPETENCIA',),

    # ------------------------------------------------------------------ RENEGOCIAÇÃO (opcional)
    ('+RENEGOCIACAO',),
    ('bar', 'DA RENEGOCIAÇÃO CONTRATUAL E DA POSSIBILIDADE DE REVISÃO'),
    ('p', 'A circunstância de o contrato decorrer de renegociação, refinanciamento, confissão de dívida, acordo extrajudicial ou eventual composição formalizada em contexto judicial não consubstancia óbice ao controle de legalidade das cláusulas nele inseridas. A mera assinatura do instrumento não possui o condão de convalidar disposições intrinsecamente abusivas, sobretudo em uma relação de consumo caracterizada por patente assimetria técnica, econômica e informacional.'),
    ('p', 'A jurisprudência pacificada do Superior Tribunal de Justiça afasta peremptoriamente qualquer impedimento à revisão judicial fundado na preexistência de renegociação bancária ou confissão de dívida. Tal entendimento encontra-se cristalizado na Súmula 286 da referida Corte:'),
    ('q', 'SÚMULA N. 286 DO STJ. A renegociação de contrato bancário ou a confissão da dívida não impede a possibilidade de discussão sobre eventuais ilegalidades dos contratos anteriores. (SÚMULA 286, SEGUNDA SEÇÃO, julgado em 28/04/2004, DJ 13/05/2004, p. 201)'),
    ('p', 'Esse raciocínio é reiteradamente aplicado pelo STJ, que afasta a tese de perda do objeto ou novação como impeditivos para a revisão contratual, garantindo a análise das ilegalidades:'),
    ('q', 'DIREITO CIVIL. AGRAVO INTERNO NO AGRAVO EM RECURSO ESPECIAL. AÇÃO MONITÓRIA. ILEGALIDADE CONTRATUAL. RENEGOCIAÇÃO. PERDA DO OBJETO. AFASTAMENTO. SÚMULA 286/STJ. AGRAVO INTERNO DESPROVIDO. 1. No presente caso, houve renegociação da dívida e ajuizamento de reconvenção em que o ora agravado pretendeu a revisão contratual a fim de revisar supostas ilegalidades contratuais. 2. Conforme entendimento desta Corte Superior: "A renegociação de contrato bancário ou a confissão da dívida não impede a possibilidade de discussão sobre eventuais ilegalidades dos contratos anteriores" (Súmula 286/STJ). 3. Agravo interno desprovido.'),
    ('qf', '(STJ - AgInt no AREsp: 2181007 PR 2022/0238676-0, Relator: Ministro RAUL ARAÚJO, Data de Julgamento: 12/12/2022, T4 - QUARTA TURMA, Data de Publicação: DJe 14/12/2022)'),
    ('p', 'No presente caso, o pleito revisional assume especial relevância, pois não se restringe ao contrato de financiamento originário, alcançando também o instrumento de renegociação, que não convalidou as ilegalidades anteriores, mas perpetuou e agravou a abusividade da relação contratual, ao incorporar cláusulas autônomas manifestamente excessivas, impondo ao consumidor ônus desproporcional e incompatível com a boa-fé objetiva, o equilíbrio contratual e a vedação à vantagem manifestamente excessiva, razão pela qual se impõe o controle judicial das cláusulas pactuadas tanto no contrato originário quanto na renegociação.'),
    ('p', 'A nulidade de tais disposições é imperativa, por se tratar de matéria de ordem pública, atraindo a incidência do artigo 51, inciso IV, do Código de Defesa do Consumidor:'),
    ('q', 'Art. 51. São nulas de pleno direito, entre outras, as cláusulas contratuais relativas ao fornecimento de produtos e serviços que: [...] IV - estabeleçam obrigações iníquas, abusivas, que coloquem o consumidor em desvantagem exagerada, ou sejam incompatíveis com a boa-fé ou a equidade; [...]'),
    ('p', 'Ademais, a ciência posterior do inteiro teor do contrato e a ausência de transparência na fase pré-contratual reforçam o cabimento da revisão judicial. O artigo 46 do Código de Defesa do Consumidor é categórico ao afastar a obrigatoriedade do instrumento quando não assegurado o direito à informação clara e precisa:'),
    ('q', 'Art. 46. Os contratos que regulam as relações de consumo não obrigarão os consumidores, se não lhes for dada a oportunidade de tomar conhecimento prévio de seu conteúdo, ou se os respectivos instrumentos forem redigidos de modo a dificultar a compreensão de seu sentido e alcance.'),
    ('p', 'Dessa forma, a presente demanda não objetiva afastar injustificadamente a obrigação assumida, mas sim submeter o contrato de renegociação ao inafastável controle de legalidade, equilíbrio e boa-fé, expurgando os encargos abusivos e readequando a obrigação à realidade econômico-financeira d{{O_A}} Autor{{A}}.'),
    ('vazio', ''),
    ('-RENEGOCIACAO',),

    # ------------------------------------------------------------------ FATOS
    ('bar', 'DOS FATOS'),
    ('p', 'A parte autora adquiriu um automóvel em uma concessionária onde lhe foi ofertado o modelo {{VEICULO}}, {{CHASSI_TXT}}{{RENAVAM_TXT}}{{COR_TXT}}{{PLACA_TXT}}através da Cédula de Crédito Bancário objeto da presente ação revisional, nos seguintes termos:'),
    ('tabela_contrato', ''),
    ('vazio', ''),
    ('p', 'O contrato possui um total de {{QTD_PARCELAS}} ({{QTD_PARCELAS_EXT}}) parcelas financiadas, tendo sido pagas {{PARCELAS_PAGAS}} ({{PARCELAS_PAGAS_EXT}}) parcelas no montante de R$ {{VALOR_PAGO}} ({{VALOR_PAGO_EXT}}), devendo ao Banco um valor exorbitante de R$ {{SALDO_DEVEDOR}} ({{SALDO_DEVEDOR_EXT}}).'),
    ('p', 'Entende-se que a PARCELA INCONTROVERSA passaria a ser R$ {{PARCELA_INCONTROVERSA}} ({{PARCELA_INCONTROVERSA_EXT}}), o que multiplicado por {{PARCELAS_RESTANTES}} parcelas que ainda faltam pagar, enseja um total de R$ {{TOTAL_INCONTROVERSO}} ({{TOTAL_INCONTROVERSO_EXT}}).'),
    ('+DEPINTEGRAL',),
    ('p', 'Mesmo diante de tal fato, a parte autora, garantindo sua boa-fé, REQUER O DEPÓSITO DO VALOR INTEGRAL DA PARCELA (R$ {{VALOR_PARCELA}}), mesmo tal valor sendo {{PERC_MAIOR}}% A MAIOR do que o valor realmente devido.'),
    ('-DEPINTEGRAL',),
    ('+DEPINCONTROVERSO',),
    ('p', 'Diante de tal fato, a parte autora, nos termos do art. 330, §2º do CPC, REQUER O DEPÓSITO DO VALOR INCONTROVERSO DA PARCELA (R$ {{PARCELA_INCONTROVERSA}}), com a emissão de novo carnê pela ré, sob pena de multa diária.'),
    ('-DEPINCONTROVERSO',),
    ('p', 'Diante do exposto, foi constatado que houve desrespeito na aplicação das Taxas do Contrato (mensal e anual), que houve pactuação de capitalização diária sem a informação da taxa do dia e mais ainda que a Taxa Contratual (efetiva ou a contratada) é superior imoderadamente ao padrão da Taxa Média Bacen, junte-se a isso as tarifas e seguros indevidamente contratados.'),
    ('p', 'Assim, são abusivas as seguintes cláusulas que tratam de: {{CLAUSULAS_ABUSIVAS}}.'),
    ('p', 'Pelas razões mencionadas se faz necessário que se proceda à devida revisão das cláusulas abusivas apontadas, objetivando, desde logo, a concessão da tutela de urgência requerida, sem prejuízo do julgamento de procedência da matéria de mérito, consoante as razões as quais passam a ser expostas:'),
    ('vazio', ''),

    # ------------------------------------------------------------------ TUTELA
    ('bar', 'DA TUTELA DE URGÊNCIA'),
    ('p', 'Estabelece o Código de Processo Civil que são requisitos gerais da tutela de urgência: a) probabilidade do direito; e, b) perigo de dano ou o risco ao resultado útil do processo. Em sede de tutela antecipada (satisfativa), ainda há o acréscimo do requisito negativo, qual seja, ausência de risco de irreversibilidade da medida (§3º, art. 300, CPC).'),
    ('p', 'A probabilidade do direito decorre do fato de que a aplicação e incidência de capitalização diária sem a informação da taxa do dia, furtando d{{O_A}} autor{{A}} a possibilidade de sindicar a taxa efetivamente praticada, estão comprovando a exata dicção do TEMA 28 dos precedentes do STJ, no caso o REsp 1061530/RS, apta a afastar inclusive a mora em casos extremos de inadimplência:'),
    ('q', 'O reconhecimento da abusividade nos encargos exigidos no período da normalidade contratual (juros remuneratórios e capitalização) descaracteriza a mora.'),
    ('p', 'O perigo da demora está salientado nos elementos aqui apresentados, já que a espera por um provimento jurisdicional final (em sede de cognição exauriente) prejudicará sobremaneira, ou poderá tornar imprestável, o direito da parte Autora buscado nesta demanda. Isto porque o abuso do direito pela Demandada (prática de juros abusivos e de capitalização indevida) compromete o cumprimento do contrato e a própria subsistência mensal da parte Demandante, aliado ao fato de existir risco iminente de deferimento liminar de busca e apreensão a ser eventualmente manejada. Ademais é cediço na própria jurisprudência do STJ, que o devedor necessita de algo além do próprio exercício do direito de ação, conforme previsto no verbete da Súmula 380/STJ:'),
    ('q', '“A simples propositura da ação de revisão de contrato não inibe a caracterização da mora do autor.”'),
    ('p', 'Por fim, tem-se como plenamente reversível a medida a ser concedida, haja vista que a retomada dos pagamentos no valor contratual pode ser feita a qualquer momento.'),
    ('p', 'Portanto, merece ser concedida a tutela de urgência satisfativa antecipada e acautelatória, para que:'),
    ('+DEPINTEGRAL',),
    ('lista', 'a) Seja deferido à parte autora o direito de DEPOSITAR JUDICIALMENTE O VALOR INTEGRAL de cada parcela (R$ {{VALOR_PARCELA}}), com a produção do efeito de afastamento da mora, MANTENDO O BEM NA POSSE DA PARTE AUTORA, sob pena de multa diária;'),
    ('-DEPINTEGRAL',),
    ('+DEPINCONTROVERSO',),
    ('lista', 'a) Seja deferido à parte autora o direito de contraprestar o valor incontroverso de R$ {{PARCELA_INCONTROVERSA}}, determinando-se à ré a emissão de novo carnê, sob pena de multa diária, e/ou ainda autorizado o depósito judicial do montante, com a produção do efeito de afastamento da mora, MANTENDO O BEM NA POSSE DA PARTE AUTORA;'),
    ('-DEPINCONTROVERSO',),
    ('lista', 'b) Seja afastada a mora com base no TEMA 28 dos precedentes do STJ (REsp 1061530/RS);'),
    ('lista', 'c) SEJA A RÉ INIBIDA, sob pena de multa diária, de:'),
    ('lista', 'c.1) AJUIZAR BUSCA E APREENSÃO enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', 'c.2) INSERIR O NOME E CPF DA PARTE AUTORA no SCR Bacen, seja na guia vencido, seja na guia prejuízo, enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', 'c.3) INSERIR O NOME E CPF DA PARTE AUTORA no SPC, SERASA e BOA VISTA, enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', 'c.4) LEVAR O NOME E CPF DA PARTE AUTORA a PROTESTO CARTORÁRIO em razão dos débitos aqui discutidos, enquanto perdurarem os efeitos da tutela de urgência requerida.'),
    ('vazio', ''),

    # ------------------------------------------------------------------ DIREITO
    ('bar', 'DO DIREITO'),
    ('p', 'A relação entre as partes se enquadra no conceito de relação de consumo, estando presentes as figuras do consumidor, fornecedor e produto/serviço (arts. 2º, 3º do CDC e Súmula 297 do STJ). Assim, aplica-se o diploma consumerista ao contrato aderido pel{{O_A}} autor{{A}}, se fazendo necessária interpretação protetiva (art. 47 do CDC) diante da violação ocorrida nos dois principais pilares de um contrato durante o período da normalidade, quais sejam, cláusula de capitalização e abusividade na taxa de juros, colocando o consumidor em desvantagem exagerada (art. 51, IV e §1º, CDC), dando ensejo à:'),
    ('lista', 'a) Revisão contratual das cláusulas abaixo discriminadas (art. 6º, V; §4º do art. 51 do CDC c/c Tema 28 do STJ – REsp 1.061.530/RS);'),
    ('lista', 'b) O afastamento da mora (Tema 28 do STJ);'),
    ('lista', 'c) A proteção do nome do consumidor (Tema 31 do STJ – REsp 1.061.530/RS) contra os cadastros de negativação (SPC, Serasa, Boa Vista, SCR Bacen e Cartórios de Protestos); e'),
    ('lista', 'd) A inversão do ônus da prova quanto aos pontos específicos que adiante serão individualizados (art. 6º, VIII, do CDC).'),
    ('vazio', ''),

    # ---------------------------------------------- TESE 1: CAPITALIZAÇÃO DIÁRIA
    ('+CAPDIARIA',),
    ('h', '{{§}}. DA ABUSIVIDADE DA CLÁUSULA DE CAPITALIZAÇÃO DIÁRIA DE JUROS'),
    ('p', 'A parte Autora pretende o afastamento de toda e qualquer forma de capitalização de juros no contrato em análise, especialmente a capitalização diária, pleiteando ao final o recálculo das parcelas a juros simples, pelas razões de fato e de direito que passa a expor.'),
    ('p', 'Conforme já narrado, a parte Autora aderiu a um contrato de crédito com garantia de alienação fiduciária, por meio do qual restou imposta cláusula de CAPITALIZAÇÃO DIÁRIA dos juros remuneratórios, sem qualquer indicação expressa do percentual da taxa diária aplicada. Analisemos:'),
    ('img', '[INSERIR AQUI O PRINT DA CLÁUSULA DE JUROS REMUNERATÓRIOS E DA CLÁUSULA DE CAPITALIZAÇÃO DIÁRIA]'),
    ('p', 'Tal prática, além de violar o princípio da transparência e o dever de informação previstos no Código de Defesa do Consumidor (arts. 6º, III, 46, 52, II, 54-B, II e 54-D, I, do CDC), vem sendo reiteradamente rechaçada pelos Tribunais pátrios e pelo Superior Tribunal de Justiça, que entendem ser abusiva a cláusula que prevê capitalização diária sem indicação expressa da taxa correspondente.'),
    ('p', 'O STJ, no julgamento do Tema 28 (REsp 1.061.530/RS) e, mais recentemente, no REsp 1.826.463/SC, firmou entendimento no sentido de que a ausência de informação clara acerca da taxa diária de juros compromete o equilíbrio contratual e caracteriza cláusula abusiva, passível de revisão judicial e descaracterização da mora. Vejamos:'),
    ('q', 'APELAÇÃO CÍVEL. AÇÃO DE BUSCA E APREENSÃO. CONTRATO DE FINANCIAMENTO BANCÁRIO COM CLÁUSULA DE ALIENAÇÃO FIDUCIÁRIA PARA AQUISIÇÃO DE VEÍCULO. APRESENTAÇÃO DE RECONVENÇÃO. […] CAPITALIZAÇÃO DIÁRIA. INEXISTÊNCIA DE INFORMAÇÃO DA TAXA DIÁRIA DE JUROS CAPITALIZADOS QUE CONSTITUI DANO AO EQUILÍBRIO MATERIAL DO CONTRATO. AFASTAMENTO. DESCARACTERIZAÇÃO DA MORA DIANTE DO RECONHECIMENTO DA NULIDADE DA CLÁUSULA DE CAPITALIZAÇÃO DIÁRIA. ORIENTAÇÃO FIXADA PELO STJ NO RECURSO ESPECIAL Nº 1.061.530-RS. SENTENÇA REFORMADA PARA JULGAR IMPROCEDENTE A AÇÃO DE BUSCA E APREENSÃO E DETERMINAR A DEVOLUÇÃO DO BEM AO APELANTE. APLICAÇÃO SUBSIDIÁRIA DO ARTIGO 3º, § 6º E § 7º DO DECRETO-LEI Nº 911/69. REDISTRIBUIÇÃO DO ÔNUS SUCUMBENCIAL. APELAÇÃO CÍVEL PARCIALMENTE PROVIDA.'),
    ('qf', '(TJ-PR 00208583620218160021 Cascavel, Relator: Naor Ribeiro de Macedo Neto, Data de Julgamento: 14/05/2023, 13ª Câmara Cível, Data de Publicação: 16/05/2023)'),
    ('p', 'Da análise detida do Tema 28 do STJ – REsp 1.061.530/RS e do REsp 1826463/SC é possível subtrair a premissa de que a ausência de indicação da taxa do dia é tão grave ao ponto de autorizar, por colocar o consumidor em desvantagem exagerada, (a) tanto a revisão do contrato, impactando no montante das parcelas e do saldo devedor, (b) quanto o afastamento da mora.'),
    ('p', 'Nesse sentido, a capitalização diária de juros sem a devida indicação da taxa efetiva diária coloca o consumidor em nítida desvantagem exagerada, violando os princípios da boa-fé objetiva, da equidade contratual e do dever de clareza, consagrados no art. 51, IV, do CDC.'),
    ('p', 'Diante disso, a jurisprudência pátria vem consolidando o entendimento de que a cobrança de encargos abusivos durante a normalidade contratual, como a capitalização diária não pactuada de forma clara e expressa, é suficiente para descaracterizar a mora do consumidor, afastando os efeitos jurídicos dela decorrentes, inclusive em eventuais ações de busca e apreensão.'),
    ('p', 'Ressalte-se, por oportuno, que o entendimento ora defendido encontra respaldo em recentes precedentes dos Tribunais pátrios, cujos trechos colacionam-se a seguir, por guardarem plena pertinência com a matéria em debate:'),
    ('q', 'DIREITO CIVIL E PROCESSUAL CIVIL. EMBARGOS DE DECLARAÇÃO. CONTRATO DE ALIENAÇÃO FIDUCIÁRIA. CAPITALIZAÇÃO DIÁRIA DE JUROS SEM TAXA EXPRESSA. DESCARACTERIZAÇÃO DA MORA. [...] 6. Segundo o STJ (REsp 1826463/SC), a capitalização diária de juros exige, além da pactuação expressa, a indicação da taxa diária correspondente, sob pena de violação ao dever de informação do consumidor (arts. 6º, III, 46, 52, II, 54-B, II e 54-D, I, do CDC). 7. No caso, embora haja cláusula contratual prevendo a capitalização das taxas mensal e anual, não consta a taxa diária de juros, tornando abusiva a cláusula e ilegítima a cobrança. 8. A ausência de informação clara quanto à taxa diária gera desequilíbrio contratual e compromete a boa-fé objetiva, configurando cláusula abusiva. 9. A cobrança de capitalização diária sem a taxa respectiva descaracteriza a mora do devedor.'),
    ('qf', '(TJ-AL - Embargos de Declaração Cível: 07030156220248020001 Maceió, Relator.: Des. Paulo Barros da Silva Lima, Data de Julgamento: 21/08/2025, 1ª Câmara Cível, Data de Publicação: 22/08/2025)'),
    ('q', 'DIREITO CIVIL E DO CONSUMIDOR. APELAÇÕES CÍVEIS. CONTRATO DE EMPRÉSTIMO COM GARANTIA DE VEÍCULO. AÇÃO REVISIONAL. JUROS REMUNERATÓRIOS ABUSIVOS. CAPITALIZAÇÃO DIÁRIA DE JUROS. DESCARACTERIZAÇÃO DA MORA. REPETIÇÃO EM DOBRO DO INDÉBITO. [...] A capitalização diária de juros remuneratórios é ilegal por ausência de cláusula contratual clara e expressa sobre a taxa diária aplicada, violando o dever de informação e a jurisprudência consolidada do STJ. Reconhecida a ilegalidade da capitalização diária de juros, impõe-se a descaracterização da mora contratual, nos termos do Tema 28 do STJ. [...] Em contratos firmados após 30/03/2021, a repetição do indébito deve ocorrer em dobro, independentemente da comprovação de má-fé da instituição financeira.'),
    ('qf', '(TJ-AL - Apelação Cível: 07017023220258020001 Maceió, Relator.: Des. Alcides Gusmão da Silva, Data de Julgamento: 05/02/2026, 3ª Câmara Cível, Data de Publicação: 09/02/2026)'),
    ('qf', '(Grifos nossos)'),
    ('p', 'Diante disto, deve ser reconhecida a DESCARACTERIZAÇÃO DA MORA da parte autora em decorrência da NULIDADE DESTA CAPITALIZAÇÃO DIÁRIA DE JUROS REMUNERATÓRIOS, seja pelos argumentos da inconstitucionalidade, seja pela não pactuação clara, adequada e expressa no contrato.'),
    ('vazio', ''),
    ('-CAPDIARIA',),

    # ---------------------------------------------- TESE 2: JUROS DE MORA > 1%
    ('+JUROSMORA',),
    ('h', '{{§}}. DA ILEGALIDADE DOS JUROS DE MORA SUPERIORES A 1% AO MÊS – VIOLAÇÃO À SÚMULA 379 DO STJ'),
    ('p', 'É imperioso reconhecer, com a máxima ênfase e respaldo jurídico, que a cobrança de juros moratórios em percentual superior a 1% ao mês, conforme previsto no contrato em análise, constitui prática manifestamente ilegal, afrontando de maneira direta e inequívoca o entendimento consolidado pelo Superior Tribunal de Justiça.'),
    ('p', 'A Súmula 379 do STJ é categórica ao dispor que, nos contratos bancários não regidos por legislação específica, os juros moratórios podem ser convencionados até o limite de 1% ao mês. Tal orientação visa justamente coibir abusos na estipulação contratual, garantir a segurança jurídica e preservar a boa-fé objetiva nas relações contratuais.'),
    ('q', 'APELAÇÃO CÍVEL. AÇÃO DE REVISÃO DE CONTRATO DE FINANCIAMENTO CUMULADA COM PEDIDO DE CONSIGNAÇÃO INCIDENTE. SENTENÇA DE PARCIAL PROCEDÊNCIA. RECURSO INTERPOSTO PELA PARTE RÉ. LIMITAÇÃO DOS JUROS DE MORA A 1% AO MÊS. EMBORA A CÉDULA DE CRÉDITO BANCÁRIO SEJA REGIDA POR LEGISLAÇÃO ESPECÍFICA, A LEI EM QUESTÃO NÃO TRATA DOS JUROS MORATÓRIOS, RAZÃO PELA QUAL DEVE SER APLICADO O DISPOSTO NA SÚMULA 379 DO STJ. TARIFA DE CADASTRO. POSSIBILIDADE DE COBRANÇA. RECURSO CONHECIDO E PARCIALMENTE PROVIDO.'),
    ('qf', '(TJ-AL - Apelação Cível: 0732626-36.2019.8.02.0001 Maceió, Relator.: Des. Tutmés Airan de Albuquerque Melo, Data de Julgamento: 15/05/2024, 1ª Câmara Cível, Data de Publicação: 17/05/2024)'),
    ('p', 'A pactuação entre as partes é admitida, desde que respeitado o teto de 1% ao mês, limite este que se fundamenta, ainda, no artigo 406 do Código Civil, combinado com o artigo 161, §1º, do Código Tributário Nacional, ao contrário do disposto no contrato, que prevê juros moratórios de {{JUROS_MORA}}. Senão vejamos, no contrato:'),
    ('img', '[INSERIR AQUI O PRINT DA CLÁUSULA DE MULTA E JUROS DE ATRASO]'),
    ('p', 'A estipulação de juros moratórios em patamar superior ao permitido pela legislação configura, portanto, cláusula abusiva, sujeita à revisão judicial, conforme autorizado expressamente pelo art. 6º, inciso V, e pelo art. 51, inciso IV, do Código de Defesa do Consumidor, que repudiam práticas contratuais que coloquem o consumidor em desvantagem excessiva ou contrariem os princípios da equidade, consequentemente acarretando a descaracterização da mora.'),
    ('p', 'Dessa forma, impõe-se a adequação do percentual dos juros de mora ao limite legal de 1% ao mês, posto que qualquer cobrança em patamar superior a este representa não apenas violação à jurisprudência pacificada do STJ, mas também enriquecimento ilícito da parte credora, em nítido desrespeito aos ditames legais e à função social do contrato, ensejando a DESCARACTERIZAÇÃO DA MORA D{{O_A_MAI}} AUTOR{{A_MAI}}.'),
    ('p', 'Assim sendo, requer-se, com o devido acatamento, a imediata limitação dos juros moratórios ao teto legal de 1% ao mês, com a consequente nulidade da cláusula abusiva.'),
    ('vazio', ''),
    ('-JUROSMORA',),

    # ---------------------------------------------- TESE 3: ENCARGOS / VENDA CASADA
    ('+ENCARGOS',),
    ('h', '{{§}}. DOS ENCARGOS ABUSIVOS E DA VENDA CASADA'),
    ('p', 'A Ré cobra, no contrato em análise, {{LISTA_ENCARGOS}}.'),
    ('p', 'Nestes termos, ressalta-se o posicionamento do e. Tribunal da Cidadania, frisando, inclusive, que havendo a constatação destes encargos, deve ser descaracterizada a mora do devedor:'),
    ('q', 'CIVIL E PROCESSUAL. AGRAVOS REGIMENTAIS. CONTRATO DE FINANCIAMENTO COM ALIENAÇÃO FIDUCIÁRIA EM GARANTIA. [...] ENCARGOS INDEVIDAMENTE COBRADOS. DESCARACTERIZAÇÃO DA MORA. TEMAS PACIFICADOS. omissis III. A descaracterização da mora ocorre pela cobrança de encargos indevidos, como, no caso concreto, as tarifas de emissão de carnê, de abertura de crédito e a "bancária", entendimento amparado na jurisprudência pacificada na 2ª Seção do STJ, nos termos do EREsp n. 163.884/RS, Rel. p/ acórdão Min. Ruy Rosado de Aguiar, e REsp n. 713.329/RS, Rel. p/ acórdão Min. Carlos Alberto Menezes Direito. IV. Agravos improvidos.'),
    ('qf', '(STJ, AgRg no REsp 899287/RS, Rel. Min. Aldir Passarinho Júnior, Quarta Turma, DJ 07.05.2007)'),
    ('+SEGURO',),
    ('p', 'Com relação ao SEGURO, no valor de R$ {{VALOR_SEGURO}} ({{VALOR_SEGURO_EXT}}), o STJ já enfrentou a temática da venda casada de seguros sob o espectro vinculativo dos Recursos Repetitivos, tendo fincado no TEMA 972 – REsp 1639320/SP, a tese segundo a qual “2 - Nos contratos bancários em geral, o consumidor não pode ser compelido a contratar seguro com a instituição financeira ou com seguradora por ela indicada.”.'),
    ('p', 'Trata-se da consagração da dupla liberdade (a) de contratar e (b) de escolher com quem contratar. Ora, um ligeiro cotejo contratual nos entremostra que a parte autora tinha pouca ou nenhuma escapatória na escolha da seguradora, já previamente eleita e pertencente ao mesmo grupo econômico da ré. Esse fato incontroverso nos autos desafia a inversão do ônus da prova, desde logo requerida.'),
    ('-SEGURO',),
    ('p', 'Ocorre, Excelência, que não há qualquer discriminação pormenorizada do que sejam esses pagamentos extorsivos. Com isso, essas cobranças, à luz do CDC, são contrárias aos direitos básicos do consumidor, o que as tornam ilegais e/ou abusivas, não podendo de forma alguma qualquer resolução se sobrepor à legislação federal:'),
    ('q', 'Art. 51. São nulas de pleno direito, entre outras, as cláusulas contratuais relativas ao fornecimento de produtos e serviços que: (...) IV – estabeleçam obrigações consideradas iníquas, abusivas, que coloquem o consumidor em desvantagem exagerada, ou sejam incompatíveis com a boa-fé ou a equidade.'),
    ('q', 'Art. 6. São direitos básicos do consumidor: (...) III – a informação adequada e clara sobre os diferentes produtos e serviços, com especificação correta de quantidade, características, composição, qualidade e preço, bem como sobre os riscos que apresentem.'),
    ('p', 'Com isso, como essas cobranças não apresentam qualquer serviço prestado ao consumidor, não são transparentes quanto às suas finalidades, bem como foram impostas como forma de “venda casada”, merecem ser declaradas nulas, com a consequente exclusão dos respectivos valores do montante financiado e a repetição do indébito, em dobro, dos valores cobrados.'),
    ('vazio', ''),
    ('-ENCARGOS',),

    # ---------------------------------------------- TESE 4: TARIFA DE AVALIAÇÃO
    ('+TARIFAAVAL',),
    ('h', '{{§}}. DA ABUSIVIDADE NA COBRANÇA DA TARIFA DE AVALIAÇÃO'),
    ('p', 'A partir da exegese da Resolução-CMN n. 3.518/2007, atualmente revogada e substituída pela Resolução CMN n. 3.919/2010, compreendeu-se que a validade da cobrança de tarifa nos contratos bancários depende da conjugação dos seguintes elementos: (i) a tarifa ter sua cobrança autorizada pela citada normativa; (ii) expressa previsão contratual ou o serviço tarifado ter sido solicitado pelo consumidor; e (iii) respeito ao fato gerador da cobrança constante do anexo da Resolução 3.919/10.'),
    ('p', 'Especificamente sobre a tarifa de avaliação, o Superior Tribunal de Justiça firmou tese em sede de recurso repetitivo no sentido de que é válida a sua cobrança. No entanto, essa cobrança é considerada abusiva quando: a) o serviço não for efetivamente prestado; b) houver onerosidade excessiva (Tema nº 958).'),
    ('p', 'Nesse sentido, é essencial que se fixe como ônus à parte Ré (art. 373, I, CPC) na ação revisional de contrato a prova da efetiva prestação do serviço de avaliação e respectivo pagamento deste serviço. E, portanto, seja aplicada a inversão do ônus prevista no art. 6º, VIII, do CDC, por ser a parte Autora vulnerável e a prova ser impossível para esta, porque está na esfera de disponibilidade exclusiva da Ré.'),
    ('p', 'Vale destacar que a prova da avaliação não pode ser suprida pela simples apresentação de: a) vistoria simples do veículo; b) cotação feita por sistemas abstratos; c) tabela FIPE; d) avaliação realizada pelo vendedor do bem.'),
    ('p', 'Mesmo que a Resolução CMN 3.919/10 não conceitue ou detalhe como deve ser a avaliação, deve-se compreender que a cobrança por este serviço somente poderá ocorrer quando o bem for efetivamente avaliado (física e juridicamente) e no documento avaliativo constar necessariamente a descrição detalhada do bem objeto da avaliação, todas as suas características, o seu estado de conservação e o seu valor. Isso decorre do emprego, por analogia (permitido pelo art. 4º da LINDB) da Resolução CMN n° 4.676 de 31/7/2018, que assim diz:'),
    ('q', 'Art. 11-A. Para fins desta Resolução, a avaliação de imóvel compreende: I - a análise técnica efetuada para a estimação do valor de um bem imóvel, com base em suas especificações, características, custos, frutos, direitos e finalidade; e II - a análise jurídica efetuada para determinar riscos que possam repercutir sobre a viabilidade da utilização do bem imóvel como garantia, incluindo a confirmação da titularidade, da livre disposição do imóvel e da inexistência de ônus ou impedimentos.'),
    ('p', 'Em último plano, no mínimo a avaliação deverá seguir o que diz o art. 872 do CPC.'),
    ('p', 'Portanto, forte no art. 51, IV, do CDC, merece ser declarada nula a cláusula que prevê a TARIFA DE AVALIAÇÃO, no valor de R$ {{TARIFA_AVALIACAO}} ({{TARIFA_AVALIACAO_EXT}}), devendo ser excluído tal valor do montante total financiado, com a consequente repetição do indébito, em dobro, dos valores cobrados.'),
    ('vazio', ''),
    ('-TARIFAAVAL',),

    # ---------------------------------------------- TESE 5: JUROS ACIMA DA MÉDIA BACEN
    ('+JUROSBACEN',),
    ('h', '{{§}}. DA DESCARACTERIZAÇÃO DA MORA EM VIRTUDE DA TAXA DE JUROS SE ENCONTRAR ACIMA DA MÉDIA DE MERCADO DIVULGADA PELO BANCO CENTRAL'),
    ('p', 'O contrato bancário possui taxa de juros acima da média do mercado divulgada pelo Banco Central à época da contratação. A taxa à época da contratação do financiamento divulgada pelo Banco Central era de {{BACEN_ANUAL}}% a.a. (ou {{BACEN_MENSAL}}% a.m.), enquanto no financiamento consta uma taxa de juros de {{TX_ANUAL}}% a.a. (ou {{TX_MENSAL}}% a.m.), ou seja, uma diferença extremamente abusiva de {{DIF_ANUAL}}% a.a. (ou {{DIF_MENSAL}}% a.m.), que multiplicada pelo tempo de financiamento — no caso, {{ANOS_FINANCIAMENTO}} — totaliza {{DIF_TOTAL}}% acima do que é referenciado pelo Banco Central, e é a causa direta de uma distorção financeira brutal: para um financiamento de R$ {{VALOR_LIBERADO}}, a parte autora se viu obrigada a pagar um montante final de R$ {{TOTAL_FINANCIADO}}, um valor {{PERC_ACRESCIMO}}% superior ao capital liberado. A desvantagem exagerada é manifesta. Veja-se:'),
    ('img', '[INSERIR AQUI O PRINT DA TAXA MÉDIA DE JUROS DO BACEN NO PERÍODO DA CONTRATAÇÃO]'),
    ('p', 'Outrossim, o E. STJ dispõe do seguinte entendimento acerca das taxas de juros aplicadas a contratos bancários e suas respectivas abusividades, veja-se:'),
    ('q', 'AGRAVO INTERNO NO RECURSO ESPECIAL. AÇÃO REVISIONAL. CONCLUSÃO NO SENTIDO DA ABUSIVIDADE DA TAXA DE JUROS REMUNERATÓRIOS. ÍNDICE CONTRATADO SUPERIOR À MÉDIA DE MERCADO APURADA PELO BACEN. SÚMULAS 5 E 7/STJ. AGRAVO INTERNO DESPROVIDO. [...] 2. O fato de a taxa de juros entabulada supostamente não ser superior a uma vez e meia a taxa média apurada pelo Bacen não impede o reconhecimento da abusividade. Essa aferição compete às instâncias ordinárias, que fazem, para sua conclusão, uma apreciação entre a prevista no contrato e a média de mercado, o que foi feito para justificar a conclusão pela abusividade. 3. Agravo interno desprovido.'),
    ('qf', '(STJ - AgInt no REsp: 1979175 RS 2021/0406124-4, Relator: Ministro MARCO AURÉLIO BELLIZZE, Data de Julgamento: 16/05/2022, T3 - TERCEIRA TURMA, Data de Publicação: DJe 18/05/2022)'),
    ('q', 'AGRAVO INTERNO NO AGRAVO EM RECURSO ESPECIAL. [...] AÇÃO DE BUSCA E APREENSÃO. JUROS REMUNERATÓRIOS. TAXA MÉDIA DE MERCADO. NÃO OBSERVÂNCIA. REVISÃO. POSSIBILIDADE. MORA DESCARACTERIZADA. [...] 3. Em conformidade com a jurisprudência pacífica desta Corte Superior, firmada por ocasião do julgamento do Recurso Especial 1.061.530/RS, submetido ao rito dos recursos repetitivos, "o reconhecimento da abusividade nos encargos exigidos no período da normalidade contratual (juros remuneratórios e capitalização) descaracteriza a mora".'),
    ('qf', '(STJ - AgInt no AREsp: 1584971 RS 2019/0277195-0, Relator: Ministro RAUL ARAÚJO, Data de Julgamento: 22/03/2021, T4 - QUARTA TURMA, Data de Publicação: DJe 13/04/2021)'),
    ('p', 'Portanto, por se tratar de encargo abusivo no período da normalidade contratual, NÃO HÁ MORA POR PARTE D{{O_A_MAI}} AUTOR{{A_MAI}}, devendo ser aplicado ao caso em comento o Recurso Repetitivo e Representativo, na Relatoria da e. Min. Nancy Andrighi (REsp 1.061.530/RS):'),
    ('q', '“ORIENTAÇÃO 2 - CONFIGURAÇÃO DA MORA a) O reconhecimento da abusividade nos encargos exigidos no período da normalidade contratual (juros remuneratórios e capitalização) descaracteriza a mora;”'),
    ('qf', '(STJ, REsp 1.061.530/RS, Rel. Min. Nancy Andrighi, 2ª Seção, DJe 10.03.2009)'),
    ('p', 'Assim, requer o reconhecimento da ilegalidade da taxa de juros remuneratórios aplicada ao contrato, com a sua substituição pela TAXA MÉDIA BACEN de {{BACEN_MENSAL}}% a.m. e {{BACEN_ANUAL}}% a.a., afastando-se, pois, a mora contratual e julgando procedente a presente ação.'),
    ('vazio', ''),
    ('-JUROSBACEN',),

    # ---------------------------------------------- REPETIÇÃO DO INDÉBITO
    ('h', '{{§}}. DA REPETIÇÃO DO INDÉBITO'),
    ('p', 'Ao longo do contrato houve pagamentos indevidos e a maior, os quais precisam ser devolvidos em dobro, acrescidos de juros desde a primeira cobrança ilícita realizada (art. 398, CC), incidentes sobre a diferença corrigida monetariamente, tendo em vista que a ré converteu uma obrigação ex re (art. 397, CC) em trampolim de ilicitude para cobrar valores acima dos expressamente devidos.'),
    ('p', 'A título de esclarecimento, as parcelas estão sendo cobradas em dobro, sem prejuízo da inclusão das parcelas vincendas e que forem pagas ao longo do processo no montante originário do contrato, tendo em vista o precedente formado pela CORTE ESPECIAL do STJ no EAREsp 676.608/RS, Rel. Ministro OG FERNANDES, julgado em 21/10/2020, DJe 30/03/2021.'),
    ('p', 'Isto posto, requer que seja descaracterizada a mora da parte autora, afastando os encargos moratórios, bem como que, caso haja crédito a favor da parte autora, seja determinada a compensação/repetição de indébito, corrigidos pelo INPC desde o desembolso e com juros legais desde a citação do Réu.'),
    ('vazio', ''),

    # ---------------------------------------------- INVERSÃO DO ÔNUS
    ('h', '{{§}}. DA INVERSÃO DO ÔNUS DA PROVA'),
    ('p', 'Tendo em vista que se trata de uma relação consumerista a travada entre pessoa física e uma instituição bancária, a parte autora requer, nos termos do artigo 6º, inciso VIII, da Lei nº 8.078/90, a inversão do ônus da prova a fim de que o Banco comprove:'),
    ('lista', 'a) O custo da captação dos recursos pela instituição financeira credora (esse custo varia entre os agentes do mercado financeiro), na época da contratação;'),
    ('lista', 'b) O risco envolvido na operação, aqui considerado o histórico de crédito do devedor, fornecendo o histórico do Rating bancário da parte autora;'),
    ('lista', 'c) Que ofertou alternativas à contratação da seguradora pertencente ao seu mesmo grupo econômico;'),
    ('lista', 'd) Que efetivamente prestou os serviços de avaliação do bem e de registro no órgão de trânsito.'),
    ('vazio', ''),

    # ------------------------------------------------------------------ PEDIDOS
    ('bar', 'DOS PEDIDOS'),
    ('p', 'Posto isso, requer:'),
    ('lista', '1) O deferimento da justiça gratuita;'),
    ('lista', '2) Que, neste momento, não seja designada audiência preliminar de conciliação prevista no artigo 334 do Código de Processo Civil, sem prejuízo de que a mesma seja realizada após a citação do réu e/ou a apresentação do contrato e dos documentos que o compõem, quando então a parte Autora poderá ter ciência de todo o conteúdo contratual;'),
    ('lista', '3) A concessão da tutela de urgência satisfativa antecipada e acautelatória (Tema 31 do STJ – REsp 1.061.530/RS), a fim de que:'),
    ('+DEPINTEGRAL',),
    ('lista', 'a) Seja deferido à parte autora o direito de DEPOSITAR JUDICIALMENTE O VALOR INTEGRAL de cada parcela, no importe de R$ {{VALOR_PARCELA}} ({{VALOR_PARCELA_EXT}}), mantendo a posse do bem em favor da parte Autora;'),
    ('-DEPINTEGRAL',),
    ('+DEPINCONTROVERSO',),
    ('lista', 'a) Seja deferido à parte autora o direito de contraprestar doravante o valor incontroverso de R$ {{PARCELA_INCONTROVERSA}} ({{PARCELA_INCONTROVERSA_EXT}}), determinando-se à ré a emissão de novo carnê, sob pena de multa diária, e/ou ainda autorizado o depósito judicial do montante, mantendo a posse do bem em favor da parte Autora;'),
    ('-DEPINCONTROVERSO',),
    ('lista', 'b) Seja afastada a mora com base no TEMA 28 dos precedentes do STJ (REsp 1061530/RS);'),
    ('lista', 'c) Seja a ré inibida, sob pena de multa diária, de:'),
    ('lista', 'c.1) Ajuizar busca e apreensão enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', 'c.2) Inserir o nome e CPF da parte autora no SCR Bacen, seja na guia vencido, seja na guia prejuízo, enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', 'c.3) Inserir o nome e CPF da parte autora no SPC, SERASA e BOA VISTA, enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', 'c.4) Levar o nome e CPF da parte autora a PROTESTO CARTORÁRIO em razão dos débitos aqui discutidos, enquanto perdurarem os efeitos da tutela de urgência requerida;'),
    ('lista', '4) Que, LIMINARMENTE, seja oficializado o Setor de Distribuição do Fórum para que, caso a parte ré ingresse com uma Ação Possessória (Busca e Apreensão ou Reintegração de Posse) em desfavor da parte autora e que se refira ao mesmo contrato/bem desta ação, seja ela destinada a este d. juízo, a fim de ser apensada por dependência ao presente processo, determinando, logo após o apensamento, a SUSPENSÃO desta ação possessória;'),
    ('lista', '5) A citação e intimação da parte demandada, para, querendo, apresentar defesa no prazo legal, sob pena de revelia;'),
    ('lista', '6) A inversão do ônus da prova;'),
    ('lista', '7) Que seja julgada procedente a ação, declarando a NULIDADE DOS VALORES e cláusulas contratuais abusivos e/ou ilegais indicados na exordial ({{CLAUSULAS_ABUSIVAS}}) e outras que serão apontadas precisamente na primeira oportunidade que tiver conhecimento de todo o contrato bancário, o que não faz neste momento por culpa exclusiva do Réu em não ter entregue, previamente, uma via deste contrato (COMPLETO) à parte autora;'),
    ('lista', '8) Ainda, em homenagem ao princípio da eventualidade, declarar afastada a mora da parte requerente, com a vedação à requerida de realizar a cobrança de qualquer encargo moratório sobre as prestações inadimplidas antes e após o ajuizamento da ação;'),
    ('lista', '9) Condenar a Demandada à repetição do indébito em dobro, acrescido de juros desde a primeira cobrança ilícita realizada (art. 398, CC), incidente sobre a diferença corrigida monetariamente, tendo em vista que a ré converteu uma obrigação ex re (art. 397, CC) em trampolim de ilicitude para cobrar valores acima dos expressamente devidos;'),
    ('lista', '10) Que seja a Requerida condenada ao pagamento das custas processuais e honorários advocatícios de sucumbência, que requer sejam fixados no percentual de 20% (vinte por cento) do valor da condenação;'),
    ('lista', '11) Protesta provar o alegado por todos os meios de prova em direito admissíveis, especialmente a documental inclusa e depoimento pessoal do Representante da Demandada sob pena de confissão, bem como a apresentação de demais documentos que entender necessários e que forem ordenados, tudo nos termos do art. 369 do CPC.'),
    ('vazio', ''),
    ('p', 'Dá-se à causa o valor de R$ {{VALOR_CAUSA}} ({{VALOR_CAUSA_EXT}}).'),
    ('vazio', ''),
    ('c', 'Nestes termos,'),
    ('c', 'Pede deferimento.'),
    ('vazio', ''),
    ('c', '{{LOCAL}}, {{DATA_EXTENSO}}.'),
    ('vazio', ''),
    ('vazio', ''),
    ('c', '{{ADVOGADA}}'),
    ('c', 'OAB/{{OAB_UF}} {{OAB_NUM}}'),
]

# Linhas possíveis do quadro do contrato.
# (chave do campo, rótulo que sai no documento, tipo)
LINHAS_QUADRO = [
    ('VALOR_VEICULO',      'Valor do veículo à vista',            'moeda'),
    ('VALOR_ENTRADA',      'Valor da entrada',                    'moeda'),
    ('VALOR_LIBERADO',     'Valor Líquido Liberado',              'moeda'),
    ('VALOR_SEGURO',       'Seguro',                              'moeda'),
    ('TARIFA_CADASTRO',    'Tarifa de Cadastro',                  'moeda'),
    ('TARIFA_AVALIACAO',   'Tarifa de Avaliação',                 'moeda'),
    ('TARIFA_REGISTRO',    'Registro de contrato - órgão de trânsito', 'moeda'),
    ('IOF',                'IOF',                                 'moeda'),
    ('IOF_ADICIONAL',      'IOF Adicional',                       'moeda'),
    ('DATA_ASSINATURA',    'Data de assinatura',                  'texto'),
    ('DATA_PRIMEIRO_VENC', 'Data do 1º Vencimento',               'texto'),
    ('QTD_PARCELAS',       'Número de parcelas mensais',          'texto'),
    ('TX_MENSAL',          'Taxa de juros mensal',                'perc'),
    ('TX_ANUAL',           'Taxa de juros anual',                 'perc'),
    ('JUROS_MORA',         'Juros moratórios',                    'texto'),
    ('VALOR_PARCELA',      'Valor de cada parcela mensal',        'moeda'),
    ('TOTAL_FINANCIADO',   'Valor total financiado com impostos', 'moeda'),
]
