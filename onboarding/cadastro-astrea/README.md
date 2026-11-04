# Cadastro automático de clientes no Astrea

Quando o setor comercial cria a pasta de um cliente novo em
**PREPARAÇÃO PARA INGRESSO**, esta automação lê os documentos, extrai a
qualificação, valida, confere se o CPF já existe no Astrea e cadastra o cliente
— sem ninguém precisar digitar nada.

Ninguém do comercial roda comando nenhum. Basta criar a pasta.

---

## 1. Como funciona

```
Comercial cria a pasta do cliente e joga os documentos dentro
        ↓  (a automação verifica a pasta a cada 15 minutos)
Pasta parada há 10 minutos  →  sinal de que o upload terminou
        ↓
Acha o contrato de honorários assinado e lê a qualificação
        ↓
Confere com o comprovante de residência, quando dá
        ↓
Valida CPF (dígito verificador), e-mail, telefone, CEP
        ↓
Consulta o CPF no Astrea
        ├── já existe → registra o ID e NÃO duplica
        └── não existe → cadastra o contato
        ↓
Guarda o resultado e escreve no relatório de pendências
```

### Escopo atual: só o cadastro do cliente

A automação **cadastra o contato e para por aí**. A abertura do caso/pasta no
Astrea continua sendo sua, por enquanto — a tela de casos ainda não foi
calibrada e não faz sentido a automação clicar às cegas nela.

O que já foi lido do contrato **não se perde**: o tipo de ação e o banco adverso
aparecem no relatório, na coluna **"Caso a abrir"**, prontos para você abrir a
pasta sem precisar reabrir o contrato.

Quando a tela de casos for calibrada, é só trocar `ASTREA_CRIAR_CASO=true` no
`.env` — o resto do sistema já está preparado.

### De onde vêm os dados

Do **contrato de honorários assinado**, não das fotos de RG e CNH. Ele é PDF
com camada de texto e traz tudo num trecho de formato estável:

> …como Cliente Contratante **FULANO DE TAL**, *brasileiro, casado, vigilante,*
> portador do **RG** n°: … SSP/AL, inscrito no **CPF** de nº …, residente e
> domiciliado na **Rua Bom Jesus, 27 A – Benedito Bentes – Maceió/AL – CEP:
> 57084-818**, endereço eletrônico: **fulano@gmail.com** e contato telefônico
> **(82) 99188-6196**…

É texto digital assinado eletronicamente pelo próprio cliente — mais confiável
que OCR de foto, e é a mesma fonte que o *Gerador de Onboarding* já usa.

As CNH-e em PDF **não** servem: os dados estão dentro de uma imagem (o PDF só
tem o carimbo do SERPRO). Elas entram no relatório como *documento não
interpretado*, sem chute.

### Trava de documentação (25/09/2026)

Nada anda — nem o cadastro no Astrea, nem a abertura do caso, nem a cópia da
pasta para "A - REVISIONAL"/"A - CÍVEL" — enquanto a pasta do cliente no
COMERCIAL não tiver:

- **RG ou CNH** (documento de "RESP FINANCEIRO" não conta)
- **COMPROVANTE DE RESIDÊNCIA** (aceita "C DE RESIDÊNCIA", "COMP RESIDÊNCIA")
- **CRLV** — só em Busca e Apreensão e Revisional Veicular

O contrato bancário chegou a ser exigido e foi retirado da lista no mesmo
dia (25/09/2026).

O documento é reconhecido **só pelo nome do arquivo/subpasta** (.docx, áudio
e planilha não contam). Arquivo com nome que não diz o que é
("WhatsApp Image….jpeg") trava a pasta: renomeie e a próxima rodada libera
sozinha. O motivo aparece no relatório de pendências. Regras em
`src/validators/documentacao.py`.

### Quais meses a automação olha (25/09/2026)

Só **SETEMBRO 2026 em diante** (`MESES=a partir de SETEMBRO 2026` no
`.env`). Nunca mexe nas pastas dos meses anteriores. Na virada do mês,
setembro continua sendo olhado, e a pasta do mês seguinte também, caso o
comercial a crie antes da virada.

### O que a automação nunca faz

- **Não inventa dado.** Campo que não está no documento fica vazio. Se for
  obrigatório, o cliente vira pendência em vez de ser cadastrado.
- **Não cadastra sem conferir duplicidade.** Se o Astrea não responder à busca
  do CPF, o cliente espera a próxima rodada.
- **Não apaga, não move e não altera nada** — nem no Drive, nem no Astrea.
  Ela só lê, valida, consulta, cadastra e registra.
- **Não corrige nome.** Espaço duplicado sim; grafia não. A pasta
  "ANDESON LOPES DA SILVA" continua sendo cadastrada como
  "ANDERSON LOPES DA SILVA" porque é o que o contrato assinado diz — o nome da
  pasta não é documento.

