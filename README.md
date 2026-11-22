<img src="site/trem.svg" alt="" width="72" align="right">

# FullChico Harness

[![npm](https://img.shields.io/npm/v/@fullchico/harness?label=npm&color=1d1b16)](https://www.npmjs.com/package/@fullchico/harness)
[![ci](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/fullchico/fullchico-harness/actions/workflows/ci.yml)

[Página do projeto](https://fullchico.github.io/fullchico-harness/) · [Pacote no npm](https://www.npmjs.com/package/@fullchico/harness)

```bash
npx @fullchico/harness@latest add bugs qualidade
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

*Status: disponível. O portão vem no `tr`; a skill `tr:configurar` entrevista o dono
(usando a `grilling` do `mattpocock-skills` quando ligado) e escreve o registro.*

### 3. Paralelismo com grafo

Cards com dependências; a fronteira roda junto.

*Status: a vir, no plugin `orquestracao`.*

### 4. Loops

O loop gira até os carimbos fecharem; o meio do fluxo é livre.

*Status: a vir, no plugin `orquestracao`.*

### 5. Guardrails

O sandbox do Claude Code; a proteção do `.claude/trilho.json` (só o plugin `tr` escreve) e,
com registro, a do `.claude/settings.json`. Custam zero e não se customizam.

*Status: disponível.*

### 6. Portões

Só no começo (barra a escrita) ou no fim (barra o envio: `git push`, `gh pr create`). O meio é
livre. Customizáveis pelo registro `.claude/trilho.json`, protegido.

*Status: disponível.*

### 7. Validações

O que assina um carimbo. São três jeitos:

| Jeito | Assina quando |
|---|---|
| **comando** | `portao <nome>` roda o comando e ele passa |
| **agente** | o veredito do agente é aprovado (ex.: o caçador de bugs) |
| **artefato** | o arquivo existe, está em commit e passa na validação |

O carimbo guarda o commit, a versão do portão e a impressão digital; commit novo pede carimbo
novo.

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
| `tr` | o núcleo: modo puro, registro de portões, comando `portao`, aplicador único | disponível |
| `memoria` | mapa do código e notas ancoradas, injetados no começo da sessão | disponível |
| `bugs` | o caçador de bugs lê o diff; aprovado, carimbo no fim | opção sugerida quando o projeto não tem validador próprio |
| `qualidade` | roda a checagem do projeto; passou, carimbo no fim | opção sugerida quando o projeto não tem validador próprio |
| `orquestracao` | grafo de cards, loop e worktrees | a vir |
| `planejamento` | o portão de começo, com a entrevista | a vir como skill fina do `tr`, não como plugin separado |
| `seguranca` | revisão de segurança, carimbo no fim | a vir |

Cada plugin é independente e se liga só no projeto (`--scope project`).

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
`portoes --gravar`; `portoes --padrao` grava o registro padrão da lib.

> **Atenção:** `cc` sobrepõe o `/usr/bin/cc` do sistema (compilador de C). Quem precisa do
> compilador chama `/usr/bin/cc` direto ou cria um alias.

### Só o que quiser

```bash
npx @fullchico/harness@latest add bugs qualidade
```

O `qualidade` lê o comando do projeto em `.claude/trilho.json`:

```json
{"qualidade": {"comando": "pnpm lint && pnpm test"}}
```

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
      "agente": "bugs:cacador"
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

- `assina: comando`: `portao <nome>` roda o comando. Passou, com a árvore limpa, o hook carimba o commit.
- `assina: artefato`: `portao <nome>` acha os arquivos do glob alterados nesta branch, em commit.
  Se houver `valida`, esse comando passa recebendo-os. O carimbo é do plano.
- `assina: agente`: só o agente nomeado assina, pelo veredito APPROVED dele.
- `codigo`: as pastas que são código do app. Sem a chave, é tudo menos `docs/`, `.claude/`, `.md` e o ignorado pelo git.

O comando `portao`, sem argumento, lista cada portão com `ok` ou `falta`, o momento, o modo de
assinar e, se falta, o que fazer. `portao <nome>` roda a verificação e termina com
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
