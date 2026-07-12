# Checklist de release

Este checklist prepara e publica a versão 0.3.0 em uma sequência única. A versão continua não lançada enquanto a GitHub Release `v0.3.0` não for publicada, e `Formula/supa-cc.rb` deve permanecer em `v0.2.0` até a publicação no PyPI ser verificada.

## 1. Validar o commit candidato

Revise `git status --short`, `git remote -v` e o histórico. Confirme que não há PAT, caminho absoluto local, cache, ambiente virtual, diff ou documento privado no conteúdo rastreado ou nos artefatos.

Em um checkout limpo do commit candidato, execute:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m pip check
pip-audit --skip-editable
rm -rf dist
python3 -m build
python3 scripts/inspect_artifacts.py dist
```

O inspetor exige exatamente uma wheel e um sdist em `dist/`, valida os caminhos dos membros e procura referências privadas e caminhos absolutos locais. Instale também a wheel em um ambiente virtual descartável, execute `pip check`, `supa.cc --version` e `supa.cc version`, e confirme `0.3.0`.

A matriz CI executa a suíte normal completa em Python 3.9 e atual no Ubuntu, macOS e Windows, além dos testes direcionados em Fedora e Arch, sem acessar cofres reais nos runners hospedados. Aguarde a CI validada no commit exato antes de continuar. Smoke tests nativos permanecem opt-in e exigem execução explícita em um host com o armazenamento nativo disponível.

## 2. Confirmar o contrato operacional

Confirme Supabase CLI >= 2.109.1, perfil oficial `supabase`, confiança do executável, verificação da credencial nativa exata, recuperação mutation-aware, logout ao remover a conta ativa e bloqueio de fallback plaintext. `doctor` deve permanecer não-live por padrão; somente `doctor --account <nome> --live` abre o token para validação explícita. A trava não coordena comandos `supabase` externos concorrentes.

## 3. Configurar o Trusted Publisher

No PyPI, configure previamente um Trusted Publisher para o projeto `supa.cc` com estes valores:

- Owner: `dgabreuu`
- Repository: `supa.cc`
- Workflow: `release.yml`
- Environment: `pypi`

Proteja o environment `pypi` conforme a política do repositório. O workflow usa OIDC com `id-token: write`; não crie token de API nem secret do PyPI.

## 4. Publicar a GitHub Release

Crie a tag anotada `v0.3.0` somente no commit com CI validada. Crie a GitHub Release correspondente, use a seção 0.3.0 do `CHANGELOG.md` como base das notas e confira o alvo antes de selecionar **Publish release**.

A publicação da GitHub Release dispara `.github/workflows/release.yml`. O job de build faz checkout da tag da release, confirma que ela corresponde à versão do `pyproject.toml`, testa, constrói uma única vez e envia uma wheel e um sdist como artifact. Não anexe builds locais à release.

## 5. Publicar no PyPI por Trusted Publishing

O job `build` possui somente `contents: read`. O job `publish` baixa exatamente o artifact produzido pelo build e o envia ao PyPI por Trusted Publishing usando somente `id-token: write`. O job de verificação não recebe permissões do `GITHUB_TOKEN`.

Se build, inspeção ou publicação falhar, não recrie a mesma versão no PyPI e não avance para a fórmula. Corrija a causa e prepare uma nova versão conforme a imutabilidade dos artefatos publicados.

## 6. Verificar pipx no Linux e no Windows

Após a publicação, o workflow instala `supa.cc==0.3.0` diretamente do PyPI com pipx no Linux e no Windows e executa os dois comandos de versão. Confirme os jobs verdes e faça uma verificação manual independente se a política da release exigir:

```bash
pipx install supa.cc==0.3.0
supa.cc --version
supa.cc version
```

## 7. Atualizar a fórmula Homebrew

Somente depois da verificação com pipx no Linux e no Windows e após a tag existir, altere `Formula/supa-cc.rb`. Use o tarball real da tag `v0.3.0`, calcule seu SHA256 real e atualize os recursos Python; nunca antecipe ou invente o checksum.

```bash
archive="${TMPDIR:-.}/supa.cc-v0.3.0.tar.gz"
curl -L -o "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.3.0.tar.gz
sha256sum "$archive"
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
cd "$(brew --repo dgabreuu/supa-cc)"
brew update-python-resources Formula/supa-cc.rb
brew audit --strict supa-cc
brew install --build-from-source supa-cc
brew test supa-cc
```

No macOS, use `shasum -a 256` se `sha256sum` não estiver disponível. Mantenha `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"`.

## 8. Atualizar o texto de disponibilidade

Somente depois de PyPI e Homebrew estarem verificados, remova de `README.md` e `docs/installation.md` o texto de disponibilidade que descreve os canais como planejados. Finalize a entrada do changelog trocando “Não lançado (preparado)” pela data real da release e substituindo `HEAD` pela tag `v0.3.0` no link de comparação.

Não crie assets Debian, AUR ou RPM neste processo.
