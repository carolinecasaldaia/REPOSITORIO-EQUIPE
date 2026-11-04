# Segurança

Este repositório é **privado** e guarda só código, modelos e documentação.

## Regras

- **Nenhum dado de cliente** entra aqui: documentos, planilhas, PDFs, relatórios e listas ficam no Google Drive.
- **Nenhuma credencial** entra aqui: chaves de API (ASAAS, Conta Azul, Autentique, Astrea), senhas e tokens ficam em `.env`, fora do Git. Use os arquivos `.env.example` / `.env.exemplo` como modelo.
- Exemplos em testes e documentação usam apenas dados fictícios ou anonimizados.

## Proteções ativas

| Proteção | Onde |
|---|---|
| Arquivos sensíveis ignorados pelo Git | `.gitignore` |
| Arquivos sensíveis fora de imagens Docker | `.dockerignore` |
| Varredura de credenciais em cada PR e push na `main` | `.github/workflows/seguranca.yml` (gitleaks) |
| Varredura antes de cada commit local | `.pre-commit-config.yaml` + hook `.git/hooks/pre-commit` |
| Alertas de dependências vulneráveis | `.github/dependabot.yml` |

Ativar a verificação local numa máquina nova:

```bash
brew install gitleaks pre-commit
pre-commit install
```

## Se uma credencial vazar

1. **Revogue a chave imediatamente** no painel do serviço (ASAAS, Conta Azul etc.) e gere uma nova.
2. Só depois remova do código. Apagar o commit não basta: a chave já deve ser considerada comprometida.
