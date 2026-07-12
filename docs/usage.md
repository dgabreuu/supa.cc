# Uso

## Primeiro uso pela TUI

Crie um Personal Access Token na [página oficial de tokens do Supabase](https://supabase.com/dashboard/account/tokens). Não coloque o PAT em comandos, arquivos, logs ou relatórios.

Abra a interface interativa:

```bash
supa.cc
```

1. Escolha **Adicionar conta**, informe um nome local e forneça o PAT no prompt oculto. O nome deve ter de 1 a 50 letras ASCII, números, underscores ou hífens (`[a-zA-Z0-9_-]{1,50}`).
2. Escolha **Alternar conta** e selecione a conta cadastrada.
3. Verifique a sessão ativada:

```bash
supabase projects list
```

A ativação valida o PAT, sincroniza o perfil oficial `supabase`, verifica a credencial nativa persistida e somente então grava a conta ativa. Se houver falha, siga a [solução de problemas](troubleshooting.md); para garantias e limites, consulte [segurança](security.md).

## Fluxos

### Gerenciar contas

```bash
supa.cc add <nome>
supa.cc list
supa.cc switch <nome>
supa.cc remove <nome>
supa.cc remove <nome> --yes
```

`add` solicita o PAT em prompt oculto. `list` mostra somente nomes. `switch` valida e ativa a conta. `remove` pede confirmação, exceto com `--yes`; remover a conta ativa também encerra a sessão oficial associada.

### Usar a conta ativa

Depois de `switch`, use o Supabase CLI normalmente. Para uma execução isolada opcional, sem alterar argumentos:

```bash
supa.cc run -- projects list
```

### Diagnosticar

```bash
supa.cc doctor
supa.cc doctor --json
supa.cc doctor --account <nome> --live
```

Os dois primeiros comandos são não-live e não abrem token. `--live` exige `--account` e autoriza a leitura e validação online da credencial escolhida. Consulte a [remediação por plataforma](troubleshooting.md#macos) antes de inspecionar manualmente qualquer armazenamento.

## Comandos

| Comando | Finalidade |
| --- | --- |
| `supa.cc` | Abrir a TUI |
| `supa.cc add <nome>` | Adicionar ou atualizar uma conta |
| `supa.cc list` | Listar nomes cadastrados |
| `supa.cc switch <nome>` | Validar e ativar uma conta |
| `supa.cc remove <nome> [--yes]` | Remover uma conta |
| `supa.cc run -- <argumentos>` | Executar o Supabase CLI com a conta ativa |
| `supa.cc doctor [--json]` | Gerar diagnóstico local não-live |
| `supa.cc doctor --account <nome> --live` | Autorizar diagnóstico autenticado |
| `supa.cc --version` | Mostrar a versão |
| `supa.cc version` | Mostrar a versão e também verificar atualizações |

Instalação, atualização e desinstalação ficam no [guia de instalação](installation.md).
