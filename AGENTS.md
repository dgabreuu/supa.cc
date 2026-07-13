# Instruções para agentes

Mantenha toda contribuição genérica e segura para este repositório open source público.

## Estrutura

| Caminho | Responsabilidade |
| --- | --- |
| `supa_cc/` | Código-fonte Python |
| `tests/` | Suíte `pytest` |
| `docs/` | Instalação, uso, segurança, remediação e release |
| `Formula/` | Fórmula Homebrew |
| `pyproject.toml` | Metadados, dependências, build e ferramentas |
| `README.md` | Apresentação pública concisa |
| `SKILL.md` | Invariantes operacionais para agentes |

## Convenções

- Python 3.11+, build com `hatchling` e console script `supa.cc`.
- Siga os padrões existentes em `supa_cc/`, mantenha arquivos focados e cubra mudanças de comportamento em `tests/`.
- Dependências de runtime: `click`, `questionary` e `keyring`. Dependências de desenvolvimento são declaradas em `pyproject.toml`.
- Execute `python3 -m pytest`; veja [Como contribuir](CONTRIBUTING.md) para preparação do ambiente, build e smokes nativos.
- Atualize o documento canônico correspondente: [Instalação](docs/installation.md), [Uso](docs/usage.md), [Segurança](docs/security.md) ou [Solução de problemas](docs/troubleshooting.md).

## GitHub

- O repositório oficial é `https://github.com/dgabreuu/supa.cc.git`.
- Operações no GitHub assumem a conta `dgabreuu`; não sugira outra conta, chave SSH ou remote.
- Use mensagens de commit concisas e alinhadas ao histórico.

## Segurança pública

- Nunca exponha PATs reais em código, testes, logs, documentação, prompts ou transcripts. Os formatos aceitos começam com `sbp_` ou `sbp_oauth_` e são validados antes do armazenamento; não publique exemplos com aparência de credencial.
- Não publique caminhos locais absolutos, e-mails pessoais, nomes de usuário, remotes privados, dumps completos de ambiente ou conteúdo do armazenamento nativo.
- Não introduza fallback plaintext, `keyrings.alt` ou backends não suportados. Preserve as invariantes detalhadas em [SKILL.md](SKILL.md) e no [modelo de segurança](docs/security.md).
- Preserve os backends nativos: Keychain no macOS, Secret Service no Linux e Windows Credential Manager por `WinVaultKeyring` no Windows.
- Antes de publicar, revise histórico, arquivos ignorados, logs, caches, ambientes virtuais, fixtures e capturas de tela em busca de segredos.
