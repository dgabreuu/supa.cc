```text
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
```

# Supa.cc

Supa.cc é uma ferramenta de linha de comando para gerenciar múltiplas contas do Supabase no macOS e em Debian/Ubuntu, Arch Linux e Fedora. Derivados dessas distribuições podem funcionar em caráter best-effort. Os Personal Access Tokens (PATs) ficam no Keychain do macOS ou no Secret Service do Linux; nenhum arquivo local do Supa.cc contém PAT.

## Requisitos

- macOS, Debian/Ubuntu, Arch Linux ou Fedora.
- Python 3.9 ou superior.
- Supabase CLI >= 2.109.1 disponível como `supabase` no `PATH`, instalada pelas [instruções oficiais](https://supabase.com/docs/guides/local-development/cli/getting-started).
- No Linux, D-Bus de usuário em execução e Secret Service desbloqueado. Em sessões headless sem esses serviços, o Supa.cc falha com orientação segura, sem armazenar tokens em texto puro.
- Um PAT no formato oficial: prefixo `sbp_` ou `sbp_oauth_`, seguido por exatamente 40 caracteres hexadecimais minúsculos (`0-9`, `a-f`).

## Instalação

### Homebrew (somente macOS)

No macOS, o método recomendado é o Homebrew:

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supa-cc
```

Para instalar a versão atual do branch `main` durante desenvolvimento:

```bash
brew install --HEAD supa-cc
```

### Linux (somente pipx)

Em Linux, instale os pré-requisitos do seu sistema e use `pipx`; os comandos exatos estão em [docs/installation.md](docs/installation.md). `pipx` também pode instalar em um ambiente Python isolado no macOS:

```bash
pipx install "git+https://github.com/dgabreuu/supa.cc.git"
```

Consulte [docs/installation.md](docs/installation.md) para instalação local, atualização e reinstalação segura.

## Uso rápido

Adicione uma conta. O PAT é solicitado sempre por um prompt com entrada oculta; não há opção de linha de comando para fornecê-lo:

```bash
supa.cc add work
```

O formato aceito é `^(?:sbp_|sbp_oauth_)[0-9a-f]{40}$`; nenhum exemplo usa um token real.

Selecione a conta e execute comandos autenticados:

```bash
supa.cc switch work
supabase projects list
# opcional: execução isolada com a conta ativa
supa.cc run -- projects list
```

`switch` valida o PAT com uma operação read-only da Management API, autentica o perfil oficial `supabase` e verifica exatamente a credencial nativa persistida pelo CLI oficial antes de gravar a seleção. Após sucesso, `supabase ...` direto usa a conta selecionada. `supa.cc run -- <argumentos>` continua disponível como execução isolada opcional.

Um `SUPABASE_ACCESS_TOKEN` herdado faz override da sessão persistida e bloqueia a sincronização até ser removido do ambiente. O Supa.cc também bloqueia qualquer fallback `access-token` plaintext criado ou encontrado pela Supabase CLI, sem ler ou migrar seu conteúdo.

## Comandos

| Comando | Descrição |
| --- | --- |
| `supa.cc` | Abre a TUI interativa. |
| `supa.cc add <nome>` | Solicita o PAT em prompt oculto e cadastra ou atualiza a conta. |
| `supa.cc list` | Lista somente os nomes cadastrados. |
| `supa.cc switch <nome>` | Valida o PAT e sincroniza a sessão nativa antes de gravar a conta ativa. |
| `supa.cc run -- <argumentos>` | Executa o Supabase CLI com o PAT da conta ativa somente no ambiente do processo filho. |
| `supa.cc doctor` | Diagnóstico local read-only que não abre nenhum token. |
| `supa.cc doctor --json` | Emite o mesmo diagnóstico em JSON, sem segredos. |
| `supa.cc doctor --account <nome> --live` | Lê o token uma vez e realiza uma validação online autorizada. |
| `supa.cc remove <nome>` | Remove a conta após confirmação. |
| `supa.cc remove <nome> --yes` | Remove a conta sem confirmação interativa. |
| `supa.cc version` / `supa.cc --version` | Mostra a versão. |

`run` passa os argumentos literalmente para o executável resolvido do Supabase, transmite a saída já sanitizada e devolve o código de saída do processo filho. O PAT nunca entra em `argv`, em arquivos de configuração ou em mensagens.

## Diagnóstico

O modo padrão de `doctor` é seguro para coleta de suporte: não consulta o armazenamento de credenciais e não executa uma operação autenticada. A saída humana ou JSON informa, sem valores secretos:

Nesse modo, o backend aparece como configurado, mas não verificado: o comando não testa a disponibilidade do D-Bus nem do armazenamento de credenciais e não afirma que estejam disponíveis ou desbloqueados.

- launcher do `supa.cc`, runtime Python e caminho invocado → caminho real do Supabase CLI;
- versões, proveniência e informações de assinatura disponíveis;
- backend e serviço do armazenamento de credenciais;
- estado do índice e da seleção ativa;
- presença, nunca o valor, de variáveis sensíveis e configuração de telemetria;
- presença do journal de recuperação e do fallback plaintext, sem abrir seus conteúdos;
- falhas classificadas de CLI, ambiente e permissões.

Use `--live` somente com `--account`. Esse modo abre uma única vez o item escolhido no armazenamento de credenciais e valida o PAT por `projects list` com `SUPABASE_ACCESS_TOKEN` no ambiente do processo filho.

Os diagnósticos distinguem token ausente, formato inválido, PAT rejeitado/HTTP 401, leitura ou permissão do armazenamento de credenciais, rede, CLI ausente ou incompatível, ambiente sem permissão (`EPERM`) e divergência de perfil. Um `EPERM` ao acessar `~/.supabase` dentro do sandbox do Codex é uma falha ambiental independente da validade do PAT; quando necessário, faça a validação live em uma execução aprovada fora do sandbox.

## Modelo de segurança

- O serviço canônico é `supa.cc.supabase.accounts.v2`.
- Nenhum arquivo local contém PAT. O estado inclui `accounts.json`, `active-account`, `session-sync.json`, `.session-sync.lock` e `.accounts.json.lock`; journals e locks guardam apenas metadados sem segredo.
- Backups de credencial usados por rollback ficam exclusivamente no Keychain ou Secret Service, sob identidade reservada, e nunca no índice ou journal.
- Tokens recuperados podem permanecer apenas em cache positivo de curta duração no processo atual. Ausências não são memorizadas.
- Um índice inválido ou ilegível é preservado para diagnóstico; não é substituído automaticamente por um índice vazio.
- Namespaces anteriores são ignorados. Migração exige uma ação explícita ou adicionar novamente cada conta pelo prompt oculto.
- A sincronização usa somente o perfil oficial e os comandos públicos `login`, `logout --yes` e `projects list` do Supabase CLI >= 2.109.1; não edita diretamente credenciais ou perfis dele.
- Antes de executar, o binário resolvido precisa ser um arquivo executável confiável, pertencente ao usuário ou root, sem escrita por grupo/outros; a execução usa o mesmo arquivo aberto para evitar troca de caminho.
- O Supa.cc não cria marcadores de ACL ou de correção da credencial nativa.
- O Supa.cc não instala ACL ampla, não contorna um Keychain bloqueado e não exporta segredos em texto puro.
- No Linux, o único backend aceito é o Secret Service acessado pelo D-Bus de usuário. Um serviço indisponível ou bloqueado, inclusive em ambiente headless, falha com orientação de correção; o Supa.cc não usa arquivos plaintext nem o fallback `keyrings.alt`.
- O diretório de configuração no Linux segue `XDG_CONFIG_HOME` quando definido, ou `~/.config/supa.cc` caso contrário.
- Erros, `stdout`, `stderr` e exceções são sanitizados antes de serem exibidos.
- Remover a conta ativa invoca o logout oficial. Esse comando pode remover credenciais auxiliares de projeto gerenciadas pelo próprio Supabase CLI.
- Rollback e recuperação são mutation-aware: um journal sem token registra a fase, e backups seguros permitem restaurar a credencial anterior exata após interrupção. A trava cobre processos Supa.cc cooperantes, mas não coordena execuções concorrentes externas do comando `supabase`.

No macOS, quem acessa o item do Keychain é o runtime Python que executa o Supa.cc. Em uma instalação `pipx`, atualizar o ambiente, mudar o caminho do Python ou alterar a assinatura do executável pode justificar uma nova autorização única. Prompts repetidos com o mesmo runtime indicam permissão/controle de acesso inconsistente; use `doctor` para identificar os caminhos envolvidos, sem exportar o token ou afrouxar a ACL.

## Desenvolvimento

```bash
git clone https://github.com/dgabreuu/supa.cc.git supa.cc
cd supa.cc
python3 -m pip install -e ".[dev]"
pytest
```

### Smoke test do Keychain do macOS

Com consentimento explícito para acessar o Keychain real, execute o smoke test opt-in somente no macOS:

```bash
SUPA_CC_RUN_KEYCHAIN_SMOKE=1 .venv/bin/pytest -q tests/test_macos_keychain_smoke.py
```

O teste cria uma credencial falsa e descartável com serviço `supa.cc.tests.<uuid>` e conta `smoke-<uuid>`, verifica o round-trip e a remove em um bloco `finally`. Ele nunca usa o serviço canônico do Supa.cc nem lê, altera ou remove credenciais do Supabase CLI.

## Licença

MIT. Veja `LICENSE`.
