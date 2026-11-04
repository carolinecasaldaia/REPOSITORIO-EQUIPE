# Anonimização local — v0.6.9

## Uso simples (ícones na Mesa)

1. **CM - 1 Anonimizar parecer.command** (dois cliques):
   - escolha o PDF original;
   - digite os nomes e números a remover, separados por `;`;
   - o sistema copia o arquivo com nome genérico (`documento-01`), anonimiza, verifica e abre tudo para conferência.
   - **Nada é liberado** nesta etapa.
   - Se a verificação reprovar (por exemplo, página escaneada ou dado financeiro alterado), o procedimento é **interrompido**.
2. Confira a cópia (roteiro abaixo).
3. **CM - 2 Liberar parecer anonimizado.command** (dois cliques, v0.6.5):
   1. escolha a cópia (só aparecem as cópias APROVADAS);
   2. informe o seu nome (é pedido de novo se ficar em branco);
   3. **digite AUTORIZO** e clique em "Liberar".

   - Enter, Esc ou "Cancelar" em qualquer janela encerram **sem liberar**.
   - A liberação fica registrada com o seu nome, data e hora, o arquivo e o hash. Se o arquivo for alterado depois, a liberação deixa de valer.
   - Diário das etapas, sem conteúdo de documentos: `~/Library/Logs/CM-Calculadora/liberacao.log`.
   - Pela linha de comando, `liberar` exige `--confirmo-conferencia`. Se o Claude tentar liberar, o hook pede a aprovação da advogada.

Os ícones são cópias de `~/cm-calculadora/ferramentas/`. Eles não mencionam a pasta de dados: tudo passa pelos comandos `cm-calc validacao ...`, que só exibem nomes genéricos e contagens.

## Fluxo

```
original/  →  cm-calc validacao anonimizar  →  anonimizados/ + anonimizacao/  →  conferência  →  cm-calc validacao liberar  →  parecer/ ou documentos/
```

- **Originais:** nunca são alterados; o hash é conferido antes e depois.
- **Redação real:** o texto sob a tarja é apagado do arquivo.
- **Removido do arquivo:** imagens (assinaturas, QR codes), metadados, XMP, anotações, campos, anexos, links, JavaScript e marcadores.
- **Valores, percentuais e datas financeiras:** são protegidos e nunca são removidos.
- **Verificação automática:**
  - original intacto;
  - nenhum texto removido reaparece;
  - zero imagens, anotações, anexos e metadados;
  - todos os dados financeiros preservados;
  - tabelas AP01 a AP03 idênticas às do original.
- **Relatórios:**
  - `anonimizacao/verificacao.md`: sem dados pessoais;
  - `anonimizacao/relatorio-detalhado-*.md`: **confidencial**, lista o que foi removido.

## Conferência pela advogada (antes de liberar)

1. Em `verificacao.md`, confirme:
   - resultado **APROVADA**;
   - "dados financeiros N/N preservados";
   - "tabelas idênticas: True";
   - zero imagens, metadados e marcadores.
2. Em `relatorio-detalhado-*.md`, confirme que:
   - tudo o que foi removido é dado pessoal;
   - nada essencial ao cálculo foi removido.
3. Abra a cópia em `anonimizados/` no Pré-Visualização:
   - percorra capa, rodapés e páginas de assinatura;
   - use **Cmd+F** para procurar nomes, partes do nome, CPF (só os números), processo, contrato e placa;
   - use **Cmd+A**, **Cmd+C** e cole no TextEdit para procurar de novo (pega texto invisível);
   - em **Ferramentas → Mostrar Inspetor (Cmd+I)**, confira autor e título vazios;
   - confira que a barra lateral não mostra marcadores com nomes;
   - compare por amostragem as tabelas e os totais com o original.
4. Se algo escapou: acrescente o termo em `anonimizacao/termos.txt` e rode a anonimização de novo.
5. Libere: `uv run cm-calc validacao liberar VAL-001 ARQUIVO --como parecer|documento --por "Nome"`. A liberação fica registrada em `anonimizacao/liberacoes.jsonl`.

## Camadas tratadas e verificadas (v0.6.9)

