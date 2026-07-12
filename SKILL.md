---
name: supa-cc-cli
description: Use ao operar ou manter autenticação, armazenamento nativo, diagnóstico ou integração com o Supabase CLI no Supa.cc
---

# Supa.cc CLI

Use [Instalação](docs/installation.md) para o ciclo de instalação, [Uso](docs/usage.md) para fluxos e comandos, [Segurança](docs/security.md) para o contrato interno e [Solução de problemas](docs/troubleshooting.md) para remediação.

## Invariantes para agentes

- Nunca coloque PATs reais ou exemplos com formato de credencial em comandos, código, fixtures, arquivos, logs, erros, documentação, prompts ou transcripts. O PAT é solicitado por entrada oculta e aceito somente por `^(?:sbp_|sbp_oauth_)[0-9a-f]{40}$`.
- No macOS, use somente o Keychain; no Linux, somente Secret Service com D-Bus de usuário e coleção desbloqueada; no Windows, somente Windows Credential Manager pelo backend exato `WinVaultKeyring`.
- Nunca habilite fallback plaintext, `keyrings.alt` ou outro backend. Ambientes Linux headless sem os serviços exigidos devem falhar com orientação segura.
- Nenhum arquivo local contém PAT. Índice, seleção, journal e locks contêm somente nomes ou metadados; backups temporários de rollback permanecem no armazenamento nativo.
- Passe o PAT ao Supabase CLI somente por `SUPABASE_ACCESS_TOKEN` no ambiente do processo filho, nunca em `argv`. Um `SUPABASE_ACCESS_TOKEN` herdado bloqueia a sincronização.
- Use somente o perfil oficial `supabase` e o Supabase CLI >= 2.109.1. Verifique a confiança do executável e a credencial nativa exata; não edite diretamente credenciais ou perfis do CLI.
- Rollback e recuperação devem ser mutation-aware. A trava coordena processos Supa.cc cooperantes, não comandos `supabase` externos concorrentes.
- `doctor` e `doctor --json` são não-live, não abrem token e não comprovam disponibilidade do backend. Somente `doctor --account <nome> --live` autoriza leitura e validação autenticada da conta escolhida.
- Não afrouxe ACLs, exporte itens, despeje ambientes ou credenciais, nem apague itens legados, journals, locks ou credenciais sem estado prévio exato e aprovação explícita.
- No macOS e Linux, aceite apenas executável regular, executável, pertencente ao usuário ou root e sem escrita por grupo/outros. No Windows, preserve a identidade canônica entre inspeção, abertura e execução sem alegar validação de ACL ou modos POSIX.

Identidades canônicas: `macOS: Keychain service supa.cc.supabase.accounts.v2`; `Linux: Secret Service supa.cc.supabase.accounts.v2`; `Windows: Windows Credential Manager (WinVaultKeyring) service supa.cc.supabase.accounts.v2`.
