# Como contribuir

Obrigado por contribuir com o Supa.cc. Use as [GitHub Issues](https://github.com/dgabreuu/supa.cc/issues) para bugs, problemas de instalação e propostas de funcionalidade. Vulnerabilidades devem seguir exclusivamente a [política de segurança](SECURITY.md).

## Ambiente de desenvolvimento

O projeto requer Python 3.11 ou mais recente. Faça um fork, clone o repositório e instale o pacote com as dependências de desenvolvimento.

### macOS e Linux (POSIX)

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

### Windows

```powershell
py -m pip install -e ".[dev]"
py -m pytest
```

Para mudanças de empacotamento, valide também:

```text
python3 scripts/security_scan.py --worktree --history
python3 -m pytest --cache-clear --collect-only -q
python3 scripts/security_scan.py --path .pytest_cache
python3 -m build
python3 scripts/inspect_artifacts.py dist
# Windows: substitua python3 por py
```

## Smokes nativos

Testes que acessam o armazenamento real são opt-in, específicos da plataforma e exigem consentimento explícito. Eles criam o serviço `supa.cc.tests.<uuid>` e a conta `smoke-<uuid>`, removidos em `finally`; nunca acessa o serviço canônico do Supa.cc nem credenciais do Supabase CLI.

```bash
SUPA_CC_RUN_KEYCHAIN_SMOKE=1 .venv/bin/pytest -q tests/test_macos_keychain_smoke.py
SUPA_CC_REAL_SECRET_SERVICE=1 .venv/bin/pytest -q tests/test_linux_secret_service_smoke.py
SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE=1 .venv/bin/pytest -q tests/test_windows_credential_manager_smoke.py
```

## Diretrizes

- Mantenha mudanças pequenas, focadas e acompanhadas por testes quando alterarem comportamento.
- Preserve suporte a macOS, Debian/Ubuntu, Arch Linux, Fedora e Windows conforme a documentação atual.
- Atualize a documentação pública quando comandos ou comportamento mudarem.
- Descreva como a mudança foi validada.

## Dados sensíveis

Nunca inclua PATs, tokens do Supabase, itens do armazenamento nativo, dumps de credenciais ou dumps completos de ambiente em issues, pull requests, testes, logs ou documentação. Use somente dados fictícios que não tenham formato de credencial real.