| Camada | Tratamento | Verificação (reprova se falhar) |
|---|---|---|
| Texto visível, invisível, branco, minúsculo, em XObjects | detecção por padrão, rótulo e termos; tarja real | busca de novo na cópia (sem diferença de acento/maiúscula) |
| Certidões e quadros em colunas | rótulo ("RG", "REGISTRO", "NOME"…) e valor localizados **pela posição** (embaixo ou ao lado) | a mesma busca por posição na cópia |
| Variações (R.G., UF-número, SSP/UF, CNH, PIS, CTPS, matrícula, passaporte, título de eleitor) | padrões dedicados; exige ao menos 4 dígitos | idem |
| Texto fora da área da página | removido por inteiro | nenhuma palavra fora da página |
| Camadas opcionais ocultas | reveladas antes da detecção (registrado no resumo) | conferência visual |
| Imagens (inclusive em linha) | removidas | zero imagens |
| Rubricas, assinaturas e logotipos **desenhados em vetor** | removidos pela forma (muitas curvas); texto preservado | zero desenhos suspeitos |
| Formulários, assinatura digital (certificados), árvore de estrutura (texto alternativo), rótulos de página, ações, XMP por objeto | estruturas apagadas | nenhuma estrutura restante; varredura das cadeias de texto de **todos** os objetos |
| Revisões anteriores (gravação incremental) | arquivo regravado inteiro | uma única revisão |
| Valores, percentuais, datas, tabelas | nunca removidos | conferência estrita e tabelas idênticas |

### Imagens (v0.6.10)

- **Pequenas e médias** (assinaturas, logotipos, QR codes, faixas e fios): removidas. Se a redação do MuPDF não remover alguma, uma **rede de segurança** apaga a imagem em linha direto do fluxo da página (leitura léxica) ou a desliga dos recursos.
- **Grandes** (mais de 25% da página; possível gráfico, tabela ou foto): **não** são removidas automaticamente. Ficam retidas, são exportadas para `anonimizados/revisao-imagens/` (pasta protegida, só no Mac) e a verificação reprova. Depois de olhar a imagem:
  - se ela pode sair: `uv run cm-calc validacao anonimizar VAL-001 --remover-imagens-grandes`;
  - se ela é necessária ao cálculo: não há liberação automática. Tarje manualmente apenas o dado pessoal e reverifique.
- **Diagnóstico sem conteúdo:** `uv run cm-calc validacao diagnosticar-imagens VAL-001` lista página, origem, tamanho, posição e função provável (só pela forma) das imagens que restaram.

## Revisão manual obrigatória (mesmo com APROVADA)

A verificação automática reduz o risco, mas não o elimina. Antes de liberar:

1. **Página a página, com zoom de 150% ou mais:** olhe capa, cabeçalhos, rodapés, certidões, quadros de qualificação e páginas de assinatura. Procure números de documento, nomes, rubricas e carimbos que tenham escapado.
2. **Busca (Cmd+F)** por:
   - cada nome e sobrenome das partes, da perita e dos advogados;
   - CPF, RG e registro, **só com os números**, inteiros e em pedaços (por exemplo, os 4 primeiros dígitos);
   - número do processo e do contrato, placa e e-mail.
3. **Cmd+A, Cmd+C e colar no TextEdit:** repita a busca no texto colado. Assim aparece texto invisível ou fora de ordem.
4. **Inspetor (Cmd+I):** autor, título, assunto e palavras-chave vazios; nenhum marcador na barra lateral.
5. **Se "camadas opcionais reveladas" for 1 ou mais:** confira se surgiram textos sobrepostos ou ilegíveis.
6. **Se "desenhos vetoriais removidos" for 1 ou mais:** confira que sumiram só rubricas ou logotipos, e nenhum gráfico necessário ao cálculo.
7. **Tabelas:** compare com o original, por amostragem (em cada apêndice, a primeira linha, a última e 3 aleatórias), e confira os totais.
8. **Qualquer dúvida: não libere.** Acrescente o termo em `termos.txt` e rode de novo. Ou tarje manualmente uma cópia e repita a verificação (`cm-calc validacao verificar`).

## Limitações

- **Assinaturas desenhadas como vetor:** são removidas pela forma (10 curvas ou mais numa área pequena). Rubricas com poucos traços e **texto convertido em contorno** podem escapar; só a conferência visual garante.
- **Identificadores sem rótulo e sem formato conhecido** (por exemplo, um número solto numa linha, sem "RG" ou "registro" por perto) não são reconhecidos.
- **Rótulo distante do valor** (mais de cerca de 2,5 linhas abaixo, ou coluna deslocada) pode não ser associado.
- **Conteúdo em padrões, sombreamentos e fontes Type3 desenhadas** não é inspecionado como imagem.
- **Páginas digitalizadas:** o dado está na imagem e não é detectável; a página é sinalizada. Use o PDF digital.
- **Nomes sem rótulo** ("Autor:", "Perita:" etc.) **e fora de qualificação:** só são removidos se listados em `termos.txt`.
- **Formatos:** apenas PDF, XLSX e CSV. Converta DOCX para PDF.
