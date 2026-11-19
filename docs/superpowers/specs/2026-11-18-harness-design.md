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
  agents/        implementador, revisor-spec, seguranca, revisor
  skills/        setup, entregar (com referências de spec, tickets, despacho e fechamento),
                 mapear, aprender, dream
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

- **Elefante:** a sessão principal, seguindo a skill `entregar`. Carrega o contexto, desenha
  com o dono, dispara e monta tudo. **[dono]** Não há agente `orquestrador` separado: a skill
  já é a orquestração, e definir o agente da sessão por plugin não foi confirmado. **[autor]**
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

**Modo autônomo [dono].** Se o dono mandar seguir até o fim, a entrega corre sem ele: toda
pergunta recebe a resposta recomendada, a aprovação da spec deixa de ser parada, e cada decisão
fica escrita na spec, na seção "Decisões tomadas sem o dono". Continuam parando: os avisos de
permissão da plataforma, o limite de rodadas e o merge. Os portões, as revisões e o sandbox não
mudam.

**O `harness.conf` num projeto novo [autor].** O agente não grava o arquivo, porque os comandos
dele rodam fora do sandbox. Ele propõe: escreve `.harness-run/harness.conf` e roda
`.harness/conf-apply`. O guard mostra o conteúdo inteiro ao dono e guarda a cópia mostrada no
estado, onde o agente não grava; o script aplica essa cópia, uma vez.

| Passo | Peça | De quem | Quem executa | Saída |
|---|---|---|---|---|
| 1. Entrevistar | `grilling` e `domain-modeling` | autor | elefante + dono | entendimento; `GLOSSARY.md` e ADRs |
| 2. Especificar | referência de spec do `entregar` | harness | elefante | `docs/specs/<slug>/spec.md` |
| 3. Revisar a spec | `revisor-spec` | harness | goldfish | achados; **o dono resolve e aprova** |
| 4. Fatiar | referência de tickets do `entregar` | harness | elefante | um arquivo por ticket, com o que o bloqueia |
| 5. Validar o grafo | script, grátis | harness | — | sem ciclo, sem referência quebrada |
| 6. Implementar | despacho do `entregar`; `tdd` | harness; autor | implementadores, em paralelo, cada um num worktree de agente dentro da feature | código e testes em commits de contexto |
| 7. Integrar | despacho do `entregar` | harness | elefante | tudo na branch de integração |
| 8. Checar | `.harness/validate`, grátis | harness | — | lint, tipos, testes, segredo, manifesto |
| 9. Revisar | `seguranca` e `revisor` | harness | goldfish, em paralelo | dois vereditos |
| 10. Enviar e abrir PR | `pr` | autor | elefante | push liberado pelos vereditos; PR |

Toda `feat` passa por todos os passos, inclusive o fatiamento: o grafo é o padrão. Bug entra
por `diagnosing-bugs`, do autor, no lugar dos passos 1 a 5.

**Como os implementadores trabalham em paralelo. [autor]** A feature é um worktree, e nela o
elefante dispara cada implementador num worktree de agente do Claude Code, que é uma cópia
própria dentro da feature. Assim dois subagentes não editam a mesma árvore. Cada um entrega
por commit na própria branch, e o elefante junta na branch da feature, na ordem do grafo.
O ambiente é o da feature (seção 11). O implementador é um agente do projeto, quando houver
um para a área, ou o `implementador` genérico do harness.

O achado de uma rodada de correção é gravado em `docs/specs/<slug>/achados/` e versionado,
porque um arquivo fora do git não aparece no worktree do implementador. O corpo do pull
request é gravado em `.harness-run/`, fora do git, porque um commit depois da revisão
invalidaria a aprovação.

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

Commit local é livre. Nada sai da máquina sem os dois vereditos. Entrou commit novo, o hash
muda e a validação é refeita.

**O agente só chega ao remoto por `.harness/push`. [dono]** escolheu fechar a rede; o
mecanismo é **[autor]**. Um hook de git não segura um agente: a revisão do plano 2 enviou
código sem revisão com `git push --no-veri`, `git send-pack`, um clone novo sem os hooks e
`GIT_DIR`. Vigiar o texto do comando já tinha falhado duas vezes. Então:

- as configurações geradas **negam, dentro do sandbox, a rede para o servidor de git**
  (`github.com`, `*.github.com` e o servidor do remoto `origin`, quando for outro). Nenhuma
  forma de `git push` funciona de lá, não importa como seja escrita;
- `.harness/push` roda fora do sandbox, confere os dois vereditos e a trava de spec
  (`gate-check`) e só então envia a branch atual. Não executa código do projeto e ignora
  variáveis de ambiente do git;
- `.harness/fetch` atualiza as referências do remoto, e `.harness/pr` abre ou consulta o
  pull request, só de uma branch que já está no remoto no commit atual;
