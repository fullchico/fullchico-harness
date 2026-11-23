<img src="site/trem.svg" alt="" width="72" align="right">

# FullChico Harness

[![npm](https://img.shields.io/npm/v/@fullchico/harness?label=npm&color=1d1b16)](https://www.npmjs.com/package/@fullchico/harness)
[![ci](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml)

[Página do projeto](https://fullchico.github.io/fullchico-harness/) · [Pacote no npm](https://www.npmjs.com/package/@fullchico/harness)

```bash
npx @fullchico/harness@latest install
```

**Harness de plugins para Claude Code: confiabilidade por portões e qualidade.** Cada projeto monta
o próprio harness com plugins ligados só nele, sem poluir a configuração global. Planejamento,
qualidade e envio são **portões**: cada um deixa um **carimbo** assinado por hook, e sem o carimbo
o Claude não escreve código novo nem envia. A lib é distribuída como pacote Node por conveniência
(`npx` em uma linha), mas o conceito é plugin de Claude Code, não biblioteca de aplicação.

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

O conjunto do projeto: os plugins ligados, o registro de portões e a configuração. Fica em
`.claude/`, versionado com o código.

**Modo puro.** O projeto roda só com o que declara em `.claude/` mais o escopo local
(`.claude/settings.local.json`, a ferramenta pessoal de quem usa, como Orca e rtk). O global do
usuário não entra. Ative com `npx @fullchico/harness puro` e abra a sessão com `cc`
no lugar de `claude`.

*Status: disponível.*

### 2. Planejamento

O portão de começo, assinado por um artefato (OpenSpec, `docs/specs/*/spec.md`) ou por comando. A
lib não entrevista produto nem força uma stack de processo: ela liga a etapa à ferramenta que o
projeto já usa.

Cada demanda começa por `/tr:processo-planejar`: a entrevista (`grilling` + `domain-modeling` do
`mattpocock-skills`), a spec com o **passaporte** (a linha `Portões:` diz os portões opcionais que a
demanda pede) e os tickets, cada um com a `Complexidade:` que decide o modelo de quem o executa.

*Status: disponível. O portão vem no `tr`; `/tr:configurar` entrevista o dono e propõe o registro.*

### 3. Paralelismo com grafo

Cards com dependências; a fronteira roda junto.

*Status: conduzido pela skill `/tr:processo-planejar` (tickets com `Bloqueado por:`); o grafo com
trava por hook vem no plugin `orquestracao`.*

### 4. Loops

O loop gira até os carimbos fecharem; o meio do fluxo é livre.

*Status: a vir, no plugin `orquestracao`.*

### 5. Guardrails

O sandbox do Claude Code; a proteção do `.claude/trilho.json` (só o plugin `tr` escreve) e,
com registro, a do `.claude/settings.json`. Com registro, o hook também:

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

Só no começo (barra a escrita) ou no fim (barra o envio: `git push`, `gh pr create`). O meio é
livre. Customizáveis pelo registro `.claude/trilho.json`, protegido.

*Status: disponível.*

### 7. Validações

O que assina um carimbo. São três jeitos:

| Jeito | Assina quando |
|---|---|
| **comando** | o `tr:qualidade-verificador`, um subagente limpo por portão, roda `portao <nome>` e passa (`/tr:qualidade-verificar`) |
| **agente** | o veredito do agente é aprovado (ex.: `tr:bugs-cacador`, por `/tr:bugs-cacar`) |
| **artefato** | o arquivo existe, está em commit e passa na validação |

**Quem escreveu não assina.** Todo portão de fim é validado num subagente de contexto limpo, com o
pedido escrito pelo hook; o `portao` rodado pela sessão principal mostra o resultado, mas não carimba.
Cada validador valida só o que o portão dele propõe.

O carimbo guarda o commit, a versão do portão e a impressão digital; commit novo pede carimbo
novo. A exceção é commit só de documentação (`docs/` ou `.md`) depois do carimbo de fim: ele não muda
o que os portões verificaram, e o carimbo continua valendo (`portao` mostra de qual commit ele veio).

*Status: disponível.*

### 8. Memória organizada

Mapa do código e notas ancoradas, por projeto, injetadas no começo de cada sessão, no plugin
`memoria`: `/memoria:mapear` atualiza o mapa, a skill `memoria:dream` consolida o que as sessões
ensinaram (proposto por um extrator isolado, conferido contra o código) e `/memoria:aprender` mede
o consumo e faz a retrospectiva depois de uma entrega.

*Status: disponível.*

## Plugins

| Plugin | O que faz | Estado |
|---|---|---|
| `tr` | os portões: registro, `portao`, aplicador único, validadores, passaporte, modelo por papel, modo puro | disponível |
| `memoria` | mapa do código e notas ancoradas, injetados no começo da sessão | disponível |
| `orquestracao` | grafo de cards com trava por hook, loop e worktrees | a vir |

Todo portão mora no `tr`, com invoker `/tr:<portão>-<ação>`:

| Invoker | Validador | Valida só |
|---|---|---|
| `/tr:processo-planejar` | (a sessão que planeja) | abre a demanda: entrevista, spec, tickets, orquestra |
| `/tr:qualidade-verificar` | `tr:qualidade-verificador` (haiku), um por portão de comando | o comando daquele portão |
| `/tr:bugs-cacar` | `tr:bugs-cacador` (sonnet) | defeitos no diff |

Os plugins `bugs` e `qualidade` da 2.x foram absorvidos pelo `tr` na 3.0. Cada plugin se liga só no
projeto (`--scope project`).

## Instalar

### Tudo

```bash
npx @fullchico/harness@latest install
npx @fullchico/harness puro                 # liga o modo puro
cc                                          # abre a sessão no modo do projeto
```

`cc` (de "claude clean") passa a ser o lançador. O `install` traz `tr`, `memoria`, `ponytail`
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
antes de gravar qualquer coisa. Depois de instalar, faça o commit desses dois arquivos: carimbo de
fim só assina com a árvore limpa.

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

- `assina: comando`: o `tr:qualidade-verificador` roda `portao <nome>`. Passou, com a árvore limpa, o hook carimba o commit.
- `assina: artefato`: `portao <nome>` acha os arquivos do glob alterados nesta branch, em commit.
  Se houver `valida`, esse comando passa recebendo-os. O carimbo é do plano.
- `assina: agente`: só o agente nomeado assina, pelo veredito APPROVED dele.
- `sempre` (portão de fim, padrão `true`): `false` torna o portão opcional; ele só vale para a demanda
  cuja spec o pede na linha `Portões:`. Sem a linha, todos os de fim valem.
- `codigo`: as pastas que são código do app. Sem a chave, é tudo menos `docs/`, `.claude/`, `.md` e o ignorado pelo git.

O comando `portao`, sem argumento, lista cada portão com `ok`, `falta` ou `fora` (fora do passaporte
desta demanda), o momento, o modo de assinar e, se falta, o invoker que o valida. `portao <nome>` roda a verificação e termina com
`portao <nome>: passou` ou `portao <nome>: FALHOU (<motivo>)`.

**O registro é protegido.** Só o dono altera: o agente não edita `.claude/trilho.json` nem
`.claude/settings.json`, e `portoes --gravar` o põe no `denyWrite` do sandbox.

## Limites honestos

- Os hooks só valem dentro de sessões do Claude Code. Um `git push` no terminal, fora da sessão,
  não é barrado.
- Projeto sem sandbox permite, em tese, forjar o arquivo do carimbo.
- O carimbo prova que a etapa aconteceu, não que o revisor foi bom.

## Licença

MIT.
