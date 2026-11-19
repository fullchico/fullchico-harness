# FullChico Harness: desenho

Data: 2026-11-19. Estado: aprovado pelo dono. Orquestração própria do harness, ofício dos autores.

Legenda: **[dono]** é decisão dita pelo dono. **[autor]** é decisão de quem escreveu, ainda
não confirmada. O que não tem marca é descrição.

## 1. Intenção

Hoje cada projeto do dono recebe a configuração de agentes de IA à mão, e cada cópia
diverge. Este repositório passa a ser a fonte única dessa configuração: o ambiente de
desenvolvimento do dono, que orquestra skills de vários autores, impõe guardrails e mantém
a memória do projeto. Os projetos consomem o harness como dependência, não editam o que
veio dele, e recebem melhorias por atualização de versão. **[dono]**

Nenhum projeto existente restringe o desenho. **[dono]** O `~/www/movacrm` é fonte de código
já testado a aproveitar (guard de serviços, portas por worktree) e régua de maturidade.
Regra que só existe lá por limitação daquele projeto não entra.

## 2. Os cinco focos **[dono]**

1. **Processo com qualidade e entrega.** Da entrevista ao PR com o mínimo de paradas.
2. **Memória que não envelhece.** Código, glossário e mapa valem igual, porque tudo é
   ancorado no git.
3. **Paralelismo.** O trabalho é um grafo e roda em paralelo.
4. **Balanceamento de custo.** O grátis antes do pago, modelo certo por papel, medição.
5. **Loop contínuo.** A entrega se corrige sozinha, e cada entrega melhora o harness.

## 3. Objetivos, não-objetivos e o que seria fracasso

**Objetivos**

- Um padrão único de fluxo, commit, revisão, segurança e orquestração. **[dono]**
- A orquestração é do harness; o ofício vem das skills dos autores, usadas como eles
  publicam. **[dono]**
- Tudo com escopo de projeto: quem não declarou o harness não recebe nada. **[dono]**
- Projeto não mexe na configuração gerenciada; o `CLAUDE.local.md` é livre. **[dono]**
- Configuração inicial montada por IA a partir de template. **[dono]**
- Ambiente por worktree em shell, com Orca principal e Conductor secundário chamando os
  mesmos scripts. **[dono]**
- Repositório público, de uso livre. **[dono]**

**Não-objetivos**

- Windows. CI remoto. Skills de domínio de um produto.
- Migrar projetos existentes: a adoção vem depois e não molda o desenho.
- OpenSpec e o plugin do Elephant-Goldfish: avaliados e removidos pelo dono (seção 5.5).

**Seria fracasso mesmo funcionando**

- O projeto guardar cópias editáveis dos padrões, que voltam a divergir.
- Um agente aprovar o próprio trabalho, editar configuração gerenciada ou subir serviço fora
  dos scripts do harness.
- Memória em prosa que ninguém confere contra o código.
- A lógica de ambiente existir em três versões (Orca, Conductor, terminal).
- Uma atualização apagar em silêncio conteúdo que é do projeto.
- Uma limitação de um projeto virar regra para todos.

## 4. Arquitetura

### 4.1 Três canais de entrega

| Canal | O que carrega | No projeto | Como atualiza |
|---|---|---|---|
| Plugin do Claude Code | agentes, skills do harness, mapa de skills | só a declaração em `.claude/settings.json` | tag fixada |
| Pasta `.harness/` | hooks de guardrail, scripts de ambiente, validação, memória, git hooks | copiada, travada, com manifesto | `.harness/update <tag>` |
| Arquivos gerados | `AGENTS.md`, `CLAUDE.md`, `settings.json`, `docs/agents/`, `orca.yaml`, espelho do Codex | na raiz, gerados do template | o mesmo `update` |

`.harness/` existe porque Orca, Conductor, git, terminal e Codex rodam fora do plugin do
Claude e precisam de caminho estável dentro do repositório. Os hooks de guardrail ficam nela
para haver uma cópia só, usada por Claude e Codex. **[autor]**

A versão do harness num projeto é uma tag deste repositório, a mesma no `ref` do marketplace
em `.claude/settings.json` e em `.harness/MANIFEST`. **[autor]**

