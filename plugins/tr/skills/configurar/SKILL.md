---
name: configurar
description: Diagnostica Claude Code e Codex, analisa o projeto e entrevista o dono com grill-me para propor trilhos e portões de entrada e saída (.claude/trilho.json).
---

# Configurar os portões do projeto

Você vai diagnosticar os ambientes, analisar o projeto, entrevistar o dono com `/tr:grill-me`
e propor o registro `.claude/trilho.json`. O agente **não escreve** esse
arquivo: o hook do trilho barra, e com sandbox o arquivo também é protegido para escrita. Quem grava é
o CLI `fullchico-harness portoes`, rodado pelo dono no terminal dele. Você faz a pergunta, decide os
portões, monta o esboço e entrega ao dono os comandos prontos.

## 1. Diagnosticar os ambientes

Detecte os ambientes instalados para este projeto. Se Claude Code estiver instalado, rode
`claude doctor` na raiz do projeto. Se Codex estiver instalado, rode `codex doctor --json`.
São diagnósticos de saúde dos CLIs, não validadores do código. Resuma erros, avisos e dicas;
não cole credenciais, caminhos pessoais nem o JSON bruto no esboço de portões. Se o doctor
não estiver disponível ou falhar, registre a limitação e continue a análise do projeto.
Não aplique reparos sugeridos pelos doctors sem decisão do dono.

## 2. Analisar o projeto

Rode `fullchico-harness portoes --analisar` (ou o script instalado no projeto) e leia o
registro existente. Confira também `package.json`, `pyproject.toml`, `Cargo.toml`, scripts
de CI, testes, configuração de lint/typecheck, documentação de specs e ferramentas de
deploy. Para cada sugestão, anote a evidência concreta e confira se o comando realmente
existe. Preserve os portões já definidos pelo dono.

## 3. Entrevistar com o fluxo de Matt Pocock

Chame `/tr:grill-me`, incluída neste plugin a partir do fluxo `grilling` de Matt Pocock.
Mostre primeiro o que os doctors e o projeto revelaram. Explore as decisões em rodadas,
com recomendação por pergunta, até o dono confirmar o desenho. A entrevista define:

- quais portões de **entrada** impedem começar código: spec, validação da spec, revisão
  de arquitetura, aprovação ou outro artefato/comando/agente verificável;
- quais portões de **saída** validam a entrega: testes, lint, typecheck, build, e2e, revisão,
  segurança, acessibilidade, deploy ou outros checks realmente usados no projeto;
- quais são sempre obrigatórios e quais dependem do tipo de entrega.

Portões de entrada específicos de task usam `sempre: false` no registro e são nomeados na
linha `Entrada:` do ticket. Os de saída específicos usam a linha `Portões:`. Exemplo:
uma task de frontend pede `Entrada: design` e `Portões: acessibilidade`; uma de backend
usa `Entrada: nenhum` e `Portões: api`. Os portões sem `sempre: false` continuam globais.

Não limite a configuração aos nomes `processo`, `qualidade` e `bugs`: eles são apenas
propostas padrão. Pode criar qualquer quantidade de portões de entrada e saída. Um
aviso do doctor é uma melhoria de ambiente; só vira portão se houver uma checagem de
projeto verificável e o dono a escolher. Sem comando conhecido, deixe `@definir` e
explique como defini-lo depois.

## Como entregar ao dono

1. **Portão novo** (nome que ainda não está no registro): monte um esboço JSON. Exemplo
   de entrada: `{"planejamento": {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/spec.md"}}`.
   Exemplo de saída: `{"e2e": {"momento": "fim", "assina": "comando", "comando": "pnpm test:e2e", "sempre": false}}`.
   Use um campo que corresponda ao modo de assinatura e grave o esboço
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
4. Depois que o dono gravar, diga para ele revisar `.claude/trilho.json` e
   `.claude/settings.json`, se mudou. O carimbo final valida o estado atual do projeto.

Nunca tente `Write` ou `Edit` em `.claude/trilho.json`: o hook barra.

Um portão de comando roda exatamente o comando do registro, por `portao <nome>`, sem variável na
frente. Se a checagem precisa de ambiente (porta, URL, navegador), ela lê de um arquivo que o projeto já
carrega (por exemplo `.env`), não da linha de comando.

Ao terminar, rode `portao` e mostre o resultado ao dono. Se algum portão falhar na primeira
verificação, explique o que falta sem reescrever o registro.

## Checklist

- [ ] Resumi o doctor de cada ambiente disponível e analisei o projeto antes de perguntar.
- [ ] Usei `/tr:grill-me` para decidir os portões de entrada e saída com o dono.
- [ ] Cada portão proposto tem evidência, momento, modo de assinatura e verificador concreto.
- [ ] Esboço fora do repositório; comandos `--definir`/`--registrar` entregues ao dono, nunca `Write`/`Edit`.
- [ ] Lembrei de revisar o registro antes de carimbar.
- [ ] Rodei `portao` ao final e mostrei o estado.
