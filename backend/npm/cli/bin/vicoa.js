#!/usr/bin/env node
"use strict";

const { execFileSync } = require("child_process");
const path = require("path");

const PLATFORM_PACKAGES = {
  "darwin-arm64": "@vicoa/cli-darwin-arm64",
  "darwin-x64":   "@vicoa/cli-darwin-x64",
  "linux-x64":    "@vicoa/cli-linux-x64",
  "win32-x64":    "@vicoa/cli-win32-x64",
};

const key = `${process.platform}-${process.arch}`;
const alias = PLATFORM_PACKAGES[key];

if (!alias) {
  console.error(`Unsupported platform: ${key}`);
  process.exit(1);
}

let pkgDir;
try {
  pkgDir = path.dirname(require.resolve(`${alias}/package.json`));
} catch {
  console.error(`Platform package for ${key} is not installed.`);
  console.error(`Try reinstalling: npm install -g @vicoa/cli`);
  process.exit(1);
}

const isWindows = process.platform === "win32";
const binary = path.join(pkgDir, "bin", isWindows ? "vicoa.exe" : "vicoa");

try {
  execFileSync(binary, process.argv.slice(2), { stdio: "inherit" });
} catch (err) {
  process.exit(err.status ?? 1);
}
