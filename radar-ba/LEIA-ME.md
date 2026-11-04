# RADAR B&A — Caroline Macedo Advocacia

Monitora a carteira de clientes e avisa quando aparece uma nova **Busca e
Apreensão em Alienação Fiduciária** ou **Execução de Título Extrajudicial**
contra alguém do escritório.

---

## Como usar no dia a dia

Dois cliques em **`RADAR B&A.command`** (há um alias na Área de Trabalho).
Na primeira vez ele instala tudo sozinho, num ambiente isolado em
`~/.radar-ba/venv` — não mexe no Python do sistema.

O menu tem tudo: rodar o monitoramento, ver a carteira, importar clientes,
conferir se as fontes estão no ar e abrir os relatórios.

---

## O que o sistema faz, em uma frase

Todo dia ele lê as publicações judiciais do país inteiro, procura os nomes da
carteira no **polo passivo** de processos de busca e apreensão, e monta um
alerta para cada processo novo — em ordem de urgência.

---

## Arquitetura

```
        ┌──────────────────────────────────────────────┐
        │  DJEN / API Comunica (CNJ)  ·  DETECÇÃO      │
        │  nacional · D+1 · sem captcha · com partes   │
        └───────────────────┬──────────────────────────┘
                            ↓
              classificador de Busca e Apreensão
              (código da classe CNJ, não texto)
                            ↓
                  casador de nomes da carteira
                            ↓
        ┌───────────────────┴──────────────────────────┐
        │ TJSP TJAL TJAC TJAM TJCE │  demais tribunais │
        │ e-SAJ confirma por CPF   │  sem CPF possível │
        │ → CONFIRMED_MATCH        │  → POSSIBLE_MATCH │
        └───────────────────┬──────────────────────────┘
                            ↓
          prioridade → deduplicação → alerta → relatório
                            ↑
        DataJud (CNJ): enriquece classe, assunto, vara, movimentos
```

### Por que o DJEN, e não o DataJud

O plano original supunha o DataJud como fonte de busca por CPF. O levantamento
da FASE 1 derrubou a premissa, com teste:

- **o DataJud não expõe as partes** — nem nome, nem CPF, nem polo;
- **e está de 2 semanas a 2 meses atrasado** — no TJSP, 49 dias.

O DJEN resolve os dois problemas: é nacional, atualizado em D+1 e traz nome das
partes com polo. Detalhes e evidências em `docs/mapeamento-tribunais.md`.

---

## Instalação

Basta o atalho. Se preferir a mão:

```bash
python3 -m venv ~/.radar-ba/venv
~/.radar-ba/venv/bin/pip install -r requirements.txt
cp .env.exemplo ~/.radar-ba/.env
~/.radar-ba/venv/bin/python3 executar.py gerar-chaves   # cole no .env
~/.radar-ba/venv/bin/python3 executar.py saude
```

---

## Configuração

O arquivo real de configuração fica em **`~/.radar-ba/.env`**, fora do Google
Drive, para os segredos não serem sincronizados. O `.env.exemplo` do projeto
não contém segredo nenhum.

| Variável | Para que serve |
|---|---|
| `DATAJUD_API_KEY` | chave pública do CNJ. Fica no `.env` porque o CNJ pode trocá-la a qualquer momento |
| `DJEN_RPM` | requisições por minuto no DJEN. O servidor publica limite de 20; usamos 18 por margem |
| `DATAJUD_RPM` | ritmo no DataJud |
| `ESAJ_HABILITADO` | **`false` por padrão** — ver a seção do e-SAJ abaixo |
| `ESAJ_INTERVALO_S` | segundos entre consultas ao e-SAJ (padrão 5) |
| `CPF_PEPPER` | sal do hash determinístico. **Se mudar, todos os hashes mudam** |
| `CPF_CHAVE` | chave AES-256-GCM em base64 (32 bytes) |
| `RETENCAO_DIAS` | política de retenção (padrão 1825 = 5 anos) |
| `LOG_NIVEL` | `INFO` ou `DEBUG` |

---

## Comandos

```bash
python3 executar.py saude                    # as fontes estão no ar?
python3 executar.py gerar-chaves             # gera pepper e chave
python3 executar.py importar carteira.csv    # importa clientes
python3 executar.py importar carteira.csv --simular
python3 executar.py clientes                 # lista a carteira
python3 executar.py monitorar --dias 1       # roda um ciclo
python3 executar.py monitorar --dias 7 --modo varredura
```

