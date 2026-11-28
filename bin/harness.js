#!/usr/bin/env node
// Entrada do pacote: `npx @fullchico/harness <command>`. Os comandos repassam aos scripts do plugin `tr`
// (Python); aqui só se acha a pasta do pacote, se instalam os plugins no projeto e se grava o settings.
"use strict";
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const [command, ...originalArgs] = process.argv.slice(2);
let rest = originalArgs;
let environment = "both";
const version = require(path.join(root, "package.json")).version;
// Teste de uma versão local antes de publicar: o marketplace vem desta pasta, não do GitHub.
// O registro de marketplace é global por nome; num teste assim, o `fullchico` aponta para a pasta local.
const LOCAL_SOURCE = process.env.FULLCHICO_HARNESS_SOURCE ? path.resolve(process.env.FULLCHICO_HARNESS_SOURCE) : "";
const LEGACY = /\.harness\//;
// Plugins de portão que o tr absorveu na 3.0: o agente mudou de nome junto.
const ABSORBED = { "bugs@fullchico": true, "qualidade@fullchico": true };
const RENAMED_AGENTS = { "bugs:cacador": "tr:bug-hunter" };
const usage = "uso: fullchico-harness install [pasta do projeto] [--target claude|codex|both] [--default] [--migrate] [--sandbox]\n" +
  "     fullchico-harness install-codex [pasta do projeto] [--default]   (portões e memória no Codex)\n" +
  "     fullchico-harness gates [--analyze] [--write] [--default] [--approve <gate>] [--set <gate> \"<command>\"] [--register <draft.json>] [--remove <gate>] [--accept] [--project <pasta>]\n" +
  "     fullchico-harness doctor [pasta do projeto]   (a máquina e o projeto têm o que o plugin precisa?)\n" +
  "     fullchico-harness watch                    (painel ao vivo dos terminais da demanda)\n" +
  "     fullchico-harness models configure [role cli:model ...] | show | run <role> [--prompt <texto>] [--ticket <caminho>] [--detach] | validate-gate <gate> [--ticket <caminho>] [--prompt <texto>] [--detach] | wait <id> [--timeout <s>] [--project <pasta>]\n" +
  "     fullchico-harness deliver [pasta do projeto]   (valida portões e passaportes na entrega)\n" +
  "     fullchico-harness add <plugin> [<plugin>...] [--project <pasta>]   (tr, memory)\n" +
  "     fullchico-harness status [pasta do projeto]   (tickets e subagentes da demanda, com quem parou)\n" +
  "     fullchico-harness cost [pasta do projeto] [--since <commit|AAAA-MM-DD[THH:MM]>] [--json]   (o que a entrega custou)\n" +
  "     fullchico-harness --version\n" +
  "  (pelo npx: npx @fullchico/harness <comando>)";

main().catch((error) => {
  console.error(`fullchico-harness: ${error && error.message ? error.message : error}`);
  process.exit(1);
});

