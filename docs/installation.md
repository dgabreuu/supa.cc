# Instalação

Este guia cobre pré-requisitos e o ciclo completo de instalação em cada plataforma. Os comandos estáveis são instruções para releases publicadas no respectivo canal; não significam que a versão 0.3.0 já foi publicada.

Em todas as plataformas, instale antes o [Supabase CLI oficial](https://supabase.com/docs/guides/local-development/cli/getting-started) >= 2.109.1 e confirme que `supabase` está no `PATH`. O Supa.cc requer Python 3.9+.

## Instalação por plataforma

### Homebrew (somente macOS)

#### Pré-requisitos

Instale o Homebrew e o Supabase CLI oficial. O canal estável usa Homebrew e guarda PATs no Keychain.

#### Instalar

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supa-cc
```

#### Verificar

```bash
supa.cc --version
```

#### Atualizar

```bash
brew upgrade supa-cc
```

#### Desinstalar

```bash
brew uninstall supa-cc
```

O runtime Python instalado é quem acessa o Keychain. Uma alteração de caminho, ambiente ou assinatura pode pedir uma nova autorização única; prompts repetidos sem alteração devem ser diagnosticados, não contornados.

### Linux (somente pipx)

São suportados Debian/Ubuntu, Arch Linux e Fedora; derivados são best-effort. A instalação estável é somente por `pipx`.

#### Pré-requisitos

Instale Python, `pipx`, Secret Service e suas ferramentas com o comando da sua distribuição:

```bash
# Debian ou Ubuntu
sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools

# Arch Linux
sudo pacman -S python python-pipx gnome-keyring libsecret

# Fedora
sudo dnf install python3 pipx gnome-keyring libsecret
```

Execute `pipx ensurepath` e reabra o shell se o comando orientar. É obrigatório haver D-Bus de usuário e um Secret Service desbloqueado. Sessões headless sem esses serviços falham de forma segura, sem plaintext, `keyrings.alt` ou backend alternativo.

#### Instalar

```bash
pipx install supa.cc
```

#### Verificar

```bash
supa.cc --version
```

#### Atualizar

```bash
pipx upgrade supa.cc
```

#### Desinstalar

```bash
pipx uninstall supa.cc
```

Após instalar, execute `supa.cc doctor`. O estado sem segredo fica em `$XDG_CONFIG_HOME/supa.cc` quando a variável está definida, ou em `~/.config/supa.cc`.

### Windows (somente pipx)

A instalação estável é somente por `pipx`. PATs e backups seguros ficam no Windows Credential Manager, exclusivamente pelo backend `WinVaultKeyring`; metadados sem segredo ficam em `%APPDATA%\supa.cc`.

#### Pré-requisitos no PowerShell

Instale Python 3.9+ para o usuário atual e o Supabase CLI oficial. Depois instale e configure `pipx`:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Feche e reabra o PowerShell para aplicar o `PATH`. Confirme que `pipx` e `supabase` são encontrados antes de continuar. `%APPDATA%` deve existir e ser um caminho absoluto.

#### Instalar

```powershell
pipx install supa.cc
```

#### Verificar

```powershell
supa.cc --version
```

#### Atualizar

```powershell
pipx upgrade supa.cc
```

#### Desinstalar

```powershell
pipx uninstall supa.cc
```

Se `supa.cc` não for encontrado após reabrir o shell, repita `py -m pipx ensurepath` e consulte [Solução de problemas](troubleshooting.md#windows).

## Depois da instalação

Siga o [primeiro uso pela TUI](usage.md#primeiro-uso-pela-tui). O diagnóstico padrão mostra o backend como configurado, mas não verificado: ele não testa D-Bus nem abre o armazenamento de credenciais. Antes de trocar o método de instalação, siga a [reinstalação segura](troubleshooting.md#reinstalação-segura). Detalhes de Keychain, Secret Service e Credential Manager estão em [Solução de problemas](troubleshooting.md); garantias de estado e rollback estão em [Segurança](security.md). O ambiente de desenvolvimento é documentado em [Como contribuir](../CONTRIBUTING.md).
