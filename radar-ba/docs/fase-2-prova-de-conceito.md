# RADAR B&A — FASE 2 · Prova de conceito
**Data:** 18/08/2026 · **Situação:** concluída, funcionando com dado real

---

## 1. O que foi construído

Sistema em **Python 3.9**, com 36 módulos e 116 testes automatizados.

> **Desvio da especificação, e o porquê.** O plano pedia TypeScript. Esta
> máquina não tem Node, npm nem Homebrew, e todas as automações do escritório
> (Cadastro Astrea, Baixar Autentique, Gerador Onboarding) são em Python com
> atalho `.command` de dois cliques. Mantive o mesmo padrão — a interface
> `JudicialProvider` virou classe base abstrata com contrato idêntico. Se
> preferir TypeScript, é preciso instalar o Node antes; me avise.

| Componente | Arquivo | Item da especificação |
|---|---|---|
| Contrato dos providers | `src/provedores/base.py` | 5 |
| Detector nacional | `src/provedores/djen/cliente.py` | 2, 3 |
| Enriquecimento | `src/provedores/datajud/cliente.py` | 4 |
| Confirmação por CPF | `src/provedores/esaj/cliente.py` | 5 |
| Classificador de B&A | `src/servicos/classificador_busca_apreensao.py` | 6 |
| Normalização de bancos | `src/servicos/normalizador_bancos.py` | 7 |
| Casamento de nomes | `src/servicos/casador_nomes.py` | 21 |
| Segurança do CPF | `src/seguranca/cpf.py` | 9 |
| Ciclo de monitoramento | `src/servicos/monitor.py` | 10, 11 |
| Prioridade | `src/servicos/prioridade.py` | 12 |
| Alerta | `src/servicos/alertas.py` | 13 |
| Importação da carteira | `src/servicos/carteira.py` | 15 |
| Relatório | `src/servicos/relatorio.py` | 16 |
| Auditoria | `src/util/http.py` | 17 |
| Testes | `tests/` | 18 |
| README | `LEIA-ME.md` | 19 |

Não foram construídos: banco relacional (FASE 3), dashboard (FASE 6) e
integrações externas (FASE 8).

---

## 2. Testes executados

### 2.1 Suíte automatizada — **116 testes, 116 passando**

Nenhum toca a rede: os providers são testados com dublês e com uma amostra real
de HTML do e-SAJ salva em `tests/amostra_esaj_tjal.html`.

| Arquivo | Testes | Cobre |
|---|---|---|
| `test_cpf.py` | 26 | validação, máscara, hash, criptografia, falha fechado |
| `test_classificador.py` | 15 | classes alvo, exclusões, reforços, formato JSON |
| `test_bancos.py` | 18 | normalização, precedência de regras, fundos |
| `test_casador_nomes.py` | 17 | grafia, cadastro incompleto, pessoas diferentes |
| `test_provedores.py` | 25 | DJEN, DataJud, e-SAJ, contrato comum |
| `test_duplicidade.py` | 10 | deduplicação, ciclo, relatório |
| `test_alerta_prioridade.py` | 20 | régua de prioridade, campos do alerta |
| `test_log.py` | 5 | mascaramento de CPF no log |

### 2.2 Testes contra as fontes reais

| Teste | Resultado |
|---|---|
| Health check DJEN | ✅ OK |
| Health check DataJud | ✅ OK |
| Health check e-SAJ TJAL | ✅ OK (formulário com `DOCPARTE`, sem CAPTCHA) |
| Detecção ponta a ponta | ✅ localizou B&A real no TJSP, publicada 1 dia antes |
| Enriquecimento DataJud | ✅ classe, assunto, vara, data e movimento de processo real |
| Estatística DataJud | ✅ 827 B&A no TJAL em maio/2026 — **bate com a medição da FASE 1** |
| Deduplicação | ✅ 2ª execução: 1 processo encontrado, **0 alertas novos** |
| Varredura de volume | ✅ **7.272 comunicações do TJAL em 9 segundos** |

### 2.3 Varredura real — TJAL, 17/08/2026

```
comunicações lidas          7.272   (8 páginas, 9 segundos)
de interesse                  388   (5,3%)
  Execução de Título Extrajudicial      215
  Busca e Apreensão em Alienação Fid.   171
  Busca e Apreensão                       2
bancos no polo ativo: HONDA 36 · AYMORÉ 32 · BB 28 · BV 17 · BRADESCO 16 · VW 16
```

### 2.4 Alerta gerado com dado real