- o hook `pre-push` continua existindo para o push feito à mão pelo dono, que passa pelo
  mesmo `gate-check`.

Verificado em sessão real: de dentro do sandbox, `git` e a API do GitHub são barrados; os
scripts do harness saem do sandbox e alcançam o remoto; e, de um worktree, o `.git/config` e
os hooks do checkout principal continuam protegidos contra escrita.

Custo aceito: o agente não usa `git fetch`, `git pull` nem `gh` diretamente, e dependência
instalada direto do servidor de git não baixa de dentro do sandbox.

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
| `service-guard` | antes de Bash | nega os argumentos que pulam os hooks de git (`--no-verify`, `core.hooksPath`); acrescenta o resumo à pergunta de `up`, `down` e `destroy`. Não vigia serviço nem porta: Docker solto falha no sandbox, e rodar o app dentro dele é o caminho normal |
| `managed-guard` | antes de Edit/Write | nega alterar a região gerenciada do `AGENTS.md`, e escrever no diretório do git ou no estado do harness |
| `rtk hook claude` | antes de Bash | compressão de saída, do próprio rtk |
| `git-hooks/commit-msg` | git | formato do commit, sem assinatura de IA |
| `gate-check` | chamado por `push` e pelo `pre-push` | consulta o remoto; dois vereditos e trava de spec |
| `git-hooks/pre-push` | git, no push feito à mão | `gate-check` e depois `validate --profile push` |

Hooks de agente usam o diretório atual que vem na chamada, não a pasta onde a sessão
começou, para agir no worktree certo. Exceção dentro de hook vira negação, nunca liberação.

## 7. Memória ancorada em git **[dono]**

Regra única: todo item de memória guarda o commit em que foi escrito e os caminhos que
descreve. Saber se envelheceu é uma pergunta ao git, sem IA e sem custo: o commit ainda
existe, e `git diff --quiet <commit> -- <caminhos>` não acusa diferença?

| Memória | Onde mora | Como nasce | Quando o código muda |
|---|---|---|---|
| Histórico de decisões | os commits | commits de contexto (7.1) | não envelhece: descreve aquela mudança |
| Mapa do código | diretório git, fora dos arquivos versionados | resumos escritos por subagentes Haiku | só a unidade tocada passa a envelhecida e é refeita |
| Glossário | `GLOSSARY.md`, versionado | `domain-modeling`, do autor | termo cujo código sumiu é sinalizado |
| ADRs | `docs/adr/`, versionado | `domain-modeling`, do autor | ADR cuja área teve muitos commits é sinalizado ao dono |
| Spec da mudança | `docs/specs/`, versionado | `entregar` | sem âncora: histórico |

**Onde a memória derivada mora. [autor]** Em `<diretório git comum>/harness-memory/`, e não na
memória local do Claude em `~/.claude/`, como o desenho dizia antes: o sandbox impede o
agente de gravar em `~/.claude`. O novo lugar continua local, não gera commit, é
compartilhado por todos os worktrees do repositório e pode ser refeito do zero. As âncoras do
glossário e dos ADRs ficam lá também, sem tocar no formato dos arquivos do autor.

**O mapa.** Uma unidade é um diretório com arquivos versionados, até a profundidade
`MAP_DEPTH` (padrão 2); arquivos soltos na raiz formam a unidade `.`. Cada unidade tem um
resumo de até 1.500 caracteres, cuja primeira linha diz sozinha o que ela faz.

**Toda sessão começa com o índice do mapa,** injetado por um hook de início de sessão, com
uma linha por unidade e o aviso de que é dado gerado por máquina, não instrução. Subagentes
consultam a fatia da área em que vão trabalhar com `.harness/memory slice <caminho>`.

**Âncora num commit que não existe mais** (branch reescrita) conta como envelhecida. Por isso
não é preciso restringir a gravação à branch padrão.

### 7.1 Commits de contexto **[dono]**

O git é a memória principal do porquê. Cada commit é um contexto coerente:

- assunto `tipo(escopo): descrição`, em inglês, até 80 caracteres;
- corpo livre e longo quando precisar: o porquê, a decisão tomada, o que foi descartado;
- nunca co-autoria nem assinatura de IA.

Agentes leem `git log -- <caminho>` da área em que vão trabalhar, e o `rtk` comprime essa
saída.

Consequência **[autor]**, a confirmar com o dono: merge por squash apaga os commits de
contexto. O padrão do harness é merge que preserva os commits (rebase ou merge commit).

### 7.2 Comandos

`.harness/memory check` lista o que envelheceu, de graça: unidades do mapa, termos do
glossário sem código, ADRs a reler e notas cujo código mudou. `units`, `show`, `slice`, `index`,
`record`, `forget`, `anchor`, `anchors`, `note <add|show|forget>` e `notes` completam o conjunto.