### 4.2 Este repositório **[autor]**

```
.claude-plugin/marketplace.json
plugin/
  .claude-plugin/plugin.json
  agents/        orquestrador, revisor-spec, seguranca, revisor
  skills/        setup, update, entregar (com referências de spec, tickets e despacho),
                 aprender, dream
  map.json       mapa de skills de terceiros
  hooks/         hooks.json
  payload/       conteúdo copiado para .harness/ do projeto
  templates/     AGENTS.md, CLAUDE.md, settings.json, docs/agents, orca.yaml, conductor, codex
  bin/sync       copia payload e regenera os gerados
tests/
LICENSE          MIT
```

Público no GitHub. Endereço assumido: `FullChico/fullchico-harness`. Licença MIT. Ambos
**[autor]**. Nada de segredo, caminho pessoal ou nome de projeto do dono entra no plugin, no
payload ou nos templates.

## 5. Ciclo de entrega

### 5.1 Papéis

Modelo de papéis tirado do Elephant-Goldfish, usado como princípio, sem instalar o plugin
dele. **[dono]**

- **Elefante:** o agente raiz da sessão (`orquestrador`). Carrega o contexto, desenha com o
  dono, dispara e monta tudo. **[dono]**
- **Goldfish:** todo subagente, de contexto novo, sem a conversa. Implementadores e
  revisores. Entregam o trabalho; não validam o próprio resultado. **[dono]**
- **Dono:** aprova a spec e faz o merge.

Três regras, impostas pelo harness: **[autor]**

1. **O documento é a única interface.** O pedido a um goldfish do harness só aponta: caminho
   da spec, do ticket, intervalo do diff e lista de leitura. Sem narrativa nem opinião. Um
   hook antes da ferramenta de subagente confere o formato para `revisor-spec`, `seguranca`
   e `revisor`, e nega o que fugir.
2. **Lacuna se corrige no documento.** Se um implementador não constrói só com spec e
   ticket, o elefante corrige a spec, não explica por fora.
3. **Revisão no mesmo contexto não é revisão.** Quem escreveu não revisa, e o elefante não
   revisa o que orquestrou.

"Contexto novo" é sobre a conversa, não sobre evidência: goldfish lê código, o mapa, o
glossário e o histórico do git.

### 5.2 Um comando, duas paradas **[dono]**

O dono roda `/harness:entregar`. O comando é a orquestração inteira, escrita no harness. Ele
começa pela entrevista e vai até o PR aberto. O dono só é chamado em:

- **a entrevista**, que é conversa;
- **a aprovação da spec**;
- limite de rodadas estourado (seção 5.4).

Depois o dono faz o merge.

| Passo | Peça | De quem | Quem executa | Saída |
|---|---|---|---|---|
| 1. Entrevistar | `grilling` e `domain-modeling` | autor | elefante + dono | entendimento; `GLOSSARY.md` e ADRs |
| 2. Especificar | referência de spec do `entregar` | harness | elefante | `docs/specs/<slug>/spec.md` |
| 3. Revisar a spec | `revisor-spec` | harness | goldfish | achados; **o dono resolve e aprova** |
| 4. Fatiar | referência de tickets do `entregar` | harness | elefante | um arquivo por ticket, com o que o bloqueia |
| 5. Validar o grafo | script, grátis | harness | — | sem ciclo, sem referência quebrada |
| 6. Implementar | despacho do `entregar`; `tdd` | harness; autor | implementadores, em paralelo, um worktree cada | código e testes em commits de contexto |
| 7. Integrar | despacho do `entregar` | harness | elefante | tudo na branch de integração |
| 8. Checar | `.harness/validate`, grátis | harness | — | lint, tipos, testes, segredo, manifesto |
| 9. Revisar | `seguranca` e `revisor` | harness | goldfish, em paralelo | dois vereditos |
| 10. Enviar e abrir PR | `pr` | autor | elefante | push liberado pelos vereditos; PR |

Toda `feat` passa por todos os passos, inclusive o fatiamento: o grafo é o padrão. Bug entra
por `diagnosing-bugs`, do autor, no lugar dos passos 1 a 5.