### Formato da carteira

CSV ou XLSX, com no mínimo `nome` e `cpf`:

```
nome,cpf,telefone,banco
Fulano de Tal,111.444.777-35,82999990000,BANCO PAN
```

O CPF é validado antes de entrar; duplicados e inválidos são recusados com o
motivo. Os nomes de coluna aceitam variações (`cliente`, `documento`,
`celular`, `financeira`, `data de contratação`...).

---

## Providers

Todos implementam o mesmo contrato (`src/provedores/base.py`):

```python
buscar_por_cpf(cpf)         -> List[ResultadoProcesso]
buscar_por_nome(nome)       -> List[ResultadoProcesso]
detalhar(numero_processo)   -> Optional[DetalheProcesso]
verificar_saude()           -> bool
```

| Provider | Papel | Consulta por CPF |
|---|---|---|
| `djen/` | detecção nacional, D+1 | não (a API não traz CPF) |
| `esaj/` | confirmação de identidade | **sim**, em 5 tribunais |
| `datajud/` | enriquecimento e estatística | não (limitação estrutural) |

Provider que não puder consultar por CPF de forma lícita devolve
`MANUAL_REVIEW_REQUIRED`. **Nunca contorna a limitação** — sem quebra de
CAPTCHA, sem burlar limite de requisições, sem evasão de bloqueio.

### DataJud — duas armadilhas que o código já trata

1. **`dataAjuizamento` é lido como `epoch_millis`.** O campo chega como
   `"20260630235628"` e o índice o interpreta como milissegundos — um processo
   de 2026 vai parar no ano 2612. Filtro com semântica de data devolve
   resultado errado **em silêncio**. Use `faixa_periodo()`, que passa o número
   cru; e `normalizar_data_ajuizamento()`, que lê os dois formatos que
   convivem no índice e descarta datas impossíveis.
2. **`grau` é campo de texto** e não aceita agregação nem ordenação. Use
   `sistema.codigo` e `classe.codigo`, que são numéricos.

### DJEN — uma armadilha

A API **aceita e ignora parâmetros desconhecidos, sem erro**. `codigoClasse`
não filtra nada. Por isso `_PARAMS_VALIDOS` lista só o que foi testado e o
filtro de classe é sempre aplicado do nosso lado. Ao acrescentar um parâmetro
novo, compare a contagem com e sem ele antes de confiar.

### e-SAJ — leia antes de ligar

O e-SAJ é a única fonte testada que cruza CPF automaticamente, e não apresenta
CAPTCHA. **Isso é um fato técnico, não uma autorização.** O provider nasce
desligado (`ESAJ_HABILITADO=false`).

Antes de ligar, o escritório precisa analisar os **Termos de Uso de cada
tribunal**. Quando ligado, o provider opera identificado, a uma consulta a
cada 5 segundos, restrito a clientes com procuração; se o tribunal recusar ou
passar a exigir CAPTCHA, ele **para de insistir** e devolve
`MANUAL_REVIEW_REQUIRED`.

---

## Monitoramento

Dois modos, escolhidos automaticamente pelo tamanho da carteira:

| Modo | Como funciona | Custo | Quando compensa |
|---|---|---|---|
| `nome` | uma consulta por cliente | N requisições/dia | até ~300 clientes |
| `varredura` | baixa tudo do dia e casa localmente | ~300–500 req/dia | acima disso |

A varredura ainda permite casamento tolerante a erro de grafia, porque o
filtro é feito aqui e não no servidor.

**Deduplicação:** a chave é `numeroCNJ + client_id`. Processo já conhecido não
gera alerta de novo — só atualiza a última checagem e a movimentação.

**Prioridade:**

| | Critério |
|---|---|
| 🚨 CRÍTICO | até 7 dias |
| 🔴 ALTO | de 8 a 30 dias |
| 🟡 ATENÇÃO | mais antigo, ainda ativo |
| ⚪ INFORMATIVO | encerrado ou apenas relacionado |

A régua usa a data de distribuição quando ela é conhecida. Como o DataJud está
defasado, no dia a dia a referência costuma ser a **data de publicação no
diário** — e o alerta diz isso com todas as letras, para ninguém confundir
"apareceu hoje no diário" com "foi distribuído hoje".