async function main() {
if (command === "install") {
  const chosen = await selectEnvironment(rest);
  if (chosen.error) {
    console.error(`install: ${chosen.error}\n${usage}`);
    process.exit(2);
  }
  rest = chosen.args;
  environment = chosen.environment;
}

if (command === "install-codex") {
  process.exit(python("tools/install_codex.py", rest));
} else if (command === "gates") {
  // Propõe (--analyze, o padrão) ou grava (--write) o registro de portões do projeto em .claude/harness.json.
  process.exit(python("plugins/tr/scripts/gates_cli.py", rest));
} else if (command === "doctor") {
  process.exit(python("plugins/tr/scripts/doctor_cli.py", rest));
} else if (command === "watch") {
  // o painel do dono: fora da sessão o `tr-harness` não está no PATH, e é daqui que ele olha os terminais
  process.exit(python("plugins/tr/scripts/watch_cli.py", rest));
} else if (command === "models") {
  process.exit(python("plugins/tr/scripts/models_cli.py", rest));
} else if (command === "deliver") {
  const project = path.resolve(rest[0] || ".");
  if (rest.length > 1 || (rest[0] || "").startsWith("-") || !fs.existsSync(project) || !fs.statSync(project).isDirectory()) {
    console.error(`deliver: informe a pasta do projeto.\n${usage}`);
    process.exit(2);
  }
  process.exit(python("plugins/tr/scripts/gate_cli.py", ["delivery"], { cwd: project }));
} else if (command === "add") {
  const names = [];
  let project = ".";
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--project") project = rest[++i] || ".";
    else names.push(rest[i]);
  }
  if (!names.length || names.some((n) => !/^[a-z0-9][a-z0-9-]*$/.test(n))) {
    console.error(usage);
    process.exit(2);
  }
  pinMarketplace(project);
  const added = addPlugins(names, project);
  process.exit(added);
} else if (command === "--version"|| command === "-v") {
  console.log(version);
} else if (command === "status") {
  // O quadro da demanda, gravado pelos hooks: tickets e subagentes ativos.
  process.exit(python("plugins/tr/scripts/status.py", [], { cwd: path.resolve(rest[0] || ".") }));
} else if (command === "cost") {
  // Só lê: transcrições do Claude Code e o livro de carimbos. Não grava nada no projeto.
  process.exit(python("plugins/tr/scripts/cost_report.py", rest));
} else if (command === "install") {
  const unknown = rest.filter((arg) => arg.startsWith("-") && !["--default", "--migrate", "--sandbox"].includes(arg));
  if (unknown.length) {
    console.error(`install: opção desconhecida ${unknown.join(" ")}\n${usage}`);
    process.exit(2);
  }
  // O harness do projeto no modelo novo: plugins por projeto e registro de portões. O dono escolhe
  // o padrão do plugin (--default) ou a análise do que o projeto já usa (o padrão do comando).
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  if (environment === "codex") {
    if (rest.includes("--migrate")) {
      console.error("install: --migrate só se aplica à instalação do Claude Code.");
      process.exit(2);
    }
    const codexStatus = installCodex(project, rest.includes("--default"));
    if (!codexStatus) writeFlowInstructions(project);
    process.exit(codexStatus);
  }
  if (!fs.existsSync(project) || !fs.statSync(project).isDirectory()) {
    console.error(`install: ${project} não é uma pasta do projeto.`);
    process.exit(2);
  }
  // Instalar é passo do dono: dentro de uma sessão com sandbox o settings do projeto é protegido, e
  // um install pela metade deixa registro sem plugin. Confere antes de mexer em qualquer coisa.
  const denied = notWritable(project);
  if (denied.length) {
    console.error(`install: sem permissão para gravar ${denied.join(" e ")}.\n` +
      "Instalar o harness é passo do dono: o sandbox da sessão do Claude Code protege esses arquivos do\n" +
      "agente. Rode este mesmo comando no seu terminal, fora da sessão. Nada foi alterado.");
    process.exit(1);
  }
  // Arquivo do dono que não faz parse não é reescrito do zero: para antes, sem mexer em nada.
  const unreadable = [".claude/settings.json", ".claude/settings.local.json", ".claude/harness.json"].filter((rel) => {
    const file = path.join(project, rel);
    if (!fs.existsSync(file)) return false;
    try { JSON.parse(fs.readFileSync(file, "utf8")); return false; } catch (e) { return true; }
  });
  if (unreadable.length) {
    console.error(`install: ${unreadable.join(" e ")} não é JSON válido. Corrija e rode de novo; nada foi alterado.`);
    process.exit(1);
  }
  // Projeto do formato em português (até a 3.x): registro, tickets e settings passam para os nomes novos.
  const migrated = python("plugins/tr/scripts/migrate.py", [project]);
  if (migrated) process.exit(migrated);
  const legacy = legacyState(project);
  if (legacy.length && rest.includes("--migrate")) migrateLegacy(project);
  const gitCheck = spawnSync("git", ["-C", project, "rev-parse", "--show-toplevel"], { encoding: "utf8" });
  if (gitCheck.status !== 0) {
    const init = spawnSync("git", ["-C", project, "init", "-q"], { encoding: "utf8" });
    if (init.status !== 0) {
      console.error(`install: não foi possível iniciar o repositório Git do projeto. ${init.stderr || ""}`);
      process.exit(1);
    }
    console.log(`Git local iniciado em ${project}.`);
  }
  // O plugin cuida do caminho e da aprendizagem; começo e fim são das ferramentas do projeto, ligadas pelos
  // portões. O ponytail (código mínimo) e o mattpocock-skills (processo: grilling, tdd, revisão) vêm junto.
  pinMarketplace(project);
  // Perfil `isolado`, por escolha do dono: o padrão (`fluxo`) fica sem sandbox para o Docker do projeto funcionar.
  if (rest.includes("--sandbox")) enableSandbox(project);
  let status = addPlugins(["tr", "memory"], project, [
    ["ponytail", "DietrichGebert/ponytail", "ponytail"],
    ["claude-plugins-official", "anthropics/claude-plugins-official", "mattpocock-skills"],
  ]);
  offerMissing();
  if (!addRtkHook(project)) status = status || 1;
  if (!requireTmux()) status = status || 1;
  writeFlowInstructions(project);
  writeProjectCli(project);
  writeLocalModels(project);
  // Instalar ferramentas não decide os portões do projeto. Só --default, pedido explícito do dono,
  // grava o modelo de exemplo; um registro existente nunca é reescrito.
  let gates = { status: 0 };
  if (hasRegistry(project)) {
    console.log("\nRegistro de portões existente mantido (.claude/harness.json). Para refazer: `fullchico-harness gates --write`.");
  } else if (rest.includes("--default")) {
    console.log("\n$ fullchico-harness gates --default --write");
    gates = { status: python("plugins/tr/scripts/gates_cli.py", ["--default", "--write", "--project", project]) };
  } else {
    console.log("\nNenhum portão cadastrado. Use `/tr:configure` para decidir os portões do projeto.");
  }
  // Portão que assina por agente de outro plugin do FullChico precisa desse plugin (os do tr já vêm).
  const agents = agentPlugins(project).filter((n) => !["tr", "memory"].includes(n));
  if (agents.length) {
    console.log(`\nOs portões pedem os agentes de: ${agents.join(", ")}`);
    status = addPlugins(agents, project) || status;
  }
  pinMarketplace(project);
  // O install termina dizendo o que a máquina e o projeto ainda não têm (é o `./tr doctor`).
  console.log("\nDiagnóstico (o mesmo de `./tr doctor`):\n");
  python("plugins/tr/scripts/doctor_cli.py", [project]);
  const ok = !status && gates.status === 0;
  if (legacy.length && !rest.includes("--migrate")) {
    console.log("\nAviso: o projeto ainda tem o harness antigo (" + legacy.join("; ") + ").\n" +
      "Os dois juntos não funcionam: a etapa final do antigo (`.harness/push`) conflita com a entrega nova e o\n" +
      "mapa do código entra duas vezes. Para desligar o antigo: `fullchico-harness install --migrate`.");
  }
  if (!ok) {
    console.error("\ninstall: terminou com erro (veja acima). Corrija e rode de novo; os passos seguintes dependem disto.");
    process.exit(status || (gates.status === null ? 1 : gates.status) || 1);
  }
  if (environment === "both") {
    const codexStatus = installCodex(project, rest.includes("--default"));
    if (codexStatus) process.exit(codexStatus);
  }
  await finish("  1. Revise `.claude/settings.json` e `.claude/harness.json`; o install inicia Git se necessário.\n" +
    "  2. Abra o projeto com `claude`. Na primeira vez, o Claude pergunta se você confia na pasta: responda\n" +
    "     \"Yes, I trust this folder\"; sem isso, o settings do projeto (e os hooks do harness) não carregam.\n" +
    "  3. Na sessão, peça `/tr:configure`: a entrevista propõe os portões e você aprova a gravação no diálogo.\n" +
    "  4. Confira com `gate` o que cada etapa pede; ao final, rode `./tr deliver`. Acompanhe a demanda com `./tr l` (ou `./tr w`, ao vivo).\n" +
    "  5. Cada demanda começa com `/tr:process-plan` (entrevista, spec, tickets); os portões de fim\n" +
    "     são validados por `/tr:quality-check` e `/tr:bugs-hunt`.\n" +
    "  Modelo por papel em .claude/settings.local.json: a sessão em opus planeja; subagentes em sonnet ou haiku." +
    (environment === "both" ? "\n  Codex: abra uma sessão nova e aceite os hooks locais; use a skill tr-codex." : ""));
  process.exit(0);
} else {
  console.error(usage);
  process.exit(command === "--help" || command === "-h" ? 0 : 2);
}
}