```
🚨 NOVA BUSCA E APREENSÃO LOCALIZADA

Cliente:            Camila Costa Alves
CPF:                ***.***.***-35
Banco:              BANCO ITAÚ
Processo:           4000116-76.2026.8.26.0405
Tribunal:           TJSP
Vara:               UPJ da 5ª a 9ª Varas Civeis da Comarca de Osasco
Publicação (DJEN):  2026-08-17
Classe:             BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA
Prioridade:         CRÍTICO — publicado no diário há 1 dia
Situação:           POSSIBLE_MATCH (confiança 99%)

⚠️  IDENTIDADE NÃO CONFIRMADA POR CPF — confira antes de agir.
```

### 2.5 Verificação de segurança

| Verificação | Resultado |
|---|---|
| CPF completo em relatório | ✅ nenhum — só máscaras |
| CPF em claro em `clientes.json` | ✅ nenhum — hash + cifrado + máscara |
| Chave embutida no código | ✅ nenhuma — tudo em `.env` |
| Permissão do `.env` | ✅ `600`, fora do Google Drive |
| Mascaramento no log | ✅ aplicado no formatter |

---

## 3. Erros encontrados durante a construção

Todos corrigidos e cobertos por teste.

| # | Erro | Como apareceu | Correção |
|---|---|---|---|
| 1 | **Charset errado no e-SAJ** | Decodifiquei como latin-1; o servidor responde `charset=UTF-8`. O rótulo "Réu:" virava "RÃ©u:" e **quebrava a identificação do polo** | decodificação UTF-8 + leitura do rótulo sem acento |
| 2 | **Falso negativo no casamento de nomes** | `ALVEZ`/`ALVES` e `SOUZA`/`SOUSA` ficavam em 0,80, abaixo do limite — o radar perderia o processo em silêncio | comparação por distância de edição: 1 letra em nome de 4+ não separa pessoas |
| 3 | **Caixa do nome da classe** | A API devolve `BUSCA E APREENSãO` (maiusculiza só ASCII) | normalização na conversão |
| 4 | **CPF não aparecia no alerta** | O cadastro guarda `cpf_cifrado`, e o alerta procurava `cpf` | máscara gravada no cadastro; nunca se decifra CPF só para exibir |
| 5 | **Agregação em `grau` falhava** | `Fielddata is disabled` — é campo `text` | usar `sistema.codigo` e `classe.codigo` |

---

## 4. Limitações — o que o sistema não faz

1. **Não confirma identidade em 22 dos 27 tribunais.** Em ~64% do volume
   nacional o alerta sai como `POSSIBLE_MATCH`. **Homônimo é risco real** e
   nome igual nunca é prova.
2. **Não detecta o ajuizamento, e sim a primeira publicação** no diário —
   alguns dias após a distribuição. É o melhor possível por meio lícito.
3. **Não enxerga processo em segredo de justiça.**
4. **Perde o processo se o nome divergir muito** do registro do tribunal. O
   casador tolera acento, pontuação, partícula, sufixo de geração e erro de uma
   letra — não tolera nome trocado.
5. **e-SAJ desligado.** Enquanto os Termos de Uso não forem analisados, nenhum
   alerta atinge `CONFIRMED_MATCH`.
6. **Estado em JSON**, não em banco. Serve à prova de conceito; não suporta
   acesso concorrente.
7. **Sem execução automática.** Hoje é sob demanda, pelo atalho.

---

## 5. Decisão pendente com o escritório

**Ligar ou não o confirmador e-SAJ.** É a única fonte que cruza CPF
automaticamente (TJSP, TJAL, TJAC, TJAM, TJCE — 36% do volume nacional) e não
apresenta CAPTCHA. A ausência de CAPTCHA é fato técnico, **não autorização**:
depende da leitura dos Termos de Uso de cada tribunal, que é decisão jurídica
sua. O provider está pronto e nasce desligado.

---

## 6. Proposta para a FASE 3

1. **Banco relacional** (SQLite) com as tabelas `clients`,
   `judicial_processes`, `monitoring_runs` e `alerts` — o formato do JSON atual
   já as espelha, a migração é direta.
2. **Execução automática diária**, no padrão `launchd` já usado no Cadastro
   Astrea, com relatório na pasta `RELATÓRIOS`.
3. **Fila de conferência humana** para os `POSSIBLE_MATCH`: uma tela onde se
   confirma ou descarta, e a decisão passa a valer para as próximas execuções.
4. **Importação da carteira real** do escritório, medindo a taxa de falso
   positivo em volume — número que hoje não temos.
5. **Política de retenção** aplicada de fato (hoje só configurada).

Sugiro executar 1, 2 e 4 primeiro: dão o número de falso positivo real, que é
o que vai calibrar o limite do casador de nomes antes do dashboard.
