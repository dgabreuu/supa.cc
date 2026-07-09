---
name: supa-cc-cli
description: Use when working with the Supa.cc CLI tool for Supabase account management, token storage, keychain operations, or TUI interface interactions
---

# Supa.cc CLI

## Overview

Supa.cc is a local CLI tool for managing multiple Supabase accounts with secure token storage in the macOS Keychain. It provides both an interactive TUI (Text User Interface) and non-interactive commands for account lifecycle management.

## When to Use

- Managing multiple Supabase personal access tokens (PATs) locally
- Switching between Supabase accounts securely
- Storing tokens outside of plain-text files or environment variables
- Integrating Supabase CLI authentication workflows with local account management

When NOT to use:

- For server-side or CI/CD token management (use environment variables instead)
- On non-macOS systems (Keychain dependency)
- For storing non-Supabase tokens

## Architecture & Data Flow

```
User Input
    |
    v
CLI Parser (Click) / TUI (Questionary + Rich)
    |
    v
AccountManager (accounts.py)
    |-- add(name, token) -> validates -> stores
    |-- list() -> reads index (no tokens)
    |-- switch(name) -> activates via Supabase CLI
    |-- remove(name) -> deletes from Keychain
    |
    v
KeychainManager (keychain.py)
    |-- Tokens: macOS Keychain (service: "supa.cc.supabase.accounts")
    |-- Index: ~/.config/supa.cc/accounts.json (names only)
    |
    v
SupabaseConfig (config.py)
    |-- Calls: SUPABASE_ACCESS_TOKEN=<token> supabase login --name <name>
```

**Security Invariant:** Tokens NEVER touch disk in plaintext. Only account names are stored in `accounts.json`. Token retrieval from Keychain happens only when activating an account.

## Commands Reference

### TUI Mode (Interactive)

Launch without arguments to enter interactive mode:

```bash
supa.cc
```

**Behavior:**

- Displays menu with Rich-rendered UI
- Navigation via Questionary prompts (arrow keys or number selection)
- Actions: Add, List, Switch, Remove, Exit
- Cancel any prompt with Esc or Ctrl+C to return/exit gracefully
- Select "Sair" to exit

### version

Show current version and check for updates.

```bash
supa.cc version
```

**Output:**

```
Supa.cc v0.1.0
Você está na versão mais recente.
```

**Update Check Behavior:**

- If run from a git repository, compares local HEAD with origin HEAD
- If not in a git repo or git is unavailable, suggests `brew upgrade supa-cc`, `brew upgrade --fetch-HEAD supa-cc`, or `pipx upgrade supa.cc`
- Network timeout: 5 seconds per git command

### add

Add a new Supabase account.

```bash
supa.cc add <name>
```

For non-interactive automation only:

```bash
supa.cc add <name> --token <token>
```

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Unique account identifier. Rules: 1-50 chars, only `a-z`, `A-Z`, `0-9`, `_`, `-` |
| `--token` | No | Supabase personal access token. If omitted, Click prompts with hidden input. Prefer the hidden prompt for normal interactive use. |

**Security Note:** Passing a token with `--token` can expose it in shell history, process arguments, logs, or agent transcripts. Do not generate commands containing real tokens unless the user explicitly chooses non-interactive automation and accepts that risk.

**Token Validation:**

- Must start with `sbp_`
- Length must be > 10 characters
- Validation happens before Keychain storage

**Account Name Validation:**

- Minimum 1 character, maximum 50 characters
- Allowed characters: letters, numbers, underscore (`_`), hyphen (`-`)
- Unicode characters (e.g., `café`, `日本語`, emoji) are rejected

**Behavior:**

- If `--token` is omitted, prompts for token with hidden input
- Stores token in macOS Keychain under service `supa.cc.supabase.accounts`
- Updates `accounts.json` index
- Duplicate names overwrite the existing token silently
- Returns: `"Conta '{name}' adicionada."`

**Error Cases:**

- Invalid token format -> `"Erro: Token inválido. Deve começar com 'sbp_'"` OR `"Erro: Erro de validação. Verifique os dados fornecidos."` if the error message contains `sbp_` (sanitization to prevent token leakage)
- Invalid account name -> `"Erro: Nome da conta deve ter entre 1 e 50 caracteres."` or `"Erro: Nome da conta contém caracteres inválidos. Use apenas letras, números, hífens e underscores."`