// Os próximos passos: num quadro no terminal interativo, em texto simples fora dele (CI, testes).
async function finish(steps) {
  if (process.stdout.isTTY) {
    const prompts = await import("@clack/prompts");
    prompts.note(steps.replace(/^  /gm, ""), "Próximos passos");
    prompts.outro("Pronto. Abra o projeto com `claude`.");
    return;
  }
  console.log("\nPróximos passos:\n" + steps);
}

function installCodex(project, padrao) {
  return python("tools/install_codex.py", padrao ? [project, "--default"] : [project]);
}

// Os comandos repassam aos scripts Python do pacote. Devolve o status de saída.
function python(script, args, options = {}) {
  const run = spawnSync("python3", ["-I", path.join(root, script), ...args], { stdio: "inherit", ...options });
  if (run.error) console.error(run.error.code === "ENOENT" ? "fullchico-harness: precisa do `python3` no PATH." : String(run.error));
  return run.status === null ? 1 : run.status;
}

async function selectEnvironment(args) {
  const kept = [];
  let selected;
  for (let i = 0; i < args.length; i++) {
    if (args[i] !== "--target") {
      kept.push(args[i]);
      continue;
    }
    if (selected !== undefined) return { error: "--target foi informado mais de uma vez." };
    selected = args[++i];
  }
  if (selected !== undefined && !["claude", "codex", "both"].includes(selected)) {
    return { error: "--target deve ser claude, codex ou both." };
  }
  if (!selected && process.stdin.isTTY && process.stdout.isTTY) {
    const prompts = await import("@clack/prompts");
    prompts.intro("FullChico Harness");
    const answer = await prompts.select({
      message: "Instalar o harness em qual ambiente?",
      initialValue: "both",
      options: [
        { value: "both", label: "Claude Code e Codex" },
        { value: "claude", label: "Claude Code" },
        { value: "codex", label: "Codex" },
      ],
    });
    if (prompts.isCancel(answer)) return { error: "instalação cancelada." };
    selected = answer;
  }
  return { environment: selected || "both", args: kept };
}

