#!/usr/bin/env node
// Entrada do pacote: `npx @fullchico/harness <comando>`. Os comandos repassam aos scripts do plugin `tr`
// (Python); aqui só se acha a pasta do pacote, se instalam os plugins no projeto e se grava o settings.
"use strict";
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const [command, ...rest] = process.argv.slice(2);
const version = require(path.join(root, "package.json")).version;
const usage = "uso: fullchico-harness install [pasta do projeto] [--padrao] [--migrar]   (plugins por projeto e portões)\n" +
  "     fullchico-harness puro [pasta do projeto]\n" +
  "     fullchico-harness portoes [--analisar] [--gravar] [--padrao] [--definir <portão> \"<comando>\"] [--registrar <esboço.json>] [--projeto <pasta>]\n" +
  "     fullchico-harness add <plugin> [<plugin>...] [--project <pasta>]   (tr, bugs, qualidade)\n" +
  "     fullchico-harness custo [pasta do projeto] [--desde <commit|AAAA-MM-DD[THH:MM]>] [--json]   (o que a entrega custou)\n" +
  "     fullchico-harness --version\n" +
  "  (pelo npx: npx @fullchico/harness <comando>)";

if (command === "puro") {
  // Marca o projeto como puro e traz do global só a ferramenta pessoal (Orca, rtk), para o escopo local.
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/make_pure.py"), project], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "portoes") {
  // Propõe (--analisar, o padrão) ou grava (--gravar) o registro de portões do projeto em .claude/trilho.json.
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/portoes.py"), ...rest], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
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
  const added = addPlugins(names, project);
  pinMarketplace(project);
  process.exit(added);
} else if (command === "--version"|| command === "-v") {
  console.log(version);
} else if (command === "custo") {
  // Só lê: transcrições do Claude Code e o livro de carimbos. Não grava nada no projeto.
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/custo.py"), ...rest], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "install") {
  const unknown = rest.filter((arg) => arg.startsWith("-") && !["--padrao", "--migrar"].includes(arg));
  if (unknown.length) {
    console.error(`install: opção desconhecida ${unknown.join(" ")}\n${usage}`);
    process.exit(2);
  }
  // O harness do projeto no modelo novo: plugins por projeto e registro de portões. O dono escolhe
  // o padrão da lib (--padrao) ou a análise do que o projeto já usa (o padrão do comando).
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  const inGit = spawnSync("git", ["-C", project, "rev-parse", "--show-toplevel"], { encoding: "utf8" });
  if (inGit.status !== 0) {
    console.error(`install: ${project} não é um repositório git.`);
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
  const legacy = legacyState(project);
  if (legacy.length && rest.includes("--migrar")) migrateLegacy(project);
  // A lib cuida do caminho e da aprendizagem; começo e fim são das ferramentas do projeto, ligadas pelos
  // portões. O ponytail (código mínimo) e o mattpocock-skills (processo: grilling, tdd, revisão) vêm junto.
  let status = addPlugins(["tr", "memoria"], project, [
    ["ponytail", "DietrichGebert/ponytail", "ponytail"],
    ["claude-plugins-official", "anthropics/claude-plugins-official", "mattpocock-skills"],
  ]);
  addRtkHook(project);
  const mode = rest.includes("--padrao") ? "--padrao" : "--analisar";
  console.log(`\n$ fullchico-harness portoes ${mode} --gravar`);
  const gates = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/portoes.py"), mode, "--gravar",
    "--projeto", project], { stdio: "inherit" });
  // Portão que assina por agente precisa do plugin que traz o agente (`bugs:cacador` → `bugs`).
  const agents = agentPlugins(project).filter((n) => !["tr", "memoria"].includes(n));
  if (agents.length) {
    console.log(`\nOs portões pedem os agentes de: ${agents.join(", ")}`);
    status = addPlugins(agents, project) || status;
  }
  pinMarketplace(project);
  const ok = !status && gates.status === 0;
  if (legacy.length && !rest.includes("--migrar")) {
    console.log("\nAviso: o projeto ainda tem o harness antigo (" + legacy.join("; ") + ").\n" +
      "Os dois juntos não funcionam: o envio do antigo (`.harness/push`) passa por fora dos portões novos e o\n" +
      "mapa do código entra duas vezes. Para desligar o antigo: `fullchico-harness install --migrar`.");
  }
  if (!ok) {
    console.error("\ninstall: terminou com erro (veja acima). Corrija e rode de novo; os passos seguintes dependem disto.");
    process.exit(status || (gates.status === null ? 1 : gates.status) || 1);
  }
  console.log("\nPróximos passos:\n" +
    "  1. Faça o commit de `.claude/settings.json` e `.claude/trilho.json`: carimbo de fim só assina com a árvore limpa.\n" +
    "  2. Ligue o modo puro: `fullchico-harness puro`, e abra o projeto com `cc` (claude clean).\n" +
    "  3. Na sessão, peça `/tr:configurar` para a entrevista propor os portões; quem grava é você, no terminal.\n" +
    "  4. Confira com `portao` o que cada etapa pede.");
  process.exit(0);
} else {
  console.error(usage);
  process.exit(command === "--help" || command === "-h" ? 0 : 2);
}