**Por que a orquestração é própria.** Testado em 2026-11-19: o plugin do autor reserva ao
usuário exatamente as skills que orquestram (`grill-with-docs`, `to-spec`, `to-tickets`,
`implement`, `implement-spec`), e a plataforma proíbe o agente de reproduzi-las por outros
meios. As de ofício (`tdd`, `grilling`, `domain-modeling`, `code-review`, `pr`,
`diagnosing-bugs`, `prototype`, `research`) o agente invoca livremente. Daí a divisão:
**a orquestração é do harness, o ofício é dos autores.** As referências de spec, de tickets
e de despacho são escritas pelo harness, sem copiar o texto do autor.

A spec segue as seções: problema, solução, histórias, decisões de implementação, decisões de
teste com os pontos de costura, fora de escopo. Tickets são fatias verticais, um arquivo
cada, com `Blocked by:` e `Status:` no topo.

### 5.3 Modelos e custo **[dono]** definiu os níveis; escalada e ordem são **[autor]**

| Papel | Modelo |
|---|---|
| elefante | Opus |
| `revisor-spec` | o mesmo do elefante |
| implementadores, `seguranca`, `revisor` | Sonnet |
| trabalho bruto: mapa, verificação de memória, resumo de log, `dream` | Haiku |

- A tabela é teto: sessão em Sonnet mantém Sonnet no lugar do Opus.
- **Escalada:** ticket reprovado duas vezes sobe para Opus, só aquele ticket.
- **O grátis antes do pago:** revisor de IA só roda sobre código que passou no
  `.harness/validate`. Não existe agente de qualidade: quando o script falha, o log vai para
  o implementador corrigir.
- **Dieta de contexto:** cada goldfish recebe a fatia do mapa da área do ticket, em vez de
  explorar o repositório. `rtk` comprime a saída de git e de testes; `ponytail` segura o
  tamanho do código.
- **Teto de paralelismo:** `MAX_PARALLEL` no `harness.conf`, padrão 3.
- **Medição:** tokens por fase de cada entrega, registrados no ciclo de aprendizado.

Cada agente declara o modelo em `model:`. O `settings.json` gerado não define
`CLAUDE_CODE_SUBAGENT_MODEL`, que valeria para todos e anularia o Haiku.

Precedência entre ferramentas: `tdd` manda nos testes, nos pontos de costura combinados na
spec; `ponytail` manda no tamanho do código de produção.

### 5.4 Correção em loop

Reprovou na checagem ou na revisão: o elefante devolve o achado ao implementador da parte
afetada (pedido de formato fixo, apontando o achado), e os passos 8 e 9 rodam de novo.
Limite de 3 rodadas por entrega; estourou, o elefante para e relata ao dono o que travou.

### 5.5 Por que só as skills do Matt Pocock **[dono]**

Medido no movacrm: o ciclo do OpenSpec carrega cerca de 18.600 tokens de instrução por
mudança; o do Elephant-Goldfish, cerca de 14.000 mais personas; `grill-with-docs` mais
`to-spec`, cerca de 1.300. O Elephant-Goldfish não cobre implementação. Empilhar dois
sistemas de especificação não se justifica.

O que os dois removidos tinham e o Matt não tem é documento vivo. O harness responde a isso
com a memória ancorada em git (seção 7), não com outro sistema de specs.

A spec é uma por mudança (formato na seção 5.2). Entra no mesmo PR que o código. Depois do merge é histórico e fica
fora da lista de leitura dos agentes.

## 6. Portões e guardrails

### 6.1 Dois portões, no push **[dono]**

| Portão | Revisor | O que assina |
|---|---|---|
| segurança | `seguranca` | o commit no topo da branch enviada |
| revisão de código | `revisor` | o mesmo commit |

Commit local é livre. Nada sai da máquina sem os dois vereditos. O portão é um hook de git
(`pre-push`): vale para Claude, Codex e o dono no terminal, e cobre o que chegou por merge.
Entrou commit novo, o hash muda e a validação é refeita.

O `revisor` revisa direto o diff contra a spec, em dois eixos (padrões e aderência), sem
relatório intermediário do elefante. Também confere: **[autor]**

- se o tipo do commit bate com a mudança (uma `feat` rotulada `fix` escaparia da trava);
- termo de domínio novo fora do glossário, ou sinônimo de termo existente.

