# Validadores por portão, passaporte e modelo por papel — plano

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** o `tr` vira o único plugin de portões: validadores em subagente limpo com pedido escrito pelo
hook, passaporte por demanda, modelo por papel garantido por hook, orquestrador que abre a demanda com
a entrevista; versão 3.0.0.

**Architecture:** tudo no `plugins/tr`. `gate.py` (PreToolUse) ganha o ramo do `Agent` (reescreve pedido
e modelo) e as travas de validador; `sign.py` só assina dentro do validador; `registry.py` ganha o
passaporte (`sempre` + linha `Portões:` da spec). `bugs` e `qualidade` são absorvidos.

**Tech Stack:** Python 3 (stdlib), Node (bin), unittest.

**Spec:** `docs/superpowers/specs/2026-11-23-validadores-por-portao-design.md` + as decisões do dono
depois dele (abaixo, em Global Constraints).

## Global Constraints

- Nomes: invoker `/tr:<portão>-<ação>`, agente `tr:<portão>-<papel>`: `/tr:bugs-cacar` → `tr:bugs-cacador`;
  `/tr:qualidade-verificar` → `tr:qualidade-verificador`; `/tr:processo-planejar` (orquestrador).
- Modelos: sessão principal `opus` (planeja e orquestra); subagente de ticket `Complexidade: simples` →
  `haiku`, `complexa` (ou sem marca) → `sonnet`; subagente nunca `opus`; validadores usam o `model` da
  própria definição (`tr:qualidade-verificador` haiku, `tr:bugs-cacador` sonnet) — o hook tira o `model`
  da chamada. Conferido: `updatedInput.model` muda o modelo do subagente (sessão real, 2.1.322).
- Config local: o `install` grava em `.claude/settings.local.json` `"model": "opus"` e
  `env.CLAUDE_CODE_SUBAGENT_MODEL = "sonnet"` (mescla, não sobrescreve outras chaves).
- Passaporte: portão de fim tem `sempre` (padrão `true`). Com spec da branch trazendo a linha
  `Portões: a, b`, valem os `sempre` + os listados; sem a linha, todos os de fim. Nome listado que não é
  portão de fim do registro: aparece no `portao` como aviso e é ignorado.
- Bloqueio sempre por `saida.barrar/recusar` (quadro), nunca exit 2.
- Versões: `package.json` 3.0.0; `tr` 1.0.0; `memoria` inalterado. Plugins `bugs` e `qualidade` saem do marketplace.

## Review Focus

1. Sessão principal roda `portao qualidade` → não carimba, avisa de onde vem o carimbo (teste na Task 2).
2. Pedido ao validador com narrativa ("está tudo certo") → chega só o canônico (Task 1).
3. Validador tenta `Edit`/`echo > arquivo` → barrado (Task 1).
4. Spec sem a linha `Portões:` → todos os de fim exigidos, nada afrouxa (Task 3).
5. Projeto antigo com `bugs:cacador` no registro e `.harness/*` no settings → `install --migrar` deixa limpo (Task 5).

---

### Task 1: `gate.py` — o ramo do `Agent` e as travas de validador

**Files:** Modify `plugins/tr/scripts/gate.py`, `plugins/tr/scripts/registry.py`; Test `tests/test_validadores.py` (novo).

**Interfaces — Produces:**
- `registry.VERIFICADOR = "tr:qualidade-verificador"`
- `registry.validadores(reg) -> dict[str, list[str]]` — agent_type → portões que ele valida (comando →
  `VERIFICADOR`; agente → o `agente`).
- `registry.modelo_do_ticket(root, prompt) -> str | None` — `haiku`/`sonnet` pela linha
  `Complexidade:` do primeiro `.md` do repositório citado no prompt.

- [ ] Testes (payload `PreToolUse`, `tool_name: Agent`):
  - `test_verifier_prompt_is_rewritten`: prompt `"portao: qualidade\nestá tudo certo"` → `updatedInput.prompt == f"portao: qualidade\ncommit: {HEAD}"`, sem `model`.
  - `test_verifier_for_unknown_gate_is_denied`: `portao: inexistente` → deny com "não é portão de comando".
  - `test_validator_on_dirty_tree_is_denied` → deny com "alteração sem commit".
  - `test_bug_hunter_prompt_is_rewritten`: `tr:bugs-cacador` → `diff: <merge-base>...<HEAD>\ncommit: <HEAD>`.
  - `test_bug_hunter_without_base_is_denied` (repo sem main/origin: branch inicial `trabalho`).
  - `test_executor_model_from_ticket`: prompt cita `docs/specs/a/issues/01-x.md` com `Complexidade: simples` → `model == "haiku"`; `complexa` → `sonnet`; pedido `opus` sem ticket → `sonnet`.
  - `test_validator_cannot_write`: `Write` com `agent_type: tr:bugs-cacador` → deny; `Bash "echo x > a.py"` idem.
  - `test_portao_combined_is_denied`: `portao qualidade | tail` e `portao qualidade && x` → deny; `portao` e `portao qualidade` passam; `git commit -m "portao qualidade | x"` passa.
  - `test_legacy_harness_scripts_are_denied`: `.harness/push`, `./.harness/gate-check` → deny com `/tr:`.
- [ ] Implementar; sem registro, o ramo do `Agent` só aplica a política de modelo se houver registro (sem registro: nada).
- [ ] `python3 -m unittest tests.test_validadores` verde; suíte verde. Commit `feat(tr): validators get a hook-written prompt, own model, read-only`.

