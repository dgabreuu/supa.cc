---
name: supa-cc-cli
description: Use ao operar ou manter fluxos de conta, Keychain, Secret Service, autenticação, diagnóstico ou execução do Supabase CLI no Supa.cc
---

# Supa.cc CLI

## Propósito e limite

Supa.cc gerencia PATs do Supabase localmente no macOS e em Debian/Ubuntu, Arch Linux e Fedora. Os tokens são armazenados pelo Python `keyring` no Keychain do macOS ou no Secret Service do Linux; os arquivos contêm apenas nomes de contas. Uma seleção bem-sucedida sincroniza a sessão oficial por comandos públicos do Supabase CLI.

Use-o para seleção interativa local de contas. Não o use como gerenciador de segredos de CI, em sistemas fora das plataformas suportadas, nem para credenciais que não sejam do Supabase.

## Fluxo canônico de dados

```text
supa.cc add <name>
    hidden PAT prompt
      -> validate format
      -> macOS: Keychain service supa.cc.supabase.accounts.v2
      -> Linux: Secret Service supa.cc.supabase.accounts.v2
      -> accounts.json stores name only

supa.cc switch <name>
    macOS: Keychain read
    Linux: Secret Service read
      -> read-only projects list with PAT in child environment
      -> public login and persisted-session verification
      -> active-account stores name only

supa.cc run -- <supabase arguments>
    active-account name
      -> macOS: Keychain read
      -> Linux: Secret Service read
      -> resolved real Supabase CLI executable
      -> PAT in child SUPABASE_ACCESS_TOKEN only
      -> sanitized streaming output and child exit code
```

`switch` executa `login` e verifica a sessão persistida com `projects list`. Depois do sucesso, `supabase projects list` e outros comandos diretos usam a conta selecionada. `supa.cc run -- ...` permanece opcional para uma execução isolada.

## Comandos

### Adicionar uma conta

```bash
supa.cc add work
```

O PAT é sempre lido de um prompt oculto. Não construa um comando que contenha um PAT. Nomes de conta têm de 1 a 50 letras ASCII, dígitos, underscores ou hífens. O formato oficial aceito é `^(?:sbp_|sbp_oauth_)[0-9a-f]{40}$`: qualquer um dos prefixos seguido de exatamente 40 caracteres hexadecimais minúsculos.

### Listar contas

```bash
supa.cc list
```

Lê apenas `accounts.json`. Não deve abrir o Keychain.

### Selecionar uma conta

```bash
supa.cc switch work
```

A operação lê o item v2, valida online, executa o login oficial, verifica a sessão persistida e grava atomicamente `work` em `active-account`. Um `SUPABASE_ACCESS_TOKEN` herdado faz override e bloqueia a sincronização. Fallback `access-token` plaintext é bloqueado sem leitura do conteúdo.

### Executar o CLI oficial com a conta selecionada

```bash
supa.cc run -- projects list
supa.cc run -- functions list
```

Argumentos após `--` são encaminhados sem adicionar argumento de token. O PAT é colocado somente no `SUPABASE_ACCESS_TOKEN` do processo filho. A saída sanitizada é transmitida em streaming e o código de saída do filho é propagado.

### Diagnosticar

```bash
supa.cc doctor
supa.cc doctor --json
supa.cc doctor --account work --live
```

O modo padrão é totalmente read-only e não abre token. Os modos humano e JSON reportam apenas metadados não secretos:

- launcher do Supa.cc e runtime Python;
- caminhos invocado → real resolvido do Supabase CLI, versão, proveniência e metadados de assinatura disponíveis;
- backend do Keychain e nome canônico do serviço;
- saúde/contagem do índice e estado do nome ativo;
- apenas presença de configurações de autenticação/telemetria no ambiente;
- presença do journal de sincronização e do fallback plaintext, nunca seus conteúdos;
- diagnósticos tipados de ambiente, CLI e permissões.

O modo live exige uma conta. Ele lê esse item do Keychain uma vez e realiza a mesma validação read-only da Management API usada por `switch`.

