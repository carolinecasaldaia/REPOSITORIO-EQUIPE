# Baixar Contratos Assinados (Autentique)

Todo contrato do Autentique que já tem a **assinatura de todas as partes** é
baixado sozinho e arquivado na pasta do cliente, em **PREPARAÇÃO PARA
INGRESSO** — já separado em contrato, procuração e declarações, e com o
**onboarding do cliente gerado** na mesma rodada.

Roda **de hora em hora, das 8h às 20h**, sem você abrir nada.

## O que ela faz, na ordem

1. Pergunta ao Autentique quais documentos existem.
2. Separa os que **todo mundo já assinou** (ninguém pendente, ninguém recusou).
3. Baixa o PDF assinado.
4. Confere se é mesmo envelope de onboarding (contrato de prestação de
   serviços, procuração ou declaração de hipossuficiência). **Se não for,
   não entra em pasta de cliente nenhuma.**
5. Lê no próprio contrato quem é o **Cliente Contratante** e acha a pasta dele.
   Não achou? Cria `<MÊS ANO>/<NOME DO CLIENTE>` com as cinco subpastas de sempre.
6. Grava:

| Arquivo | Vai para |
|---|---|
| `<nome do envelope> [assinado].pdf` (o PDF inteiro) | `CONTRATO HO` |
| `Contrato HO Assinado.pdf` | `CONTRATO HO` |
| `Procuracao Assinada.pdf` | `DOC ESCRITÓRIO` |
| `Declaracao de Hipo Assinada.pdf` | `DOC ESCRITÓRIO` |
| `Declaracao de Residencia Assinada.pdf` (quando houver) | `DOC ESCRITÓRIO` |

7. Chama o **Gerador de Onboarding**, que lê o contrato recém-arquivado e grava
   `onboarding_<nome>.pdf` na subpasta `ONBOARDING`.

A separação e o onboarding são feitos pelos mesmos programas dos atalhos
**Separar Documentos** e **Gerar Onboarding do Cliente** — não existe uma
segunda lógica para dar manutenção, e o que você mudar no `gerador_pdf.html`
continua valendo aqui.

Depois disso o **Cadastro Astrea** já encontra o contrato na pasta e segue o
fluxo sozinho.

> **Busca e apreensão:** esses contratos não trazem o banco adverso, que é
> campo obrigatório do onboarding. Nesses casos o contrato é arquivado
> normalmente e o onboarding aparece como *pendente* no relatório — você
> termina em segundos pelo atalho **Gerar Onboarding do Cliente**, que pergunta
> o banco. Onboarding que já existir na pasta não é gerado de novo.

## Primeira vez

1. Dois cliques em **Baixar Contratos Assinados** (atalho na Área de Trabalho).
2. Cole a **chave da API do Autentique** na janela que abrir.
   Ela é gerada no painel do Autentique: **Configurações → Chaves de API**.
3. Pronto. A automação já está ligada.

> A chave fica só nesta máquina, em `~/.baixar-autentique/.env`, fora do Google
> Drive — ela dá acesso a todos os documentos do escritório e por isso não pode
> viajar junto com as pastas.

Na **primeira rodada**, tudo o que já estava assinado é marcado como
**histórico** e **não** é baixado — senão anos de contrato cairiam de uma vez
nas pastas. Para trazer os antigos, use a opção *“Baixar contratos assinados de
antes”* e diga quantos dias.

> Se o macOS avisar que "não pode ser aberto porque é de um desenvolvedor não
> identificado": botão direito no arquivo → **Abrir** → **Abrir**. Só acontece
> uma vez.

## O menu do atalho

| Opção | O que faz |
|---|---|
| 1 | Abre o relatório do que já foi baixado |
| 2 | Busca agora, sem esperar a próxima hora |
| 3 | Só confere e mostra o que faria — **não grava nada** |
| 4 / 5 | Liga / desliga o automático |
| 6 | Traz contratos assinados de antes (você escolhe quantos dias) |
| 7 | Guarda a chave da API |
| 8 | Testa a conexão com o Autentique |

## Como você fica sabendo

Quando a verificação automática traz alguma coisa, aparece uma **notificação na
tela do Mac** com o nome do cliente — contrato arquivado, onboarding gerado, ou
documento esperando por você. Rodada sem novidade não avisa nada.

Para desligar o aviso: `AVISAR_NA_TELA=false` no `~/.baixar-autentique/.env`.

## O relatório

`RELATÓRIOS/CONTRATOS BAIXADOS - AUTENTIQUE.html` — abre no navegador, tem
filtro e busca. As situações:

- **Baixado** — está na pasta do cliente.
- **Precisa de você** — assinado, mas a automação não soube onde arquivar
  (duas pastas parecidas, por exemplo). O PDF fica guardado em
  `~/.baixar-autentique/quarentena`; nada se perde.
- **Não é onboarding** — documento assinado que não é contrato/procuração/
  declaração (acordo, petição...). Também fica na quarentena.
