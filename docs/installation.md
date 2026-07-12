# Instalação

Supa.cc é uma CLI para macOS e para Debian/Ubuntu, Arch Linux e Fedora; derivados são best-effort. Ela requer o [Supabase CLI oficial](https://supabase.com/docs/guides/local-development/cli/getting-started) >= 2.109.1 disponível como `supabase` no `PATH`. No macOS os tokens ficam no Keychain; no Linux ficam exclusivamente no Secret Service.

## Homebrew (somente macOS)

No macOS, este é o método principal de instalação:

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supa-cc
```

Para instalar a versão atual do branch `main` durante desenvolvimento:

```bash
brew install --HEAD supa-cc
```

O comando instalado fica disponível como:

```bash
supa.cc
```

Atualização e desinstalação:

```bash
brew update
brew upgrade supa-cc
brew uninstall supa-cc
```

## Linux (somente pipx)

No Linux, instale primeiro `pipx`, o Secret Service e suas ferramentas. Execute somente o comando correspondente à sua distribuição:

```bash
# Debian ou Ubuntu
sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools

# Arch Linux
sudo pacman -S python python-pipx gnome-keyring libsecret

# Fedora
sudo dnf install python3 pipx gnome-keyring libsecret
```

O Supa.cc requer um D-Bus de usuário funcional e um Secret Service desbloqueado. Em uma sessão headless que não forneça esses serviços, a operação de credencial falha de forma segura com orientação para configurar o ambiente; ela não degrada para arquivos plaintext, `keyrings.alt` ou outro backend.

Depois instale em um ambiente Python isolado:

```bash
pipx install "git+https://github.com/dgabreuu/supa.cc.git"
```

No macOS, o processo que acessa o Keychain é o Python do ambiente gerenciado pelo `pipx`. Uma atualização que recrie esse ambiente, altere o caminho do runtime ou mude sua assinatura pode exigir uma nova autorização única. Prompts repetidos sem mudança de runtime devem ser diagnosticados com `supa.cc doctor`; não exporte o item nem conceda acesso a qualquer aplicativo.

## Desenvolvimento local

Use quando for clonar o repositório para contribuir, testar alterações ou depurar o código.

```bash
git clone https://github.com/dgabreuu/supa.cc.git supa.cc
cd supa.cc
python3 -m pip install -e ".[dev]"
```

## Requisitos

- macOS, Debian/Ubuntu, Arch Linux ou Fedora.
- Python 3.9 ou superior.
- Supabase CLI instalado e disponível no `PATH`.
- Um Supabase Personal Access Token para cada conta local.
- Em Linux, D-Bus de usuário e Secret Service desbloqueado.

## Estado e segurança

No Linux, o estado fica em `$XDG_CONFIG_HOME/supa.cc/` quando `XDG_CONFIG_HOME` está definido; caso contrário fica em `~/.config/supa.cc/`. Nenhum arquivo local contém PAT: `accounts.json` e `active-account` guardam nomes; `session-sync.json`, `.session-sync.lock` e `.accounts.json.lock` guardam metadados sem segredo. Backups temporários usados por rollback ficam somente no Secret Service ou Keychain.

O Supa.cc aceita somente o perfil oficial `supabase`, verifica a confiança do executável resolvido e confirma a credencial nativa exata após o login. Rollback e recuperação são mutation-aware: a fase do journal determina se a mutação deve ser concluída ou se a credencial anterior deve ser restaurada do backup seguro. A trava coordena processos Supa.cc, mas não comandos `supabase` externos concorrentes.

## Verificação após instalar

```bash
supa.cc --version
supa.cc doctor
supa.cc add work
supa.cc switch work
supabase projects list
supa.cc run -- projects list
```

`add` solicita o PAT em prompt oculto. `switch` valida o PAT, executa `login` e `projects list` pelo CLI oficial e só então guarda o nome ativo. Depois do sucesso, `supabase ...` direto usa essa sessão; `supa.cc run -- ...` é opcional. `doctor` sem `--live` não abre token. Para uma verificação online explícita, use `supa.cc doctor --account work --live`.

No diagnóstico padrão, o backend é configurado, mas não verificado: essa execução não testa o D-Bus nem confirma que o Secret Service ou Keychain esteja disponível e desbloqueado.

Remova qualquer `SUPABASE_ACCESS_TOKEN` herdado antes do `switch`, pois esse override bloqueia a sincronização. Um fallback `access-token` plaintext também é bloqueado e nunca é lido. Operações interrompidas deixam um journal sem token para recuperação pelo próximo comando mutável; a trava coordena apenas processos Supa.cc, não comandos `supabase` externos concorrentes. Remover a conta ativa chama `logout --yes`, que pode remover credenciais auxiliares de projeto mantidas pelo CLI oficial.

Em Linux, execute `supa.cc doctor` após instalar para confirmar a distribuição detectada, o backend Secret Service e a orientação de correção. Se o D-Bus ou a coleção estiver indisponível ou bloqueada, desbloqueie e disponibilize o Secret Service para a sessão de usuário antes de adicionar uma conta. Não tente contornar a falha com `keyrings.alt` ou qualquer armazenamento plaintext.

## Reinstalação segura

Antes de reinstalar, registre os caminhos e a proveniência mostrados por `supa.cc doctor`. Reinstale uma única distribuição pelo mesmo método usado originalmente, evitando manter cópias concorrentes do Homebrew, pipx e checkout editável no `PATH`.

Uma reinstalação do Supa.cc não exige apagar o serviço global ou as credenciais nativas do Supabase CLI. Não remova itens do Keychain, arquivos de configuração ou marcadores sem uma prévia exata do caminho, proprietário, finalidade e reversibilidade. O índice inválido deve ser preservado para diagnóstico; namespaces antigos exigem re-add pelo prompt oculto ou migração explícita.

Depois, confirme novamente `supa.cc --version` e `supa.cc doctor`. Se o Supabase CLI falhar com `EPERM` ao gravar em `~/.supabase` apenas dentro do Codex, classifique a ocorrência como restrição do sandbox e execute a validação live por uma execução aprovada fora dele. Isso é independente de um PAT rejeitado/HTTP 401.
