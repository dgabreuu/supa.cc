# Modelo de segurança

Este é o documento canônico das garantias e limites de segurança do Supa.cc.

## Armazenamento

- O serviço canônico é `supa.cc.supabase.accounts.v2`.
- PATs ficam no Keychain do macOS, Secret Service do Linux ou Windows Credential Manager por `WinVaultKeyring`.
- Nenhum arquivo local contém PAT. `accounts.json` e `active-account` guardam nomes; `session-sync.json`, `.session-sync.lock` e `.accounts.json.lock` guardam metadados de recuperação e coordenação.
- Backups de rollback ficam no armazenamento nativo sob identidade reservada, nunca no índice ou journal.
- Leituras de credenciais não usam cache: cada leitura consulta diretamente `CredentialStore.get()` e o backend nativo. Índices inválidos ou ilegíveis são preservados para diagnóstico.
- Não há fallback plaintext, `keyrings.alt` ou backend alternativo. Namespaces anteriores não são migrados implicitamente.

## Ativação e sessão nativa

`switch` valida o PAT, usa somente o perfil oficial `supabase` e os comandos públicos `login`, `logout --yes` e `projects list` do Supabase CLI >= 2.109.1. O PAT é passado por `SUPABASE_ACCESS_TOKEN` no ambiente do processo filho e nunca em `argv`.

No macOS e Linux, o executável resolvido deve ser arquivo regular executável, pertencente ao usuário ou root e sem escrita por grupo/outros. No Windows, a verificação exige um arquivo regular e preserva sua identidade canônica entre a inspeção, a abertura e a execução; o Supa.cc não afirma validar proprietário, ACL ou modos POSIX nesse sistema. A verificação pós-login confirma a credencial nativa exata persistida. O Supa.cc não edita diretamente credenciais ou perfis do CLI.

Um `SUPABASE_ACCESS_TOKEN` herdado tem precedência e bloqueia a sincronização. Um fallback `access-token` plaintext é bloqueado sem leitura ou migração. Saída, erros e exceções são sanitizados.

Remover a conta ativa executa `logout --yes`; isso pode remover credenciais auxiliares de projeto gerenciadas pelo próprio Supabase CLI.

## Rollback, recuperação e concorrência

Rollback e recuperação são mutation-aware. O journal sem token registra operação, fase e nomes; um backup seguro permite restaurar a credencial anterior exata quando a fase exige. A trava coordena processos Supa.cc cooperantes, mas não comandos `supabase` externos concorrentes.

## Diagnóstico

`supa.cc doctor` e `supa.cc doctor --json` são não-live por padrão: não abrem token e não realizam operação autenticada. O backend aparece como configurado, mas não verificado; essa execução não testa a disponibilidade do armazenamento de credenciais.

Somente `supa.cc doctor --account <nome> --live` abre uma vez a credencial escolhida e realiza validação online explícita com `projects list`.

## Limites por plataforma

- macOS: o runtime Python é o acessor do Keychain; o Supa.cc não contorna bloqueio nem amplia ACLs.
- Linux: requer D-Bus de usuário e Secret Service desbloqueado; ambientes headless sem ambos falham com orientação segura.
- Windows: aceita somente Windows Credential Manager por `WinVaultKeyring`; `%APPDATA%` guarda apenas metadados sem segredo. O diretório e os arquivos herdam os controles de acesso do diretório `%APPDATA%`; o Supa.cc não cria uma ACL privada e não impõe modos POSIX no Windows.

Para remediação sem expor segredos, consulte [Solução de problemas](troubleshooting.md).
