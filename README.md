```text
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
```

# Supa.cc

Supa.cc é uma CLI local para alternar entre várias contas do Supabase sem espalhar Personal Access Tokens (PATs) por arquivos ou comandos. A experiência principal é uma TUI; depois da ativação, o próprio `supabase` usa a conta escolhida.

| Plataforma | Suporte | Credencial nativa |
| --- | --- | --- |
| macOS | Suportado | Keychain |
| Debian/Ubuntu, Arch Linux e Fedora | Suportado; derivados best-effort | Secret Service |
| Windows | Suportado | Windows Credential Manager |

Requer Python 3.9+ e o [Supabase CLI oficial](https://supabase.com/docs/guides/local-development/cli/getting-started) >= 2.109.1 no `PATH`.

![Supa.cc exibindo o painel inicial e as ações disponíveis no terminal](https://raw.githubusercontent.com/dgabreuu/supa.cc/main/assets/terminal.png)

## Instalação

Pré-requisitos, atualização e desinstalação estão no [guia de instalação](https://github.com/dgabreuu/supa.cc/blob/main/docs/installation.md).

### macOS

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supa-cc
```

### Linux

```bash
pipx install supa.cc
```

### Windows

```powershell
pipx install supa.cc
```

## Segurança

PATs ficam somente no armazenamento nativo de credenciais de cada plataforma; nenhum arquivo local contém PAT. O token chega ao Supabase CLI pelo ambiente do processo, nunca por argumento de linha de comando. Consulte o [modelo de segurança](https://github.com/dgabreuu/supa.cc/blob/main/docs/security.md) para garantias e limites.

## Licença

MIT. Veja a [licença completa](https://github.com/dgabreuu/supa.cc/blob/main/LICENSE).
