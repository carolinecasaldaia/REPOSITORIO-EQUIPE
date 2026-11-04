# Gerador de Contratos — Caroline Macedo Advocacia

Monta, de uma vez, os documentos de onboarding do cliente a partir de um
formulário simples:

| Documento | Arquivo gerado |
|---|---|
| Contrato de prestação de serviços | `2. CONTRATO DE PRESTAÇÃO DE SERVIÇOS COMPLETO - NOME.docx` |
| Procuração | `3. PROCURAÇÃO - NOME.docx` |
| Declaração de hipossuficiência | `4. DECLARAÇÃO DE HIPOSSUFICIÊNCIA - NOME.docx` |
| Declaração de residência (opcional) | `6. DECLARAÇÃO DE RESIDÊNCIA - NOME.docx` |

Os quatro saem em **.docx**, com o timbrado, as fontes e as margens dos
contratos do escritório — prontos para revisar e subir no Autentique.

---

## Como usar

1. Dois cliques em **Gerar Contratos** (o atalho na Área de Trabalho).
   Na primeira vez o macOS pode reclamar que “não é de um desenvolvedor
   identificado”: clique com o botão direito no arquivo → **Abrir** → **Abrir**.
2. A página abre no navegador, no endereço
   **`http://127.0.0.1:8791/gerador_contratos.html`**. Se não abrir sozinha,
   copie esse endereço da janela preta e cole em qualquer navegador.
   **Deixe a janela preta aberta** enquanto estiver usando.
   Escolha o **tipo de ação**, preencha os dados do cliente e os honorários.
3. Confira o quadro **Conferência**, na coluna da direita: ele mostra a
   qualificação do cliente, a cláusula 1ª e a cláusula 2ª já montadas, com os
   valores por extenso.
4. Clique em **Gerar documentos**. Os `.docx` caem na pasta **Downloads**.

Nada sai da máquina: o endereço `127.0.0.1` é a sua própria máquina e só aceita
conexão local — não usa internet nem nenhum site. O formulário fica salvo no
navegador, então se fechar sem querer o preenchimento continua lá.

> **Dá para abrir o `gerador_contratos.html` clicando nele?**
> Dá — testado no Chrome e no Firefox, abrindo direto da pasta do Drive. É o
> jeito mais simples de outra pessoa usar (ver “Outra pessoa usando o gerador”,
> mais abaixo).
> O atalho prefere o `http://127.0.0.1` por dois motivos práticos: funciona
> igual em qualquer navegador, sem depender de onde a pasta está, e em `http://`
> o navegador guarda o rascunho do formulário e baixa os quatro arquivos sem as
> restrições que alguns navegadores impõem a páginas abertas como arquivo
> local.

---

## Os 5 tipos de ação

O que muda de um tipo para o outro é a **cláusula 1ª** e quais cláusulas
entram no contrato:

| Tipo | Cláusula 1ª | Cláusulas |
|---|---|---|
| **Revisional de financiamento** | “Ação Revisional em desfavor do Banco X, referente ao contrato de financiamento do veículo…” | 24 |
| **Revisional de empréstimo com veículo em garantia** | “Ação Revisional de Empréstimo com garantia de veículo…, referente ao contrato sob garantia do veículo…” | 24 |
| **Revisional de empréstimo** | “Ação Revisional de Empréstimo em desfavor do Banco X, referente ao contrato de empréstimo nº…” | 24 |
| **Defesa em busca e apreensão** | “…defesa na Ação de Busca e Apreensão sob o nº…, Estado de X, … – Veículo não se encontra apreendido.” | 22 |
| **Defesa em busca e apreensão com veículo apreendido** | “…defesa da Ação de Busca e Apreensão sob o nº… – veículo apreendido no Estado de X, na data de…” | 22 |

Nas **revisionais** entram duas cláusulas que não existem nas defesas:

- as **guias judiciais** para depósito do valor incontroverso/integral;
- os **20% sobre o proveito econômico** caso o banco ajuíze busca e apreensão.