A skill `code-review` do autor fica disponível para uso à mão; não entra no portão porque
dispara subagentes, e subagente não dispara subagente.

### 6.2 Trava de spec **[dono]**

Branch com commit `feat` em relação à branch padrão precisa ter um arquivo de spec no mesmo
intervalo. `fix`, `docs`, `chore`, `refactor` e `test` passam sem spec.

### 6.3 Bloqueio técnico da autoaprovação **[dono]** pediu; mecanismo **[autor]**

**A barreira é o sandbox do Bash, imposto pelo sistema operacional.** Duas revisões
adversariais mostraram que inspecionar o texto do comando não segura: um script de oito
linhas que monta o caminho em tempo de execução gravava as duas aprovações. Com o sandbox, a
escrita é negada para qualquer processo que o agente dispare, seja Python, heredoc ou shell.
Testado em sessão real, no checkout principal e num worktree.

1. O revisor termina com `VEREDITO: APPROVED|REJECTED`, `RESUMO:` e o hash do commit revisado.
2. Um hook de fim de subagente (`gate-stamp`) grava a aprovação só se o subagente for
   `seguranca` ou `revisor`, o veredito for `APPROVED`, houver resumo e o hash for o topo
   atual. Hooks rodam fora do sandbox, então conseguem gravar.
3. O estado fica em `~/.claude/harness/<id do repositório>/`, um diretório por repositório,
   igual para todos os worktrees. O sandbox protege `~/.claude` por padrão em toda sessão.
   Não fica dentro do `.git`: de um worktree, a sessão consegue gravar no `.git` do checkout
   principal. O caminho é resolvido pelo sistema, não pela variável `HOME`.
4. As configurações geradas ligam o sandbox, impedem desligá-lo numa chamada
   (`allowUnsandboxedCommands: false`) e negam escrita em `.harness`, `harness.conf`,
   `harness.d`, `CLAUDE.md` e `docs/agents`. `.git/config`, `.git/hooks` e os `settings` do
   Claude já são protegidos pelo sandbox por padrão.
5. `.harness/approve` é o carimbo manual do dono. Exige terminal na entrada, e de dentro do
   sandbox não consegue gravar.
6. A aprovação de um revisor guarda a base do intervalo que ele leu. O push só a aceita se
   for a mesma base que o remoto informa.

O `pre-push` não confia em referência local: consulta o remoto na hora para saber a branch
padrão e o que já está lá. `git update-ref` não libera tag nem esvazia a trava de spec.

Limites conhecidos:

- **Sem sandbox, não há barreira.** Numa sessão com o sandbox desligado, ou num agente que
  não o tenha, os portões protegem contra descuido, não contra um agente que insiste.
- O sandbox não funciona no Windows nativo, e o Docker não roda dentro dele: os comandos de
  ambiente do harness entram na lista de excluídos (plano de ambiente).
- A trava contra desligar o sandbox foi respeitada estando só no arquivo do projeto, em modo
  sem interface. Em sessão interativa ainda não foi conferido; se não valer, a chave vai para
  as configurações do usuário.
- Os testes do harness gravam em `~/.claude/harness/` e não rodam de dentro do sandbox.

A aprovação registra o subagente e a transcrição, para auditoria.

### 6.4 Hooks

| Hook | Evento | Comportamento |
|---|---|---|
| `gate-stamp` | fim de subagente | grava aprovação (6.3) |
| `dispatch-guard` | antes da ferramenta de subagente | confere o pedido de formato fixo (5.1), exige que cubra a branch inteira e registra a base |
| `service-guard` | antes de Bash | nega os argumentos que pulam os hooks de git (`--no-verify`, `core.hooksPath`); no plano de ambiente, também serviço por comando solto e porta atribuída à mão |
| `managed-guard` | antes de Edit/Write | nega alterar a região gerenciada do `AGENTS.md`, e escrever no diretório do git ou no estado do harness |
| `rtk hook claude` | antes de Bash | compressão de saída, do próprio rtk |
| `git-hooks/commit-msg` | git | formato do commit, sem assinatura de IA |
| `git-hooks/pre-push` | git | consulta o remoto; dois vereditos, trava de spec, grafo, manifesto, `validate --profile push` |