---

## 2. Arquitetura

Python, tudo rodando nesta máquina. Nada de servidor, nuvem ou API do Google.

```
CADASTRO ASTREA/
├── Cadastrar Clientes.command   ← painel (duplo clique)
├── executar.py                  ← comandos
├── .env.example                 ← modelo de configuração
├── src/
│   ├── config/    configurações e leitura do .env
│   ├── drive/     varredura das pastas e ID do Drive
│   ├── extractors/ leitura do contrato e dos demais documentos
│   ├── validators/ CPF, e-mail, telefone, CEP + decisão do status
│   ├── astrea/    adaptadores: navegador | planilha | dry-run
│   ├── database/  controle em SQLite
│   ├── services/  orquestrador e relatório
│   └── logs/      log com CPF mascarado
├── tests/         55 testes automatizados
└── RELATÓRIOS/    o que você abre para conferir
```

### Por que navegador e não API

**O Astrea não tem API pública.** Não há documentação para desenvolvedores, a
busca por "API" na Central de Ajuda não devolve nada, e a única integração de
terceiros existente (clieent® CRM) é uma parceria fechada que autentica com
e-mail e senha, não com chave de API. Existe uma API interna que o próprio site
consome (`app.astrea.net.br/_ah/api/`), mas ela não é documentada nem
contratada — construir em cima dela seria construir sobre chão que some sem
aviso.

Então a automação faz pela tela o que a advogada faria pela tela, com a conta
dela, no ritmo dela — usando o **Google Chrome** da máquina.

### O que a calibração no Astrea real ensinou (13/08/2026)

Três coisas que só apareceram olhando o sistema de verdade, e que hoje estão no
código por causa disso:

1. **A busca de contatos só acha CPF com pontuação.** `390.533.447-05` acha;
   `39053344705` não acha nada. Buscar só com os dígitos faria a automação achar
   que um cliente já cadastrado é novo — e criar cadastro duplicado.
2. **O formulário tem três abas** (Informações pessoais · Informações
   complementares · Documentação) e o **CPF fica na terceira**. Salvar sem
   passar por ela cadastraria o cliente sem CPF.
3. **A tela de novo contato não tem URL estável** (`add-edit-merge/%5B,,false,
   %5B%5D,%5D/personal`). Por isso o cadastro entra clicando em ADICIONAR.

Os campos são mirados pelo atributo `ng-model` do AngularJS (`contact.name`,
`address.zipCode`, `contact.job`), que é bem mais estável que rótulo ou posição.

### A limitação que define o horário: o Astrea só aceita UMA sessão por conta

Medido no primeiro teste real (17/08/2026): a automação estava rodando, a
advogada entrou no Astrea pelo navegador dela, e **a sessão da automação caiu
no mesmo instante** — quatro clientes tinham sido conferidos, e do quinto em
diante a tela voltou para o login.

Isso tem duas consequências, e as duas estão no desenho:

1. **A automação roda às 06:00 e às 21:00**, fora do expediente, em vez de a
   cada 15 minutos. Rodando durante o dia, ela e você ficariam se derrubando do
   sistema. O cliente cadastrado hoje entra no Astrea na virada da noite.
2. **Sessão caída interrompe a rodada inteira**, e os clientes que faltaram
   voltam para a fila com status *aguardando* — não viram uma fila de erros que
   não são deles. A rodada seguinte retoma de onde parou.

Se um dia o escritório puder ter um **usuário próprio no Astrea para a
automação**, a limitação some e ela pode voltar a rodar de hora em hora: basta
entrar com esse usuário (menu 7) e ajustar `HORARIOS` no `.env`.

Quando a automação não consegue entrar, o relatório abre com um **aviso
vermelho** dizendo desde quando está parada e o que fazer. Ela nunca falha em
silêncio.

**Se um dia a Aurum publicar uma API oficial**, troca-se só o arquivo
`src/astrea/navegador.py` por um `src/astrea/api.py`. Todo o resto — varredura,
extração, validação, controle, logs — continua igual. É para isso que existe o
adaptador.

### Identificação das pastas

A chave de controle é o **ID da pasta no Google Drive**, lido do atributo
estendido `com.google.drivefs.item-id` que o Drive para Desktop grava em cada
pasta. Renomear "15 - FULANO" para "15 - OK - FULANO" **não** faz o cliente ser
cadastrado de novo.

---

## 3. Como configurar

Duplo clique em **Cadastrar Clientes.command**. Na primeira vez ele instala
tudo sozinho (ambiente Python isolado em `~/.cadastro-astrea/venv`, biblioteca
de PDF e navegador automatizado) e cria o atalho **Cadastro Astrea** na Área de
Trabalho.

