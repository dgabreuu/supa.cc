# Solução de problemas

Comece sempre com o diagnóstico não-live:

```bash
supa.cc doctor
supa.cc doctor --json
```

Ele não abre PAT nem testa ou verifica a disponibilidade do armazenamento de credenciais; mostra somente o backend configurado. Compartilhe a saída, mas não dumps completos de ambiente ou armazenamento de credenciais.

## Reinstalação segura

Antes de reinstalar, registre o método de instalação, a proveniência e a versão mostradas pelo diagnóstico. Não mantenha instalações Homebrew, `pipx` e editáveis simultâneas no `PATH`. Preserve estado inválido para diagnóstico e não apague credenciais nativas; reinstalar o pacote não exige remover PATs do armazenamento da plataforma.

## macOS

O Keychain autoriza o runtime Python que executa o Supa.cc. Recriar um ambiente `pipx`, mudar o caminho ou a assinatura desse runtime pode provocar uma nova autorização única. Prompts repetidos com o mesmo runtime indicam permissão ou controle de acesso inconsistente.

Não exporte o item, não conceda acesso a todos os aplicativos e não afrouxe ACLs. Use `doctor` para comparar os caminhos invocado e real do launcher, Python e Supabase CLI. Se o Keychain estiver bloqueado, desbloqueie-o na sessão gráfica e tente novamente.

## Linux

O backend aceito é somente Secret Service no D-Bus da sessão de usuário. Confirme que o D-Bus existe, que `gnome-keyring` ou outro provedor compatível está em execução e que a coleção está desbloqueada. Em SSH, contêiner ou ambiente headless, encaminhar apenas variáveis de D-Bus sem um serviço real e desbloqueado não resolve.

Não instale `keyrings.alt` nem configure armazenamento plaintext. Debian/Ubuntu, Arch Linux e Fedora são suportados; confira os pacotes em [Instalação](installation.md#linux-somente-pipx). O estado sem segredo usa `$XDG_CONFIG_HOME/supa.cc` ou `~/.config/supa.cc`.

## Windows

O backend deve ser exatamente Windows Credential Manager por `WinVaultKeyring`. Não habilite backends alternativos. Verifique no Credential Manager se o cofre está disponível para a mesma conta de usuário, sem copiar ou expor o valor da credencial.

Se `pipx` ou `supa.cc` não estiver no `PATH`, execute no PowerShell:

```powershell
py -m pipx ensurepath
```

Feche e reabra o PowerShell. `%APPDATA%` precisa estar definido como caminho absoluto; os metadados sem segredo ficam em `%APPDATA%\supa.cc`. Ausência ou caminho relativo causa falha segura.

## Variáveis herdadas

Um `SUPABASE_ACCESS_TOKEN` já definido faz override da sessão persistida e bloqueia `switch`. Remova-o do shell atual e da configuração que o injeta, sem imprimir seu valor. Procure somente a presença da variável com ferramentas adequadas ao seu shell.

O Supa.cc bloqueia o fallback plaintext `access-token` da Supabase CLI sem ler seu conteúdo. Não cole esse arquivo em relatórios e não tente migrá-lo para o Supa.cc.

## Diagnóstico live e erros comuns

Use `supa.cc doctor --account <nome> --live` apenas quando quiser autorizar leitura e validação online da conta escolhida. Um HTTP 401 indica PAT rejeitado; falha de rede, CLI ausente/incompatível, armazenamento bloqueado e `EPERM` são categorias distintas. Um `EPERM` restrito a sandbox não comprova token inválido.

Operações interrompidas podem deixar journal de recuperação sem token. Execute novamente um comando mutável do Supa.cc; não apague journal, locks, índice ou credenciais manualmente. A trava não coordena comandos `supabase` externos, portanto evite executá-los simultaneamente com uma ativação.