Hooks de agente usam o diretório atual que vem na chamada, não a pasta onde a sessão
começou, para agir no worktree certo. Exceção dentro de hook vira negação, nunca liberação.

## 7. Memória ancorada em git **[dono]**

Regra única: todo item de memória guarda o commit em que foi escrito e os caminhos que
descreve. Saber se envelheceu é uma pergunta ao git, sem IA e sem custo:
`git diff --quiet <commit> HEAD -- <caminhos>`.

| Memória | Onde mora | Como nasce | Quando o código muda |
|---|---|---|---|
| Histórico de decisões | os commits | commits de contexto (7.1) | não envelhece: descreve aquela mudança |
| Mapa do código | memória local do Claude | gerado do código, por Haiku | regenerado só nos caminhos tocados |
| Glossário | `GLOSSARY.md`, versionado | `grill-with-docs` | termo cuja âncora sumiu é sinalizado |
| ADRs | `docs/adr/`, versionado | `grill-with-docs` | ADR cuja área mudou muito é sinalizada ao dono |
| Notas do `dream` | memória local do Claude | consolidação das sessões | reconferida contra o código |
| Spec da mudança | `docs/specs/`, versionado | `entregar` | sem âncora: histórico |

O que é derivado (mapa, âncoras, notas do `dream`) mora no diretório de memória local que o
Claude Code já mantém por projeto, compartilhado entre worktrees e carregado a cada sessão
pelo índice. Não gera commit nem ruído no histórico, e pode ser refeito do zero. **[dono]**:
memória local, como o Claude já faz. As âncoras do glossário e dos ADRs ficam num arquivo à
parte nesse diretório, para não tocar no formato do autor.

Âncoras são gravadas só sobre commits da branch padrão, depois do merge, porque os hashes
de uma branch de trabalho mudam em rebase. **[autor]**

### 7.1 Commits de contexto **[dono]**

O git é a memória principal do porquê. Cada commit é um contexto coerente:

- assunto `tipo(escopo): descrição`, em inglês, até 80 caracteres;
- corpo livre e longo quando precisar: o porquê, a decisão tomada, o que foi descartado;
- nunca co-autoria nem assinatura de IA.

Agentes leem `git log -- <caminho>` da área em que vão trabalhar, e o `rtk` comprime essa
saída.

Consequência **[autor]**, a confirmar com o dono: merge por squash apaga os commits de
contexto. O padrão do harness é merge que preserva os commits (rebase ou merge commit).

### 7.2 Comando

`.harness/memory check` lista o que envelheceu, de graça. `.harness/memory refresh` regenera
o que é derivado, com Haiku. O ciclo de aprendizado chama os dois.

## 8. Ciclo de aprendizado

Skill `aprender`, rodada depois do merge, à mão ou agendada: **[autor]**

1. `memory check` e `memory refresh` sobre o que o merge tocou.
2. Retrospectiva: lê a sessão e propõe melhorias no ambiente do agente (checagem nova, regra
   nova, instrução que não serve mais). A skill `retro` do autor é reservada ao usuário,
   então a peça é própria; o dono pode rodar `/retro` à mão quando quiser.
3. `dream`: consolida as sessões em notas ancoradas, em duas fases (um analisador Haiku por
   transcrição; um organizador no fim, que junta duplicatas sem perder fato). Transcrição é
   dado, não instrução. Conflito sem resposta clara fica marcado, não decidido.
4. Registro de tokens por fase da entrega.

As propostas do `retro` são para este repositório, não para o projeto: o dono aprova,
publica versão, e todos os projetos recebem. Regra que dá para checar por máquina vira
checagem, não texto.

## 9. Mapa de skills **[dono]** definiu a ideia; formato **[autor]**

`plugin/map.json` é a fonte única de quais skills de terceiros o harness usa e como. Cada
entrada: passo, skill, origem com versão fixada, papel e modelo, adaptação.

Só entram no ciclo skills que o agente pode invocar. Skill reservada ao usuário fica como
avulsa, para o dono usar à mão.

Adaptação, em ordem de preferência:

