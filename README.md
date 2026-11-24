<img src="site/trem.svg" alt="" width="72" align="right">

# FullChico Harness

[![npm](https://img.shields.io/npm/v/@fullchico/harness?label=npm&color=1d1b16)](https://www.npmjs.com/package/@fullchico/harness)
[![ci](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml)

[Página do projeto](https://fullchico.github.io/fullchico-harness/) · [Pacote no npm](https://www.npmjs.com/package/@fullchico/harness)

```bash
npx @fullchico/harness@latest install
```

**Harness por projeto para Claude Code e Codex: prompts, portões e memória.** Cada projeto monta
o próprio harness com plugins ligados só nele, sem poluir a configuração global. Planejamento,
qualidade e entrega são **portões**: cada um deixa um **carimbo** assinado por hook. O início libera a
escrita; a entrega é validada quando o modelo termina o trabalho. O instalador inicia Git se necessário;
push e PR não são requisitos da entrega. A lib é distribuída como pacote Node por conveniência
(`npx` em uma linha); integra os recursos de projeto de Claude Code e Codex, não é biblioteca de aplicação.

O `install` usa o Git local e executa `git init` se necessário. Não configura remoto. Um projeto
pode exigir um remoto ou publicação por meio de um portão próprio em `.claude/trilho.json`.
Por exemplo, um portão de comando pode verificar `git remote get-url <nome>`; o nome e o momento
desse portão são escolhidos pelo projeto.

## Sumário

- [A divisão](#a-divisão)
- [Os oito conceitos](#os-oito-conceitos)
- [Plugins](#plugins)
- [Instalar](#instalar)
- [Registro de portões](#registro-de-portões)
- [Limites honestos](#limites-honestos)
- [Licença](#licença)

## A divisão

**A lib garante o caminho (orquestração) e a aprendizagem (memória). Começo e fim ficam com as
ferramentas do seu projeto, ligadas pelos portões.**

## Os oito conceitos

### 1. Harness

O conjunto do projeto: os plugins ligados, os prompts, o registro de portões e a configuração.
Fica em `.claude/` e `.codex/`, na pasta do projeto; o registro compartilhado é
`.claude/trilho.json`.

**Modo puro.** O projeto roda só com o que declara em `.claude/` mais o escopo local
(`.claude/settings.local.json` e ferramentas pessoais locais, como rtk). O global do
usuário não entra. Ative com `npx @fullchico/harness puro` e abra a sessão com `cc`
no lugar de `claude`.

*Status: disponível.*

### 2. Planejamento

O portão de começo, assinado por um artefato (OpenSpec, `docs/specs/*/spec.md`) ou por comando. A
lib não entrevista produto nem força uma stack de processo: ela liga a etapa à ferramenta que o
projeto já usa.

Cada demanda começa por `/tr:processo-planejar`: a entrevista (`/tr:grill-me`, incluída a partir do
fluxo de Matt Pocock, e `domain-modeling` do `mattpocock-skills`), a spec com o **passaporte** (a linha `Portões:` diz os portões opcionais que a
demanda pede) e os tickets, cada um com a `Complexidade:` que decide o modelo de quem o executa.

*Status: disponível. O portão vem no `tr`; `/tr:configurar` entrevista o dono e propõe o registro.*

`/tr:configurar` começa pelos diagnósticos disponíveis (`claude doctor` e `codex doctor --json`),
analisa scripts, CI e ferramentas do projeto e usa `/tr:grill-me` para decidir com o dono os
portões de entrada e saída. O fluxo de entrevista de Matt Pocock está incluído no plugin `tr`,
com atribuição em `plugins/tr/THIRD_PARTY_NOTICES.md`. Os três portões padrão são somente um
ponto de partida: novos portões podem ter nomes e verificadores próprios. A IA entrega o
esboço e os comandos; quem grava o registro protegido é o dono.

### 3. Paralelismo com grafo

Tickets com `Bloqueado por:` formam um grafo. A fronteira contém os tickets cujos bloqueadores
já foram concluídos e carimbados; o hook impede o disparo antecipado de um executor. Tickets
independentes podem avançar em contextos isolados. A skill `/tr:processo-planejar` coordena
os subagentes, os fiscais e a integração.

*Status: disponível no `tr` para tickets em `docs/specs/<demanda>/issues/`.*

### 4. Loops

Cada fiscal valida o estado atual do ticket. Se reprovar, o implementador corrige e o fiscal
reexamina. Só o trabalho aprovado entra no passaporte e libera os dependentes.

*Status: conduzido pela skill `/tr:processo-planejar`; a conferência final é aplicada pelo hook.*

### 5. Guardrails

O sandbox do Claude Code; a proteção do `.claude/trilho.json` (só o plugin `tr` escreve) e,
com registro, a do `.claude/settings.json` e do `.claude/settings.local.json` (e de `.git/`). Com registro, o hook também:

- escreve o pedido de cada validador (o que quem escreveu o código disse é descartado);
- mantém o validador só leitura;
- fixa o **modelo por papel**: a sessão principal (opus, gravado no `.claude/settings.local.json` pelo
  `install`) planeja e orquestra; o subagente de ticket `Complexidade: simples` roda em haiku, o de
  `complexa` (ou sem marca) em sonnet; subagente nunca roda em opus;
- barra `portao <nome>` combinado com pipe ou `&&` (rodaria sem carimbar) e os scripts do harness
  antigo (`.harness/`).

Custam zero e não se customizam.

*Status: disponível.*

### 6. Portões

Só no começo (requisitos antes da escrita) ou no fim (validação da entrega). O meio é
orquestrado pelo grafo de tickets. Customizáveis pelo registro `.claude/trilho.json`, protegido.

*Status: disponível.*

### 7. Validações

O que assina um carimbo. São três jeitos:

| Jeito | Assina quando |
|---|---|
| **comando** | o `tr:qualidade-verificador`, um subagente limpo por portão, roda `portao <nome>` e passa (`/tr:qualidade-verificar`) |
| **agente** | o veredito do agente é aprovado (ex.: `tr:bugs-cacador`, por `/tr:bugs-cacar`) |
| **artefato** | o fiscal confirma que o arquivo existe e passa na validação |

**Quem produziu a evidência não assina.** Portões de início e fim são validados num subagente de contexto limpo, com o
pedido escrito pelo hook; o `portao` rodado pela sessão principal mostra o resultado, mas não carimba.
Cada validador valida só o que o portão dele propõe.

O carimbo guarda uma impressão digital do estado atual. Alteração de código pede novo carimbo;
mudanças apenas em `docs/` ou arquivos `.md` não invalidam portões de fim.

*Status: disponível.*

### 8. Memória organizada

Mapa do código e notas ancoradas, por projeto, injetadas no começo de cada sessão, no plugin
`memoria`: `/tr:memory-mapear` atualiza o mapa, `/tr:memory-dream` consolida o que as sessões
ensinaram (proposto por um extrator isolado, conferido contra o código) e `/tr:memory-aprender` mede
o consumo e faz a retrospectiva depois de uma entrega.

*Status: disponível.*

## Plugins

| Plugin | O que faz | Estado |
|---|---|---|
| `tr` | os portões: registro, `portao`, aplicador único, validadores, passaporte, modelo por papel, modo puro | disponível |
| `memoria` | mapa do código e notas ancoradas, injetados no começo da sessão | disponível |
| `orquestracao` | automação dedicada de worktrees e execução em segundo plano | a vir; o grafo, a fronteira e a conferência já estão no `tr` |

Toda skill própria é acionada pelo `tr`, inclusive as de memória, com invoker `/tr:<nome>`:

| Invoker | Validador | Valida só |
|---|---|---|
| `/tr:processo-planejar` | (a sessão que planeja) | abre a demanda: entrevista, spec, tickets, orquestra |
| `/tr:qualidade-verificar` | `tr:qualidade-verificador` (haiku), um por portão de comando | o comando daquele portão |
| `/tr:bugs-cacar` | `tr:bugs-cacador` (sonnet) | defeitos no diff |
| `/tr:memory-mapear` | subagentes de leitura | mapa do código |
| `/tr:memory-dream` | `memoria:extrator` (haiku) | notas de sessões conferidas com o código |
| `/tr:memory-aprender` | (a sessão que fecha a entrega) | retrospectiva e consolidação |
| `/tr:grill-me` | (a sessão que entrevista) | decisões em rodadas para planejar e configurar trilhos e portões |

Os plugins `bugs` e `qualidade` da 2.x foram absorvidos pelo `tr` na 3.0. Em Claude Code, cada
plugin usa `--scope project`. Em Codex, o marketplace local `.agents/plugins/marketplace.json`
aponta para as cópias em `.codex/harness/`, e `.codex/config.toml` habilita `tr` e `memoria` no
projeto. Os prompts vêm das skills de cada plugin.

## Instalar

### Codex

```bash
npx @fullchico/harness@latest install --ambiente codex
```

`install` abre um menu no terminal para escolher **Claude Code**, **Codex** ou **ambos**. A escolha
padrão é **ambos**, inclusive sem terminal interativo. Em automações, use
`--ambiente claude|codex|ambos` para fixar a escolha. `install-codex` permanece como atalho.

O instalador monta os plugins `tr` e `memoria` em `.codex/harness/`, registra o marketplace local
em `.agents/plugins/marketplace.json`, habilita ambos em `.codex/config.toml` e cria três agentes
em `.codex/agents/`. As oito skills próprias e o fluxo `grill-me` incluído ficam em `tr`; o prompt auxiliar fica
em `.agents/skills/`. Instala também todas as skills de
[Ponytail](https://www.skills.sh/dietrichgebert/ponytail) e
[Matt Pocock](https://www.skills.sh/mattpocock/skills) pelo skills CLI, direcionadas ao Codex.
O registro de portões fica em
`.claude/trilho.json` e é compartilhado com Claude Code quando os dois estão instalados.
`install --ambiente codex --padrao` usa os portões padrão; sem a opção, analisa o projeto. Rodar o
instalador novamente preserva a configuração de outros plugins, hooks e registro existentes.
Abra uma sessão nova em um projeto
confiável e aceite os hooks locais quando o Codex pedir. Use a skill `tr-codex` para executar
as validações e consultar a memória. As skills próprias aparecem como `$tr-memory-mapear`,
`$tr-memory-dream` e `$tr-memory-aprender`. O estado pode ser visto com
`python3 -I .codex/harness/tr/scripts/portao.py`.

O Codex usa os mesmos scripts de portões, com um adaptador para `Bash`, `apply_patch` e
subagentes. A cobertura de hooks depende das ferramentas locais que o Codex expõe; ferramentas
fora desse caminho e comandos rodados fora da sessão não são barrados. Os hooks locais só
executam depois da revisão de confiança do usuário. A memória é injetada no início da sessão;
o extrator registra candidatos por hook, e `memoria-sessoes` lê transcrições locais do Codex
(`.jsonl` e `.jsonl.zst`; estas exigem `zstd` instalado).

### Claude Code

#### Tudo

```bash
npx @fullchico/harness@latest install
npx @fullchico/harness puro                 # liga o modo puro
cc                                          # abre a sessão no modo do projeto
```

No terminal interativo, escolha **1** para este fluxo do Claude Code; também pode usar
`install --ambiente claude` para escolher sem menu. `cc` (de "claude clean") passa a ser o lançador.
O `install` traz `tr` (incluindo `grill-me`), `memoria`, `ponytail`
(código mínimo) e `mattpocock-skills` (processo e revisão: `grilling`, `domain-modeling`, `tdd`,
`clean-code-guard`...), e liga o hook do `rtk`. O `install` analisa o que o projeto já usa (specs,
OpenSpec, scripts do `package.json`) e grava os portões em `.claude/trilho.json`. Para ver a
proposta sem gravar, ou mudá-la depois: `npx @fullchico/harness portoes --analisar` e
`portoes --gravar`; `portoes --padrao` grava o registro padrão da lib (com o comando de qualidade
tirado do `package.json`). Um registro que já existe não é reescrito por um `install` de novo. O
marketplace fica preso a esta versão da lib, e o `install` grava o modelo por papel em
`.claude/settings.local.json` (`"model": "opus"`, `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`), sem tocar no resto.

Instalar e gravar portões são passos **do dono, no terminal**: dentro de uma sessão com sandbox,
`.claude/settings.json` e `.claude/trilho.json` são protegidos do agente, e os dois comandos param
antes de gravar qualquer coisa. Depois de instalar, revise esses dois arquivos. Se a pasta ainda não
tinha Git, o instalador já executou `git init`.

Projeto com o harness antigo (`harness@fullchico`, `.harness/`) ou com os plugins `bugs`/`qualidade` da
2.x: `npx @fullchico/harness install --migrar` desliga o antigo no `settings.json` (plugin, hooks e
permissões de `.harness/`), tira `bugs@`/`qualidade@` e troca `bugs:cacador` por `tr:bugs-cacador` no
registro. A pasta `.harness/` fica para você apagar; atualize o `AGENTS.md` se ele ainda mandar usar
`.harness/push`.

Portão novo, além dos que o `install` grava: monte um esboço `{"nome": {portão}}` e rode
`npx @fullchico/harness portoes --registrar esboco.json`. Para trocar só o comando de um portão:
`portoes --definir <nome> "<comando>"`.

### Quanto a entrega custou

```bash
npx @fullchico/harness custo                      # a branch atual
npx @fullchico/harness custo --desde 2026-11-22T21:55
```

Lê as transcrições do Claude Code e o livro de carimbos, sem gravar nada: tokens e US$ por modelo,
sessão principal contra subagentes, tempo ativo contra paradas, e bloqueios e carimbos dos portões.
O US$ é estimativa pelo preço de API e serve para comparar entregas e versões da lib.

> **Atenção:** `cc` sobrepõe o `/usr/bin/cc` do sistema (compilador de C). Quem precisa do
> compilador chama `/usr/bin/cc` direto ou cria um alias.

### Cada clone precisa do `install`

Ligar o plugin no `settings.json` não baixa o plugin. Isso é um limite da plataforma. Quem clona o
projeto roda o `add` (ou o `claude plugin install <nome>@fullchico --scope project`) uma vez.

## Registro de portões

Fica em `.claude/trilho.json`, chave `portoes`. Cada portão tem um `momento` (`inicio` ou `fim`) e
um modo de assinar (`comando`, `artefato` ou `agente`).

```json
{
  "codigo": ["apps", "packages"],
  "portoes": {
    "processo": {
      "momento": "inicio",
      "assina": "artefato",
      "artefato": "docs/specs/*/spec.md",
      "descricao": "spec da mudança, saída da entrevista (grill-me)"
    },
    "qualidade": {
      "momento": "fim",
      "assina": "comando",
      "comando": "pnpm lint && pnpm test"
    },
    "bugs": {
      "momento": "fim",
      "assina": "agente",
      "agente": "tr:bugs-cacador"
    },
    "e2e": {
      "momento": "fim",
      "assina": "comando",
      "comando": "pnpm test:e2e",
      "sempre": false
    },
    "segredos": {
      "momento": "fim",
      "assina": "comando",
      "comando": "gitleaks detect",
      "descricao": "nenhum segredo no histórico"
    }
  }
}
```

- `assina: comando`: o `tr:qualidade-verificador` roda `portao <nome>`. Passou, o hook carimba o estado atual.
- `assina: artefato`: `portao <nome>` acha os arquivos do glob no projeto.
  Se houver `valida`, esse comando passa recebendo-os. O carimbo é do plano.
- `assina: agente`: só o agente nomeado assina, pelo veredito APPROVED dele.
- `sempre` (padrão `true`): `false` torna o portão específico. No início, ele vale para tickets
  que o pedem em `Entrada:`. No fim, vale para tickets que o pedem em `Portões:` ou para a
  demanda cuja spec o pede nessa linha. Em demandas antigas, sem tickets com passaporte nem
  linha `Portões:` na spec, todos os portões de fim continuam exigidos.
- `codigo`: as pastas que são código do app. Sem a chave, é tudo menos `docs/`, `.claude/` e arquivos `.md`.

### Passaporte por ticket

Cada ticket em `docs/specs/<demanda>/issues/<NN>-<nome>.md` declara seus bloqueadores
e os portões de fim específicos do trabalho:

```text
Status: open
Bloqueado por: 01, 02
Entrada: design
Portões: acessibilidade, e2e
Arquivos: apps/web/**, packages/ui/**
```

Tickets sem bloqueio usam `Bloqueado por: nenhum`; sem portões específicos, `Entrada: nenhum`
ou `Portões: nenhum`. Um portão de início com `sempre: false` só é exigido dos tickets que
o citam em `Entrada:`. O fiscal o carimba antes de liberar o executor.
O fiscal valida o estado atual do projeto. Depois, o orquestrador registra `Status: done` no ticket.
O `portao entrega` confere os carimbos, bloqueios e ciclos. Se o código mudar após a validação,
o passaporte pede novos carimbos. A demanda ativa fica em `.claude/demanda-atual` (o slug da pasta
em `docs/specs/`), para tickets antigos não entrarem na entrega atual. Os portões
`sempre: true` do registro continuam exigidos do resultado integrado. Se há tickets com passaporte,
portões opcionais sem pedido na spec valem apenas nos tickets que os declaram.

O comando `portao`, sem argumento, lista cada portão com `ok`, `falta` ou `fora` (fora do passaporte
desta demanda), o momento, o modo de assinar e, se falta, o invoker que o valida. `portao <nome>` roda a verificação e termina com
`portao <nome>: passou` ou `portao <nome>: FALHOU (<motivo>)`. Ao terminar, rode
`fullchico-harness entregar` ou `portao entrega`; o hook Stop confere de novo quando a resposta final
começa com `ENTREGA: concluída`.

**O registro é protegido.** Só o dono altera: o agente não edita `.claude/trilho.json` nem
`.claude/settings.json`, e `portoes --gravar` o põe no `denyWrite` do sandbox.

## Limites honestos

- Os hooks só valem dentro da sessão da plataforma em que foram instalados. A validação final explícita
  funciona também no terminal; `git push` não é o gatilho da entrega.
- Projeto sem sandbox permite, em tese, forjar o arquivo do carimbo.
- O carimbo prova que a etapa aconteceu, não que o revisor foi bom.

## Licença

MIT.
