#!/usr/bin/env node
// Entrada do pacote: `npx @fullchico/harness install [pasta do projeto] [--profile <perfil>] [--force]`
// e `npx @fullchico/harness@latest update [pasta do projeto] [--force]`, para o projeto que já tem o harness.
// O trabalho é do script `install`, em shell e Python: aqui só se acha a pasta do pacote e se repassa.
"use strict";
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const [command, ...rest] = process.argv.slice(2);
const usage = "uso: fullchico-harness install [pasta do projeto] [--padrao]   (plugins por projeto e portões)\n" +
  "     fullchico-harness install [pasta do projeto] --legado [--profile ...] [--force]   (modelo anterior)\n" +
  "     fullchico-harness update [pasta do projeto] [--force]\n" +
  "     fullchico-harness puro [pasta do projeto]\n" +
  "     fullchico-harness portoes [--analisar] [--gravar] [--padrao] [--projeto <pasta>]\n" +
  "     fullchico-harness add <plugin> [<plugin>...] [--project <pasta>]   (trilho, bugs, qualidade)\n" +
  "     fullchico-harness --version";

if (command === "puro") {
  // Marca o projeto como puro e traz do global só a ferramenta pessoal (Orca, rtk), para o escopo local.
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/trilho/scripts/make_pure.py"), project], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "portoes") {
  // Propõe (--analisar, o padrão) ou grava (--gravar) o registro de portões do projeto em .claude/trilho.json.
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/trilho/scripts/portoes.py"), ...rest], { stdio: "inherit" });
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
  process.exit(addPlugins(names, project));
} else if (command === "--version"|| command === "-v") {
  console.log(require(path.join(root, "package.json")).version);
} else if (command === "install" && !rest.includes("--legado")) {
  // O harness do projeto no modelo novo: plugins por projeto e registro de portões. O dono escolhe
  // o padrão da lib (--padrao) ou a análise do que o projeto já usa (o padrão do comando).
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  const inGit = spawnSync("git", ["-C", project, "rev-parse", "--show-toplevel"], { encoding: "utf8" });
  if (inGit.status !== 0) {
    console.error(`install: ${project} não é um repositório git.`);
    process.exit(2);
  }
  // A lib cuida do caminho e da aprendizagem; começo e fim são das ferramentas do projeto, ligadas pelos
  // portões. O ponytail (código mínimo e reutilizável) vem junto, do marketplace dele.
  const status = addPlugins(["trilho", "memoria"], project, [["ponytail", "DietrichGebert/ponytail", "ponytail"]]);
  addRtkHook(project);
  const mode = rest.includes("--padrao") ? "--padrao" : "--analisar";
  console.log(`\n$ fullchico-harness portoes ${mode} --gravar`);
  const gates = spawnSync("python3", ["-I", path.join(root, "plugins/trilho/scripts/portoes.py"), mode, "--gravar",
    "--projeto", project], { stdio: "inherit" });
  console.log("\nPróximos passos:\n" +
    "  1. Confira os portões em .claude/trilho.json (só você os altera: `fullchico-harness portoes`).\n" +
    "  2. Para rodar o projeto só com o que ele declara: `fullchico-harness puro`, e abra com `cc`.\n" +
    "  3. Abra uma sessão nova no projeto e rode `portao` para ver o que cada etapa pede.\n" +
    "O modelo anterior (plugin único `harness`) continua em `fullchico-harness install --legado`.");
  process.exit(status || (gates.status === null ? 1 : gates.status));
} else if (command === "install" || command === "update") {
  const env = { ...process.env };
  if (command === "update") {
    // Atualizar é instalar por cima, na versão deste pacote: os mesmos arquivos, plugins e skills.
    const project = rest.find((arg) => !arg.startsWith("-")) || ".";
    if (!fs.existsSync(path.join(project, ".harness"))) {
      console.error(`update: ${path.resolve(project)} ainda não tem o harness. Use: fullchico-harness install`);
      process.exit(2);
    }
    env.HARNESS_UPDATE = "1";
  }
  const legacy = rest.filter((arg) => arg !== "--legado");
  const run = spawnSync("bash", [path.join(root, "install"), ...legacy], { stdio: "inherit", env });
  process.exit(run.status === null ? 1 : run.status);
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
    spawnSync("python3", ["-I", path.join(root, "plugins/trilho/scripts/portoes.py"), "--registrar", manifest,
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