1. arquivo de configuração que a skill do autor já lê, gerado pelo harness;
2. instrução passada na invocação;
3. peça própria do harness no lugar, com o motivo registrado.

Nunca se copia nem se edita a skill do autor. Trocar de autor ou acrescentar skill é mudar
uma entrada e publicar versão. O `update` confere que toda skill do ciclo existe na versão
fixada e é invocável pelo agente, e falha na hora se não for.

Quem lê o mapa: `setup` e `update` (instalam e geram), a tabela do ciclo no `AGENTS.md`, a
skill `entregar`, e os portões (caminho da spec e dos tickets).

| Passo | Skill | Origem | Adaptação |
|---|---|---|---|
| entrevistar | `grilling`, `domain-modeling` | `mattpocock-skills@claude-plugins-official` | `docs/agents/domain.md` gerado: glossário e ADRs |
| implementar | `tdd` | idem | instrução: testes nos pontos de costura da spec |
| bug | `diagnosing-bugs` | idem | nenhuma |
| abrir PR | `pr` | idem | instrução: corpo em português, sem assinatura de IA |
| sempre ligado | ponytail | `ponytail@ponytail`, marketplace `DietrichGebert/ponytail` | nenhuma |
| sempre ligado | rtk | binário na máquina mais hook no `settings.json` gerado | nenhuma |
| avulsas, o agente invoca | `code-review`, `prototype`, `research`, `codebase-design` | `mattpocock-skills` | nenhuma |
| avulsas, só o dono | `grill-with-docs`, `to-spec`, `to-tickets`, `implement-spec`, `retro`, `wayfinder`, `handoff` | idem | nenhuma |

Peças próprias do harness e o motivo: especificar, fatiar e despachar (o autor as reserva ao
usuário); `revisor-spec` (o autor não tem revisão de spec); `seguranca` e `revisor` (o
portão precisa de um agente com nome, e subagente não dispara subagente).

`docs/agents/` é gerado pelo harness para as skills do autor que leem configuração de lá. O
instalador do autor (`/setup-matt-pocock-skills`) não é rodado.

## 10. O projeto

### 10.1 Setup

Skill `setup`, uma vez por projeto. Uma IA lê o repositório e preenche o template. Confere
os pré-requisitos da máquina (`git`, `docker`, `python3`, `jq`, `rtk`). Nunca sobrescreve
arquivo existente sem mostrar a diferença e pedir confirmação.

```
.claude/settings.json     marketplaces, plugins, agente da sessão, hooks, negações
AGENTS.md                 fonte única para Claude e Codex
CLAUDE.md                 aponta para AGENTS.md
CLAUDE.local.md           fora do git, livre
docs/agents/              arquivos que as skills do autor leem
.codex/, .agents/skills/  espelho gerado
.harness/                 scripts travados, MANIFEST
harness.conf, harness.d/  do projeto
orca.yaml                 setup e archive chamando .harness/
.conductor/settings.toml  só se o dono pedir
```

Plugin declarado não instala sozinho: `claude plugin install <plugin>@<marketplace> --scope
project` uma vez por máquina, feito pelo `setup` e repetido pelo `orca.yaml`. Git hooks são
apontados por `core.hooksPath` para `.harness/git-hooks`; projeto com husky precisa
removê-lo.

### 10.2 Três classes de arquivo **[autor]**, a partir da regra do dono

| Classe | Arquivos | Quem altera |
|---|---|---|
| Gerenciado | `.harness/`, `docs/agents/`, `.claude/settings.json`, `CLAUDE.md`, `.codex/`, `.agents/skills/` gerado, `orca.yaml`, `.conductor/`, região marcada do `AGENTS.md` | só o `update` |
| Do projeto, só o dono | `harness.conf`, `harness.d/`, `.claude/settings.local.json` | o dono, à mão |
| Livre | `CLAUDE.local.md`, código, skills e agentes do projeto, região do projeto no `AGENTS.md` | qualquer um |

`harness.conf` e `harness.d/` são negados ao agente porque controlam os guardrails. O
`.claude/settings.local.json` entra na mesma classe **[autor]**, a confirmar com o dono: por ele
um agente desligaria todos os hooks. Achado da revisão final do plano 1.

