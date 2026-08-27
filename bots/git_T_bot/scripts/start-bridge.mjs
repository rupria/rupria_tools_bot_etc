import { existsSync, readFileSync } from "node:fs";
import { readdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

function loadEnvFile(envPath) {
  const values = {};
  if (!existsSync(envPath)) {
    return values;
  }
  for (const rawLine of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const separator = line.indexOf("=");
    if (separator === -1) {
      continue;
    }
    const key = line.slice(0, separator).trim();
    const value = line
      .slice(separator + 1)
      .trim()
      .replace(/^['"]|['"]$/g, "");
    values[key] = value;
  }
  return values;
}

function withExtraPath(env, entries) {
  const filtered = entries.filter(Boolean);
  if (!filtered.length) {
    return env;
  }
  return {
    ...env,
    PATH: `${filtered.join(path.delimiter)}${path.delimiter}${env.PATH || ""}`,
  };
}

function resolveWindowsCodexBin() {
  const localAppData = process.env.LOCALAPPDATA;
  if (!localAppData) {
    return null;
  }
  const baseDir = path.join(localAppData, "OpenAI", "Codex", "bin");
  if (!existsSync(baseDir)) {
    return null;
  }
  const candidates = [];
  for (const entry of readdirSync(baseDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }
    const binDir = path.join(baseDir, entry.name);
    const codexPath = path.join(binDir, "codex.exe");
    if (existsSync(codexPath)) {
      candidates.push(binDir);
    }
  }
  return candidates.sort().at(-1) || null;
}

function resolveBundledPython() {
  const homeDir = os.homedir();
  const candidates = process.platform === "win32"
    ? [
        path.join(homeDir, ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python.exe"),
      ]
    : [
        path.join(homeDir, ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "bin", "python3"),
        path.join(homeDir, ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python"),
      ];
  return candidates.find((candidate) => existsSync(candidate)) || null;
}

function resolvePythonCommand(env) {
  const explicit = env.CONNECT_PYTHON || env.PYTHON;
  if (explicit) {
    return explicit;
  }
  const bundled = resolveBundledPython();
  if (bundled) {
    return bundled;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function resolveCdcCommand() {
  const localBin = process.platform === "win32"
    ? path.join(projectRoot, "node_modules", ".bin", "cdc.cmd")
    : path.join(projectRoot, "node_modules", ".bin", "cdc");
  if (existsSync(localBin)) {
    return [localBin, []];
  }
  return process.platform === "win32"
    ? ["npx.cmd", ["cdc"]]
    : ["npx", ["cdc"]];
}

function commandExists(command, env) {
  const probe = process.platform === "win32"
    ? spawnSync("where", [command], { env, stdio: "ignore" })
    : spawnSync("which", [command], { env, stdio: "ignore" });
  return probe.status === 0;
}

function parseRoutes(rawValue) {
  if (!rawValue) {
    return [];
  }
  return rawValue
    .split(/[\r\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function stopChild(child, signal = "SIGTERM") {
  if (!child || child.exitCode !== null) {
    return;
  }
  child.kill(signal);
}

const fileEnv = loadEnvFile(path.join(projectRoot, ".env"));
let runtimeEnv = { ...process.env, ...fileEnv, ...process.env };
runtimeEnv = withExtraPath(runtimeEnv, [process.platform === "win32" ? resolveWindowsCodexBin() : null]);

if (!commandExists("codex", runtimeEnv) && !resolveWindowsCodexBin()) {
  console.error("Codex CLI를 찾지 못했습니다. PATH 또는 OpenAI Codex 설치 경로를 확인하세요.");
  process.exit(1);
}

const python = resolvePythonCommand(runtimeEnv);
const configProcess = spawn(
  python,
  [path.join(projectRoot, "scripts", "configure-bridge.py")],
  {
    cwd: projectRoot,
    env: runtimeEnv,
    stdio: "inherit",
  },
);

configProcess.on("exit", (code) => {
  if (code !== 0) {
    process.exit(code ?? 1);
  }

  const routes = parseRoutes(runtimeEnv.DISCORD_COMPLETION_ALERT_ROUTES || "");
  let alertProcess = null;
  if (routes.length) {
    const alertArgs = [
      path.join(projectRoot, "scripts", "completion_alert.py"),
      "--project-root",
      projectRoot,
    ];
    for (const route of routes) {
      alertArgs.push("--route", route);
    }
    alertProcess = spawn(python, alertArgs, {
      cwd: projectRoot,
      env: runtimeEnv,
      stdio: "inherit",
    });
  } else {
    console.log("DISCORD_COMPLETION_ALERT_ROUTES가 비어 있어 완료 알림 모니터는 시작하지 않습니다.");
  }

  const [cdcCommand, cdcArgs] = resolveCdcCommand();
  const bridgeProcess = spawn(cdcCommand, [...cdcArgs, "start", "--direct"], {
    cwd: projectRoot,
    env: runtimeEnv,
    stdio: "inherit",
  });

  const shutdown = () => {
    stopChild(alertProcess);
    stopChild(bridgeProcess);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  bridgeProcess.on("exit", (bridgeCode) => {
    stopChild(alertProcess);
    process.exit(bridgeCode ?? 0);
  });

  if (alertProcess) {
    alertProcess.on("exit", (alertCode) => {
      if (alertCode && bridgeProcess.exitCode === null) {
        console.error(`완료 알림 모니터가 비정상 종료되었습니다. exit code=${alertCode}`);
        stopChild(bridgeProcess);
      }
    });
  }
});