// Versões anteriores do instalador deixaram o marketplace `fullchico` declarado no arquivo global do usuário,
// sem versão. Essa entrada faz o Claude Code ignorar o marketplace nos projetos que fixam a versão. Aqui ela é
// retirada (só ela, com cópia de segurança ao lado); o projeto continua dizendo de onde o plugin vem.
function healUserMarketplace() {
  const file = path.join(require("os").homedir(), ".claude", "settings.json");
  let raw, data;
  try { raw = fs.readFileSync(file, "utf8"); data = JSON.parse(raw); } catch (e) { return; }
  const markets = data.extraKnownMarketplaces;
  const entry = markets && markets.fullchico;
  const source = (entry && entry.source) || {};
  if (!entry || source.source !== "github" || String(source.repo || "").toLowerCase() !== "fullchico/fullchico-harness") return;
  try {
    const backup = `${file}.bak-fullchico-${Date.now()}`;
    fs.writeFileSync(backup, raw);
    delete markets.fullchico;
    fs.writeFileSync(file, JSON.stringify(data, null, raw.startsWith("{\n    ") ? 4 : 2) + (raw.endsWith("\n") ? "\n" : ""));
    console.log("\nRetirei do seu arquivo global (~/.claude/settings.json) a entrada antiga do marketplace `fullchico`: sem" +
      "\nversão, ela fazia o Claude Code ignorar o plugin nos projetos. O projeto continua fixando a versão." +
      `\nCópia do arquivo como estava: ${backup.replace(require("os").homedir(), "~")}`);
  } catch (e) {
    console.log("\nAviso: o seu ~/.claude/settings.json declara o marketplace `fullchico` sem versão, e isso faz o Claude" +
      "\nCode ignorar o plugin. Retire essa entrada de `extraKnownMarketplaces` (não consegui gravar o arquivo).");
  }
}

