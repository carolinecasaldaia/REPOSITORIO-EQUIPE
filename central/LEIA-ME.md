# Central do Escritório

Um só lugar para tudo o que já foi construído: painéis, geradores, robôs, rotinas agendadas
e a Calculadora Judicial. Roda só neste Mac, em http://127.0.0.1:8500, com o Python que já
vem no macOS (sem instalar nada).

**Abrir:** dois cliques em `Central do Escritório.command` (atalho em `~/Desktop/CLAUDE`).
**Desligar:** fechar a janela do Terminal que ela abre.

## O que tem

| Seção | O que faz |
|---|---|
| Início | Resumo: rotinas com erro, painéis desatualizados, sistemas ligados |
| Painéis | Abre os HTML do Drive (previsão Asaas, prazos, comercial consolidado) e avisa quando um está velho |
| Geradores | Contratos, petição, calculadora revisional, onboarding, PDF, abertos dentro da central |
| Sistemas | Calculadora Judicial (casos reais :8501 e demo :8502), com botão para ligar |
| Robôs | Mesmo efeito do atalho da Área de Trabalho: abre o `.command` no Terminal |
| Rotinas agendadas | Os LaunchAgents `com.carolinemacedo.*`: horários, situação, último log e erros |
| Online | Links para os painéis publicados no claude.ai (financeiro, comercial, ranking, inadimplência, alvarás…). Os que leem dados do claude.ai só funcionam lá |

## Regras

- A central **não altera** nenhuma automação: só lê os arquivos onde já estão e abre os robôs como o atalho abriria.
- Nada sai do Mac: o servidor só aceita `127.0.0.1`/`localhost`, e os botões que rodam algo exigem
  uma chave gerada a cada vez que a central abre (uma página de fora não consegue acionar robôs).
- Só abre os arquivos listados no catálogo do `central.py`, mais os arquivos da mesma pasta de cada um.

## Asaas

O Início mostra saldo, recebido no mês (líquido), a receber em 30 dias e vencido, direto da
API do Asaas, **só leitura** (a central nunca cria nem altera cobranças). Os números ficam guardados
10 minutos; o botão Atualizar força uma nova consulta.

A chave é a mesma da Previsão Asaas, guardada no Porta-chaves do Mac (serviço `asaas-api`,
conta `previsao-asaas`); não fica em nenhum arquivo. Para trocar:
`/usr/bin/python3 ~/.previsao-asaas/trocar-chave.py` (atualiza a central junto).

## Atendimentos (Multichat360)

Menu **Atendimentos**: números do WhatsApp do escritório direto da API da Multichat360, **só leitura**
(rotas de estatística por GET). Mostra total (chegaram × iniciados pelo escritório), espera até a 1ª
resposta, tempo médio do ticket aberto, em aberto/aguardando atendente, contatos novos, tabela por
atendente, atendimentos por dia e por fila, com comparação com o período anterior de mesmo tamanho.
Atalhos de período (hoje, ontem, 7 dias, este mês, mês passado, 30 dias) ou datas livres. Os números
ficam guardados 10 minutos por período; Atualizar força nova consulta.

- Token no Porta-chaves (serviço `multichat360`, conta `token`). Para trocar:
  `/usr/bin/python3 trocar-token-multichat.py` (nesta pasta): testa na Multichat antes de gravar.
  Não usar `security ... -w` sozinho: o prompt dele corta em 128 caracteres e o token tem ~300.
- A API trata a data final como "até 00h do dia": a central pede sempre fim + 1 dia.
- "Tempo médio" inclui o tempo esperando o cliente; não é tempo de conversa.
- Qualidade: ainda sem dados. O token lê estatísticas, mas não as conversas (`/tickets` exige
  um usuário logado). A URL `/v1/api/external/...` da plataforma **envia** mensagens: nunca usar.

## Conta Azul

O Conta Azul não tem API que funcione para o escritório (o OAuth do aplicativo nunca autorizou,
ago/2026; integração descontinuada em 22/09/2026). Os números vêm da coleta diária pelo Chrome
(`contaazul_extrair.js`, 8h10), que grava em `EMPRESA/FINANCEIRO/PAINEL FINANCEIRO/dados/`:

- `ca_vencidas.txt`: parcelas vencidas em aberto → vencido e idade do atraso
- `ca_<AAAA-MM>.txt`: lançamentos do mês → recebido no mês e a receber até o fim do mês

Mesmas regras do painel financeiro e das etiquetas: saem os lançamentos espelho do Asaas (conta `A`),
parceiros (`PA`), avulsos sem categoria e parcelas zeradas por renegociação. Se a coleta do dia
não chegou, a central avisa e mostra a última.

## Identidade visual

Logo e cores vêm de `EMPRESA/LOGO` no Drive: marrom `#6C3813` e dourado `#D8C99E`.
`marca/assinatura.png` é o Artboard 1 recortado (fundo marrom, por isso se encaixa na barra
lateral) e `marca/simbolo.png` é o Artboard 5 recortado (ícone da aba).

## Incluir algo novo

Acrescentar uma linha na lista certa no topo de `central.py` (`PAINEIS`, `GERADORES`, `ROBOS`,
`ROTINAS`, `ONLINE` ou `SISTEMAS`) e reabrir a central.
