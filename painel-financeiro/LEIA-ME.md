# Relatórios mensais aos clientes

Gera **um PDF por cliente** com o andamento do processo no mês, com o timbre do
escritório, e uma **planilha de controle** para o envio pelo WhatsApp.

## Rotinas automáticas (tarefas agendadas do Claude)

- **relatorios-clientes-mensal**: no **último dia útil do mês, às 20h**, gera tudo
  sozinha: lê o Diário, o e-SAJ do TJAL e o Astrea (andamentos e diligências),
  gera os PDFs, a planilha e a agenda de envio, e atualiza o Painel de Envios.
  Leva cerca de 3 horas. Na manhã seguinte está tudo pronto.
- **relatorios-clientes-financeiro-semanal**: **toda segunda, às 8h30**, atualiza no
  painel quem está em atraso, em dia ou a verificar (depois da coleta do ASAAS das
  7h). Não muda o dia de envio de ninguém, nem os checks e as anotações.
- As tarefas rodam com o app do Claude aberto e o Mac ligado. Se o app estiver
  fechado na hora, a tarefa roda quando ele for aberto.
- A agenda de envio de cada mês é congelada na primeira geração (`_dados/plano_envio.json`).
- O atalho "Relatórios do Mês" continua funcionando para rodar à mão.

## Rotina do mês (Eduarda)

1. Dois cliques em **Relatórios do Mês**, na Área de Trabalho.
   Na primeira vez o Mac pode avisar que o arquivo veio da internet: botão
   direito → **Abrir** → **Abrir**.
2. Enter para aceitar o mês sugerido. Depois do dia 25 ele sugere o mês corrente;
   antes disso, o mês anterior. A primeira rodada do mês leva cerca de **40 minutos**
   (10 min no e-SAJ do TJAL + 25 min no Astrea para os demais tribunais). Pode
   deixar rodando e fazer outra coisa. As rodadas seguintes no mesmo mês levam 1 minuto.
3. A pasta do mês abre sozinha, junto com a planilha
   **CONTROLE DE ENVIO - <MÊS>.xlsx**:
   - **Coluna laranja (CONFERIR ANTES DE ENVIAR)**: sentença, acórdão, liminar,
     audiência, custas, alvará e processos vinculados só pelo nome. Abra o PDF
     e, se quiser, a publicação original (coluna VER PUBLICAÇÃO) antes de enviar.
     Na sentença, a coluna já diz o resultado lido (procedente, improcedente…)
     e se é favorável ou não. Isso é só para você: o PDF do cliente diz que a
     equipe vai explicar o resultado.
   - **NOTA PARA O CLIENTE**: o que você escrever aqui sai no PDF, num quadro
     "Recado da equipe". Depois de escrever, rode de novo e escolha a opção **1**.
   - **WHATSAPP → Abrir conversa**: abre a conversa já com a mensagem pronta.
     Anexe o PDF (pasta RELATÓRIOS (PDF)) e envie.
   - **ENVIADO?**: marque SIM. A linha fica verde.
4. Rodar de novo no mesmo mês **não perde nada**: notas, "enviado" e data do
   envio continuam.

## Envio dividido em 20 dias úteis

Uma pessoa não consegue conferir e enviar ~400 relatórios de uma vez. Por isso o
envio é dividido do 1º ao 20º dia útil do mês seguinte (feriados nacionais não
contam): **cerca de 20 relatórios por dia**.

**Quem ainda paga o escritório recebe o relatório ~3 dias úteis ANTES do
vencimento da parcela.** O vencimento vem da coleta diária do ASAAS (Previsão de
Recebimentos) e, para quem paga pela Conta Azul, do "DADOS CONTRATOS". Quem não
tem parcela no mês preenche os dias mais vazios.

- A pasta **RELATÓRIOS (PDF)** tem uma subpasta por dia: "DIA 03 - 05-10 (seg)".
- Na planilha de controle, a aba **AGENDA** mostra quantos relatórios há em cada dia
  e quantos têm item para conferir; a aba **CLIENTES** está em ordem de dia (use o
  filtro da coluna DIA DE ENVIO para ver só o lote de hoje).
- Para fixar um cliente num dia, escreva o número (1 a 20) na coluna DIA DO ENVIO
  de **CONTATOS DOS CLIENTES.xlsx** e rode de novo. Vazio = automático.