// Instala plugins do marketplace do FullChico no escopo do projeto, pelo `claude`. Devolve o status.
// Os nomes são do marketplace do FullChico; `extras` são [marketplace, repositório, plugin] de outros.
function addPlugins(names, project, extras = []) {
  // `--scope project`: o marketplace é declarado no projeto, que fixa a versão. Declarado no arquivo global do
  // usuário (o padrão do comando), ele fica sem versão, diverge do que o projeto fixa, e o Claude Code passa a
  // ignorar o marketplace inteiro: a sessão seguinte abre sem os hooks do plugin.
  const commands = [["plugin", "marketplace", "add", LOCAL_SOURCE || "FullChico/fullchico-harness", "--scope", "project"],
    ["plugin", "marketplace", "update", "fullchico"],
    ...names.flatMap((n) => [["plugin", "install", `${n}@fullchico`, "--scope", "project"],
                            ["plugin", "update", `${n}@fullchico`, "--scope", "project"]])];
  for (const [market, repo, plugin] of extras) {
    commands.push(["plugin", "marketplace", "add", repo], ["plugin", "install", `${plugin}@${market}`, "--scope", "project"]);
  }
  let status = 0;
  for (const [i, args] of commands.entries()) {
    console.log(`$ claude ${args.join(" ")}`);
    const run = spawnSync("claude", args, { cwd: project, stdio: "inherit" });
    if (run.error && run.error.code === "ENOENT") {
      console.log("\nO `claude` não está no PATH. Rode você, na pasta do projeto:");
      for (const left of commands.slice(i)) console.log(`  claude ${left.join(" ")}`);
      status = 1;
      break;
    }
    // o marketplace já registrado não é erro; a instalação que falha é
    if ((["install", "update"].includes(args[1]) || (args[1] === "marketplace" && args[2] === "update")) &&
        run.status !== 0) status = run.status === null ? 1 : run.status;
  }
  healUserMarketplace();
  // Um marketplace `fullchico` já registrado com outra fonte (uma pasta de teste, um fork) faz o `add`
  // passar em silêncio e o install trazer o plugin de lá. Confere a fonte e para com o conserto.
  const expected = LOCAL_SOURCE || "FullChico/fullchico-harness";
  try {
    const known = JSON.parse(fs.readFileSync(path.join(require("os").homedir(), ".claude/plugins/known_marketplaces.json"), "utf8"));
    const src = (known.fullchico || {}).source || {};
    const actual = src.repo || src.path || src.url || "";
    if (actual && path.resolve(actual) !== path.resolve(expected) && actual.toLowerCase() !== expected.toLowerCase()) {
      console.log(`\nO marketplace \`fullchico\` desta máquina aponta para ${actual}, não para ${expected}:` +
        "\nos plugins vieram de lá. Para trocar, rode no terminal, um por vez:" +
        "\n  claude plugin marketplace remove fullchico" +
        `\n  claude plugin marketplace add ${expected}` +
        "\ne depois rode esta instalação de novo.");
      status = status || 1;
    }
  } catch (e) { /* sem registro legível: o `claude` já disse o que houve */ }
  return status;
}

// Os arquivos que o install grava e que o sandbox de uma sessão nega. Abrir para acréscimo não muda nada.
function notWritable(project) {
  const denied = [];
  for (const rel of [".claude/settings.json", ".claude/settings.local.json", ".claude/harness.json"]) {
    const file = path.join(project, rel);
    try {
      if (fs.existsSync(file)) fs.closeSync(fs.openSync(file, "a"));
      else {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        const probe = file + ".gravavel";
        fs.closeSync(fs.openSync(probe, "w"));
        fs.unlinkSync(probe);
      }
    } catch (e) {
      denied.push(rel);
    }
  }
  return denied;
}

function readSettings(project) {
  try { return JSON.parse(fs.readFileSync(path.join(project, ".claude", "settings.json"), "utf8")); } catch (e) { return {}; }
}

function writeSettings(project, data) {
  const file = path.join(project, ".claude", "settings.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n");
}


function isLegacyHook(h) {
  return LEGACY.test(String(h.command || ""));
}

function isLegacyGroup(event, g) {
  return event === "SubagentStop" && /(^|[^\w-])harness:/.test(String(g.matcher || ""));
}