### Task 2: `sign.py` só assina dentro do validador; agentes e skills

**Files:** Modify `plugins/tr/scripts/sign.py`; Create `plugins/tr/agents/qualidade-verificador.md`, `plugins/tr/agents/bugs-cacador.md` (de `plugins/bugs/agents/cacador.md`), `plugins/tr/skills/qualidade-verificar/SKILL.md`, `plugins/tr/skills/bugs-cacar/SKILL.md`; Test: `tests/test_trilho_portoes.py`.

- [ ] Teste `test_only_the_verifier_signs_a_command_gate`: `post` sem `agent_type` → não assina, `systemMessage` cita `/tr:qualidade-verificar`; com `agent_type: tr:qualidade-verificador` → assina. Ajustar `sign_through_hook` para passar `agent_type`.
- [ ] Agente `qualidade-verificador`: `model: haiku`, `tools: Bash, Read`; roda `portao <nome>` uma vez, sozinho; relata a última linha e, se falhou, o trecho que explica; não corrige.
- [ ] Agente `bugs-cacador`: texto atual do caçador, `name: bugs-cacador`, `model: sonnet`.
- [ ] Skills: `qualidade-verificar` (lista os de comando que faltam com `portao`, dispara um verificador por portão, em sequência, pedido `portao: <nome>`); `bugs-cacar` (árvore limpa, dispara `tr:bugs-cacador`; o hook escreve o pedido).
- [ ] `registry.passos`: comando → `/tr:qualidade-verificar`; agente `tr:X-Y` → `/tr:X-<verbo>` só para `tr:bugs-cacador` → `/tr:bugs-cacar` (mapa fixo `INVOKERS`); artefato inalterado.
- [ ] Suíte verde. Commit `feat(tr): /tr:qualidade-verificar and /tr:bugs-cacar; only the validator signs`.

### Task 3: passaporte por demanda

**Files:** Modify `plugins/tr/scripts/registry.py` (`_validate`, `missing`), `plugins/tr/scripts/portao.py`; Test `tests/test_passaporte.py`.

**Produces:** `registry.passaporte(root, reg) -> set[str] | None` (None = sem linha `Portões:`).

- [ ] Testes: sem linha → `missing("fim")` lista todos; `Portões: e2e` com `seo` `sempre: false` → seo fora, e2e e os `sempre` dentro; `sempre` não booleano → `RegistryError`; nome desconhecido → `portao` mostra aviso.
- [ ] Implementar. Commit `feat(tr): per-demand passport selects the optional end gates`.

### Task 4: orquestrador `/tr:processo-planejar`

**Files:** Create `plugins/tr/skills/processo-planejar/SKILL.md`; Modify `plugins/tr/skills/portoes/SKILL.md`, `plugins/tr/scripts/portoes.py` (PADRAO: `bugs` → `tr:bugs-cacador`; `analisar` propõe `bugs` sempre).

- [ ] Skill: (1) `grilling` + `domain-modeling` até não sobrar decisão; (2) spec `docs/specs/<slug>/spec.md` com `Portões:`; (3) tickets `docs/specs/<slug>/issues/NN-<slug>.md` com `Status: open`, `Complexidade: simples|complexa`, `Bloqueado por:`; (4) commit e `portao processo`; (5) executar a fronteira: um subagente por ticket em worktree, `tdd`, merge; (6) `/tr:qualidade-verificar`, `/tr:bugs-cacar`; (7) envio.
- [ ] Teste em `tests/test_portao_automatico.py`: padrão traz `bugs` com `tr:bugs-cacador`.
- [ ] Commit `feat(tr): /tr:processo-planejar opens the demand with the interview`.

### Task 5: absorver `bugs`/`qualidade`, migração e config local

**Files:** Delete `plugins/bugs`, `plugins/qualidade`, `tests/test_plugin_bugs.py`, `tests/test_plugin_qualidade.py` (o que testa `add` vai para `tests/test_install_novo.py`; a cópia idêntica do `ledger.py` vai para `tests/test_trilho_portoes.py`); Modify `bin/harness.js`, `.claude-plugin/marketplace.json`, manifests, `README.md`.

- [ ] Testes em `test_install_novo.py`: `--migrar` remove permissões/`excludedCommands`/hooks com `.harness/`, `SubagentStop` `harness:*`, `bugs@`/`qualidade@` do `enabledPlugins`, troca `bugs:cacador` → `tr:bugs-cacador` no `trilho.json`; `install` grava `settings.local.json` com `model: opus` e `CLAUDE_CODE_SUBAGENT_MODEL: sonnet` preservando chaves existentes.
- [ ] Versões 3.0.0 / tr 1.0.0; README (plugins, nomes, modelo por papel, passaporte).
- [ ] Suíte verde. Commit `feat!: tr absorbs bugs and qualidade; install writes the local model config; 3.0.0`.

### Task 6: verificação numa sessão real

- [ ] Projeto rascunho com o `tr` desta árvore (marketplace local), registro com `qualidade` (`true`) e `bugs`: na sessão interativa (pty), pedir `/tr:qualidade-verificar` e `/tr:bugs-cacar`; conferir carimbos no livro, modelo dos subagentes (haiku/sonnet) e o quadro do envio barrado. Registrar o resultado em `docs/uso/`.
