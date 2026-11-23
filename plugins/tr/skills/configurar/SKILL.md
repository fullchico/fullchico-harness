---
name: configurar
description: Entrevista o dono e preenche o registro de portões (.claude/trilho.json) do projeto. Use quando o projeto não tem registro, quando o dono pedir "configura os portões" ou "roda a configuração", ou depois do `fullchico-harness install` para fechar o setup.
---

# Configurar os portões do projeto

Você vai entrevistar o dono e propor o registro `.claude/trilho.json`. O agente **não escreve** esse
arquivo: o hook do trilho barra, e com sandbox o arquivo também é protegido para escrita. Quem grava é
o CLI `fullchico-harness portoes`, rodado pelo dono no terminal dele. Você faz a pergunta, decide os
portões, monta o esboço e entrega ao dono os comandos prontos.

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

## Como entregar ao dono

1. **Portão novo** (nome que ainda não está no registro): monte um esboço JSON
   `{"<nome>": {"momento": "fim", "assina": "comando", "comando": "...", "descricao": "..."}}` e grave-o
   **fora do repositório** (a pasta temporária da sessão). Arquivo novo dentro do repositório suja a
   árvore, e carimbo de fim não assina com a árvore suja.
2. **Comando de portão que já existe**: `fullchico-harness portoes --definir <nome> "<comando>"`.
3. Escreva para o dono os comandos exatos, um por linha, para ele rodar no terminal, fora da sessão:

   ```bash
   npx @fullchico/harness portoes --definir qualidade "pnpm lint && pnpm test"
   npx @fullchico/harness portoes --registrar /caminho/do/esboco.json
   ```

   Se quiser tentar você mesmo, rode o CLI uma vez. Se ele responder "Sem permissão para gravar", não
   insista nem procure outro caminho: é a proteção funcionando. Entregue os comandos e espere.
4. Depois que o dono gravar, diga para ele fazer o commit de `.claude/trilho.json` (e do
   `.claude/settings.json`, se mudou), porque carimbo de fim só assina com a árvore limpa.

Nunca tente `Write` ou `Edit` em `.claude/trilho.json`: o hook barra.

Um portão de comando roda exatamente o comando do registro, por `portao <nome>`, sem variável na
frente. Se a checagem precisa de ambiente (porta, URL, navegador), ela lê de um arquivo que o projeto já
carrega (por exemplo `.env`), não da linha de comando.

Ao terminar, rode `portao` e mostre o resultado ao dono. Se algum portão falhar na primeira
verificação, explique o que falta sem reescrever o registro.

## Checklist

- [ ] Li `package.json` (ou equivalente) e `docs/specs/` antes de perguntar.
- [ ] Fiz no máximo duas perguntas.
- [ ] Esboço fora do repositório; comandos `--definir`/`--registrar` entregues ao dono, nunca `Write`/`Edit`.
- [ ] Lembrei o commit do registro antes de carimbar.
- [ ] Rodei `portao` ao final e mostrei o estado.
