# Design do workflow de validação Homebrew

## Objetivo

Validar a fórmula Homebrew da versão 0.3.0 em um runner macOS real antes de
publicá-la no tap mantido pela branch `main`.

## Contexto

O GitHub Release e o pacote PyPI 0.3.0 já foram publicados e verificados. O
ambiente local é Linux e não possui Homebrew, portanto não atende ao gate que
exige auditoria, instalação a partir do código-fonte e teste da fórmula em
macOS.

## Abordagem

Adicionar `.github/workflows/homebrew.yml` como workflow manual e somente
leitura. O workflow será iniciado exclusivamente por `workflow_dispatch`,
executará em `macos-latest` e terá apenas `contents: read`.

O workflow não editará arquivos, criará commits, fará push nem publicará uma
release. A fórmula será atualizada e revisada no checkout normal; o runner
macOS servirá apenas como validação reproduzível do commit enviado.

## Fluxo

1. Baixar o tarball real da tag `v0.3.0` e calcular seu SHA256.
2. Atualizar a URL e o checksum de `Formula/supa-cc.rb`.
3. Atualizar os recursos Python a partir das dependências publicadas.
4. Executar localmente os testes que validam os assets de publicação.
5. Commitar a fórmula, o workflow e seus testes sem publicar automaticamente.
6. Enviar o commit para `main` e aguardar a CI normal.
7. Disparar manualmente o workflow Homebrew no SHA exato.
8. No macOS, executar auditoria estrita, instalação a partir do código-fonte,
   comandos de versão e teste da fórmula.
9. Considerar a fórmula publicada somente após o workflow ficar verde e uma
   instalação limpa pelo tap confirmar a versão 0.3.0.

## Segurança

- Permissões globais vazias e somente `contents: read` no job.
- Nenhum secret, token, credencial persistente ou permissão OIDC.
- Nenhum comando de commit, push, release ou upload de pacote.
- Nenhuma leitura de cofres nativos durante os testes da fórmula.
- A fórmula continuará usando exclusivamente o tarball imutável da tag
  `v0.3.0` e checksums reais.

## Testes

`tests/test_publication_assets.py` verificará que o workflow:

- usa apenas `workflow_dispatch`;
- executa em `macos-latest`;
- restringe permissões a `contents: read`;
- contém auditoria, instalação por source, verificação de versão e `brew test`;
- não contém secrets, permissões de escrita, push, criação de release ou
  publicação de artefatos.

O workflow validará `brew audit --strict`, `brew install --build-from-source`,
`supa.cc --version`, `supa.cc version` e `brew test`.

## Tratamento de falhas

Qualquer falha de recursos, checksum, auditoria, instalação, versão ou teste
interrompe a publicação Homebrew. O workflow não tenta corrigir nem publicar a
fórmula automaticamente. A causa deve ser corrigida em novo commit e validada
novamente.

## Critérios de conclusão

- O workflow manual é somente leitura e passa nos testes de configuração.
- A fórmula referencia `v0.3.0` com checksum e recursos reais.
- A CI normal fica verde no commit da fórmula.
- O workflow Homebrew fica verde no mesmo SHA em `macos-latest`.
- Uma instalação limpa pelo tap reporta 0.3.0 e passa em `brew test`.
