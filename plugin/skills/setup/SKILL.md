---
name: setup
description: Configura o harness neste projeto pela primeira vez. Instala os arquivos gerenciados, os portões de push e os plugins declarados.
disable-model-invocation: true
---

# Configurar o harness no projeto

Rode os passos em ordem. Não pule a confirmação do dono onde ela é pedida.

## 1. Pré-requisitos

Confira que existem na máquina: `git`, `python3`, `docker` e `rtk`. Relate o que
faltar e continue: `docker` só é preciso para o ambiente por worktree, e `rtk`
só para a compressão de saída.

O diretório precisa ser um repositório git. Se não for, pare e avise.

## 2. Sincronizar

Leia a versão em `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` e rode, com
`v` na frente da versão:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/sync" "<raiz do projeto>" --version v<versão>
```

Se o comando sair com código 1, ele lista arquivos que já existiam com outro
conteúdo e não altera nada. Mostre a lista ao dono, mostre o que cada arquivo
tem hoje, e só rode de novo com `--force` se ele confirmar. Conteúdo do projeto
que vivia nesses arquivos (hooks, permissões, servidores MCP) deve ir antes para
`harness.d/settings.json`, que é somado na geração.

## 3. Preencher o que é do projeto

Leia o repositório e proponha, mostrando ao dono antes de gravar:

- no `AGENTS.md`, abaixo da região gerenciada: **Produto** (o que é, para quem)
  e **Onde olhar** (os arquivos que explicam o domínio). Não copie stack nem
  comandos para lá: eles vivem nos arquivos de build e no `harness.conf`.
- no `harness.conf`: `PROJECT`, `INSTALL_CMD`, `VALIDATE_PUSH` e
  `VALIDATE_MERGE`, tirados dos scripts que o projeto já tem.

O `harness.conf` é negado a agentes. Entregue o conteúdo proposto para o dono
colar, em vez de tentar editar.

## 4. Instalar os plugins declarados

Para cada entrada de `enabledPlugins` em `.claude/settings.json`:

```bash
claude plugin install <plugin>@<marketplace> --scope project
```

## 5. Fechar

Liste o que foi criado, lembre o dono de commitar os arquivos gerados e de rodar
`/reload-plugins`, e diga que daqui em diante esses arquivos mudam só por
`.harness/update <tag>`.