> Na primeira abertura o macOS pode reclamar que o arquivo é de origem
> desconhecida. Clique com o **botão direito → Abrir**, e depois em **Abrir**
> de novo. Só nessa primeira vez.

Depois, no menu:

- **7) Configurar e-mail e senha do Astrea** — os dados vão para
  `~/.cadastro-astrea/.env`, fora do Google Drive, com permissão de leitura só
  para você.

### Acesso ao Astrea — sem senha guardada

O jeito recomendado é o **menu 7 — Entrar no Astrea**. Ele abre o Google Chrome
num perfil criado só para a automação (`~/.cadastro-astrea/chrome-perfil`) e
**você** digita a senha na tela do Astrea. A sessão fica salva nesse perfil e as
rodadas seguintes entram sozinhas.

Vantagens de fazer assim:

- **a senha não fica guardada em arquivo nenhum** — nem no `.env`, nem em log;
- se um dia você ligar o **2FA**, continua funcionando: você resolve o código
  na hora de entrar, e a sessão salva vale para as rodadas seguintes;
- é o mesmo Chrome que você usa, com o mesmo comportamento.

Se preferir o login automático por e-mail e senha, existe o menu **s**. Desde
29/09/2026 ele guarda a senha no **Porta-chaves do Mac** (serviço
`cadastro-astrea`, conta = o e-mail) e só o e-mail vai para o
`~/.cadastro-astrea/.env`. Antes a senha ficava em texto aberto no `.env`. Para
trocar a senha: troque no Astrea e rode o menu **s** de novo.

Não precisa de credencial do Google, nem de token, nem de nada na nuvem.

---

## 4. TEST_MODE — e como sair dele

A automação nasce em **modo teste**: ela lê as pastas, extrai, valida, consulta
o Astrea e mostra `[TEST MODE] CLIENTE SERIA CADASTRADO` com todos os dados —
**mas não grava nada**.

- Ligar o teste: menu **8**
- Ir para produção: menu **9** (pede digitar `PRODUCAO` para confirmar)

Faça a homologação assim:

1. Menu **7** → *Entrar no Astrea* (uma vez, sem guardar senha).
2. Menu **3** → *Só analisar, sem tocar no Astrea*. Confira nome, CPF e endereço
   de alguns clientes.
3. Menu **2** com TEST_MODE ligado → a automação entra no Astrea de verdade,
   confere duplicidade de verdade, e mostra o que seria enviado sem gravar.
4. Menu **9** → produção, e **menu 6 com `--limite 1`** para o primeiro cliente
   real. Confira no Astrea antes de soltar o resto.
5. Menu **4** → liga a verificação automática.

Se a tela do Astrea mudar um dia, o menu **c** (*Calibrar*) remapeia os campos.

---

## 5. Como ligar e desligar

- **Ligar o automático:** menu **4**. A pasta passa a ser verificada sozinha
  **às 06:00 e às 21:00**, mesmo com o Terminal fechado.
- **Desligar:** menu **5**. Nada mais roda sozinho.
- **Rodar na hora:** menu **2**.

Na **primeira execução** a automação faz uma coisa importante: marca todas as
pastas que já existem como *histórico* e **não cadastra nenhuma delas**. Isso
impede que ligar a automação despeje 51 clientes antigos no Astrea de uma vez.
A partir daí, só pastas novas entram no fluxo.

Para trazer os antigos de propósito: menu **6** — *Importar clientes antigos*.
Ele mostra quantos serão processados e exige digitar `IMPORTAR`.

---

## 6. Os status

| Status | O que significa | O que fazer |
|---|---|---|
| **CADASTRADO COM SUCESSO** | Cliente novo cadastrado e confirmado por nova busca do CPF | Nada |
| **JÁ CADASTRADO NO ASTREA** | O CPF já existia; o ID foi anotado | Nada |
| **PENDENTE DE INFORMAÇÃO** | Falta dado obrigatório — a mensagem diz exatamente qual | Completar a pasta |
| **DADOS DIVERGENTES** | Documentos conflitam entre si | Conferir e resolver |
| **ERRO NO CADASTRO** | Falha técnica (Astrea fora do ar, tela mudada) | Ver o log; costuma resolver sozinho na rodada seguinte |
| SIMULADO (MODO TESTE) | Seria cadastrado, mas TEST_MODE está ligado | Homologação |
| AGUARDANDO ESTABILIDADE | A pasta ainda está recebendo arquivos | Nada; entra na próxima rodada |
| IGNORADO (HISTÓRICO) | Já existia quando a automação foi ligada | Menu 6, se quiser importar |

Um campo **acessório** inválido (telefone truncado no contrato, e-mail com erro
de digitação) **não** trava o cliente: aquele campo simplesmente não é enviado
ao Astrea e fica registrado em observação. Só nome, CPF e CNPJ inválidos param
o cadastro — são o que identifica a pessoa.

