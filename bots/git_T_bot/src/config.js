const path = require("node:path");
const dotenv = require("dotenv");

dotenv.config({ quiet: true });

function parseList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeRepository(value) {
  const trimmed = String(value || "").trim().replace(/\.git$/i, "");
  if (!trimmed) {
    throw new Error("저장소 이름이 비어 있습니다.");
  }

  const cleaned = trimmed
    .replace(/^https:\/\/github\.com\//i, "")
    .replace(/^http:\/\/github\.com\//i, "")
    .replace(/^git@github\.com:/i, "");

  const parts = cleaned.split("/").filter(Boolean);
  if (parts.length !== 2) {
    throw new Error(`GitHub 저장소 형식이 아닙니다: ${value}`);
  }
  return `${parts[0]}/${parts[1]}`;
}

function normalizeBranch(value) {
  const branch = String(value || "").trim();
  if (!branch) {
    throw new Error("브랜치 이름이 비어 있습니다.");
  }
  return branch;
}

function normalizeChannelId(value) {
  const channelId = String(value || "").trim();
  if (!/^\d{17,20}$/.test(channelId)) {
    throw new Error(`Discord 채널 ID 형식이 아닙니다: ${value}`);
  }
  return channelId;
}

function normalizeWatch(watch) {
  return {
    repository: normalizeRepository(watch.repository),
    branch: normalizeBranch(watch.branch),
    channelId: normalizeChannelId(watch.channelId),
  };
}

function createWatchKey(watch) {
  return [
    normalizeRepository(watch.repository).toLowerCase(),
    normalizeBranch(watch.branch),
    normalizeChannelId(watch.channelId),
  ].join("::");
}

function dedupeWatches(watches) {
  const byKey = new Map();
  for (const watch of watches) {
    const normalized = normalizeWatch(watch);
    const source = watch.source || normalized.source;
    byKey.set(createWatchKey(normalized), source ? { ...normalized, source } : normalized);
  }
  return [...byKey.values()];
}

function parseWatchTargets(value) {
  return String(value || "")
    .split(/[\r\n,]+/)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [repository, branch, channelId] = entry.split("|").map((item) => item.trim());
      if (!repository || !branch || !channelId) {
        throw new Error(`WATCH_TARGETS 항목 형식이 잘못되었습니다: ${entry}`);
      }
      return normalizeWatch({ repository, branch, channelId });
    });
}

function parseBoolean(value, fallback = false) {
  if (value == null || value === "") {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(String(value).trim().toLowerCase());
}

function parsePollInterval(value) {
  const numeric = Number.parseInt(String(value || "60000"), 10);
  if (!Number.isFinite(numeric) || numeric < 10000) {
    throw new Error("WATCH_POLL_INTERVAL_MS는 10000 이상 숫자여야 합니다.");
  }
  return numeric;
}

function loadConfig() {
  const botToken = String(process.env.DISCORD_BOT_TOKEN || "").trim();
  if (!botToken) {
    throw new Error("DISCORD_BOT_TOKEN이 필요합니다.");
  }

  const guildId = String(process.env.DISCORD_GUILD_ID || "").trim();
  const adminChannelId = String(process.env.DISCORD_ADMIN_CHANNEL_ID || "").trim();
  if (adminChannelId && !/^\d{17,20}$/.test(adminChannelId)) {
    throw new Error("DISCORD_ADMIN_CHANNEL_ID 형식이 잘못되었습니다.");
  }

  const dataDir = path.resolve(process.cwd(), "data");

  return {
    botToken,
    guildId,
    adminChannelId,
    allowedRoleIds: parseList(process.env.DISCORD_ALLOWED_ROLE_IDS),
    githubToken: String(process.env.GITHUB_TOKEN || "").trim(),
    pollIntervalMs: parsePollInterval(process.env.WATCH_POLL_INTERVAL_MS),
    startupWatches: parseWatchTargets(process.env.WATCH_TARGETS),
    commandPrefix: String(process.env.COMMAND_PREFIX || "!watch").trim() || "!watch",
    startupNotify: parseBoolean(process.env.STARTUP_NOTIFY, true),
    dataDir,
    watchFile: path.join(dataDir, "watchers.json"),
    stateFile: path.join(dataDir, "runtime-state.json"),
  };
}

module.exports = {
  createWatchKey,
  dedupeWatches,
  loadConfig,
  normalizeRepository,
  normalizeWatch,
  parseWatchTargets,
  shortRepository: normalizeRepository,
};
