# Changelog

Todas as mudanças relevantes deste projeto serão documentadas neste arquivo.
O formato segue, de maneira simplificada, o Keep a Changelog.

## [0.3.0] - 2026-07-12

### Adicionado

- Suporte a Debian/Ubuntu, Arch Linux e Fedora com Secret Service, além de suporte ao Windows Credential Manager.
- Diagnóstico seguro com `doctor`, saída JSON e validação autenticada explícita por `--account <nome> --live`.
- Sincronização da sessão nativa do perfil oficial `supabase` ao ativar ou remover a conta ativa.

### Alterado

- A troca de conta passa a verificar a sessão nativa efetiva da Supabase CLI e a manter estado de coordenação sem segredo.
- O armazenamento de credenciais e os caminhos de estado agora são selecionados de acordo com macOS, Linux ou Windows.

### Segurança

- Backends de credenciais são restritos ao Keychain, Secret Service ou `WinVaultKeyring`, sem fallback plaintext.
- No macOS e Linux, o executável da Supabase CLI é validado por tipo, execução, proprietário e modos; no Windows, o arquivo regular e a identidade do caminho são verificados após a abertura e imediatamente antes da criação do processo, sem alegar execução por descritor, validação de ACL ou modos POSIX.
- A credencial nativa e operações de recuperação são verificadas antes da conclusão de mudanças sensíveis.
- Travas e metadados de recuperação tornam a atualização da sessão resistente a interrupções entre etapas.

### Migração da 0.2.0

- No macOS, a 0.3.0 preserva o serviço de credenciais `supa.cc.supabase.accounts.v2` e o índice `~/.config/supa.cc/accounts.json` usados pela 0.2.0.
- Linux e Windows são canais novos na 0.3.0 e, portanto, não possuem estado da 0.2.0 para migrar nesses sistemas.

[0.3.0]: https://github.com/dgabreuu/supa.cc/compare/v0.2.0...v0.3.0
