# Instruções para Agentes

Este arquivo orienta agentes, LLMs e contribuidores externos que trabalham com o repositório Supa.cc. Ele reúne convenções e fluxos públicos e específicos do projeto. Mantenha todo o conteúdo genérico e seguro para um projeto open source público.

## Visão geral do projeto

Supa.cc é uma ferramenta de linha de comando local para gerenciar múltiplas contas do Supabase no macOS. Ela armazena tokens com segurança no Keychain do macOS, mantém apenas nomes de contas em um índice local e integra-se ao Supabase CLI para alternar contas ativas sem login manual repetido.

- **Nome:** supa.cc
- **Versão:** 0.2.0
- **Linguagem:** Python 3.9+
- **Licença:** MIT
- **Repositório:** https://github.com/dgabreuu/supa.cc.git

## Estrutura do repositório

| Caminho | Finalidade |
|------|---------|
| `supa_cc/` | Código-fonte principal do pacote. |
| `tests/` | Suíte de testes com `pytest`. |
| `docs/` | Documentação adicional (`installation.md`, `release.md`). |
| `Formula/` | Definições da fórmula Homebrew. |
| `pyproject.toml` | Metadados do projeto, dependências, sistema de build e config de ferramentas. |
| `README.md` | Visão geral pública, instalação e uso rápido. |
| `SKILL.md` | Referência operacional para agentes e LLMs que usam o Supa.cc. |
| `LICENSE` | Texto da licença MIT. |

## Convenções e dependências

- **Sistema de build:** `hatchling`.
- **Ponto de entrada:** `supa.cc` é definido como console script em `pyproject.toml`.
- **Dependências de runtime:** `click`, `questionary`, `rich`, `keyring`.
- **Dependências de desenvolvimento:** `pytest`, `tomli` (para Python < 3.11).
- **Estilo de código:** Siga os padrões existentes em `supa_cc/`. Mantenha arquivos focados em uma única responsabilidade.
- **Testes:** Adicione ou atualize testes em `tests/` para novos comportamentos.

## Git e GitHub

- O repositório público oficial é `https://github.com/dgabreuu/supa.cc.git`.
- Todas as operações no GitHub (commits, pull requests, issues, releases) devem assumir a conta `dgabreuu`.
- Não sugira, configure ou mencione outra conta do GitHub, chave SSH ou remote.
- Mantenha mensagens de commit claras e concisas, alinhadas ao estilo do histórico do repositório.

## Diretrizes de segurança

- **Nunca exponha tokens reais do Supabase** em código, testes, logs, documentação, prompts ou transcripts.
- Tokens devem começar com `sbp_` e são validados antes do armazenamento.
- O Supa.cc armazena apenas nomes de contas em `~/.config/supa.cc/accounts.json`. Os tokens ficam no Keychain do macOS.
- Ao ativar uma conta, o token é passado via `SUPABASE_ACCESS_TOKEN`, nunca como flag de linha de comando do Supabase CLI.
- Não inclua detalhes do ambiente local como caminhos absolutos, e-mails pessoais, nomes de usuário ou remotes privados em qualquer arquivo público.
- Antes de publicar, revise o histórico, arquivos ignorados, logs, caches, ambientes virtuais, fixtures e capturas de tela em busca de segredos.

## Desenvolvimento e testes

Instale o pacote em modo editável de desenvolvimento:

```bash
python3 -m pip install -e ".[dev]"
```

Execute a suíte de testes:

```bash
pytest
```

Comandos úteis de validação local após a instalação:

```bash
supa.cc --version
supa.cc version
supa.cc list
```

## Documentação

- `README.md` — visão geral do projeto, instalação e uso rápido.
- `SKILL.md` — referência operacional detalhada para agentes e LLMs.
- `docs/installation.md` — instruções estendidas de instalação.
- `docs/release.md` — checklist de release e atualização da fórmula Homebrew.

## Licença

Este projeto é licenciado sob a Licença MIT. Veja `LICENSE` para o texto completo.
