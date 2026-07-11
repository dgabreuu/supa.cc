# Checklist de release

Use este checklist antes de publicar o Supa.cc no GitHub ou atualizar a fórmula Homebrew macOS-only.

## Segurança do repositório

```bash
git status --short
git remote -v
git log -1 --format='%an <%ae>'
```

Confirme que o remote é `https://github.com/dgabreuu/supa.cc.git` e que o autor público do commit é aceitável para a release.

Remova artefatos locais antes de publicar:

```bash
rm -rf .pytest_cache .ruff_cache .venv venv
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . -name .DS_Store -type f -delete
```

## Versão

Atualize a versão em:

- `pyproject.toml`
- `supa_cc/__init__.py`

Em seguida execute:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m pytest -m "not real_keychain and not real_secret_service"
SUPA_CC_REAL_SECRET_SERVICE=1 python3 -m pytest -m real_secret_service -v
python3 -m build
ls dist/
```

`python3 -m build` deve gerar uma wheel e um sdist em `dist/`. Execute os jobs de teste em Linux suportado (Debian/Ubuntu, Arch Linux e Fedora) além do macOS antes da release. Os smoke tests de Keychain e Secret Service são opt-in e não entram no job padrão sem um serviço real e consentimento explícito. O smoke de Secret Service pula com segurança caso o serviço não esteja disponível.

Após instalar a wheel em um ambiente descartável, valide as duas saídas de versão:

```bash
supa.cc --version  # Click: supa.cc, version 0.2.0
supa.cc version    # Aplicação: Supa.cc v0.2.0
```

## Release no GitHub

```bash
git tag v0.2.0
git push origin main
git push origin v0.2.0
```

Crie uma GitHub Release a partir da tag e anexe artefatos gerados somente se necessário. Não anexe arquivos de configuração local, ambientes virtuais, caches, logs ou exportações de token.

## Fórmula Homebrew

A fórmula `Formula/supa-cc.rb` permanece exclusivamente para macOS. Não crie assets Debian, PKGBUILD/AUR ou RPM como parte desta release.

O repositório não usa o prefixo `homebrew-` no nome. Faça o tap com URL explícita ao testar localmente:

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
```

Depois que a tag existir, atualize `Formula/supa-cc.rb` com a URL e o SHA256 do tarball estável e verifique os recursos Python a partir de um checkout do tap:

```bash
cd "$(brew --repo dgabreuu/supa-cc)"
brew update-python-resources Formula/supa-cc.rb
brew audit --strict supa-cc
brew test supa-cc
```

A URL da fonte estável deve seguir este formato:

```ruby
url "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.2.0.tar.gz"
sha256 "<sha256-from-release-tarball>"
```

Mantenha `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"` para instalações de desenvolvimento.