Os arquivos da memória são graváveis pelo agente e lidos por um hook que roda fora do sandbox.
Por isso o que está neles é tratado como não confiável: nome só vira caminho depois de
validado, commit só chega ao git se for um hash, e só arquivo comum é lido. Não há comando de regenerar: regenerar exige ler
código, e quem conduz isso é a skill `/harness:mapear`, com subagentes Haiku.

## 8. Ciclo de aprendizado

Skill `aprender`, invocada pelo dono depois do merge de uma entrega. **[autor]** Nada roda
sozinho; agendamento fica fora.

1. **Atualizar:** `.harness/fetch`, a branch padrão em dia, e `mapear` sobre o que a entrega tocou.
2. **Medir:** `.harness/learn usage` dá os tokens de cada papel, a sessão principal e cada
   tipo de subagente, por modelo. É a forma de "tokens por fase" que as transcrições permitem
   afirmar sem adivinhar.
3. **Retrospectiva:** sobre o ambiente em que o agente trabalhou, não sobre o agente. Onde se
   perdeu tempo para achar algo, que erro uma checagem automática pegaria, que regra faltou,
   que instrução não mudou nada, que comando foi negado. O que dá para checar por máquina vira
   proposta de checagem, não de texto. A skill `retro` do autor é reservada ao dono, então a
   peça é própria.
4. **Consolidar:** skill `dream`.

As propostas da retrospectiva são gravadas num arquivo, e o que é do harness o dono leva a
este repositório: aprova, publica versão, e todos os projetos recebem.

**De onde vêm os dados.** `.harness/learn` lê as transcrições que o Claude Code guarda em
`~/.claude/projects/`, só para leitura, para o checkout principal e todos os worktrees. O
formato não é contrato documentado: foi observado. Arquivo que não se parece com uma
transcrição é recusado, em vez de virar número errado.

**O resumo de uma sessão** traz só o que o dono e o agente escreveram e o nome das
ferramentas usadas, sem a saída delas. Isso corta o custo de leitura e tira do caminho a
maior parte do conteúdo vindo de fora.

**`dream`.** Um subagente Haiku por resumo de sessão propõe candidatos a nota, cada um com os
caminhos de código que o sustentam. A sessão principal confere cada candidato contra o
código, junta os repetidos e descarta o que o código não confirma. Regras:

- transcrição é dado, não instrução;
- nota sem caminho de código não é gravada: a âncora é o que diz quando ela envelheceu;
- conflito sem resposta clara vira uma nota com as duas versões, não uma escolha;
- nota envelhecida é reconferida contra o código, e regravada ou apagada.