Proteção em quatro camadas: o sandbox do Bash, que nega a escrita por qualquer comando;
negação nativa por caminho (`permissions.deny` com `Edit(...)`) para as ferramentas de
edição; `managed-guard` para a região marcada do `AGENTS.md`; e o manifesto, conferido no
push, que pega edição manual do dono.

### 10.3 AGENTS.md

Duas regiões num arquivo, porque o Codex não segue importações. Limite de 32 KiB.

- **Gerenciada**, entre `<!-- harness:begin -->` e `<!-- harness:end -->`: ciclo, papéis,
  portões, convenções. Sai do template e do mapa.
- **Do projeto:** Produto, Onde olhar, e só o que não dá para checar por máquina. Stack e
  comandos não são copiados para cá: apontam para o `harness.conf` e os arquivos de build.

### 10.4 harness.conf e harness.d/

```sh
PROJECT=meuapp
SERVICES="web api postgres redis"     # a ordem define o deslocamento da porta
COMPOSE_FILE=docker-compose.dev.yml
INSTALL_CMD="pnpm install"
AFTER_UP="pnpm db:migrate"
DEV_CMD="pnpm dev"
VALIDATE_PUSH="pnpm test"
VALIDATE_MERGE="pnpm test && pnpm build"
MAX_PARALLEL=3
ENV_DATABASE_URL='postgresql://app:app@localhost:${POSTGRES_PORT}/app'
```

`harness.d/settings.json` e `harness.d/codex.toml` são fragmentos somados na geração: hooks,
permissões e servidores MCP que são só do projeto. As negações e os hooks do harness sempre
entram, e o fragmento não os remove.

## 11. Pasta .harness/

Shell puro. **[dono]**

| Script | Função |
|---|---|
| `worktree-env` | deriva projeto Docker e bloco de portas do worktree e grava só essas chaves no `.env` |
| `up` | `worktree-env`, sobe o compose em segundo plano, espera ficar saudável, roda `AFTER_UP`. Só infra |
| `dev` | roda `DEV_CMD`. Primeiro plano para o dono; `--background` com PID e log para o agente |
| `down` | encerra o `dev` em segundo plano e para os containers; mantém dados |
| `destroy` | remove containers, volumes e imagens do worktree; recusa rodar no checkout principal |
| `validate` | manifesto, formato de commit, credencial, grafo, e o perfil `push` ou `merge` do projeto |
| `memory` | `check` e `refresh` (seção 7) |
| `approve` | carimbo manual do dono |
| `update` | seção 12 |

`worktree-env` aproveita o script e os testes do movacrm: base por `CONDUCTOR_PORT` quando
existir, senão `20000 + hash(caminho) % 2000 * 10`, com busca do próximo bloco livre.

**O ambiente é por spec. [dono]** Uma spec implementada por vários subagentes em paralelo,
cada um num worktree, usa um ambiente só; outra spec em paralelo tem outro, com outras
portas. A spec de um worktree vem do nome da branch: `spec/<slug>` na integração e
`ticket/<slug>/<NN>-<nome>` em cada ticket. Branch fora desse padrão tem ambiente próprio,
pelo nome da pasta.

**Quem sobe:** o orquestrador, a partir do worktree de integração, com pergunta ao dono
(uma por spec). Implementadores só gravam as portas no próprio `.env` e usam o que está de
pé. **Quando sobe:** só quando a validação exige. **[dono]**

Limite aceito: o banco é compartilhado entre implementadores em paralelo, e tickets que
criem migration ou testes que limpem tabelas podem interferir.

Integrações de uma linha: `orca.yaml` (`setup`: `worktree-env` e `INSTALL_CMD`; `archive`:
`destroy`; Quick Commands Start, Stop, Destroy) e `.conductor/settings.toml`.

## 12. Atualização

1. O dono muda o padrão aqui e publica uma tag.
2. No projeto roda `.harness/update <tag>`: baixa a tag do repositório público, executa o
   `bin/sync` da versão nova, confere as skills do mapa, mostra alteração manual
   antes de trocar, regenera os gerados, grava a tag no `ref` e no `MANIFEST`, e roda
   `claude plugin update`. A sessão aberta precisa de `/reload-plugins`.

