# Astrea — integração geral

Uma porta única para o Astrea, para qualquer automação ou agente do escritório. O Astrea não tem API
pública: usamos a API interna do próprio site com a sessão da conta **Claude**, no perfil do Chrome
da automação de cadastro (`~/.cadastro-astrea/chrome-perfil`). Se outra rotina estiver usando o perfil
(cadastro às :40, produtividade 12:10/20:10, etiquetas 9h), o comando espera até 15 min.

```
PY=~/.cadastro-astrea/venv/bin/python
$PY astrea.py ajuda
```

| Arquivo | O que é |
|---|---|
| `astrea.py` | biblioteca (`from astrea import Astrea`) + comando. Saída em JSON (`--saida ARQ` grava em arquivo) |
| `cumprimento.py` | uso para cumprimento de sentença: `triagem`, `caso`, `registrar` (agente `macedo-liquidacao`) |

## Comandos

Consultas (nada é gravado): `casos [--texto] [--processos] [--etiqueta]`, `caso NUM|ID`,
`andamentos NUM|ID [--desde] [--tipo tj|pub|todos]`, `tarefas NUM|ID`,
`agenda --de --ate [--pessoa] [--status]`, `publicacoes [--status] [--desde] [--processo]`,
`contatos TEXTO`, `contato ID`, `casos-do-contato ID`, `usuarios`, `etiquetas`.

Gravações (sem `--gravar` só simula): `criar-tarefa NUM|ID --titulo --para [--vence DD/MM/AAAA|+2u|+3]
[--comentario] [--prioridade]`, `comentar TAREFA --texto`, `concluir TAREFA`, `reabrir TAREFA`,
`responsavel TAREFA --para`, `etiqueta por|tirar NUM|ID --nome`.

Travas: gravação só com `--gravar`; `criar-tarefa` não duplica tarefa aberta de mesmo título no caso;
não há comando para protocolar, apagar caso/contato/tarefa ou mexer em financeiro. Etiqueta nova não
se cria pela API: crie à mão no Astrea e use pelo nome.

## Testado em 09/11/2026

- Consultas: todas, no Astrea real (1.489 casos, andamentos, agenda, publicações, contatos).
- Gravações: `criar-tarefa`, `comentar` e `concluir` testados (tarefa "TESTE CLAUDE - PODE APAGAR",
  concluída, no caso 0725012-67.2025, mantida a pedido da Dra. Caroline). Etiqueta em caso: mesmo
  endpoint da rotina de inadimplência (em produção desde 07/11/2026).
  `responsavel` e `reabrir` ainda não foram usados de verdade: rodar com simulação e conferir.

## Mapa da API interna (para manutenção)

Base `https://app.astrea.net.br`; credencial = cabeçalho `authorization` capturado da própria página.
Documentos de descoberta: `/_ah/api/discovery/v1/apis/<api>/v1/rest` (apis: workspace, folders, users,
shared, calendar, pro, histories, clippings, contacts, financial, billing…).

| O quê | Chamada |
|---|---|
| lista de casos | `POST /api/v2/case/query` (paginado por `queryCursor`, 100 por vez) |
| detalhe do caso | `GET /api/v2/folder/{id}?userId=&withDetails=true` (partes, vara, `urlLawsuit`) |
| andamentos | `GET /api/v2/historical/{id}/resume?limit=100&cursor=` (AUTOMATIC_LAWSUIT = tribunal, CLIPPING = publicação) |
| agenda | `POST /api/v2/calendar-pro/complete` (todas as atividades do período) |
| publicações | `POST /api/v2/clipping-service/query` (status RECEIVED/ASSIGNED/REJECTED, `page`) |
| contatos | `POST /api/v2/contact/all`, `GET /api/v2/contact/{id}` |
| pessoas | `POST /_ah/api/users/v1/getAllUsers?tenantId=6406437268422656` |
| etiquetas | `GET /_ah/api/shared/v1/getAllTags`; caso: `GET /_ah/api/folders/v1/addTagToCase|removeTagFromCase` |
| tarefas | `POST /_ah/api/workspace/v1/getTasksByCase`, `getTaskWithComments`, `saveTaskWithList`, `saveComment` (precisa `type 0`, `when`, `commenthash`), `GET changeTaskStatus`, `POST changeTaskResponsible` |