### Remover uma conta

```bash
supa.cc remove work
supa.cc remove work --yes
```

A remoção da conta ativa executa primeiro `logout --yes` no CLI oficial. O logout pode remover credenciais auxiliares de projeto gerenciadas pelo Supabase CLI; depois o Supa.cc remove seu item v2, índice e seleção local.

### TUI e versão

```bash
supa.cc
supa.cc version
supa.cc --version
```

A TUI expõe add, list, switch e remove com a mesma validação e resultados tipados do CLI direto.

### Navegação e cancelamento na TUI

```text
Home (tela principal)
├── Adicionar conta      → sub-página (formulário → Home)
├── Listar contas        → sub-página lista + Voltar
├── Alternar conta ativa → sub-página lista + Voltar
├── Remover conta        → sub-página lista + Voltar
└── Sair
```

O frame estável (header + body) permanece montado enquanto a Home atua como hub de navegação. A seleção por setas sempre começa na primeira opção. `Voltar` mostra o ponteiro `←`, as demais opções mostram `»`, e as sub-páginas mantêm duas linhas em branco abaixo do seletor.

| Contexto | Ação | Resultado |
| --- | --- | --- |
| Menu Home | Ctrl+C ou `Sair` | Sair com mensagem de despedida |
| Qualquer sub-página | `Voltar` ou Ctrl+C | Voltar à Home sem sair |
| Nome/token em add | Ctrl+C | Voltar à Home |
| Seleção em switch/remove | `Voltar` ou Ctrl+C | Voltar à Home |
| Confirmação de remoção | Não ou Ctrl+C | Voltar à Home |
| Sucesso de add/switch/remove | — | Voltar à Home com feedback |
| Lista de contas | conta, `Voltar` ou Ctrl+C | Voltar à Home |

## Contrato de armazenamento

| Dado | Local | Conteúdo |
| --- | --- | --- |
| PATs | serviço do Keychain do macOS `supa.cc.supabase.accounts.v2` | Um segredo por nome de conta |
| PATs no Linux | Secret Service `supa.cc.supabase.accounts.v2` via D-Bus de usuário | Um segredo por nome de conta |
| Índice de contas | `$XDG_CONFIG_HOME/supa.cc/accounts.json` no Linux, ou `~/.config/supa.cc/accounts.json` | Somente nomes, modo de arquivo `0600` |
| Seleção ativa | `$XDG_CONFIG_HOME/supa.cc/active-account` no Linux, ou `~/.config/supa.cc/active-account` | Somente um nome, modo de arquivo `0600` |
| Diretório de configuração | `$XDG_CONFIG_HOME/supa.cc/` no Linux, ou `~/.config/supa.cc/` | Modo de diretório `0700` |

Leituras do Keychain usam um cache positivo de curta duração no processo. Sobrescrita e exclusão invalidam a entrada. Um item ausente é consultado de novo na próxima leitura. Um índice de contas inválido ou ilegível é preservado e reportado; não é recriado silenciosamente.

O serviço antigo `supa.cc.supabase.accounts` e namespaces predecessores não são lidos, migrados, apagados ou reescritos automaticamente. Re-adicione uma conta pelo prompt oculto ou use um procedimento explícito de migração. `list`, `switch` e `doctor` normais não devem realizar migração.

## Prompts do Keychain no macOS

O acessor visto pelo Keychain é o runtime Python que executa o Supa.cc. No `pipx`, esse runtime vive no ambiente gerenciado pelo pipx. Um caminho de Python alterado, rebuild do ambiente, assinatura de código ou proveniência de instalação pode exigir uma nova autorização.

Prompts repetidos com o mesmo runtime inalterado indicam problema de permissão/controle de acesso do Keychain. Inspecione a identidade não secreta do executável com `doctor`; não despeje o item, não conceda acesso a todos os aplicativos nem afrouxa a ACL. O Supa.cc nunca realiza exclusão de credencial ou reparo de sessão nativa como efeito colateral.