function hookGroups(data) {
  return Object.entries(data.hooks || {}).filter(([, groups]) => Array.isArray(groups));
}

function readRegistry(project) {
  try { return JSON.parse(fs.readFileSync(path.join(project, ".claude", "harness.json"), "utf8")); } catch (e) { return null; }
}

function hasRegistry(project) {
  const reg = readRegistry(project);
  return !!(reg && reg.gates && Object.keys(reg.gates).length);
}

// O que resta do harness antigo e dos plugins que o tr absorveu.
function legacyState(project) {
  const data = readSettings(project);
  const found = [];
  const enabled = data.enabledPlugins || {};
  if (enabled["harness@fullchico"]) found.push("plugin `harness@fullchico` ligado");
  for (const name of Object.keys(ABSORBED)) if (name in enabled) found.push(`plugin \`${name}\` (agora dentro do tr)`);
  const hooks = hookGroups(data).flatMap(([event, groups]) =>
    groups.flatMap((g) => isLegacyGroup(event, g) ? [{ command: ".harness/" }] : g.hooks || []));
  if (hooks.some(isLegacyHook)) found.push("hooks do harness antigo no settings");
  const perms = Object.values(data.permissions || {}).flat();
  const excluded = (data.sandbox || {}).excludedCommands || [];
  if ([...perms, ...excluded].some((p) => LEGACY.test(String(p)))) found.push("permissões de `.harness/` no settings");
  const gates = Object.values((readRegistry(project) || {}).gates || {});
  if (gates.some((g) => g && RENAMED_AGENTS[g.agent])) found.push("agente `bugs:cacador` no registro");
  return found;
}

// Desliga o antigo no settings do projeto (o git guarda o anterior). A pasta `.harness/` fica: apagar é do dono.
function migrateLegacy(project) {
  const data = readSettings(project);
  if (data.enabledPlugins) {
    if (data.enabledPlugins["harness@fullchico"]) data.enabledPlugins["harness@fullchico"] = false;
    for (const name of Object.keys(ABSORBED)) delete data.enabledPlugins[name];
  }
  for (const [event, groups] of hookGroups(data)) {
    const kept = groups.filter((g) => !isLegacyGroup(event, g))
      .map((g) => ({ ...g, hooks: (g.hooks || []).filter((h) => !isLegacyHook(h)) }))
      .filter((g) => g.hooks.length);
    if (kept.length) data.hooks[event] = kept;
    else delete data.hooks[event];
  }
  for (const [kind, list] of Object.entries(data.permissions || {})) {
    if (Array.isArray(list)) data.permissions[kind] = list.filter((p) => !LEGACY.test(String(p)));
  }
  if (data.sandbox && Array.isArray(data.sandbox.excludedCommands)) {
    data.sandbox.excludedCommands = data.sandbox.excludedCommands.filter((c) => !LEGACY.test(String(c)));
  }
  writeSettings(project, data);
  const reg = readRegistry(project);
  if (reg && reg.gates) {
    let renamed = false;
    for (const gate of Object.values(reg.gates)) {
      if (gate && RENAMED_AGENTS[gate.agent]) { gate.agent = RENAMED_AGENTS[gate.agent]; renamed = true; }
    }
    if (renamed) fs.writeFileSync(path.join(project, ".claude", "harness.json"), JSON.stringify(reg, null, 2) + "\n");
  }
  console.log("Harness antigo desligado no .claude/settings.json (plugin, hooks e permissões de `.harness/`; " +
    "bugs e qualidade agora são do tr). A pasta `.harness/` ficou; apague quando não precisar mais dela.\n" +
    "Se o AGENTS.md ou docs/agents/ ainda descrevem `.harness/push` e os revisores antigos, atualize: o agente segue o que lê.");
}