Nas **defesas** esses 20% já aparecem na cláusula 2ª, como *honorários
advocatícios finais sobre o ganho* — por isso o gerador marca essa opção
sozinho quando você escolhe um dos dois tipos de busca e apreensão.

A numeração das cláusulas se refaz sozinha. Não existe risco de sair
“Cláusula 19ª” duas vezes ou pular um número.

---

## O que o gerador calcula sozinho

- **Valor total dos honorários** = entrada + (parcelas × valor).
  Só preencha o campo Total se quiser um valor diferente do calculado.
- **Data da última parcela** = 1ª parcela + (quantidade − 1) meses.
- **Todos os valores por extenso**, inclusive centavos:
  `R$ 12.639,84 (doze mil seiscentos e trinta e nove reais e oitenta e quatro centavos)`.
- **Quantidade de parcelas por extenso, no feminino**: `32 (trinta e duas) parcelas`.
- **Concordância de gênero** em tudo: *brasileiro/brasileira*,
  *portador/portadora*, *inscrito/inscrita*, *residente e domiciliado/domiciliada*,
  *solteiro/solteira*, *divorciado/divorciada*.
- **Preposição do endereço**: “residente e domiciliado **na** Rua…” /
  “**no** Condomínio…”, e “**à** Avenida…” / “**ao** Sítio…” na declaração de
  residência.
- **Estado por extenso** a partir da UF: `de Alagoas`, `do Amapá`, `de Goiás`…
- **Local de assinatura**: o contrato assina em Maceió; a procuração e as
  declarações assinam na cidade do cliente.

---

## Campos que aparecem e desaparecem

- **Segundo signatário** (Cliente Responsável pelo pagamento): marque a caixa.
  Ele entra na qualificação de abertura e ganha um bloco de assinatura próprio.
- **Duas faixas de parcela** (ex.: `01 de R$ 563,35 e 14 de R$ 413,35`):
  marque “o parcelamento tem uma segunda faixa de valores”.
- **Cartão de crédito na recorrência**: acrescenta na cláusula 2ª as cinco
  cláusulas sobre manter o meio de pagamento ativo, e o `- CARTÃO DE CRÉDITO NA
  RECORRÊNCIA` no fim da linha das parcelas.
- **Boleto mensal**: no lugar delas entra o aviso de que os boletos são gerados
  em nome do escritório e enviados por e-mail, WhatsApp e SMS.
- **Vara e Comarca** (nas defesas): se ficarem vazios, o texto simplesmente
  pula o “distribuída na … da Comarca de …”, sem deixar buraco na frase.
- **Sistema de cobrança**: CONTA AZUL ou ASAAS. O padrão vem CONTA AZUL, que é
  o que aparece nos contratos mais recentes (fim de junho/2026).

---

## Outra pessoa usando o gerador

O endereço `http://127.0.0.1:8791/...` **não pode ser compartilhado**:
`127.0.0.1` significa “este computador”, então na máquina do outro o navegador
procuraria a página nele mesmo e não acharia nada.

Para alguém mais usar, compartilhe a **pasta** `GERADOR CONTRATOS` pelo Google
Drive. Na máquina dela:

1. Se a pasta chegar em **“Compartilhados comigo”**, ela precisa clicar com o
   botão direito → **Organizar** → **Adicionar atalho ao Drive**, dentro do
   próprio “Meu Drive”. Só assim o Google Drive baixa os arquivos para o disco —
   e o gerador precisa dos arquivos no disco.
2. Depois basta **dois cliques no `gerador_contratos.html`**. Abre no navegador e
   funciona igual: gera os quatro `.docx` na pasta Downloads dela.

O atalho `Gerar Contratos.command` pode **não** funcionar na máquina dela: o
Google Drive não leva a permissão de “executável” de um computador para outro, e
o macOS ainda avisa que o arquivo não é de um desenvolvedor identificado. Se ela
só vai gerar contratos, ignore o `.command` e use o `gerador_contratos.html`
direto. O `.command` importa para quem edita as cláusulas no Word, porque é ele
que reembute o texto novo na página.