O Supa.cc também não cria arquivos marcadores de ACL ou de correção de credencial durante operações normais de conta.

## Secret Service no Linux

Em Debian/Ubuntu, Arch Linux e Fedora, instale os pré-requisitos e o `pipx` descritos em `docs/installation.md`. A sessão do usuário precisa ter D-Bus funcional e um Secret Service desbloqueado. Em ambiente headless sem eles, o Supa.cc deve falhar com a orientação exibida por `supa.cc doctor`; não habilite `keyrings.alt`, arquivos plaintext ou qualquer backend alternativo para contornar essa falha.

## Classificação de falhas

CLI e TUI usam as mesmas categorias de resultado tipado e retornam status diferente de zero para falhas reais:

| Categoria | Significado |
| --- | --- |
| token missing | Nenhum item v2 existe para o nome selecionado |
| token format invalid | O valor armazenado não tem formato válido de PAT do Supabase |
| token rejected / HTTP 401 | A Management API rejeitou um PAT bem formado; pode estar revogado, expirado ou pertencer à conta errada |
| Keychain permission denied | O macOS negou ou bloqueou o acesso |
| Keychain read failure | A leitura do backend/item falhou por outro motivo |
| network unavailable | A validação não conseguiu alcançar a API |
| CLI missing/incompatible | O executável do Supabase não pôde ser resolvido ou usado |
| environment blocked | Sandbox, caminho de telemetria ou falha de permissão de diretório como `EPERM` |
| profile mismatch | Um contexto persistido/nativo não corresponde ao contexto selecionado |
| native login/verification | O CLI oficial não autenticou ou não confirmou a sessão persistida |
| plaintext fallback blocked | O CLI tentou usar um arquivo de token plaintext |
| sync rollback/pending | A sessão anterior não foi restaurada ou há recuperação pendente |

Erros, exceções, stdout e stderr são sanitizados antes da apresentação. Nunca adicione PATs, headers de autorização, dumps de ambiente ou `repr` com segredos a um diagnóstico.

## Distinção do sandbox do Codex

O Supabase CLI pode tentar gravar estado de telemetria em `~/.supabase`. Um `EPERM` ali quando lançado dentro do sandbox do Codex é restrição de ambiente, não evidência de que o PAT é inválido. Quando a validação live for necessária, execute-a por uma execução aprovada fora do sandbox e ainda assim mantenha o PAT fora da string de comando e da saída.

## Smoke test opt-in do Keychain do macOS

Execute o smoke test do Keychain real somente no macOS e somente após consentimento explícito:

```bash
SUPA_CC_RUN_KEYCHAIN_SMOKE=1 .venv/bin/pytest -q tests/test_macos_keychain_smoke.py
```

O teste cria um item falso e descartável sob o serviço `supa.cc.tests.<uuid>` e a conta `smoke-<uuid>`, verifica o round-trip e o remove em `finally`. Ele nunca acessa o serviço canônico do Supa.cc nem qualquer credencial pertencente ao Supabase CLI. Sem a variável de ambiente opt-in, essa verificação de Keychain real permanece ignorada.

## Regras do operador

1. Nunca coloque um PAT em comando, fixture de teste, log, transcript de prompt ou arquivo.
2. Após `switch`, use `supabase ...` diretamente; `supa.cc run -- ...` é uma alternativa opcional e isolada.
3. Use `doctor` antes de inspecionar o Keychain manualmente; diagnósticos padrão não abrem segredo.
4. Não edite ACLs do Keychain, não exporte itens e não remova credenciais nativas do Supabase CLI.
5. Não apague itens duplicados/legados sem prévia exata e aprovação explícita.
6. Para CI ou servidores, use a injeção de segredos da plataforma em vez do Supa.cc.

O journal de sincronização contém apenas operação, fase e nomes e permite recuperação após interrupção. A trava evita concorrência entre processos Supa.cc cooperantes, mas não coordena comandos `supabase` externos executados ao mesmo tempo.