// Instala plugins do marketplace do FullChico no escopo do projeto, pelo `claude`. Devolve o status.
// Os nomes são do marketplace do FullChico; `extras` são [marketplace, repositório, plugin] de outros.
function addPlugins(names, project, extras = []) {
  const commands = [["plugin", "marketplace", "add", "FullChico/fullchico-harness"],
    ...names.map((n) => ["plugin", "install", `${n}@fullchico`, "--scope", "project"])];
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
      break;
    }
    // o marketplace já registrado não é erro; a instalação que falha é
    if (args[1] === "install" && run.status !== 0) status = run.status === null ? 1 : run.status;
  }
  // Cada plugin com `portao.json` registra o próprio portão (só acrescenta; entrada existente fica como está).
  for (const name of names) {
    const manifest = path.join(root, "plugins", name, "portao.json");
    if (!fs.existsSync(manifest)) continue;
    spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/portoes.py"), "--registrar", manifest,
      "--projeto", project], { stdio: "inherit" });
  }
  // O carimbo fica fora do projeto, onde o sandbox impede o agente de gravar. Sem sandbox, o agente
  // consegue gravar lá: o portão continua avisando, mas deixa de ser barreira.
  let sandboxed = false;
  for (const file of ["settings.json", "settings.local.json"]) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(project, ".claude", file), "utf8"));
      if (data.sandbox && data.sandbox.enabled === true) sandboxed = true;
    } catch (e) { /* arquivo ausente ou inválido: segue */ }
  }
  if (!sandboxed) {
    console.log("\nAviso: este projeto não liga o sandbox do Claude Code (`sandbox.enabled` em .claude/settings.json).\n" +
      "Sem ele, o agente consegue gravar no estado dos carimbos e, em tese, forjar um carimbo: o portão avisa,\n" +
      "mas deixa de ser barreira. Para ligar: https://code.claude.com/docs/en/sandboxing");
  }
  return status;
}

// Os arquivos que o install grava e que o sandbox de uma sessão nega. Abrir para acréscimo não muda nada.
function notWritable(project) {
  const denied = [];
  for (const rel of [".claude/settings.json", ".claude/trilho.json"]) {
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
  return /\.harness\/hooks\//.test(String(h.command || ""));
}

// O que resta do harness antigo (plugin `harness@fullchico` e hooks de `.harness/hooks/`).
function legacyState(project) {
  const data = readSettings(project);
  const found = [];
  if ((data.enabledPlugins || {})["harness@fullchico"]) found.push("plugin `harness@fullchico` ligado");
  const hooks = Object.values(data.hooks || {}).flat().flatMap((g) => g.hooks || []);
  if (hooks.some(isLegacyHook)) found.push("hooks de `.harness/hooks/` no settings");
  return found;
}

// Desliga o antigo no settings do projeto (o git guarda o anterior). A pasta `.harness/` fica: apagar é do dono.
function migrateLegacy(project) {
  const data = readSettings(project);
  if (data.enabledPlugins && data.enabledPlugins["harness@fullchico"]) data.enabledPlugins["harness@fullchico"] = false;
  for (const [event, groups] of Object.entries(data.hooks || {})) {
    const kept = groups.map((g) => ({ ...g, hooks: (g.hooks || []).filter((h) => !isLegacyHook(h)) }))
      .filter((g) => g.hooks.length);
    if (kept.length) data.hooks[event] = kept;
    else delete data.hooks[event];
  }
  writeSettings(project, data);
  console.log("Harness antigo desligado no .claude/settings.json (plugin e hooks de `.harness/hooks/`). " +
    "A pasta `.harness/` ficou; apague quando não precisar mais dela.");
}

// Plugins do FullChico que trazem os agentes dos portões `assina: agente` (`bugs:cacador` → `bugs`).
function agentPlugins(project) {
  let gates = {};
  try { gates = JSON.parse(fs.readFileSync(path.join(project, ".claude", "trilho.json"), "utf8")).portoes || {}; } catch (e) { /* sem registro */ }
  const names = Object.values(gates).filter((g) => g && g.assina === "agente" && typeof g.agente === "string")
    .map((g) => g.agente.split(":")[0]);
  return [...new Set(names)].filter((n) => fs.existsSync(path.join(root, "plugins", n, ".claude-plugin", "plugin.json")));
}

// O clone limpo do projeto instala os plugins do marketplace nesta versão da lib, não de uma antiga.
function pinMarketplace(project) {
  const data = readSettings(project);
  data.extraKnownMarketplaces = data.extraKnownMarketplaces || {};
  const current = data.extraKnownMarketplaces.fullchico;
  const ref = `v${version}`;
  if (current && current.source && current.source.ref === ref) return;
  data.extraKnownMarketplaces.fullchico = { source: { source: "github", repo: "FullChico/fullchico-harness", ref } };
  writeSettings(project, data);
}

// O rtk comprime a saída dos comandos e economiza token. Não é plugin: é um programa da máquina. Entra
// como hook do projeto que só roda se ele existir, para o clone sem rtk não quebrar.
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
    console.log("\nAviso: o `rtk` não está instalado nesta máquina; o hook dele fica no projeto e passa a valer quando instalar.");
  }
}
