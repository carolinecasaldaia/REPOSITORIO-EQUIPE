# Proteção de dados no Claude Code — v0.6.2

Instalada em 21/10/2026. Vale para **qualquer sessão** do Claude Code neste computador, aberta em qualquer pasta.

Backup das configurações anteriores: `~/.claude/backups/cm-protecao-20261021-152352/`.

## Camadas

| Camada | Onde | O que faz |
|---|---|---|
| 1. Regras de bloqueio | `~/.claude/settings.json` → `permissions.deny` | Impedem ler e editar originais, cópias não liberadas, relatório detalhado, `termos.txt` e documentos, extração e resultados dos casos. |
| 2. Verificação antes de cada ação | `~/.claude/hooks/cm-protecao.py` (hook PreToolUse; código-fonte em `src/cm_calc/privacidade/protecao_hook.py`) | Analisa caminho, comando, scripts executados e textos enviados a outras ferramentas ou subagentes. Nega o acesso a áreas protegidas, as buscas e cópias em massa da pasta de dados, o `cm-calc` encadeado com outros comandos e os arquivos de `parecer/` e `documentos/` que não estejam no registro de liberação com o mesmo hash. Pede confirmação para comandos `cm-calc` que exibem dados de casos. |
| 3. Verificação no sistema | `cm_calc.validacao.pasta.Validacao.exigir_liberado` | A validação recusa usar arquivo não liberado ou alterado depois da liberação. |

## O que não muda

- Ações que **não** mencionam `~/CM-Calculos-Dados` (nem ocorrem dentro dela) passam sem efeito. Isso inclui as automações do Astrea, do Asaas e as demais.
- O `~/.claude/settings.local.json` (permissão da automação do Astrea) não foi alterado.
- Se o hook falhar por erro interno numa ação sem relação com a pasta de dados, a ação segue. Se a ação envolver a pasta de dados, é bloqueada.

## Como desfazer

1. Restaure os arquivos do backup para `~/.claude/`.
2. Ou abra `/hooks` no Claude Code e desative o hook "CM: verificando proteção de dados".

## Registro

`~/.claude/hooks/cm-protecao.log` guarda data, ferramenta e motivo de cada bloqueio, sem caminhos nem conteúdo.

## Riscos que permanecem

Ver o relatório da Fase 5 (proteções). Em resumo:

- código executado indiretamente (por exemplo, um programa já instalado que lê a pasta por conta própria) não é inspecionado;
- arquivos copiados para fora da pasta de dados por você deixam de estar protegidos;
- a proteção depende de o hook estar ativo (não usar `disableAllHooks`).
