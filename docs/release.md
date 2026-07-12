# Checklist de release

Este checklist publica a versão 0.3.0 no GitHub e, somente depois, atualiza a fórmula Homebrew. A fórmula permanece na release v0.2.0 até a tag v0.3.0 existir.

## Pré-publicação

Revise `git status --short`, `git remote -v` e o histórico. Confirme que não há PAT, caminho absoluto local, cache, ambiente virtual, diff ou documento privado no conteúdo rastreado ou nos artefatos.

Em um checkout limpo da tag candidata, instale as dependências e valide:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m pip check
pip-audit --skip-editable
python3 -m build
python3 scripts/inspect_artifacts.py dist
```

O inspetor exige exatamente uma wheel e um sdist em `dist/`, valida os caminhos dos membros e examina arquivos textuais em busca de referências privadas e caminhos absolutos locais. Instale a wheel em um ambiente virtual descartável, execute `pip check`, `supa.cc --version` e `supa.cc version` e confirme 0.3.0.

A matriz CI cobre Python 3.9 e atual em Ubuntu/macOS, além de testes Linux de ambiente/build em contêineres Fedora e Arch sem exigir Secret Service real. Smoke tests nativos continuam opt-in.

## Contrato operacional

Confirme Supabase CLI >= 2.109.1, perfil oficial `supabase`, confiança do executável, verificação da credencial nativa exata, rollback/recuperação mutation-aware, logout ao remover a conta ativa e bloqueio de fallback plaintext. `doctor` deve permanecer não-live por padrão; somente `doctor --account <nome> --live` abre o token para validação explícita. A trava não coordena comandos `supabase` externos concorrentes.

## Tag e GitHub Release

Crie a tag v0.3.0 somente a partir do commit validado e construa os artefatos finais em um checkout limpo dessa tag. Publique a GitHub Release sem arquivos de configuração, logs, caches ou segredos.

## Fórmula Homebrew

Não altere `Formula/supa-cc.rb` antes da tag v0.3.0 existir. Após a tag, atualize a URL para o tarball `v0.3.0`, calcule o SHA256 do tarball real e atualize recursos Python a partir do checkout do tap:

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
cd "$(brew --repo dgabreuu/supa-cc)"
brew update-python-resources Formula/supa-cc.rb
brew audit --strict supa-cc
brew install --build-from-source supa-cc
brew test supa-cc
```

Mantenha `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"`. Não publique no PyPI e não crie assets Debian, AUR ou RPM neste processo.
