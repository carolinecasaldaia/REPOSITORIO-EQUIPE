# CM | Calculadora Judicial Bancária

Uso interno — Caroline Macedo Advocacia. Este diretório contém **somente código**.

## Regras invioláveis
- Dados de clientes ficam em `~/CM-Calculos-Dados/`, nunca neste diretório nem em testes.
- Testes usam apenas dados fictícios (origem `FICTICIO` ou documentos marcados "fictício").
- O motor (`src/cm_calc/motor/`) não faz I/O, não acessa rede e não usa IA.
- Sem `float` no motor: usar `D("...")`. Arredondamento só via `PoliticaArredondamento`.
- Nenhum critério jurídico tem valor padrão. Índice, termo inicial, dobra, ordem de imputação, tratamento de reforçadas, encargos afastados e base de honorários vêm do título. Se faltar, levantar erro ou ressalva de pendência; nunca presumir.
- Verba adicional exige trecho literal do título (`VerbaAutorizada`).
- Não alterar automações existentes do escritório (LaunchAgents `com.carolinemacedo.*`, `~/automacoes-claude/`).

## Leitura documental e privacidade (Fase 3)
- Modelo híbrido: leitura, classificação, extração e pseudonimização são 100% locais (`documentos/`, `extracao/`, `privacidade/`). Nenhum módulo faz chamada de rede (há teste para isso).
- Claude só lê pacotes pseudonimizados em `~/CM-Calculos-Dados/casos/*/claude/pacotes/`, gerados com autorização registrada (`cm-calc pacote`). Nunca abrir documentos originais, o quadro (`extracao/`) ou resultados de casos reais; as regras em `.claude/settings.json` bloqueiam a leitura direta.
- Cálculo definitivo só a partir de quadro sem bloqueios (`extracao/aprovacao.bloqueios`), com parâmetros confirmados pela advogada.
- Comandos do título vêm só do DISPOSITIVO de decisões; fundamentação e alegações das partes nunca viram parâmetro.

## Validação pericial (Fase 5)
- `src/cm_calc/validacao/`: lê o parecer (tabelas AP01–AP03 e metodologia), reconstrói com o motor a partir da FICHA (só entradas: contrato e título) e compara célula a célula.
- Nunca alterar o motor para reproduzir o parecer. Divergências são explicadas por cenários de diagnóstico (convenção de dias, regime, arredondamento, regra de meses/índice) — "COMPROVADO" só quando o cenário reproduz a célula.
- Pasta: `~/CM-Calculos-Dados/validacao/<ID>/` (parecer anonimizado; varredura local de dados pessoais antes de executar).

## Comandos
- Testes: `uv run pytest`
- Fluxo do caso: `uv run cm-calc importar|extrair|quadro|confirmar|rejeitar|pagamentos|ciencia|status|pacote` (ver `cm_calc/cli.py`)
- Interface: `./iniciar.sh` (casos reais, :8501) · `./iniciar-demo.sh` (fictícios, :8502). Ver `docs/INTERFACE.md`.
- A interface só apresenta: regras em `servicos/`, cálculos em `motor/`. Telemetria do Streamlit desligada; servidor só em 127.0.0.1.
- Validação: `uv run cm-calc validacao preparar|verificar|executar ID`
- Cobertura: `uv run pytest --cov=cm_calc --cov-report=term-missing`

## Metodologia
Ver `docs/METODOLOGIA.md`.
