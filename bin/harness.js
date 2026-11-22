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
const usage = "uso: fullchico-harness install [pasta do projeto] [--profile fullstack-typescript|livre|existente] [--force]\n" +
  "     fullchico-harness update [pasta do projeto] [--force]\n" +
  "     fullchico-harness puro [pasta do projeto]\n" +
  "     fullchico-harness add <plugin> [<plugin>...] [--project <pasta>]   (trilho, bugs, qualidade)\n" +
  "     fullchico-harness --version";

if (command === "puro") {
  // Marca o projeto como puro e traz do global só a ferramenta pessoal (Orca, rtk), para o escopo local.
  const project = rest.find((arg) => !arg.startsWith("-")) || ".";
  const run = spawnSync("python3", ["-I", path.join(root, "plugins/trilho/scripts/make_pure.py"), project], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else if (command === "add") {
  // Instala plugins do marketplace do FullChico no escopo do projeto, pelo `claude`.
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
  const commands = [["plugin", "marketplace", "add", "FullChico/fullchico-harness"],
    ...names.map((n) => ["plugin", "install", `${n}@fullchico`, "--scope", "project"])];
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
    if (i > 0 && run.status !== 0) status = run.status === null ? 1 : run.status;
  }
  process.exit(status);
} else if (command === "--version"|| command === "-v") {
  console.log(require(path.join(root, "package.json")).version);
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
  const run = spawnSync("bash", [path.join(root, "install"), ...rest], { stdio: "inherit", env });
  process.exit(run.status === null ? 1 : run.status);
} else {
  console.error(usage);
  process.exit(command === "--help" || command === "-h" ? 0 : 2);
}