### list

List all registered accounts.

```bash
supa.cc list
```

**Output Format (CLI):**

```
  account_one
  account_two
```

**Output Format (TUI):**

- Rich table with account names only
- No active/inactive status is tracked or displayed

**Behavior:**

- Reads from `accounts.json` index (not Keychain)
- Does NOT retrieve tokens from Keychain
- Returns: `"Nenhuma conta cadastrada."` if empty

**Important:** The active account concept is not implemented. The Supabase CLI tracks its own active session independently.

### switch

Activate an account for Supabase CLI usage.

```bash
supa.cc switch <name>
```

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Account name to activate |

**Behavior:**

- Retrieves token from Keychain
- Sets environment variable `SUPABASE_ACCESS_TOKEN=<token>`
- Executes: `supabase login --name <name>`
- Returns: `"Conta '{name}' ativada."` or `"Falha ao ativar conta '{name}'."`

**Security Note:** The token is intentionally NOT passed via `--token` command-line flag. It is injected via the `SUPABASE_ACCESS_TOKEN` environment variable to avoid exposure in process lists (`ps`), shell history, and process logs.

**Requirements:**

- Supabase CLI must be installed and in PATH
- Account must exist in Keychain (not just in `accounts.json`)
- If Supabase CLI is missing, returns `"Falha ao ativar conta '{name}'."`

### remove

Remove an account.

```bash
supa.cc remove <name>
```

```bash
supa.cc remove <name> --yes    # skip confirmation
```

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Account name to remove |
| `--yes` | No | Skip confirmation prompt (useful for automation) |

**Behavior:**

- Confirmation prompt: `"Remover conta?"` (CLI) or `"Remover conta '{name}'?"` (TUI)
- Deletes token from Keychain
- Removes name from `accounts.json` index
- Returns: `"Conta '{name}' removida."`

**Caveat:** If the account does not exist, the command still prints `"Conta '{name}' removida."`. Verify existence with `list` before removing if this matters.

## Data Models

### Account

```python
@dataclass
class Account:
    name: str
    token: str
```

**Validation:** `validate_token()` checks prefix `sbp_` and minimum length > 10.

**Note:** There is no `is_active` field or `created_at` timestamp in the current implementation. Active state is managed externally by the Supabase CLI, not by Supa.cc.

## File Locations

| File | Path | Contents | Permissions |
|------|------|----------|-------------|
| Account Index | `~/.config/supa.cc/accounts.json` | Account names list | 0o600 |
| Config Directory | `~/.config/supa.cc/` | Parent directory | 0o700 |
| Legacy Supa.cc predecessor index | `~/.config/supakiller/accounts.json` | Auto-migrated on first run | - |
| Legacy `sbc` Index | `~/.config/sbc/accounts.json` | Auto-migrated on first run | - |

**Index JSON Format:**

```json
{
  "accounts": ["personal", "work", "staging"]
}
```

**Index Recovery:** If `accounts.json` is corrupted or contains invalid JSON, Supa.cc automatically recreates it as an empty index on the next read.

## Keychain Integration

- **Service Name:** `supa.cc.supabase.accounts`
- **Legacy Supa.cc predecessor service:** `supakiller.supabase.accounts` (auto-migrated)
- **Legacy `sbc` Service:** `sbc.supabase.accounts` (auto-migrated)
- **Storage:** Each account name maps to one Keychain password entry
- **Access:** Python `keyring` library with macOS backend

## Security Model

1. **Token Isolation:** Tokens only in Keychain, never in files
2. **Index Minimalism:** `accounts.json` contains names only
3. **File Permissions:** 0o600 for index file, 0o700 for directory
4. **Input Hiding:** Token prompts use `hide_input=True` (CLI) or `password()` prompt (TUI)
5. **No Supabase CLI Command-Line Tokens:** During account activation, the token is passed to the Supabase CLI via `SUPABASE_ACCESS_TOKEN`, never through a Supabase CLI command-line flag. For `supa.cc add`, prefer the hidden prompt; `--token` is only for explicit non-interactive automation with exposure risks.
6. **No Logging:** Tokens never logged to stdout/stderr
7. **Error Sanitization:** If an error message contains `sbp_`, it is replaced with a generic validation message to prevent accidental token leakage

## Dependencies

- **Python:** >= 3.9
- **OS:** macOS (Keychain dependency)
- **CLI Tool:** Supabase CLI installed and in PATH
- **Python Packages:** click, questionary, keyring, rich

