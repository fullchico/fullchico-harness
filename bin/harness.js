#!/usr/bin/env node
// Entrada do pacote: `npx @fullchico/harness <comando>`. Os comandos repassam aos scripts do plugin `tr`
// (Python); aqui só se acha a pasta do pacote, se instalam os plugins no projeto e se grava o settings.
"use strict";
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const [command, ...originalArgs] = process.argv.slice(2);
let rest = originalArgs;
let environment = "ambos";
const version = require(path.join(root, "package.json")).version;
const LEGACY = /\.harness\//;
// Plugins de portão que o tr absorveu na 3.0: o agente mudou de nome junto.
const ABSORBED = { "bugs@fullchico": true, "qualidade@fullchico": true };
const RENAMED_AGENTS = { "bugs:cacador": "tr:bugs-cacador" };
const usage = "uso: fullchico-harness install [pasta do projeto] [--ambiente claude|codex|ambos] [--padrao] [--migrar]\n" +
  "     fullchico-harness install-codex [pasta do projeto] [--padrao]   (portões e memória no Codex)\n" +
  "     fullchico-harness puro [pasta do projeto]\n" +
  "     fullchico-harness portoes [--analisar] [--gravar] [--padrao] [--definir <portão> \"<comando>\"] [--registrar <esboço.json>] [--projeto <pasta>]\n" +
  "     fullchico-harness modelos configurar [papel cli:modelo ...] | mostrar | executar <papel> [--pedido <texto>] [--ticket <caminho>] [--projeto <pasta>]\n" +
  "     fullchico-harness entregar [pasta do projeto]   (valida portões e passaportes na entrega)\n" +
  "     fullchico-harness modelos configurar [papel cli:modelo ...] | mostrar [--projeto <pasta>]\n" +
  "     fullchico-harness add <plugin> [<plugin>...] [--project <pasta>]   (tr, memoria)\n" +
  "     fullchico-harness custo [pasta do projeto] [--desde <commit|AAAA-MM-DD[THH:MM]>] [--json]   (o que a entrega custou)\n" +
  "     fullchico-harness --version\n" +
  "  (pelo npx: npx @fullchico/harness <comando>)";

if (command === "install") {
  const chosen = selectEnvironment(rest);
  if (chosen.error) {
    console.error(`install: ${chosen.error}\n${usage}`);
    process.exit(2);
  }
  rest = chosen.args;
  environment = chosen.environment;
}

