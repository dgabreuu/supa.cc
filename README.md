```text
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
```

# Supa.cc

Supa.cc é uma ferramenta de linha de comando para gerenciar múltiplas contas do Supabase no macOS e em Debian/Ubuntu, Arch Linux e Fedora. Os Personal Access Tokens (PATs) ficam no Keychain do macOS ou no Secret Service do Linux; os arquivos locais contêm somente nomes de contas.

## Requisitos

- macOS, Debian/Ubuntu, Arch Linux ou Fedora.
- Python 3.9 ou superior.
- Supabase CLI disponível como `supabase` no `PATH`.
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
supa.cc run -- projects list
```

`switch` valida o PAT com uma operação read-only da Management API e grava somente o nome selecionado em `~/.config/supa.cc/active-account`. Ele não faz login, não cria perfil e não altera a credencial nativa do Supabase CLI. Por isso, use `supa.cc run -- <argumentos do supabase>` para os comandos que devem usar a conta selecionada; executar `supabase ...` diretamente continua usando a sessão própria do CLI oficial.

## Comandos

| Comando | Descrição |
| --- | --- |
| `supa.cc` | Abre a TUI interativa. |
| `supa.cc add <nome>` | Solicita o PAT em prompt oculto e cadastra ou atualiza a conta. |
| `supa.cc list` | Lista somente os nomes cadastrados. |
| `supa.cc switch <nome>` | Valida o PAT e grava o nome da conta ativa do Supa.cc. |
| `supa.cc run -- <argumentos>` | Executa o Supabase CLI com o PAT da conta ativa somente no ambiente do processo filho. |
| `supa.cc doctor` | Diagnóstico local read-only que não abre nenhum token. |
| `supa.cc doctor --json` | Emite o mesmo diagnóstico em JSON, sem segredos. |
| `supa.cc doctor --account <nome> --live` | Lê o token uma vez e realiza uma validação online autorizada. |
| `supa.cc remove <nome>` | Remove a conta após confirmação. |
| `supa.cc remove <nome> --yes` | Remove a conta sem confirmação interativa. |
| `supa.cc version` / `supa.cc --version` | Mostra a versão. |

`run` passa os argumentos literalmente para o executável resolvido do Supabase, transmite a saída já sanitizada e devolve o código de saída do processo filho. O PAT nunca entra em `argv`, em arquivos de configuração ou em mensagens.

## Diagnóstico

O modo padrão de `doctor` é seguro para coleta de suporte: não consulta o Keychain e não executa uma operação autenticada. A saída humana ou JSON informa, sem valores secretos:

- launcher do `supa.cc`, runtime Python e caminho invocado → caminho real do Supabase CLI;
- versões, proveniência e informações de assinatura disponíveis;
- backend e serviço do Keychain;
- estado do índice e da seleção ativa;
- presença, nunca o valor, de variáveis sensíveis e configuração de telemetria;
- falhas classificadas de CLI, ambiente e permissões.

Use `--live` somente com `--account`. Esse modo abre uma única vez o item escolhido no Keychain e valida o PAT por `projects list` com `SUPABASE_ACCESS_TOKEN` no ambiente do processo filho.

Os diagnósticos distinguem token ausente, formato inválido, PAT rejeitado/HTTP 401, leitura ou permissão do Keychain, rede, CLI ausente ou incompatível, ambiente sem permissão (`EPERM`) e divergência de perfil. Um `EPERM` ao acessar `~/.supabase` dentro do sandbox do Codex é uma falha ambiental independente da validade do PAT; quando necessário, faça a validação live em uma execução aprovada fora do sandbox.

## Modelo de segurança

- O serviço canônico é `supa.cc.supabase.accounts.v2`.
- `~/.config/supa.cc/accounts.json` guarda somente nomes; `~/.config/supa.cc/active-account` guarda somente o nome selecionado.
- Tokens recuperados podem permanecer apenas em cache positivo de curta duração no processo atual. Ausências não são memorizadas.
- Um índice inválido ou ilegível é preservado para diagnóstico; não é substituído automaticamente por um índice vazio.
- Namespaces anteriores são ignorados. Migração exige uma ação explícita ou adicionar novamente cada conta pelo prompt oculto.
- O Supa.cc não modifica, apaga nem recria credenciais ou perfis pertencentes ao Supabase CLI.
- O Supa.cc não cria marcadores de ACL ou de correção da credencial nativa.
- O Supa.cc não instala ACL ampla, não contorna um Keychain bloqueado e não exporta segredos em texto puro.
- No Linux, o único backend aceito é o Secret Service acessado pelo D-Bus de usuário. Um serviço indisponível ou bloqueado, inclusive em ambiente headless, falha com orientação de correção; o Supa.cc não usa arquivos plaintext nem o fallback `keyrings.alt`.
- O diretório de configuração no Linux segue `XDG_CONFIG_HOME` quando definido, ou `~/.config/supa.cc` caso contrário.
- Erros, `stdout`, `stderr` e exceções são sanitizados antes de serem exibidos.

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