## Error Handling

| Scenario | Behavior | Output |
|----------|----------|--------|
| Invalid token format | ValidationError before storage | `"Erro: Token inválido. Deve começar com 'sbp_'"` OR `"Erro: Erro de validação. Verifique os dados fornecidos."` |
| Invalid account name | ValidationError before storage | `"Erro: Nome da conta deve ter entre 1 e 50 caracteres."` / `"Erro: Nome da conta contém caracteres inválidos..."` |
| Account not found (switch) | Graceful failure | `"Falha ao ativar conta '{name}'."` |
| Account not found (remove) | Silent/no-op | `"Conta '{name}' removida."` |
| Supabase CLI missing | Activation fails gracefully | `"Falha ao ativar conta '{name}'."` |
| Empty account list (list) | Early return | `"Nenhuma conta cadastrada."` |
| Empty account list (TUI switch/remove) | Early return | `"Nenhuma conta para alternar."` / `"Nenhuma conta para remover."` |
| Keychain access denied | Exception propagated | Python exception |
| Corrupted index JSON | Auto-recovery | Recreates empty index |

## Common Mistakes

- **Reading tokens from `accounts.json`:** File contains only names, never tokens
- **Forgetting to switch:** `supabase` CLI commands use the last activated account
- **Invalid tokens:** Must use Supabase personal access tokens (prefix `sbp_`), not API keys
- **Legacy migration:** Old predecessor and `sbc` tool data auto-migrate on first Supa.cc run
- **Assuming active tracking:** Supa.cc does not track which account is active. Use `supabase status` or similar to verify

## Configuration & Environment

No environment variables required. Configuration is implicit through:

- Keychain service name (hardcoded: `supa.cc.supabase.accounts`)
- Index file path (hardcoded: `~/.config/supa.cc/accounts.json`)
- Supabase CLI binary name (hardcoded: `supabase`)

## Migration from Legacy Namespaces

On first run (specifically when reading the index and the new index does not exist), Supa.cc automatically:

1. Checks for `~/.config/supakiller/accounts.json`, then `~/.config/sbc/accounts.json`
2. Migrates account names to the new path
3. Transfers tokens from `supakiller.supabase.accounts` or `sbc.supabase.accounts` Keychain services
4. Uses `supa.cc.supabase.accounts` for all future operations

If the new index already exists, migration is skipped.

## TUI Navigation

```
Supa.cc
├── Adicionar conta
├── Listar contas
├── Alternar conta ativa
├── Remover conta
└── Sair
```

**Navigation:** Arrow keys or number selection
**Input:** Questionary prompts with validation
**Exit:** Select "Sair" or press Esc/Ctrl+C at the main menu

### Cancellation Behavior

| Prompt | Cancel Action | Result |
|--------|--------------|--------|
| Main menu | Esc / Ctrl+C | Exit with goodbye message |
| Add name | Esc / Ctrl+C | Warning: `"Nome da conta é obrigatório."` |
| Add token | Esc / Ctrl+C | Warning: `"Token de acesso é obrigatório."` |
| Switch selection | Esc / Ctrl+C | Warning: `"Alternância de conta cancelada."` |
| Remove selection | Esc / Ctrl+C | Warning: `"Remoção de conta cancelada."` |
| Remove confirmation | No / Esc | Warning: `"Remoção de conta cancelada."` |

## LLM Usage Guidelines

When invoking Supa.cc on behalf of a user:

1. **Never construct commands with real tokens visible in the command string.** Prefer `supa.cc add <name>` so the user can type the token in Click's hidden prompt. Use `--token` only for explicit non-interactive automation, and never echo, log, persist, or include the real value in generated files or transcripts.
2. **For automation, use `--yes` with `remove`.** Example: `supa.cc remove work --yes`
3. **Do not rely on `list` to determine the active account.** Supa.cc does not track this. Use `supabase status` if needed.
4. **Validate account names before calling `add`.** If the name contains spaces, unicode, or special characters, it will fail.
5. **Token format check:** If the user provides a token for automation, ensure it starts with `sbp_` and is longer than 10 characters before invoking `add`.
6. **Migration is automatic.** Do not manually move files from legacy config directories unless troubleshooting.
7. **For CI/server use, do not use Supa.cc.** Use environment variables directly instead.