- **Erro** — deu problema (internet, link expirado). A próxima rodada tenta de
  novo sozinha.

Cada linha mostra também o selo do **onboarding** (gerado / pendente / já
existia), para você ver de relance o que ainda falta.
- **Histórico** — já estava assinado quando a automação foi ligada.

## Cuidados que ela toma

- **Não baixa contrato pela metade.** O link `assinado.pdf` do Autentique
  existe desde antes de qualquer assinatura — quem decide é a lista de
  signatários: todos assinaram e ninguém recusou.
- **O nome vem do contrato, não do cadastro do Autentique.** No Autentique o
  nome sai abreviado com frequência ("Telma Cristiane E", "Felipe De Assis F De
  Souza"); no contrato está inteiro. Isso também resolve os contratos com
  **corresponsável**, em que quem assina primeiro às vezes é ele: a pasta sai
  sempre no nome do *Cliente Contratante*, e o corresponsável aparece no
  relatório.
- **Não chuta pasta de cliente.** Nome parecido demais com duas pastas vira
  pendência para você resolver.
- **Aceita erro de digitação na pasta.** "01 - OK - ANDESON" casa com
  "ANDERSON" do contrato (o nome que vale é sempre o do documento).
- **Mesma pasta em dois meses** (quando o Drive move o cliente de mês) não é
  ambiguidade: vence o mês mais recente.
- **Não sobrescreve nada.** Arquivo repetido com conteúdo idêntico é
  reconhecido e ignorado; nome repetido com conteúdo diferente vira
  `... (2).pdf`.
- **Você é reconhecida como escritório**, não como cliente: quem assina com
  `@carolinemacedoadv.com` nunca vira nome de pasta.

## O passo que o macOS exige (uma vez só)

Pelo **atalho**, quem acessa o Google Drive é o Terminal, que já tem permissão.
**Sozinha**, quem acessa é o aplicativo `Baixar Contratos Assinados.app`
(em `~/Applications`) — e o macOS só libera a pasta do Drive para aplicativos
autorizados. Por isso o agendador chama esse aplicativo, e não o Python direto.

Autorizar: atalho → **opção 9**. Ela abre o Finder com o aplicativo selecionado
e a janela de **Acesso Total ao Disco**; basta arrastar um para dentro da outra.

> **Não mexa no aplicativo depois de autorizado.** Recriá-lo troca a assinatura
> e o macOS derruba a permissão. Tudo que muda na rotina fica em
> `~/.baixar-autentique/rodar.sh`, fora do aplicativo, justamente por isso.

O `status` no topo do menu mostra como foi a última rodada automática:
`ok` ou `FALHOU: o macOS bloqueou o acesso ao Google Drive`.

## Se algo sair errado

| Sintoma | O que é |
|---|---|
| "O Autentique recusou a chave" | A chave foi revogada ou copiada pela metade. Gere outra no painel e use a opção 7. |
| "Não consegui falar com o Autentique" | Internet fora. A próxima rodada tenta de novo. |
| Documento certo virou "Precisa de você" | Não achou a pasta. Crie/renomeie a pasta do cliente e rode a opção 2 — ele volta a tentar. |
| Contrato novo não aparece | Confira no relatório se ele está como *histórico* (isso acontece com o que já estava assinado quando a automação foi ligada). |
| Nada acontece sozinho | Veja "última vez sozinha" no `status`. Se disser que o macOS bloqueou, use a opção 9. Se disser "desligado", use a opção 4. |
| Erro de permissão na pasta do Drive | Opção 9 do menu — é o aplicativo que precisa entrar em Acesso Total ao Disco. |

## Linha de comando (opcional)

```bash
~/.baixar-autentique/venv/bin/python executar.py --help
```

`rodar` · `conferir` · `historico --dias 30` · `pendencias` · `status` ·
`chave` · `testar` · `agendador --instalar|--remover|--ver`

## Como é por dentro

| Arquivo | Papel |
|---|---|
| `src/autentique.py` | Fala com a API (GraphQL v2) e decide o que está assinado por todos |
| `src/contrato.py` | Lê no contrato quem é o Cliente Contratante (e o corresponsável) |
| `src/pastas.py` | Acha ou cria a pasta do cliente |
| `src/arquivar.py` | Grava na pasta e chama o separador existente |
| `src/onboarding.py` | Chama o gerador de onboarding e traduz o que ele responde |
| `src/servico.py` | A rodada: a ordem das decisões |
| `src/estado.py` | O que já foi baixado (`~/.baixar-autentique/estado.json`) |
| `src/relatorio.py` | O HTML que você lê |
| `src/aviso.py` | A notificação na tela do Mac |
| `lancador.c` | O executável do aplicativo que o agendador chama (por causa da permissão do Drive) |
| `tests/` | 64 testes — `~/.baixar-autentique/venv/bin/python -m pytest tests` |

Ajustes finos (limiar de nome, horário, criar pasta ou não, filtro por nome do
documento) ficam em `~/.baixar-autentique/.env`; o modelo comentado é o
`.env.example` desta pasta.