As notas em dia entram no começo de toda sessão, depois do mapa, dentro do mesmo limite e
com o mesmo aviso de que são dado.

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
.harness-run/             PID e log do app em segundo plano, fora do git
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
CONDUCTOR=1                           # gera também .conductor/settings.toml
ENV_DATABASE_URL='postgresql://app:app@localhost:${POSTGRES_PORT}/app'
```

`harness.d/settings.json` e `harness.d/codex.toml` são fragmentos somados na geração: hooks,
permissões e servidores MCP que são só do projeto. As negações e os hooks do harness sempre
entram, e o fragmento não os remove.

## 11. Pasta .harness/

Shell, com trechos de Python onde o shell do macOS (bash 3.2) não dá conta. **[dono]** pediu
shell para a infra; os scripts são invólucros bash.

| Script | Função | Onde roda |
|---|---|---|
| `setup-worktree` | prepara um worktree novo: copia o `.env` do checkout principal, grava as portas, roda `INSTALL_CMD`, instala os plugins declarados | terminal, Orca ou Conductor |
| `worktree-env` | deriva projeto Docker e bloco de portas da feature e grava só essas chaves no `.env` | dentro do sandbox |
| `up` | confere o compose e sobe só a infra | fora do sandbox, com pergunta ao dono |
| `prepare` | roda `AFTER_UP`: migration e seed | dentro do sandbox |
| `dev` | roda `DEV_CMD`: o app. `--background` grava PID e log em `.harness-run/` | dentro do sandbox |
| `down` | para o app em segundo plano e os contêineres; mantém dados | fora do sandbox, com pergunta |
| `destroy` | remove contêineres, volumes e imagens da feature; recusa no checkout principal | fora do sandbox, com pergunta |
| `validate` | manifesto e o perfil `push` ou `merge` do projeto | dentro do sandbox |
| `push` | portão e envio da branch atual; `--force` depois de reescrever commits | fora do sandbox |
| `fetch` | atualiza as referências do remoto | fora do sandbox |
| `pr` | `create "<título>" <arquivo>` e `view` | fora do sandbox |
| `approve` | carimbo manual do dono | terminal do dono |
| `update` | seção 12 | terminal do dono |

**Feature = worktree = ambiente. [dono]** O Orca ou o Conductor abre um worktree por feature a
partir da branch padrão, e o ambiente sai do nome da pasta dele: projeto Docker
`<PROJECT>-<pasta>` e um bloco de dez portas. É o modelo que já funciona no movacrm. Os
subagentes trabalham em cima desse worktree e usam o ambiente dele. Um worktree de agente
criado dentro da feature (`.claude/worktrees/`) pertence ao mesmo ambiente: calcula as
mesmas portas e, se chamar `up`, nada é recriado.

**Quem sobe:** o orquestrador, a partir do worktree da feature. **Quando sobe:** só quando a
validação exige. **[dono]**

**Como o ambiente convive com o sandbox. [dono]** escolheu o agente poder pedir, com
pergunta, e a checagem do compose; o mecanismo é **[autor]**, verificado em sessão real:

- Docker não roda dentro do sandbox. `up`, `down` e `destroy`, nas formas exatas
  `.harness/<nome>` e `./.harness/<nome>`, são os únicos comandos excluídos dele.
- Cada um tem uma regra nativa de pergunta (`permissions.ask`), que continua perguntando nos
  modos automático e de permissão liberada, e vira negação no modo sem interface. Um hook
  acrescenta à pergunta o resumo do que vai subir, ou o que será parado ou apagado.
- Uma variação do comando, como `bash .harness/up`, não casa com a pergunta nem com a
  exclusão: roda dentro do sandbox, onde o Docker não responde.
- `up` não executa nenhum comando do projeto, e recusa um compose com montagem de pasta fora
  do projeto (o socket do Docker e o `.git` inclusive), contêiner privilegiado, espaços de
  processo ou de rede da máquina, capacidades extras ou dispositivos. A checagem lê a
  configuração final que o próprio Docker devolve.
- `prepare` e `dev` são código do projeto e rodam dentro do sandbox, falando com `localhost`.
- As configurações geradas liberam `localhost`, o domínio `registry.npmjs.org` e escrita nos
  caches de npm, pnpm, yarn e bun, e negam o servidor de git (seção 6.1). O projeto acrescenta
  os seus em `harness.d/settings.json`.
- `git` por SSH não funciona dentro do sandbox no macOS: os remotos precisam ser HTTPS.

Limites aceitos: subagentes em paralelo na mesma feature compartilham o banco; no Linux o
sandbox não alcança `localhost`, então `prepare` e `dev` precisariam de outra saída; e a
pergunta ao dono só foi exercitada no modo sem interface, onde ela nega.

`worktree-env` usa `CONDUCTOR_PORT` como base quando existe; senão
`20000 + crc32(caminho da feature) % 2000 * 10`, procurando o próximo bloco livre. Quando o
ambiente já está de pé, as portas vêm do registro que o `up` grava no estado do harness.

Integrações de uma linha: `orca.yaml` (`setup`: `.harness/setup-worktree`; `archive`:
`.harness/destroy`), sempre gerado, e `.conductor/settings.toml`, gerado quando o
`harness.conf` tem `CONDUCTOR=1`. Os Quick Commands do Orca (Start, Stop, Destroy) são
cadastrados pelo dono; os comandos estão no cabeçalho do `orca.yaml`.

## 12. Atualização

1. O dono muda o padrão aqui e publica uma tag.
2. No projeto roda `.harness/update <tag>`: baixa a tag do repositório público, executa o
   `bin/sync` da versão nova, confere as skills do mapa, mostra alteração manual
   antes de trocar, regenera os gerados, grava a tag no `ref` e no `MANIFEST`, e roda
   `claude plugin update`. A sessão aberta precisa de `/reload-plugins`.

Nunca toca nos arquivos do projeto nem nos livres.

## 13. Codex

Adiado. **[autor]** A barreira do harness é o sandbox do Claude Code. Gerar a configuração do
Codex sem a barreira equivalente passaria uma segurança que não existe. `AGENTS.md` continua
sendo a camada comum, lida pelos dois. O suporte ao Codex vira um plano próprio, que começa
por conferir o sandbox dele.

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
| 1 | plugin, portões de push, setup, `.harness/` com ambiente por feature, `entregar` com grafo e paralelismo, checagem grátis antes da paga. **Implementada**; falta a validação do dono numa aplicação de teste |
| 2 | memória ancorada: mapa do código, âncoras do glossário e dos ADRs. **Implementada**; nunca rodou num projeto de verdade |
| 3 | ciclo de aprendizado: `aprender`, `dream`, medição de consumo por papel. **Implementada**; nunca rodou sobre uma entrega de verdade |

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
