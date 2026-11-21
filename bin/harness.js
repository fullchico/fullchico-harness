#!/usr/bin/env node
// Entrada do pacote: `npx @fullchico/harness install [pasta do projeto] [--profile <perfil>] [--force]`.
// O trabalho é do script `install`, em shell e Python: aqui só se acha a pasta do pacote e se repassa.
"use strict";
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const [command, ...rest] = process.argv.slice(2);
const usage = "uso: fullchico-harness install [pasta do projeto] [--profile fullstack-typescript|livre|existente] [--force]\n" +
  "     fullchico-harness --version";

if (command === "--version" || command === "-v") {
  console.log(require(path.join(root, "package.json")).version);
} else if (command === "install") {
  const run = spawnSync("bash", [path.join(root, "install"), ...rest], { stdio: "inherit" });
  process.exit(run.status === null ? 1 : run.status);
} else {
  console.error(usage);
  process.exit(command === "--help" || command === "-h" ? 0 : 2);
}