// Modelo local de planejamento; o orquestrador usa a configuração por papel e por portão.
// Subagente sem modelo definido roda em sonnet; o hook ainda escolhe pelo ticket quando não há CLI configurada.
function writeLocalModels(project) {
  const file = path.join(project, ".claude", "settings.local.json");
  let data = {};
  try { data = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { /* novo */ }
  data.model = data.model || "opus";
  data.env = { CLAUDE_CODE_SUBAGENT_MODEL: "sonnet", ...(data.env || {}) };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n");
}

// Plugins do FullChico que trazem os agentes dos portões `signs: agent` (`bugs:cacador` → `bugs`).
function agentPlugins(project) {
  let gates = {};
  try { gates = JSON.parse(fs.readFileSync(path.join(project, ".claude", "harness.json"), "utf8")).gates || {}; } catch (e) { /* sem registro */ }
  const names = Object.values(gates).filter((g) => g && g.signs === "agent" && typeof g.agent === "string")
    .map((g) => g.agent.split(":")[0]);
  return [...new Set(names)].filter((n) => fs.existsSync(path.join(root, "plugins", n, ".claude-plugin", "plugin.json")));
}

// O clone limpo do projeto instala os plugins do marketplace nesta versão do plugin, não de uma antiga.
function pinMarketplace(project) {
  const data = readSettings(project);
  data.extraKnownMarketplaces = data.extraKnownMarketplaces || {};
  const current = data.extraKnownMarketplaces.fullchico;
  const ref = `v${version}`;
  if (!LOCAL_SOURCE && current && current.source && current.source.ref === ref) return;
  data.extraKnownMarketplaces.fullchico = LOCAL_SOURCE
    ? { source: { source: "directory", path: LOCAL_SOURCE } }
    : { source: { source: "github", repo: "FullChico/fullchico-harness", ref } };
  writeSettings(project, data);
}

// Liga o sandbox nativo do Claude Code e protege o registro. O `docker` precisa sair do sandbox para rodar;
// essa exclusão dá a ele acesso fora do isolamento, então fica só para o comando necessário.
function enableSandbox(project) {
  const data = readSettings(project);
  const sandbox = data.sandbox = data.sandbox || {};
  sandbox.enabled = true;
  const fs_ = sandbox.filesystem = sandbox.filesystem || {};
  fs_.denyWrite = [...new Set([...(fs_.denyWrite || []), ".claude/harness.json"])];
  sandbox.excludedCommands = [...new Set([...(sandbox.excludedCommands || []), "docker", "fullchico-harness"])];
  writeSettings(project, data);
  console.log("\nSandbox nativo ligado (perfil isolado): `.claude/harness.json` protegido; `docker` e `fullchico-harness` rodam fora do sandbox.");
}

// O fluxo do projeto, dito onde o agente sempre lê: CLAUDE.md (Claude) e AGENTS.md (Codex). Proibir outras
// skills não adianta; elas entram como ferramenta dentro do fluxo. Só o bloco entre os marcadores é do harness.
// A CLI do dono mora no projeto: `./tr l`, `./tr doctor`. Não é global (um `tr` no PATH esconderia o `tr` do
// sistema, que os scripts usam), e roda a versão do plugin que o projeto fixou.
function writeProjectCli(project) {
  const file = path.join(project, "tr");
  const mark = "# fullchico-harness: CLI do projeto (gerada pelo install; não edite)";
  try {
    if (fs.existsSync(file) && !fs.readFileSync(file, "utf8").includes(mark)) {
      console.log("\nAviso: já existe um arquivo `tr` na raiz que não é do harness; a CLI do projeto não foi escrita.");
      return;
    }
  } catch (e) { return; }
  fs.writeFileSync(file, [
    "#!/bin/sh",
    mark,
    "# uso: ./tr l | ./tr doctor | ./tr help",
    'here=$(cd "$(dirname "$0")" && pwd)',
    'base="$HOME/.claude/plugins/cache/fullchico/tr"',
    "# a versão do plugin que este projeto usa: a que o Claude Code instalou por último para ele",
    'v=$(ls "$base" 2>/dev/null | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)',
    'if [ ! -x "$base/$v/bin/tr-harness" ]; then',
    '  echo "o plugin tr ainda não está nesta máquina: abra o Claude neste projeto uma vez (ele instala), ou rode npx @fullchico/harness install" >&2',
    "  exit 1",
    "fi",
    'cd "$here" && exec "$base/$v/bin/tr-harness" "$@"',
    ""].join("\n"));
  fs.chmodSync(file, 0o755);
  console.log("\nCLI do projeto: `./tr l` (o que está executando), `./tr doctor`, `./tr help`.");
}

function writeFlowInstructions(project) {
  const begin = "<!-- fullchico-harness:begin -->";
  const finish = "<!-- fullchico-harness:end -->";
  const block = [begin,
    "## FullChico harness",
    "",
    "This project follows the tr flow. Every request to build or change something starts with",
    "`/tr:process-plan` (in Codex, `$tr-process-plan`): grilling interview (Matt Pocock), spec, tickets, then the",
    "orchestrator in the background. If the gates are not configured yet, run `/tr:configure` first.",
    "Other skills (brainstorming, TDD, review) are tools inside this flow, not a replacement for it.",
    "The main session plans and talks to the owner; executors write the code. Check the state with `gate`.",
    finish].join("\n");
  for (const name of ["CLAUDE.md", "AGENTS.md"]) {
    const file = path.join(project, name);
    const current = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
    const at = current.indexOf(begin);
    const stop = current.indexOf(finish);
    const next = at >= 0 && stop > at
      ? current.slice(0, at) + block + current.slice(stop + finish.length)
      : (current.trim() ? current.replace(/\s*$/, "\n\n") : "") + block + "\n";
    if (next !== current) fs.writeFileSync(file, next);
  }
}

// O rtk comprime a saída dos comandos e economiza token. É obrigatório: sem ele a instalação termina com erro
// e diz como instalar. Não é plugin, é um programa da máquina; o hook do projeto confere se ele existe para o
// clone ainda sem rtk não quebrar a sessão, e a instalação desse clone cobra o rtk de novo.
// O tmux é obrigatório: é nele que o maestro abre o orquestrador (e os executores em outro CLI), cada um num
// terminal próprio que ele lê e encerra. É um programa da máquina, de código aberto.
function requireTmux() {
  if (spawnSync("sh", ["-c", "command -v tmux"]).status !== 0) {
    console.log("\nErro: o tmux é obrigatório e não está no PATH desta máquina. Instale (`brew install tmux`, ou o pacote `tmux` do sistema) e rode o install de novo.");
    return false;
  }
  return true;
}

// Programa obrigatório que falta na máquina: no terminal do dono, com o Homebrew, o install pergunta e instala.
// Fora disso (CI, sessão de agente, sem Homebrew) não instala nada: os erros adiante dizem o comando.
function offerMissing() {
  const has = (name) => spawnSync("sh", ["-c", `command -v ${name}`]).status === 0;
  const want = ["tmux", "rtk"].filter((name) => !has(name));
  if (!want.length || !process.stdin.isTTY || !process.stdout.isTTY || !has("brew")) return;
  process.stdout.write(`\nFalta nesta máquina: ${want.join(" e ")}. Instalar agora com \`brew install ${want.join(" ")}\`? [s/N] `);
  const answer = spawnSync("sh", ["-c", 'read -r a; printf %s "$a"'], { stdio: ["inherit", "pipe", "inherit"], encoding: "utf8" });
  if (!["s", "sim", "y", "yes"].includes(String(answer.stdout || "").trim().toLowerCase())) return;
  spawnSync("brew", ["install", ...want], { stdio: "inherit" });
}

function addRtkHook(project) {
  const file = path.join(project, ".claude", "settings.json");
  let data = {};
  try { data = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { /* novo */ }
  const command = "if command -v rtk >/dev/null 2>&1; then rtk hook claude; fi";
  data.hooks = data.hooks || {};
  const groups = data.hooks.PreToolUse = data.hooks.PreToolUse || [];
  const present = groups.some((g) => (g.hooks || []).some((h) => String(h.command || "").includes("rtk hook claude")));
  if (!present) {
    groups.push({ matcher: "Bash", hooks: [{ type: "command", command }] });
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n");
  }
  if (spawnSync("sh", ["-c", "command -v rtk"]).status !== 0) {
    console.log("\nErro: o `rtk` é obrigatório e não está instalado nesta máquina. Instale e rode o install de novo:" +
      "\n  brew install rtk" +
      "\n  (outras formas: https://github.com/rtk-ai/rtk)");
    return false;
  }
  return true;
}
