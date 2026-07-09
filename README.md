# Supa.cc

Supa.cc é uma ferramenta de linha de comando para gerenciar múltiplas contas do Supabase localmente no macOS. Ela guarda tokens no Keychain do macOS, mantém apenas um índice local com nomes de contas e integra com o Supabase CLI para alternar a conta ativa sem repetir login manual.

## Por que foi criado

O projeto nasceu de uma necessidade prática: alternar com frequência entre contas do Supabase CLI sem repetir autenticação, troca de token e comandos manuais. Supa.cc simplifica esse fluxo criando um gerenciador local de contas, com uma TUI para uso interativo e comandos diretos para automação.

## Recursos

- Gerenciamento local de múltiplas contas Supabase.
- Armazenamento seguro de tokens no Keychain do macOS via `keyring`.
- Índice local com nomes de contas apenas, sem tokens em texto puro.
- Integração com o Supabase CLI usando `SUPABASE_ACCESS_TOKEN` ao alternar contas.
- TUI no terminal com Rich e Questionary.
- Comandos CLI para scripts e automações.
- Migração de dados legados dos antigos namespaces `supakiller` e `sbc`, quando encontrados.
- `SKILL.md` incluído para orientar agentes e LLMs que precisem operar este projeto.

## Requisitos

- macOS, pois o armazenamento seguro usa o Keychain.
- Python 3.9 ou superior.
- Supabase CLI instalado e disponível como `supabase` no `PATH`.
- Um Personal Access Token (PAT) do Supabase para cada conta. PATs válidos devem começar com `sbp_`.

## Instalação

A instalação recomendada para uso local é via Homebrew:

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supa-cc
```

Para instalar diretamente do branch `main` durante desenvolvimento:

```bash
brew install --HEAD supa-cc
```

Depois da instalação, o comando fica disponível como:

```bash
supa.cc
```

Para uso global isolado com `pipx`:

```bash
pipx install "git+https://github.com/dgabreuu/supa.cc.git"
```

Para instalar a partir de um checkout local de desenvolvimento:

```bash
NEW_REPO_URL="https://github.com/dgabreuu/supa.cc.git"
git clone "$NEW_REPO_URL" supa.cc
cd supa.cc
python3 -m pip install -e ".[dev]"
```

Veja detalhes em `docs/installation.md`.

## Uso rápido

Abra a interface interativa:

```bash
supa.cc
```

Adicione uma conta pelo prompt interativo. O Click pedirá o PAT com entrada oculta, sem exibir o token no terminal:

```bash
supa.cc add work
```

Para uso normal, prefira o prompt interativo. Informe apenas um PAT do Supabase válido, começando com `sbp_`, e nunca publique tokens reais em comandos, logs ou documentação.

Liste contas cadastradas e alterne a conta ativa:

```bash
supa.cc list
supa.cc switch work
```

## Comandos disponíveis

| Comando | Descrição |
| --- | --- |
| `supa.cc` | Abre a TUI interativa. |
| `supa.cc add <name> --token <token>` | Cadastra ou atualiza uma conta local. Disponível para automação; para uso normal, prefira `supa.cc add <name>` e digite o token no prompt oculto. Passar tokens em comandos pode expô-los no histórico do shell, logs ou listas de processos. |
| `supa.cc list` | Lista os nomes das contas cadastradas. |
| `supa.cc switch <name>` | Ativa a conta informada no Supabase CLI. |
| `supa.cc remove <name>` | Remove uma conta após confirmação interativa. |
| `supa.cc remove <name> --yes` | Remove uma conta sem pedir confirmação, útil para scripts. |
| `supa.cc version` | Mostra a versão do Supa.cc e tenta verificar atualizações. |
| `supa.cc --version` | Mostra a versão via opção padrão do CLI. |

## Como a alternância funciona

Cada conta cadastrada tem um nome local e um token armazenado no Keychain. Ao executar `supa.cc switch <name>`, Supa.cc recupera o token da conta escolhida e chama o Supabase CLI passando o valor pela variável de ambiente `SUPABASE_ACCESS_TOKEN`.

Esse modelo evita colocar o token como argumento de processo ou em histórico de shell. O arquivo `~/.config/supa.cc/accounts.json` existe apenas para listar nomes de contas rapidamente; ele não contém tokens.

## Modelo de segurança

- Tokens não são gravados em texto puro no disco.
- Tokens ficam no Keychain do macOS, associados ao serviço local do Supa.cc.
- O índice em `~/.config/supa.cc/accounts.json` guarda somente nomes de contas.
- Exemplos públicos devem usar placeholders em prosa; nunca use tokens reais em README, issues, logs, testes ou exemplos.
- Tokens devem ser PATs do Supabase e devem começar com `sbp_`.
- Antes de publicar o repositório, revise o histórico, arquivos ignorados, logs, capturas de tela e fixtures para garantir que não há segredos.
- Não publique conteúdo de `~/.config/supa.cc`, arquivos `.env`, saídas de terminal com segredos ou exports do Keychain.

## Migração legada

Supa.cc inclui suporte para migrar dados locais legados dos namespaces antigos `supakiller` e `sbc`. Quando não encontra um índice novo do Supa.cc, ele procura os índices legados e tenta copiar os tokens correspondentes dos serviços legados no Keychain para o serviço atual. A migração preserva a regra principal: tokens continuam no Keychain e o índice local contém apenas nomes.

## Uso por agentes e LLMs

Este repositório inclui um `SKILL.md` com instruções para agentes/LLMs que precisem usar ou manter o projeto. Use esse arquivo como referência operacional para automações assistidas por IA, sem colocar tokens reais no prompt, no contexto ou em arquivos gerados.

## Desenvolvimento e testes

Instale as dependências de desenvolvimento em modo editável:

```bash
python3 -m pip install -e ".[dev]"
```

Rode a suíte de testes:

```bash
pytest
```

Comandos úteis durante validação local:

```bash
supa.cc --version
supa.cc version
supa.cc list
```

## Publicação

O repositório público oficial é `https://github.com/dgabreuu/supa.cc.git`.

Antes de publicar uma release, revise histórico, arquivos ignorados, logs, caches, ambientes virtuais, fixtures e saídas de terminal para confirmar que não há tokens, URLs privadas, nomes pessoais, emails privados ou referências a remotes antigos. O checklist de publicação e atualização da fórmula Homebrew está em `docs/release.md`.

## Licença

MIT. Veja `LICENSE`. A licença permite baixar, usar, modificar e redistribuir o projeto, mantendo os avisos de copyright e permissão.