Nunca toca nos arquivos do projeto nem nos livres.

## 13. Codex

`AGENTS.md` é a camada comum. O resto é gerado de uma fonte só: skills do harness em
`.agents/skills/`, agentes em `.codex/agents/*.toml`, `service-guard` em `.codex/hooks.json`.
Os portões de push são git, então valem igual. Arquivo gerenciado no Codex só tem a camada
do manifesto. Sem evento de fim de subagente no Codex, o push dele depende do
`.harness/approve` do dono.

## 14. Fatos da plataforma

Conferidos na documentação do Claude Code:

- `extraKnownMarketplaces` (com `ref`) e `enabledPlugins` no `settings.json` do projeto.
- Plugin não carrega `permissions` nem `env`.
- `SubagentStop` entrega `agent_type` (com prefixo do plugin), `last_assistant_message` e
  `agent_transcript_path`. `SubagentStart` aceita `additionalContext`.
- `PreToolUse` dispara em subagentes e traz `agent_type`.
- `permissions.deny` com `Edit(/caminho)` nega Edit e Write.
- Memória por projeto em `~/.claude/projects/<projeto>/memory/`, compartilhada entre worktrees.
- Subagente não dispara subagente.
- O sandbox do Bash nega escrita em caminhos dentro do projeto para qualquer processo filho,
  protege `~/.claude`, `.git/config` e `.git/hooks` por padrão, vale para subagentes, e os
  hooks rodam fora dele. O diretório temporário do usuário é gravável dentro do sandbox.

Testado em 2026-11-19, com `mattpocock-skills` 1.3.1 instalado por projeto:

- Skill com `disable-model-invocation` não pode ser invocada pelo agente. A ferramenta
  recusa e instrui: "Do not replicate this skill's workflow by other means — it is reserved
  for explicit user invocation". Vale para `grill-with-docs`, `to-spec`, `to-tickets`,
  `implement`, `implement-spec`, `retro`, `handoff`, `wayfinder`, `grill-me`, `ask-matt`.
- O agente invoca normalmente: `tdd`, `grilling`, `domain-modeling`, `code-review`, `pr`,
  `diagnosing-bugs`, `prototype`, `research`, `codebase-design`, `wizard`,
  `writing-for-agents`.
- `claude plugin list --json` devolve o `installPath` de cada plugin.

A testar na implementação:

- Se `model:` e a chave `agent` do `settings.json` valem para agente de plugin.
- Se `$CLAUDE_PROJECT_DIR` e `cwd` se comportam como descrito num worktree.
- Custo de gerar o mapa pela primeira vez num repositório grande.

## 15. Versões e critério de pronto

| Versão | Conteúdo |
|---|---|
| 1 | plugin, portões de push, setup, `.harness/` com ambiente por worktree, `entregar` com grafo e paralelismo, checagem grátis antes da paga |
| 2 | memória ancorada: mapa do código, âncoras do glossário e dos ADRs |
| 3 | ciclo de aprendizado: `retro`, `dream`, medição de custo |

**Validação final. [dono]** Só depois das três versões fechadas, e não antes: adotar o
harness numa cópia do `agenda-ai`, removendo a configuração de agentes que existe lá, e usar
o ciclo de entrega para transformar o código dele num app só de agendamento para salões: um
marketplace de salões e de serviços de estúdio e beleza. A remoção é feita numa cópia ou
branch, com confirmação do dono na hora.

Versão 1 pronta quando, num projeto que adotou o harness:

- Um projeto novo fica configurado só com o `setup`.
- Da entrevista ao PR, o dono só para na aprovação da spec.
- Push sem os dois vereditos é negado, e um agente não consegue carimbar.
- Um agente não edita arquivo gerenciado nem `harness.conf`.
- Dois worktrees sobem ambiente ao mesmo tempo sem conflito de porta.
- Uma mudança de padrão feita aqui chega ao projeto por `update`.

## 16. Fica para quem implementa

Formato do `harness.conf`, do `MANIFEST` e do `map.json`. Formato do mapa
do código e granularidade das âncoras. Geração do espelho do Codex. Cadastro dos Quick
Commands do Orca. Lista das skills próprias do dono que entram no plugin.
