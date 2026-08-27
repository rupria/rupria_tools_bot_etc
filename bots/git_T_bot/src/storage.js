const fs = require("node:fs");
const path = require("node:path");

function ensureDataDir(dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
}

function readJsonFile(filePath, fallback) {
  if (!fs.existsSync(filePath)) {
    return fallback;
  }
  const raw = fs.readFileSync(filePath, "utf8").trim();
  if (!raw) {
    return fallback;
  }
  return JSON.parse(raw);
}

function writeJsonFile(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function loadPersistedWatches(filePath) {
  const data = readJsonFile(filePath, { version: 1, watches: [] });
  return Array.isArray(data.watches) ? data.watches : [];
}

function savePersistedWatches(filePath, watches) {
  writeJsonFile(filePath, { version: 1, watches });
}

function loadRuntimeState(filePath) {
  const data = readJsonFile(filePath, { version: 1, branches: {} });
  return {
    version: 1,
    branches: typeof data.branches === "object" && data.branches ? data.branches : {},
  };
}

function saveRuntimeState(filePath, state) {
  writeJsonFile(filePath, state);
}

module.exports = {
  ensureDataDir,
  loadPersistedWatches,
  loadRuntimeState,
  savePersistedWatches,
  saveRuntimeState,
};
