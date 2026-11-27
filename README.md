<img src="site/mascote.png" alt="" width="72" align="right">

# FullChico Harness

[![npm](https://img.shields.io/npm/v/@fullchico/harness?label=npm&color=1d1b16)](https://www.npmjs.com/package/@fullchico/harness)
[![ci](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml)

[Página do projeto](https://fullchico.github.io/fullchico-harness/) · [Pacote no npm](https://www.npmjs.com/package/@fullchico/harness)

```bash
npx @fullchico/harness@latest install
```

**Um harness por projeto para Claude Code e Codex.** O plugin organiza a demanda, distribui
tarefas independentes, mantém guardrails ativos, consulta a memória do código e confere os
portões antes de declarar a entrega. Cada tarefa carrega um passaporte: requisitos de entrada,
validações específicas no percurso e carimbos de conclusão. O carimbo é um certificado escrito no
próprio documento da demanda e assinado por commit de quem validou: vale em qualquer máquina. Se faltar
evidência, o executor corrige e o fiscal independente revisa novamente. O instalador inicia Git se necessário;
push e PR não são requisitos da entrega. O plugin é distribuído como pacote Node por conveniência
(`npx` em uma linha); o pacote só instala, não é biblioteca para importar no app.

O `install` usa o Git local e executa `git init` se necessário. Não configura remoto. Um projeto
pode exigir um remoto ou publicação por meio de um portão próprio em `.claude/harness.json`.
Por exemplo, um portão de comando pode verificar `git remote get-url <name>`; o nome e o momento
desse portão são escolhidos pelo projeto.

Para registrar modelos por papel, rode `fullchico-harness models configure` no terminal
(interativo) ou informe pares, por exemplo `models configure planning claude:opus
execution codex:luna review codex:sol support claude:sonnet`. `models show` exibe os espelhos
iniciais Opus/Sol, Sonnet/Luna, Haiku/Terra e Fable/Astra. A configuração registra a intenção;
`models run <role> --prompt "<text>" [--ticket <path>]` inicia a CLI escolhida,
grava um manifesto fora do repositório e passa ao modelo de apoio se a primeira CLI retornar
erro de limite. Com `--detach`, a execução roda à parte e devolve um id na hora;
`models wait <id> [<id>...]` espera uma onda inteira (sai com 3 enquanto ainda roda). O
orquestrador sempre usa `--detach`: uma chamada de terminal longa seria cortada pelo limite de
tempo da ferramenta. Com `--terminals` na partida, cada executor abre num terminal e num worktree
próprios, e cada revisor de portão de agente também.
O executor aberto via Codex CLI usa `workspace-write`: nesse modo ele não grava em `.git` nem
escuta numa porta, então entrega os arquivos e o relato, e o orquestrador roda as conferências que
precisam de porta e faz o commit do worktree dele. A sessão Claude usa a configuração efetiva do projeto;
o fiscal Codex continua em modo de revisão.
A entrevista (`grilling`) identifica os serviços e comandos necessários, como subir o Compose, acessar
uma API local ou abrir o navegador. Quando a plataforma exigir permissão, o executor solicita
liberação para a ação concreta; uma necessidade não prevista não reabre toda a entrevista.
No Claude Code, `review claude:<model>` também define o modelo padrão dos fiscais. Para um
portão de agente específico, use `gate:<name> claude:<model>` ou `gate:<name> codex:<model>`, por exemplo
`npx @fullchico/harness models configure review claude:sonnet gate:security codex:sol
gate:design-review claude:opus`.
Cada portão de agente pode usar Claude ou Codex e um modelo próprio. O orquestrador abre os
executores com `models run execution --ticket <path> --prompt <handoff>` e os fiscais
externos com `models validate-gate <name> [--ticket <path>]`. O revisor recebe o critério aceito e o
código, nunca instrução de quem pediu a revisão; o relato de quem chama fica só no manifesto.
O harness exige veredito, hash do estado examinado e processo bem sucedido antes de certificar.
Se o modelo do portão for Codex, o hook impede que um Agent Claude assine no lugar dele.
As execuções e seus manifestos ficam fora do repositório.

## O elefante conduz, os peixinhos executam, o tubarão valida

<img src="site/img/elefante-peixes-tubarao.png" alt="" width="720">

| Papel | Bicho | O que faz | Memória |
|---|---|---|---|
| **Maestro e orquestrador** | elefante | o modelo maior: pensa, conversa com o dono, fecha a definição e conduz o trem; o maestro guarda o que foi entregue, e o orquestrador coordena a demanda e reporta a ele | o maestro guarda tudo; o orquestrador é montado para a demanda e desmontado ao fim |
| **Executores** | peixinhos | os modelos menores: cada um no seu vagão, executa o seu ticket e reporta ao orquestrador | nenhuma: cada um é desmontado ao relatar |
| **Revisores** | tubarão | valida na chegada: confere cada vagão contra o critério aceito e assina o certificado | nenhuma: desmontado ao dar o veredito |

Cada peixe é uma sessão inteira num **terminal próprio** (tmux), com o contexto só dele: o executor gasta o
contexto no ticket e some; o orquestrador recebe só o relato de cada um; o maestro recebe só o relato do
orquestrador. O nome do terminal diz quem é, então `tmux ls` vira o painel da demanda:

```
orq-clinica-api-opus
exec-02-tutores-terra
exec-03-gatos-haiku
rev-bugs-sonnet
```

`tmux attach -t <nome>` entra em qualquer um para assistir (`Ctrl+b` `d` sai sem encerrar).

- **Modelos por demanda.** Quando a definição fecha, o dono escolhe três coisas para aquela demanda: o modelo do
  orquestrador, o dos executores e o dos revisores. A escolha vai no comando de partida
  (`tr-harness orchestrate --agent claude --model opus --executors claude:haiku,codex:terra --reviewers
  claude:sonnet --terminals`) e não muda o registro do projeto. Vários modelos de executor se revezam. Um nome
  de modelo é um apelido para a versão mais nova (`terra`, `sol`, `haiku`); só um id com versão fixa a versão.
- **O peixe só leva o que é do projeto.** Skills, instruções, plugins, hooks e conectores MCP registrados no
  projeto chegam a todo peixe (é onde o instalador põe o plugin, as skills do Matt Pocock, o `rtk` e o
  ponytail). O ambiente do usuário não entra. No Codex o isolamento é parcial: os conectores MCP do usuário
  saem, mas os plugins de usuário do Codex ainda carregam.
- **O aviso é um relato em arquivo.** O peixe grava o relato ao terminar, e o hook de parada não o deixa parar
  sem isso. Quem espera (`tr-harness orchestrate --wait` no maestro, `tr-harness models wait <id>...` no
  orquestrador) volta na hora. O relato do orquestrador traz o resultado do `gate delivery` e o balanço
  calculados pelo comando, não pela palavra dele.
- **Nada escapa.** Cada terminal é gravado desde a abertura, e o relato aponta para o registro que o próprio
  agente guarda da sessão. O orquestrador só abre um log por critério (relato bloqueado ou contradito por uma
  conferência, terminal que encerrou sem relato, reprovação que ele não consegue explicar) e nunca inteiro.
- **O trilho é limite, não procedimento.** A garantia mora nos portões: os critérios são levantados na partida
  e validados na chegada. No caminho, o peixe é livre dentro do ticket; o hook só barra o que a chegada não
  desfaz (dano fora do projeto, reescrever histórico sobre um certificado) e cobra o relato.

Requisitos da máquina: Git, Node 18+, Python 3, **tmux**, **rtk** e o Claude Code; o Codex só para quem usar
modelos dele. O instalador cobra o tmux e o rtk.

## Execução em paralelo

O orquestrador despacha a fronteira de tickets em ondas, cada executor no próprio worktree. No embarque, o
comando avisa quando dois tickets da mesma onda declaram o mesmo arquivo em `Files:` (merge em paralelo
conflita ali) e roda uma vez cada verificador de comando, para saber antes da viagem se ele funciona.

- **até `max_parallel` executores ao mesmo tempo** quando são subagentes (3 por padrão); em terminais, as vagas
  são pastas fixas (`tr-seat-N`), reaproveitadas entre tickets;
- **nenhum portão de fim roda no meio da viagem**: o ticket integrado já libera quem depende dele, e os
  portões de fim auditam o estado final uma vez, na chegada (o hook barra antes disso);
- **a máquina não dorme** enquanto há peixe trabalhando (`caffeinate` no macOS, `systemd-inhibit` no
  Linux); o pedido expira sozinho quando a entrega para. Desligue com `"keep_awake": false`;
- **retomada depois de queda**: a sessão nova libera os tickets presos e retoma pelo quadro;
- `tr-harness status` mostra tickets, executores ativos, contêineres esquecidos e até quando a máquina fica acordada.

## A entrega é um trem, com início e fim

| Momento | O que acontece |
|---|---|
| **Embarque** | só parte com todos a bordo: o dono aceita o critério escrito (uma pergunta na própria sessão, `Aprovo` ou `Não aprovo`; no terminal, `gates --accept`), os pré-requisitos do dono foram derivados do verificador de cada portão, e os portões de início estão certificados |
| **Viagem** | automática: tickets em paralelo, cada executor alinhado à branch da demanda, sem portão de fim no caminho |
| **Socorro** | o maestro espera com `tr-harness orchestrate --wait`, que também volta se o terminal do orquestrador parar numa tela que só o dono responde ou travar; `--read` mostra a tela e `--stop` desmonta; quem trava ou bloqueia deixa um handoff em `docs/specs/<demanda>/progress/`, e o próximo continua dali, em Claude ou Codex |
| **Chegada** | auditoria: todos os portões de fim ao mesmo tempo; cada revisor valida o delta entre o planejado (spec, tickets, artefatos aprovados) e o entregue, com a prova vinda do estado entregue; `tr-harness balance --write` grava o balanço |
| **Trem de ajuste** | cada reprovação vira um ajuste em `progress/adjust-NN-*.md` (andamento, não critério: o aceite do dono continua); revalida só o portão que reprovou e os de comando se o código mudou; a aprovação de um revisor segue valendo se o ajuste ficou nos arquivos que declarou |
| **Limite** | cada portão de fim tem um limite de reprovações (3 por padrão; falha de comando também conta); passou dele, o dono decide |

O dono só é chamado nas bordas: no embarque, no limite estourado, se o critério precisar mudar, numa ação
externa irreversível ou num bloqueio sem alternativa. Para conferir fora da sessão, `npx @fullchico/harness deliver`
roda em qualquer clone (pre-push ou CI, à escolha do projeto; no CI use `fetch-depth: 0`).

## Exemplo: dois trilhos, uma entrega

![Duas locomotivas puxam vagões independentes até a conferência do passaporte](site/img/locomotivas-cartoon.png)

Uma tela e uma API podem avançar em paralelo. Cada ticket declara seus próprios portões: a tela
pede acessibilidade; a API pede testes de contrato. A conferência final exige os carimbos de
qualidade e bugs do estado entregue.

```text
# docs/specs/perfil/issues/01-tela.md
Status: open
Blocked by: none
Start: process
Middle: accessibility
Gates: quality, bugs
Files: apps/web/src/perfil

# docs/specs/perfil/issues/02-api.md
Status: open
Blocked by: none
Start: process
Middle: contract
Gates: quality, bugs
Files: apps/api/src/perfil
```

Os nomes `accessibility` e `contract` são exemplos de portões que o projeto registra em
`.claude/harness.json`. Um fiscal independente assina cada validação; se reprovar, o ticket volta
ao executor. O comando `fullchico-harness deliver` confere o passaporte antes de declarar a
entrega concluída.

![O dono aceita o critério, o vagão executa, o fiscal confere e o documento chega certificado](site/img/passaporte-cartoon.png)

Neste exemplo, o mascote do Claude conduz a entrevista e a execução; o do Codex faz a revisão.
Esses papéis podem ser configurados por projeto:

```bash
fullchico-harness models configure planning claude:opus execution claude:sonnet review codex:sol support codex:luna
fullchico-harness models show
```

O primeiro comando registra a escolha; `models run <role> --prompt "..."` inicia uma
CLI por vez e usa o modelo de apoio quando encontra um erro de limite. O fluxo completo entre
os papéis ainda é conduzido pelas skills do `tr`.

## Sumário

- [A entrega é um trem](#a-entrega-é-um-trem-com-início-e-fim)
- [Exemplo: dois trilhos, uma entrega](#exemplo-dois-trilhos-uma-entrega)
- [A divisão](#a-divisão)
- [Os oito conceitos](#os-oito-conceitos)
- [Plugins](#plugins)
- [Core e ferramentas integradas](#core-e-ferramentas-integradas)
- [Instalar](#instalar)
- [Registro de portões](#registro-de-portões)
- [Limites honestos](#limites-honestos)
- [Licença](#licença)

## A divisão

**O plugin invoca as skills por você.** Você faz o pedido, responde à entrevista e aprova o que grava
portões, modelos e plugins; o `tr` escolhe e chama, na hora certa, as skills maduras da comunidade
(como `grilling` e `domain-modeling`, de Matt Pocock) em vez de manter cópias adaptadas. Se for
preciso lembrar de chamar uma skill de processo, é falha do `tr`.

**O plugin garante o caminho (orquestração) e a aprendizagem (memória). Começo e fim ficam com as
ferramentas do seu projeto, ligadas pelos portões.**

## Os oito conceitos

### 1. Harness

O conjunto do projeto: os plugins ligados, os prompts, o registro de portões e a configuração.
Fica em `.claude/` e `.codex/`, na pasta do projeto; o registro compartilhado é
`.claude/harness.json`.

*Status: disponível.*

### 2. Planejamento

O portão de começo, assinado por um artefato (`docs/specs/*/spec.md`) ou por comando. Um fluxo próprio
do projeto que já faz spec, plano ou revisão é tratado como concorrente: o `/tr:configure` mostra onde ele
está ligado e recomenda trocá-lo pelo fluxo do `tr`, convertendo as specs abertas. O dono decide.

Cada demanda começa por `/tr:process-plan`, que orquestra as skills de Matt Pocock (`mattpocock-skills`)
sem cópia adaptada: a entrevista (`grilling` e `domain-modeling`; o glossário `GLOSSARY.md` e os ADRs em
`docs/adr/` são saídas do planejamento, e o portão `domain` confere o glossário na entrada), a spec
(`to-spec`) com o **passaporte** (a linha `Gates:` diz os portões opcionais que a demanda pede) e as
pré-condições do dono, e os tickets (`to-tickets`), cada um com a `Complexity:` que decide o modelo de quem o
executa. A execução segue o `implement-spec` com `tdd`, e o revisor de escopo aplica o eixo Spec do
`code-review`. O Matt produz e julga; o `tr` certifica e protege a cadeia. Antes de qualquer executor, o dono
aceita o critério escrito (`tr-harness gates --accept`).

*Status: disponível. O portão vem no `tr`; `/tr:configure` entrevista o dono e propõe o registro.*

`/tr:configure` começa pelos diagnósticos disponíveis (`claude doctor` e `codex doctor --json`),
analisa scripts, CI e ferramentas do projeto e usa a entrevista (`grilling`, de Matt Pocock) para decidir com o dono os
portões de entrada e saída. O install não cadastra portões;
o projeto pode criar portões com nomes e verificadores próprios. A IA entrega o
esboço e os comandos; quem grava o registro protegido é o dono.

### 3. Paralelismo com grafo

Tickets com `Blocked by:` formam um grafo. A fronteira contém os tickets cujos bloqueadores
já foram concluídos e carimbados; o hook impede o disparo antecipado de um executor, e o
orquestrador só dispara executor com o caminho do ticket no pedido. **Quem planeja não executa:**
enquanto a demanda tem tickets abertos, o hook barra escrita de código pela sessão principal e
pelo orquestrador; o código é dos executores (em terminais próprios, ou subagentes). Tickets
independentes podem avançar em contextos isolados. Após o planejamento aprovado, o maestro
abre o orquestrador com `tr-harness orchestrate`, num terminal próprio. Ele coordena executores,
fiscais e integração; o maestro continua livre para o dono. A confirmação final
da entrevista autoriza o plano recomendado até a entrega. Reprovações voltam ao executor para
correção e nova validação. Cada portão final aceita `"attempts": 3` por padrão; na quarta
reprovação, o orquestrador solicita intervenção humana. O limite pode ser aumentado por portão.
`"approval": "auto"` é o padrão; `"human"` exige aprovação explícita do estado já validado com
`fullchico-harness gates --approve <name>`. O orquestrador só consulta o dono se
precisar mudar o objetivo aprovado, executar uma ação irreversível não coberta pelo plano ou
enfrentar um bloqueio sem alternativa permitida.

*Status: disponível no `tr` para tickets em `docs/specs/<demanda>/issues/`.*

### 4. Loops

Cada fiscal valida o estado atual do ticket. Se reprovar, o implementador corrige e o fiscal
reexamina. Só o trabalho aprovado entra no passaporte e libera os dependentes.

*Status: conduzido pelo orquestrador; a conferência final é aplicada pelo hook.*

### 5. Guardrails

Os hooks protegem `.claude/harness.json`, `.claude/settings.json`,
`.claude/settings.local.json` e `.git/`. O CLI de portões recusa gravações quando é chamado pelo
shell do Claude. O sandbox nativo do Claude Code é opcional (perfil `isolado`,
`install --sandbox`); se ativado, acrescenta isolamento de arquivos e rede. Com registro, o hook também:

- escreve o pedido de cada validador (o que quem escreveu o código disse é descartado);
- mantém o validador só leitura;
- aplica o modelo de executor escolhido para a demanda, ou, sem escolha, a complexidade do ticket (haiku ou sonnet);
  `fullchico-harness models configure` registra os modelos por papel e permite escolher Claude
  ou Codex e o modelo próprio de cada portão de agente;
- barra `gate <name>` combinado com pipe ou `&&` (rodaria sem carimbar) e os scripts do harness
  antigo (`.harness/`).

Custam zero e não se customizam.

*Status: disponível.*

### 6. Portões

Na entrada, exigem requisitos antes da escrita; no fim, validam a entrega. O meio segue o grafo
de tickets e pode ter portões próprios por tarefa, como acessibilidade para uma tela ou testes de
contrato para uma API. São customizáveis no registro protegido `.claude/harness.json`.

*Status: disponível.*

### 7. Validações

O que assina um carimbo. São três jeitos:

| Jeito | Assina quando |
|---|---|
| **comando** | o `tr:quality-checker`, um subagente limpo por portão, roda `gate <name>` e passa (`/tr:quality-check`) |
| **agente** | o veredito do agente é aprovado (ex.: `tr:bug-hunter`, por `/tr:bugs-hunt`) |
| **artefato** | o fiscal confirma que o arquivo existe e passa na validação |

**Quem produziu a evidência não assina.** Portões de início e fim são validados num subagente de contexto limpo, com o
pedido escrito pelo hook; o `gate` rodado pela sessão principal mostra o resultado, mas não carimba.
Cada validador valida só o que o portão dele propõe.

**O carimbo é um certificado no próprio documento.** Como a assinatura de um especialista num
documento revisado, ele vai no apêndice `## Certificates` da spec da demanda (ou do ticket, para o que é do
ticket) e é assinado pelo commit do responsável pelo portão, com o trailer `Certified-by:`:

- **o que ele prova:** este estado do código passou por este portão, contra o critério que o dono aceitou. A
  chave é a impressão digital do código mais a do critério (spec e tickets, sem o andamento `Status:` e
  `Delivery:`). Mudou um dos dois, o certificado cai;
- **quem assina:** só o responsável. Partida: o aceite do dono (`tr-harness gates --accept`) sobre o critério
  escrito. Fim: cada revisor, pelo hook. Quem executa commita trabalho, nunca certificado. O guard barra o
  agente de editar o apêndice ou forjar o trailer, e uma linha sem o commit do responsável não vale;
- **onde vale:** em qualquer máquina, agente ou CI, porque está no Git. As reprovações também ficam no
  apêndice, e o limite de tentativas vai junto com a demanda.

![O dono assina o primeiro selo do apêndice e o fiscal carimba o último; cada selo desce até um marco no trilho](site/img/certificado-cartoon.png)

Arquivos `.md` e `docs/` fora da demanda não invalidam nada; mexer na configuração local do Git ou publicar
(push, PR) também não, porque não é conteúdo.

*Status: disponível.*

### 8. Memória organizada

Mapa do código e notas ancoradas, por projeto, injetadas no começo de cada sessão, no plugin
`memory`: `/tr:memory-map` atualiza o mapa, `/tr:memory-dream` consolida o que as sessões
ensinaram (proposto por um extrator isolado, conferido contra o código) e `/tr:memory-learn` mede
o consumo e faz a retrospectiva depois de uma entrega. `memory graph rebuild` atualiza o
Graphify local quando instalado; `memory graph search <termos>` cruza o grafo de código com
resumos, notas, glossário e ADRs. A memória fica fora dos arquivos versionados, no diretório Git comum.

**A memória é um loop do processo, não um comando para lembrar:**

![A locomotiva percorre o trilho circular: mapa, prancheta com lupa e o sonho depois da entrega; no centro, o caderno de notas](site/img/memoria-cartoon.png)

| Momento | Quem dispara | O que acontece |
|---|---|---|
| Fim do `/tr:configure` | o próprio configure | cria o mapa: um resumo por pasta de **código** (pasta só de Markdown não entra) |
| Entrada de cada demanda | o `/tr:process-plan`, antes da entrevista | `memory check`; refaz só o que envelheceu |
| Fim de cada entrega | a sessão, ao receber `DELIVERY: done` | `/tr:memory-dream` das sessões da demanda, sem bloquear a entrega |

O dream lê a sessão inteira, em partes, com o que cada subagente escreveu (executores, orquestrador,
revisores). `memory-sessions sessions` diz o tipo de cada sessão: `trabalho` é lida; `revisão` (aberta por
um `validate-gate`, com o veredito já certificado) só é marcada; `em andamento` fica para depois. Uma
sessão só é marcada quando todas as partes passaram pelo extrator.

*Status: disponível.*

## Plugins

| Plugin | O que faz | Estado |
|---|---|---|
| `tr` | entrevista, orquestrador, grafo de tickets, portões, fiscais independentes, passaporte e modelos por papel | disponível |
| `memory` | mapa, grafo local e notas ancoradas, compartilhados entre Claude e Codex | disponível |

O orquestrador abre num terminal próprio (tmux), montado para a demanda. Uma segunda demanda em paralelo viaja num worktree filho (`tr-harness demand open <slug>`), que nasce da branch do pai e volta a ela por merge; não há plugin separado de orquestração.

## Core e ferramentas integradas

O **core do FullChico** reúne o `tr` e o `memory`: entrevista e planejamento, tickets com
dependências, seleção de modelos para planejar/executar/revisar, hooks de proteção, memória local,
portões e passaportes. Claude e Codex podem conduzir trabalhos independentes em trilhos paralelos;
o loop completo entre os três papéis ainda depende das skills do `tr`. O verificador não é o agente
que produziu a evidência.

As **ferramentas integradas** têm papéis separados:

| Ferramenta | Papel | Instalação |
|---|---|---|
| [Matt Pocock skills](https://www.skills.sh/mattpocock/skills) | entrevista, modelagem e práticas de implementação; o `tr` invoca `grilling` e `domain-modeling` em vez de manter cópia | skills CLI na instalação |
| [Ponytail](https://www.skills.sh/dietrichgebert/ponytail) | mudanças pequenas e revisão | skills CLI na instalação |
| [Graphify](https://github.com/Graphify-Labs/graphify) | grafo AST opcional para busca na memória; skill incluída no pacote | CLI `graphifyy` opcional |
| [rtk](https://github.com/rtk-ai/rtk) | compacta a saída dos comandos e economiza tokens, no Claude Code e no Codex | **obrigatório**: o `install` termina com erro sem ele |
| Git | ancora o estado do código, os carimbos e o índice local | requisito; `install` executa `git init` se faltar |

Remoto, push, PR e ferramentas como lint, teste, acessibilidade ou análise de segurança são
decisões do projeto, registradas como portões quando fizerem parte da entrega.

Toda skill própria é acionada pelo `tr`, inclusive as de memória, com invoker `/tr:<name>`:

| Invoker | Validador | Valida só |
|---|---|---|
| `/tr:process-plan` | sessão principal → `tr:orchestrator` | entrevista, spec e tickets; depois delega execução e validação |
| `/tr:quality-check` | `tr:quality-checker` (haiku), um por portão de comando | o comando daquele portão |
| `/tr:bugs-hunt` | `tr:bug-hunter` (sonnet) | defeitos no diff |
| `/tr:scope-check` | `tr:scope-checker` (sonnet) | a entrega cumpre cada critério da spec e dos tickets, dentro do `Files:` |
| `/tr:memory-map` | subagentes de leitura | mapa do código |
| `/tr:memory-dream` | `memory:extractor` (haiku) | notas de sessões conferidas com o código |
| `/tr:memory-learn` | (a sessão que fecha a entrega) | retrospectiva e consolidação |
| `mattpocock-skills:grilling` | (a sessão que entrevista, invocada pelo `tr`) | decisões em rodadas para planejar e configurar trilhos e portões |
| `/tr:skills-discover` | catálogo skills.sh + entrevista `grilling` | compara skills para a demanda, instala a escolhida nos ambientes e propõe portão só com evidência verificável |

Os plugins `bugs` e `quality` da 2.x foram absorvidos pelo `tr` na 3.0. Em Claude Code, cada
plugin usa `--scope project`. Em Codex, o marketplace local `.agents/plugins/marketplace.json`
aponta para as cópias em `.codex/harness/`, e `.codex/config.toml` habilita `tr` e `memory` no
projeto. Os prompts vêm das skills de cada plugin.

## Instalar

### Codex

```bash
npx @fullchico/harness@latest install --target codex
```

`install` abre um menu no terminal para escolher **Claude Code**, **Codex** ou **ambos**. A escolha
padrão é **ambos**, inclusive sem terminal interativo. Em automações, use
`--target claude|codex|both` para fixar a escolha. `install-codex` permanece como atalho.

O instalador monta os plugins `tr` e `memory` em `.codex/harness/`, registra o marketplace local
em `.agents/plugins/marketplace.json`, habilita ambos em `.codex/config.toml` e cria quatro agentes
em `.codex/agents/`. As dez skills próprias ficam em `tr`; o prompt auxiliar fica
em `.agents/skills/`. Instala também todas as skills de
[Ponytail](https://www.skills.sh/dietrichgebert/ponytail) e
[Matt Pocock](https://www.skills.sh/mattpocock/skills) pelo skills CLI, direcionadas ao Codex.
A skill `graphify` do plugin `memory` também é instalada em `.agents/skills/graphify`.
Para habilitar o motor AST local, instale a CLI oficial com `uv tool install --with anyio graphifyy`.
O registro de portões fica em
`.claude/harness.json` e é compartilhado com Claude Code quando os dois estão instalados.
O install não cria portões; o dono os escolhe em `$tr-configurar` e os registra pelo CLI.
A entrevista também define os critérios de aprovação e o limite de correções automáticas de cada
portão final. Exemplo: `"quality": {"stage":"end","signs":"command","command":"pnpm test","attempts":5,"approval":"auto"}`.
`install --target codex --default` é uma opção explícita para o modelo de exemplo. Rodar o
instalador novamente preserva a configuração de outros plugins, hooks e registro existentes.
Abra uma sessão nova em um projeto
confiável e aceite os hooks locais quando o Codex pedir. Use a skill `tr-codex` para executar
as validações e consultar a memória. As skills próprias aparecem como `$tr-memory-map`,
`$tr-memory-dream` e `$tr-memory-learn`. O estado pode ser visto com
`python3 -I .codex/harness/tr/scripts/gate_cli.py`.

O Codex usa os mesmos scripts de portões, com um adaptador para `Bash`, `apply_patch` e
subagentes. A cobertura de hooks depende das ferramentas locais que o Codex expõe; ferramentas
fora desse caminho e comandos rodados fora da sessão não são barrados. Os hooks locais só
executam depois da revisão de confiança do usuário; sem ela, o `codex exec` ignora os hooks sem
avisar. Por isso o `models run` recusa uma execução Codex de executor em que os hooks do `tr` não
rodaram (código 125), com a instrução de abrir `codex` no projeto e confiar nos hooks. No Codex
0.171, a mensagem do `spawn_agent` chega cifrada ao hook: a fronteira por ticket e o pedido
canônico do fiscal não se aplicam a esses disparos; valem a regra de quem planeja não executa,
os portões de início e fim e a conferência de escrita por efeito. A memória é injetada no início da sessão;
o extrator registra candidatos por hook, e `memory-sessions` lê transcrições locais do Codex
(`.jsonl` e `.jsonl.zst`; estas exigem `zstd` instalado).

### Claude Code

#### Tudo

```bash
npx @fullchico/harness@latest install
claude                                      # abre a sessão normalmente
```

No terminal interativo, escolha **1** para este fluxo do Claude Code; também pode usar
`install --target claude` para escolher sem menu.
O `install` escreve o fluxo do projeto num bloco gerenciado do `CLAUDE.md` e do `AGENTS.md` (todo pedido começa por `/tr:process-plan`; outras skills são ferramentas dentro dele). Sem portões configurados, o hook barra escrita de código até o `/tr:configure`. O `install` traz `tr` `memory`, `ponytail`
(código mínimo) e `mattpocock-skills` (o processo que o `tr` orquestra: `grilling`, `domain-modeling`,
`to-spec`, `to-tickets`, `tdd`, `code-review`), e liga o hook do `rtk`. Se o marketplace `fullchico` da
máquina apontar para outra fonte, o `install` para e mostra como trocar. O `install` não escolhe nem grava portões.
Com a stack decidida, o `/tr:configure` procura skills de boas práticas para cada tecnologia e separa o que é do projeto do que existe só na máquina do dono, propondo fixar no projeto o que importa (a instalação é aprovada pelo dono). O dono configura os portões com `/tr:configure`, que usa o diagnóstico do projeto e a entrevista
`grilling`. Para ver sugestões sem gravar, ou mudá-las depois: `npx @fullchico/harness gates --analyze` e
`gates --write`. O modelo de exemplo `gates --default` só grava se o dono o pedir
explicitamente. Um registro que já existe não é reescrito por um `install` de novo. O
marketplace fica preso a esta versão do plugin, e o `install` grava o modelo por papel em
`.claude/settings.local.json` (`"model": "opus"`, `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`), sem tocar no resto.

Instalar é passo do dono, no terminal. Gravar portões e modelos é decisão do dono, mas não exige
terminal: a sessão roda `tr-harness gates --register …` (o CLI do plugin, na mesma versão dele) e o
hook transforma a chamada num diálogo de permissão do Claude Code com o comando exato. A aprovação vale
uma vez, para aquele comando, por 2 minutos; sem ela, o CLI recusa gravar. Nos modos `auto`,
`bypassPermissions` e `dontAsk`, onde não há diálogo, a gravação volta para o terminal, com a linha pronta de
`tr-harness owner <args>`; o prefixo `!` roda dentro da sessão e também é recusado. O mesmo vale para o
aceite do critério de cada demanda (`tr-harness gates --accept`). O instalador não liga o sandbox nativo por padrão (perfil
`fluxo`, para o Docker do projeto funcionar); `install --sandbox` liga o perfil `isolado`, com o
registro protegido e só `docker` e `fullchico-harness` fora do sandbox. Se você já o usa, preserva a configuração. Depois de instalar, revise esses dois arquivos. Se a pasta ainda não
tinha Git, o instalador já executou `git init`.

Projeto com o harness antigo (`harness@fullchico`, `.harness/`) ou com os plugins `bugs`/`quality` da
2.x: `npx @fullchico/harness install --migrate` desliga o antigo no `settings.json` (plugin, hooks e
permissões de `.harness/`), tira `bugs@`/`quality@` e troca `bugs:cacador` por `tr:bug-hunter` no
registro. A pasta `.harness/` fica para você apagar; atualize o `AGENTS.md` se ele ainda mandar usar
`.harness/push`.

Para cadastrar um portão: monte um esboço `{"name": {portão}}` e rode
`npx @fullchico/harness gates --register esboco.json`; um portão de mesmo nome é substituído. Para trocar só
o comando de um portão: `gates --set <name> "<command>"`. Para tirar um portão: `gates --remove <name>`.

### Quanto a entrega custou

```bash
npx @fullchico/harness cost                      # a branch atual
npx @fullchico/harness cost --since 2026-11-22T21:55
```

Lê as transcrições do Claude Code e o livro de carimbos, sem gravar nada: tokens e US$ por modelo,
sessão principal contra subagentes, tempo ativo contra paradas, e bloqueios e carimbos dos portões.
O US$ é estimativa pelo preço de API e serve para comparar entregas e versões do plugin.

### Cada clone precisa do `install`

Ligar o plugin no `settings.json` não baixa o plugin. Isso é um limite da plataforma. Quem clona o
projeto roda o `add` (ou o `claude plugin install <name>@fullchico --scope project`) uma vez.

## Registro de portões

Fica em `.claude/harness.json`, chave `gates`. Cada portão tem um `stage` (`start`, `middle` ou `end`) e
um modo de assinar (`command`, `artifact` ou `agent`). Portões de meio são vinculados a um
ticket pelo campo `Middle:` e usam `gate <name> --ticket <path>`; nesta versão, aceitam
`command` ou `artifact`.

```json
{
  "code": ["apps", "packages"],
  "gates": {
    "process": {
      "stage": "start",
      "signs": "artifact",
      "artifact": "docs/specs/*/spec.md",
      "description": "spec da mudança, saída da entrevista (grilling)"
    },
    "quality": {
      "stage": "end",
      "signs": "command",
      "command": "pnpm lint && pnpm test"
    },
    "bugs": {
      "stage": "end",
      "signs": "agent",
      "agent": "tr:bug-hunter"
    },
    "e2e": {
      "stage": "end",
      "signs": "command",
      "command": "pnpm test:e2e",
      "always": false
    },
    "segredos": {
      "stage": "end",
      "signs": "command",
      "command": "gitleaks detect",
      "description": "none segredo no histórico"
    }
  }
}
```

- `signs: command`: o `tr:quality-checker` roda `gate <name>`. Passou, o hook carimba o estado atual.
- `signs: artifact`: `gate <name>` acha os arquivos do glob no projeto.
  Se houver `check`, esse comando passa recebendo-os. O carimbo é do plano.
- `signs: agent`: só o agente nomeado assina, pelo veredito APPROVED dele.
- `always` (padrão `true`): `false` torna o portão específico. No início, ele vale para tickets
  que o pedem em `Start:`. No fim, vale para tickets que o pedem em `Gates:` ou para a
  demanda cuja spec o pede nessa linha. Em demandas antigas, sem tickets com passaporte nem
  linha `Gates:` na spec, todos os portões de fim continuam exigidos.
- `code`: as pastas que são código do app. Sem a chave, é tudo menos `docs/`, `.claude/` e arquivos `.md`.

### Passaporte por ticket

Cada ticket em `docs/specs/<demanda>/issues/<NN>-<name>.md` declara seus bloqueadores
e os portões de fim específicos do trabalho:

```text
Status: open
Blocked by: 01, 02
Start: design
Gates: accessibility, e2e
Files: apps/web/**, packages/ui/**
```

Tickets sem bloqueio usam `Blocked by: none`; sem portões específicos, `Start: none`
ou `Gates: none`. Um portão de início com `always: false` só é exigido dos tickets que
o citam em `Start:`. O fiscal o carimba antes de liberar o executor.
O fiscal valida o estado atual do projeto. Depois, o orquestrador registra `Status: done` no ticket.
O `gate delivery` confere os carimbos, bloqueios e ciclos. Se o código mudar após a validação,
o passaporte pede novos carimbos. A demanda ativa fica em `.claude/current-demand` (o slug da pasta
em `docs/specs/`), para tickets antigos não entrarem na entrega atual. Os portões
`always: true` do registro continuam exigidos do resultado integrado. Se há tickets com passaporte,
portões opcionais sem pedido na spec valem apenas nos tickets que os declaram.

O comando `gate`, sem argumento, lista cada portão com `ok`, `falta` ou `fora` (fora do passaporte
desta demanda), o momento, o modo de assinar e, se falta, o invoker que o valida. `gate <name>` roda a verificação e termina com
`gate <name>: passou` ou `gate <name>: FALHOU (<motivo>)`. Ao terminar, rode
`fullchico-harness deliver` ou `gate delivery`; o hook Stop confere de novo quando a resposta final
começa com `ENTREGA: concluída`.

**O registro é protegido na sessão.** O hook barra edições diretas e o CLI recusa alterações
quando chamado pelo shell do Claude. Se o sandbox nativo estiver ligado, `gates --write`
também põe `.claude/harness.json` no `denyWrite`.

## Limites honestos

- Os hooks só valem dentro da sessão da plataforma em que foram instalados. A validação final explícita
  funciona também no terminal; `git push` não é o gatilho da entrega.
- O agente e os hooks rodam como o mesmo usuário da máquina: não existe assinatura que o agente seja
  fisicamente incapaz de imitar. A garantia do certificado vem de três camadas: o guard barra o agente de
  escrever no apêndice ou forjar o trailer; tudo fica no Git e aparece no diff do PR; e qualquer um
  recalcula os hashes, então um certificado copiado para outro conteúdo não bate.
- Sem o sandbox nativo, comandos arbitrários podem contornar hooks e alterar arquivos;
  os portões funcionam como guardrails de fluxo, não como isolamento do sistema.
- O certificado prova que a etapa aconteceu contra o critério aceito, não que o revisor foi bom.
- No Codex o peixe não fica isolado como no Claude: os conectores MCP do usuário saem, mas os plugins e skills
  de usuário do Codex ainda carregam. E, no modo protegido, o Codex não grava em `.git` nem escuta numa porta:
  o orquestrador faz o commit e roda essas conferências por ele.
- Uma tela que só uma pessoa responde (confiar numa pasta nova, revisar um hook que mudou) para o peixe até o
  dono responder; o maestro mostra a tela, mas não responde por ele.

## Licença

MIT.