- Cliente novo entra sozinho, pelo vencimento da parcela dele.
- **Em atraso com o escritório**: a coleta do ASAAS (todo dia às 7h) grava a lista
  de parcelas vencidas e não pagas. A planilha mostra isso na coluna
  FINANCEIRO (INTERNO) e na aba EM ATRASO (INTERNO). É só para uso do escritório:
  nada disso vai para o PDF do cliente. Clientes da Conta Azul ainda não aparecem
  nessa lista.
- Feriado de Alagoas ou Maceió não é descontado: se cair num deles, envie no dia útil seguinte.

## Painel de envios (claude.ai)

https://claude.ai/artifact/XZ13yuQnLyyrd5jNwuzgD2

Página compartilhável com os relatórios do mês divididos pelos dias de envio: PDF
para abrir ou baixar, botão do WhatsApp, itens a conferir, situação financeira
(interna), **check de ENVIADO** (mostra quem marcou e quando) e **anotação da
equipe**. Os checks e as anotações ficam salvos no próprio painel e todos que têm
acesso veem a mesma coisa na hora. O CPF não vai para o painel.

- Quem precisa marcar envios (a Eduarda) deve receber acesso de **Colaborador**
  (ou Editor) no menu Compartilhar; acesso de Leitor só consulta.
- Todo mês, depois de gerar os relatórios, peça ao Claude: "atualize o painel de
  envios com os relatórios de <mês>". Ele roda `gerar_painel.py` e republica no
  mesmo link. Os checks do mês anterior ficam guardados.
- A "nota para o cliente" que sai no PDF continua na planilha de controle; a
  anotação do painel é interna.

## Clientes novos

Não é preciso cadastrar nada aqui. **Quem está na RODAGEM PROCESSUAL recebe o
relatório.** Cliente lançado na rodagem entra sozinho no mês seguinte, e também
entra sozinho em **CONTATOS DOS CLIENTES.xlsx**, onde falta só digitar o
telefone uma vez. Quando o cliente passou pelo Cadastro Astrea, o telefone já
vem preenchido.

Duas abas da planilha de controle servem para fechar buracos da rodagem:

- **FORA DA RODAGEM**: processos que tiveram publicação para a OAB da
  Dra. Caroline mas não estão na rodagem. Pode ser um cliente que precisa ser
  lançado, ou um caso de outra área.
- **SEM Nº DE PROCESSO**: linhas da rodagem sem número de processo. Sem o
  número não há como acompanhar.

## De onde vêm as informações

- **Quem recebe**: `A - RODAGEM/RODAGEM PROCESSUAL <ano>.xlsx`. Quando virar o
  ano, basta criar a planilha 2027 na mesma pasta; a de ano mais recente é a usada.
- **O que aconteceu no mês**: DJEN (Diário de Justiça Eletrônico Nacional, CNJ),
  consultado pelas OABs AL 15.766, SP 528.725 e PE 70.091. Traz todas as
  intimações do mês, de qualquer tribunal. Publicação de recurso no Tribunal
  (número novo) é ligada ao cliente pelo nome completo.
- **Movimentação do TJAL**: consulta pública do e-SAJ (sem login), processo por
  processo. Traz o que não sai no Diário: contestação do banco, petições,
  réplica, envio ao juiz, mandados, cartas de citação.
- **Demais tribunais (PJe, eproc, Projudi)**: histórico do **Astrea**, lido pela tela
  com a conta "Claude" (a mesma do Cadastro Astrea), só consulta. Entram os
  andamentos do tribunal e as peças que a equipe concluiu ("Nossa equipe protocolou
  a réplica"). Tarefas internas (cobrança, pagamento, "informar ao cliente") **nunca**
  vão para o cliente. Processo que não está no Astrea aparece na coluna laranja como
  "cadastrar no Astrea". Se a sessão do Astrea cair, entre pelo atalho do Cadastro
  Astrea e rode de novo.
- **Situação atual**: a última movimentação que indica a fase (no mês ou antes, pelo e-SAJ). Se o processo não teve
  novidade, vem das colunas DESPACHO/SITUAÇÃO da rodagem. **Manter essas
  colunas em dia deixa o relatório mais preciso.**

O DataJud (CNJ) não é usado: em 30/09/2026 ele recusou 1 de cada 3 consultas,
levou 4 minutos para 15 processos e tem de 2 semanas a 2 meses de atraso.

## Arquivos

- `gerar_relatorios.py`: o programa
- `timbre/`: logo e rodapé extraídos do TIMBRADO NOVO.docx
- `<MÊS ANO>/_dados/djen.json`: publicações baixadas. A opção 1 reaproveita
  este arquivo; a opção 2 baixa de novo.
- Ambiente Python em `~/.relatorios-clientes` (fora do Drive).