if (command === "install-codex") {
  const run = spawnSync("python3", ["-I", path.join(root, "tools/install_codex.py"), ...rest], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "puro") {
  // Marca o projeto como puro e traz do global só a ferramenta pessoal (Orca, rtk), para o escopo local.
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/make_pure.py"), project], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "portoes") {
  // Propõe (--analisar, o padrão) ou grava (--gravar) o registro de portões do projeto em .claude/trilho.json.
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/portoes.py"), ...rest], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "modelos") {
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/modelos.py"), ...rest], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "entregar") {
  const project = path.resolve(rest[0] || ".");
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/portao.py"), "entrega"],
    { cwd: project, stdio: "inherit" });
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
  ensureSandbox(project);
  pinMarketplace(project);
  const added = addPlugins(names, project);
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
  if (environment === "codex") {
    if (rest.includes("--migrar")) {
      console.error("install: --migrar só se aplica à instalação do Claude Code.");
      process.exit(2);
    }
    process.exit(installCodex(project, rest.includes("--padrao")));
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
  const unreadable = [".claude/settings.json", ".claude/settings.local.json", ".claude/trilho.json"].filter((rel) => {
    const file = path.join(project, rel);
    if (!fs.existsSync(file)) return false;
    try { JSON.parse(fs.readFileSync(file, "utf8")); return false; } catch (e) { return true; }
  });
  if (unreadable.length) {
    console.error(`install: ${unreadable.join(" e ")} não é JSON válido. Corrija e rode de novo; nada foi alterado.`);
    process.exit(1);
  }
  const legacy = legacyState(project);
  if (legacy.length && rest.includes("--migrar")) migrateLegacy(project);
  const gitCheck = spawnSync("git", ["-C", project, "rev-parse", "--show-toplevel"], { encoding: "utf8" });
  if (gitCheck.status !== 0) {
    const init = spawnSync("git", ["-C", project, "init", "-q"], { encoding: "utf8" });
    if (init.status !== 0) {
      console.error(`install: não foi possível iniciar o repositório Git do projeto. ${init.stderr || ""}`);
      process.exit(1);
    }
    console.log(`Git local iniciado em ${project}.`);
  }
  // A lib cuida do caminho e da aprendizagem; começo e fim são das ferramentas do projeto, ligadas pelos
  // portões. O ponytail (código mínimo) e o mattpocock-skills (processo: grilling, tdd, revisão) vêm junto.
  ensureSandbox(project);
  pinMarketplace(project);
  let status = addPlugins(["tr", "memoria"], project, [
    ["ponytail", "DietrichGebert/ponytail", "ponytail"],
    ["claude-plugins-official", "anthropics/claude-plugins-official", "mattpocock-skills"],
  ]);
  addRtkHook(project);
  writeLocalModels(project);
  // O registro do dono não é reescrito por um install de novo: os portões dele (e2e, seo...) ficam.
  let gates = { status: 0 };
  if (hasRegistry(project)) {
    console.log("\nRegistro de portões existente mantido (.claude/trilho.json). Para refazer: `fullchico-harness portoes --gravar`.");
  } else {
    const mode = rest.includes("--padrao") ? "--padrao" : "--analisar";
    console.log(`\n$ fullchico-harness portoes ${mode} --gravar`);
    gates = spawnSync("python3", ["-I", path.join(root, "plugins/tr/scripts/portoes.py"), mode, "--gravar",
      "--projeto", project], { stdio: "inherit" });
  }
  // Portão que assina por agente de outro plugin do FullChico precisa desse plugin (os do tr já vêm).
  const agents = agentPlugins(project).filter((n) => !["tr", "memoria"].includes(n));
  if (agents.length) {
    console.log(`\nOs portões pedem os agentes de: ${agents.join(", ")}`);
    status = addPlugins(agents, project) || status;
  }
  pinMarketplace(project);
  const ok = !status && gates.status === 0;
  if (legacy.length && !rest.includes("--migrar")) {
    console.log("\nAviso: o projeto ainda tem o harness antigo (" + legacy.join("; ") + ").\n" +
      "Os dois juntos não funcionam: a etapa final do antigo (`.harness/push`) conflita com a entrega nova e o\n" +
      "mapa do código entra duas vezes. Para desligar o antigo: `fullchico-harness install --migrar`.");
  }
  if (!ok) {
    console.error("\ninstall: terminou com erro (veja acima). Corrija e rode de novo; os passos seguintes dependem disto.");
    process.exit(status || (gates.status === null ? 1 : gates.status) || 1);
  }
  if (environment === "ambos") {
    const codexStatus = installCodex(project, rest.includes("--padrao"));
    if (codexStatus) process.exit(codexStatus);
  }
  console.log("\nPróximos passos:\n" +
    "  1. Revise `.claude/settings.json` e `.claude/trilho.json`; o install inicia Git se necessário.\n" +
    "  2. Abra o projeto com `claude`. Modo puro opcional: `npx @fullchico/harness puro`; depois, abra com `claude --setting-sources project,local --strict-mcp-config`.\n" +
    "  3. Na sessão, peça `/tr:configurar` para a entrevista propor os portões; quem grava é você, no terminal.\n" +
    "  4. Confira com `portao` o que cada etapa pede; ao final, rode `fullchico-harness entregar`.\n" +
    "  5. Cada demanda começa com `/tr:processo-planejar` (entrevista, spec, tickets); os portões de fim\n" +
    "     são validados por `/tr:qualidade-verificar` e `/tr:bugs-cacar`.\n" +
    "  Modelo por papel em .claude/settings.local.json: a sessão em opus planeja; subagentes em sonnet ou haiku." +
    (environment === "ambos" ? "\n  Codex: abra uma sessão nova e aceite os hooks locais; use a skill tr-codex." : ""));
  process.exit(0);
} else {
  console.error(usage);
  process.exit(command === "--help" || command === "-h" ? 0 : 2);
}

function installCodex(project, padrao) {
  const args = ["-I", path.join(root, "tools/install_codex.py"), project];
  if (padrao) args.push("--padrao");
  const run = spawnSync("python3", args, { stdio: "inherit" });
  return run.status === null ? 1 : run.status;
}

function selectEnvironment(args) {
  const kept = [];
  let selected;
  for (let i = 0; i < args.length; i++) {
    if (args[i] !== "--ambiente") {
      kept.push(args[i]);
      continue;
    }
    if (selected !== undefined) return { error: "--ambiente foi informado mais de uma vez." };
    selected = args[++i];
  }
  if (selected !== undefined && !["claude", "codex", "ambos"].includes(selected)) {
    return { error: "--ambiente deve ser claude, codex ou ambos." };
  }
  if (!selected && process.stdin.isTTY && process.stdout.isTTY) {
    process.stdout.write("\nInstalar o harness em qual ambiente?\n  1. Claude Code\n  2. Codex\n  3. Ambos\nEscolha [3]: ");
    const buffer = Buffer.alloc(32);
    const pause = new Int32Array(new SharedArrayBuffer(4));
    let line = "";
    while (!line.includes("\n") && line.length < 32) {
      let count;
      try {
        count = fs.readSync(0, buffer, 0, buffer.length, null);
      } catch (error) {
        if (!["EAGAIN", "EWOULDBLOCK", "EINTR"].includes(error.code)) throw error;
        Atomics.wait(pause, 0, 0, 25);
        continue;
      }
      if (!count) return { error: "nenhuma escolha recebida." };
      line += buffer.toString("utf8", 0, count);
    }
    const answer = line.trim();
    selected = ({ "": "ambos", "1": "claude", "2": "codex", "3": "ambos",
      "claude": "claude", "codex": "codex", "ambos": "ambos" })[answer];
    if (!selected) return { error: "escolha inválida; use 1, 2 ou 3." };
  }
  return { environment: selected || "ambos", args: kept };
}

// Instala plugins do marketplace do FullChico no escopo do projeto, pelo `claude`. Devolve o status.
// Os nomes são do marketplace do FullChico; `extras` são [marketplace, repositório, plugin] de outros.
function addPlugins(names, project, extras = []) {
  const commands = [["plugin", "marketplace", "add", "FullChico/fullchico-harness"],
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
  return LEGACY.test(String(h.command || ""));
}

function isLegacyGroup(event, g) {
  return event === "SubagentStop" && /(^|[^\w-])harness:/.test(String(g.matcher || ""));
}

function hookGroups(data) {
  return Object.entries(data.hooks || {}).filter(([, groups]) => Array.isArray(groups));
}

function readRegistry(project) {
  try { return JSON.parse(fs.readFileSync(path.join(project, ".claude", "trilho.json"), "utf8")); } catch (e) { return null; }
}

function hasRegistry(project) {
  const reg = readRegistry(project);
  return !!(reg && reg.portoes && Object.keys(reg.portoes).length);
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
  const gates = Object.values((readRegistry(project) || {}).portoes || {});
  if (gates.some((g) => g && RENAMED_AGENTS[g.agente])) found.push("agente `bugs:cacador` no registro");
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
  if (reg && reg.portoes) {
    let renamed = false;
    for (const gate of Object.values(reg.portoes)) {
      if (gate && RENAMED_AGENTS[gate.agente]) { gate.agente = RENAMED_AGENTS[gate.agente]; renamed = true; }
    }
    if (renamed) fs.writeFileSync(path.join(project, ".claude", "trilho.json"), JSON.stringify(reg, null, 2) + "\n");
  }
  console.log("Harness antigo desligado no .claude/settings.json (plugin, hooks e permissões de `.harness/`; " +
    "bugs e qualidade agora são do tr). A pasta `.harness/` ficou; apague quando não precisar mais dela.\n" +
    "Se o AGENTS.md ou docs/agents/ ainda descrevem `.harness/push` e os revisores antigos, atualize: o agente segue o que lê.");
}

// Modelo por papel, na configuração local (não versionada): a sessão principal planeja e orquestra em
// opus; subagente sem modelo definido roda em sonnet. O hook do tr garante o resto (haiku no ticket simples).
function writeLocalModels(project) {
  const file = path.join(project, ".claude", "settings.local.json");
  let data = {};
  try { data = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { /* novo */ }
  data.model = data.model || "opus";
  data.env = { CLAUDE_CODE_SUBAGENT_MODEL: "sonnet", ...(data.env || {}) };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n");
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

function ensureSandbox(project) {
  const data = readSettings(project);
  if (data.sandbox && data.sandbox.enabled === false) return;
  data.sandbox = data.sandbox || {};
  data.sandbox.enabled = true;
  data.sandbox.filesystem = data.sandbox.filesystem || {};
  const deny = data.sandbox.filesystem.denyWrite || [];
  for (const file of [".claude/trilho.json", ".claude/settings.json"]) {
    if (!deny.includes(file)) deny.push(file);
  }
  data.sandbox.filesystem.denyWrite = deny;
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