---

## 7. Como consultar os logs

- **Relatório para leigo:** menu **1**, ou abra
  `CADASTRO ASTREA/RELATÓRIOS/PENDÊNCIAS - CADASTRO ASTREA.html`.
- **Log detalhado:** `~/.cadastro-astrea/logs/execucao-AAAA-MM-DD.log`
- **Log em formato de dados:** `~/.cadastro-astrea/logs/eventos-AAAA-MM-DD.jsonl`

Cada registro traz data/hora, pasta, cliente, CPF (mascarado), ação, resultado,
ID no Astrea e o erro quando existir. **Senha e token nunca são gravados** — há
um filtro que apaga antes de escrever, mesmo que alguém passe por engano.

Logs são apagados automaticamente depois de 180 dias (`DIAS_RETENCAO_LOG`).

---

## 8. Como tratar pendências

Abra o relatório (menu 1). Para cada cliente ele diz o que houve.

- *"Contrato de honorários não localizado na pasta"* → a pasta não tem o
  contrato assinado. Coloque o PDF em `CONTRATO HO` e espere a próxima rodada:
  a automação tenta de novo sozinha.
- *"CPF não localizado nos documentos"* → o contrato não trouxe o CPF.
- *"CPF inválido"* → o número no contrato não passa no dígito verificador.
  Confira o contrato; isso costuma ser erro de digitação na hora de gerar.
- *"PDF sem camada de texto"* → o contrato foi digitalizado/fotografado.
  Use o PDF original do Autentique.
- *"CEP do contrato não confere com o comprovante"* → conferir qual endereço
  vale.

Pendência resolvida entra sozinha na rodada seguinte. Não precisa avisar nada
ao sistema.

---

## 9. Se a automação parar

1. **Ver se está ligada:** menu do atalho, o topo mostra o estado do agendador.
2. **Religar:** menu **4**.
3. **Ver o erro:** `~/.cadastro-astrea/logs/agendador.err` e o log do dia.
4. **Astrea mudou de tela?** Menu **c** (calibrar). Ele abre o Astrea visível,
   anota como os campos aparecem hoje e salva um arquivo de referência. Os
   ajustes vão para `~/.cadastro-astrea/seletores.json`, sem precisar mexer no
   programa.
5. **Precisa cadastrar mesmo assim, agora?** No `.env`, troque
   `ASTREA_ADAPTADOR=navegador` por `ASTREA_ADAPTADOR=planilha`. A automação
   passa a gerar uma planilha pronta em `RELATÓRIOS/` para você conferir e
   lançar — ninguém fica sem cadastro.
6. **Queda no meio do processo:** nada trava. Cliente que ficou preso volta
   para a fila na execução seguinte, e a trava de execução impede duas rodadas
   ao mesmo tempo.

---

## 10. Segurança e LGPD

- Processamento **100% local**. Nenhum documento de cliente sai da máquina:
  sem OCR em nuvem, sem IA externa, sem upload.
- Senha só no `.env` (permissão 600), fora do Google Drive, nunca no código
  nem em log.
- CPF mascarado (`049.***.***-56`) em log e relatório.
- Banco e logs em `~/.cadastro-astrea` (pasta com permissão 700), fora do Drive.
- Capturas de tela do navegador só em caso de erro (`SALVAR_EVIDENCIA=erro`);
  pode ser desligado com `nunca`.
- Só se guarda o que é necessário para o controle: nenhum documento é copiado.

---

## 11. Para quem for dar manutenção

```bash
python3 -m unittest discover -s tests    # 55 testes, ~0,3 s, sem rede
```

Cobrem cliente novo, cliente já existente, CPF inválido, CPF ausente, pasta sem
documentos, documento ilegível, erro do Astrea, Astrea fora do ar, duas
execuções simultâneas, reinicialização após queda e tentativa de cadastro
duplicado.

Comandos diretos:

```bash
python3 executar.py status                 # configuração e contagens
python3 executar.py analisar "FULANO"      # lê e mostra, sem gravar
python3 executar.py rodar                  # uma rodada
python3 executar.py importar --limite 5    # importação controlada
python3 executar.py pendencias             # atualiza e abre o relatório
python3 executar.py agendador --ver
```

Pontos de atenção:

- `src/extractors/contrato_ho.py` é o coração. Se o **modelo do contrato**
  mudar, é aqui que se mexe — e os testes em `tests/test_extrator.py`
  reproduzem as variações reais encontradas nas pastas.
- `src/astrea/seletores.py` concentra os "endereços" dos campos na tela do
  Astrea. Layout novo se resolve aqui ou no `seletores.json`, sem tocar na
  lógica.
- O adaptador de navegador **nunca declara sucesso sem confirmar**: depois de
  salvar, ele busca o CPF de novo e só então marca CADASTRADO.