Ou seja: quem **edita os modelos** usa o atalho; quem só **gera contratos** abre
o HTML.

---

## Para mudar o texto de uma cláusula

Não mexa no HTML. Abra no **Word** o modelo mestre correspondente, nesta mesma
pasta, edite e salve:

- `MODELO MESTRE - CONTRATO.docx`
- `MODELO MESTRE - PROCURACAO.docx`
- `MODELO MESTRE - DECLARACAO DE HIPOSSUFICIENCIA.docx`
- `MODELO MESTRE - DECLARACAO DE RESIDENCIA.docx`

Na próxima vez que abrir o atalho **Gerar Contratos**, o gerador já usa o texto
novo (o `.command` reembute os modelos toda vez que abre).

### Os marcadores dentro dos modelos

| Marcador | O que é |
|---|---|
| `{{CAMPO}}` | valor preenchido pelo formulário — não apague |
| `{{#}}` | número da cláusula; refaz a numeração sozinho |
| `[[+TAG]]` … `[[-TAG]]` | parágrafos inteiros que entram ou saem (em vermelho, pequeno) |
| `{{+TAG}}` … `{{-TAG}}` | trecho que entra ou sai **no meio da frase** |

Regras ao editar:

- **Não apague as linhas vermelhas** `[[+…]]` / `[[-…]]`. Elas são o que faz o
  bloco entrar ou sair. Se apagar uma, o gerador acusa erro.
- Pode escrever livremente **dentro** de um bloco.
- Se acrescentar uma cláusula nova, escreva o rótulo como
  `Cláusula {{#}}.` — a numeração se ajusta.
- Se quiser um campo novo, escreva `{{MEU_CAMPO}}`. O gerador vai avisar que
  esse campo ficou em branco (não sabe preenchê-lo), até que a página seja
  ajustada para pedi-lo.

Se algum modelo se perder, o botão **Baixar os 4 modelos mestres**, na coluna
da direita da página, devolve todos com os marcadores.

---

## Arquivos desta pasta

| Arquivo | Para que serve |
|---|---|
| `Gerar Contratos.command` | o atalho. É o único que você precisa abrir |
| `gerador_contratos.html` | a página do formulário (os modelos ficam embutidos aqui) |
| `MODELO MESTRE - *.docx` | os textos, editáveis no Word |
| `_embutir_modelos.py` | reembute os modelos na página; roda sozinho pelo atalho |
| `_abrir_gerador.py` | serve a página em `http://127.0.0.1:8791`; roda sozinho pelo atalho |
| `_construir_modelos.py` | reconstrói os 4 modelos do zero, a partir do `_conteudo_modelos.py` |
| `_conteudo_modelos.py` | o texto-fonte dos modelos. Só é usado na reconstrução |

---

## Detalhes que vale saber

- O modelo do contrato foi tirado do **“CONTRATO DE PRESTAÇÃO DE SERVIÇOS
  COMPLETO - ATUALIZADO 06:2026”** do cliente Carlos Daniel (25/06/2026), que é
  a versão mais nova de 24 cláusulas. A variante de 22 cláusulas veio do
  contrato da cliente Mariana (Goiás, veículo apreendido, 23/06/2026).
- Procuração, hipossuficiência e residência vieram dos `.docx` das pastas de
  junho/2026 (Carlos Daniel e Jailton).
- O modelo do tipo **“revisional de empréstimo”** puro (sem veículo) não existia
  assinado em nenhuma pasta — a redação da cláusula 1ª foi montada a partir da
  variante “empréstimo com garantia de veículo”. **Confira essa frase na
  primeira vez que usar esse tipo.**
- A página lê e regrava o `.docx` em JavaScript puro, sem servidor e sem
  biblioteca externa. Por isso os modelos são sempre gravados **sem compressão**;
  o `.command` renormaliza o arquivo toda vez, então salvar no Word não quebra
  nada.
- Entra no fluxo **antes** do separador do Autentique: gerar os documentos →
  colher as assinaturas no Autentique → `Separar Documentos` → `Gerar Onboarding
  do Cliente`.