---

## Segurança do CPF

- **Nunca em texto puro em disco.** Em `clientes.json` vão o hash
  determinístico (HMAC-SHA256 com pepper), o CPF cifrado (AES-256-GCM) e a
  máscara `***.***.***-12`.
- **Nunca em log, relatório ou alerta.** O mascaramento é aplicado no próprio
  formatter do log — mesmo um log escrito por engano com CPF cru sai mascarado.
- **Falha fechado.** Sem chave configurada o sistema **recusa** a gravação em
  vez de gravar em claro.
- **Retenção** configurável em `RETENCAO_DIAS` (padrão 5 anos).
- A trilha de auditoria registra data, provedor, tribunal, status, duração e
  quantidade de resultados — **nunca o CPF**.

---

## Como acrescentar um novo tribunal

Antes de escrever código, responda com **teste**, não com suposição:

1. o tribunal permite consulta pública por CPF?
2. há CAPTCHA ou bloqueio anti-bot?
3. os Termos de Uso permitem consulta automatizada?

Se qualquer resposta impedir a automação, **não force**: o tribunal fica
coberto pela detecção do DJEN (que é nacional e já o alcança) e a confirmação
de identidade vai para conferência humana.

Se puder automatizar:

1. crie `src/provedores/<sigla>/cliente.py`;
2. herde de `ProvedorJudicial` e implemente `verificar_saude()` e o que mais
   for lícito;
3. devolva `ResultadoProcesso` com o `status_casamento` correto —
   `CONFIRMED_MATCH` só quando a identidade tiver sido conferida por CPF;
4. escreva os testes com mock em `tests/`, sem tocar a rede;
5. registre no `docs/mapeamento-tribunais.md` o que você testou e a data.

---

## Testes

```bash
~/.radar-ba/venv/bin/python3 -m pytest tests/ -q
```

Nenhum teste toca a rede: os provedores são testados com dublês e com uma
amostra real de HTML do e-SAJ salva em `tests/`.

---

## Estrutura

```
radar-ba/
├── RADAR B&A.command          atalho de dois cliques
├── executar.py                painel de linha de comando
├── docs/mapeamento-tribunais.md   levantamento da FASE 1 (evidências)
├── evidencias/                respostas cruas das APIs testadas
├── RELATÓRIOS/                saída de cada execução
├── src/
│   ├── config/ajustes.py      configuração via .env
│   ├── provedores/
│   │   ├── base.py            contrato comum
│   │   ├── djen/              detecção nacional
│   │   ├── esaj/              confirmação por CPF (desligado por padrão)
│   │   └── datajud/           enriquecimento
│   ├── servicos/
│   │   ├── classificador_busca_apreensao.py
│   │   ├── normalizador_bancos.py
│   │   ├── casador_nomes.py
│   │   ├── carteira.py        importação de clientes
│   │   ├── monitor.py         ciclo de monitoramento
│   │   ├── prioridade.py
│   │   ├── alertas.py
│   │   └── relatorio.py
│   ├── seguranca/cpf.py       validação, hash, criptografia
│   └── util/                  log e cliente HTTP
└── tests/
```

---

## Limites conhecidos — o que este sistema **não** faz

1. **Não confirma identidade fora dos 5 tribunais e-SAJ.** Em cerca de 64% do
   volume nacional o alerta sai como `POSSIBLE_MATCH` e depende de conferência.
   Homônimo existe: nome igual **nunca** é prova.
2. **Não detecta o ajuizamento, e sim a primeira publicação** no diário —
   normalmente alguns dias após a distribuição. É o melhor que se consegue por
   meio lícito.
3. **Não enxerga processo em segredo de justiça.**
4. **Pode perder um processo se o nome do cadastro divergir muito** do registro
   do tribunal. O casador tolera acento, pontuação, partícula, sufixo de
   geração e erro de uma letra — não tolera nome trocado.
5. **Não substitui o monitoramento oficial por OAB** dos processos em que o
   escritório já atua.

---

## Banco de dados

A FASE 2 é prova de conceito e guarda o estado em JSON, em `~/.radar-ba/dados/`:
`clientes.json` e `processos_vistos.json`. O formato já espelha as tabelas
`clients`, `judicial_processes`, `monitoring_runs` e `alerts` previstas para a
**FASE 3**, quando entra o banco relacional.
