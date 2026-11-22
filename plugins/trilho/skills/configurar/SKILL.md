---
name: configurar
description: Entrevista o dono e preenche o registro de portões (.claude/trilho.json) do projeto. Use quando o projeto não tem registro, quando o dono pedir "configura os portões" ou "roda a configuração", ou depois do `fullchico-harness install` para fechar o setup.
---

# Configurar os portões do projeto

Você vai entrevistar o dono e escrever `.claude/trilho.json` por ele. O agente **não escreve** esse
arquivo: o hook do trilho barra. Quem escreve é o CLI `fullchico-harness portoes`. Você faz a
pergunta, decide o comando, chama o CLI.

## Como começar

1. **Olhe o projeto antes de perguntar.** Leia `package.json` (scripts `test`, `lint`, `build`),
   `pyproject.toml`, `Cargo.toml`. Veja se há `docs/specs/` com `spec.md` dentro, se o OpenSpec está
   presente (`openspec/`), se há `vitest.config`, `jest.config`, `eslint.config`.
2. **Chame o `grilling`.** Se a skill `grilling` (do plugin `mattpocock-skills`) estiver ligada,
   invoque-a para conduzir a entrevista — ela já sabe como arrancar o que falta sem ser chata.
   Se não estiver disponível, siga com o roteiro curto abaixo.

## Roteiro curto (sem `grilling`)

Faça no máximo **duas perguntas**:

1. **Portão de começo (planejamento).** Pergunte como o projeto garante que uma mudança foi pensada
   antes do código. Três respostas possíveis:
   - *"Temos spec por mudança"* → portão de artefato. Sugira o glob que você viu (ex.
     `docs/specs/*/spec.md`, `openspec/changes/*/spec.md`).
   - *"Rodamos um comando (ex. `openspec validate`)"* → portão de comando.
   - *"Um agente revisa"* → portão de agente.
2. **Portão de fim (qualidade).** Pergunte qual comando valida o projeto no envio
   (ex. `pnpm test`, `pnpm lint && pnpm test`, `cargo test`). Esse é o portão de comando no fim.

Se a resposta para alguma for *"não sei ainda"*, deixe o portão como `@definir` e avise que o dono
precisa rodar `fullchico-harness portoes --definir <nome> "<comando>"` depois.

## Como escrever

Para cada portão combinado, chame uma vez o CLI (sozinho na chamada, sem `&&`):

```bash
fullchico-harness portoes --definir planejamento "openspec validate --strict"
fullchico-harness portoes --definir qualidade "pnpm test"
```

Para portão de artefato, prefira editar o registro pelo CLI (`portoes --registrar <arquivo>`) a
partir de um esboço JSON que você monta e grava num arquivo temporário sob `.claude/`. Nunca tente
`Write` ou `Edit` diretamente em `.claude/trilho.json` — o hook barra.

Ao terminar, rode `portao` e mostre o resultado ao dono. Se algum portão falhar na primeira
verificação, explique o que falta sem reescrever o registro.

## Checklist

- [ ] Li `package.json` (ou equivalente) e `docs/specs/` antes de perguntar.
- [ ] Fiz no máximo duas perguntas.
- [ ] Usei `fullchico-harness portoes --definir` (ou `--registrar`) para gravar, nunca `Write`/`Edit`.
- [ ] Rodei `portao` ao final e mostrei o estado.
