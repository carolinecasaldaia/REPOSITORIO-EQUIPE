# Produtividade Astrea — Ranking do Escritório

- `ranking_escritorio.py` — lê no Astrea (só consulta, sessão da automação de cadastro) todas as
  atividades do ano de todas as pessoas e grava `RELATÓRIOS/atividades_escritorio_AAAA.csv` e
  `ranking-escritorio-dados.json` na pasta do Drive. Importa o `coletar.py` da mesma pasta
  (original só no Drive) para a sessão e a espera do perfil do Chrome.
- `rodar.sh` — cópia de `~/.produtividade-astrea/rodar.sh`, chamado pelo app "Produtividade Astrea"
  (launchd, 12:10 e 20:10). Roda o `coletar.py` e depois o ranking.
- `ranking-escritorio.html` — modelo da página publicada no claude.ai
  (https://claude.ai/code/artifact/f7316780-6902-4741-b27d-9fe305ba681b). Lê o .json pelo conector
  do Google Drive (ID `1-vjiIVbVNQoHjnNUNRTp2Q4IypOwi7oS`); `/*__COPIA__*/null` recebe uma cópia
  dos dados ao publicar, usada quando o Drive não está disponível.


PUBLICAÇÕES (06/11/2026)
O ranking_escritorio.py também lê as publicações do Astrea (tratadas, descartadas
e não tratadas) e grava RELATÓRIOS/publicacoes_escritorio_AAAA.csv. A página
"Ranking do Escritório" tem a aba Publicações: quem leu, por dia, mês a mês,
duplicidades e não tratadas. O Astrea guarda quem tratou e o DIA (sem horário).
Duplicidade = mesmo processo + mesma data de divulgação recebido mais de uma vez
(quase sempre diário do TJAL + DJEN). Se as publicações falharem, o ranking de
atividades sai igual e a página mantém as publicações da rodada anterior.
