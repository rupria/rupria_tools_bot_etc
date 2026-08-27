const { Client, GatewayIntentBits } = require("discord.js");
const { loadConfig, createWatchKey, dedupeWatches, normalizeWatch } = require("./src/config");
const {
  ensureDataDir,
  loadPersistedWatches,
  loadRuntimeState,
  savePersistedWatches,
  saveRuntimeState,
} = require("./src/storage");
const { GitHubClient } = require("./src/github");
const {
  buildCommitAlertPayload,
  buildHelpText,
  buildListText,
  buildStartupText,
  buildWatchAddedText,
  buildWatchRemovedText,
  buildPollSummaryText,
} = require("./src/messages");

const config = loadConfig();
ensureDataDir(config.dataDir);

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

const github = new GitHubClient(config.githubToken);
let savedWatches = loadPersistedWatches(config.watchFile);
let runtimeState = loadRuntimeState(config.stateFile);
let pollInFlight = false;
const lastAdminErrors = new Map();

function getAllWatches() {
  const envWatches = config.startupWatches.map((watch) => ({ ...watch, source: "env" }));
  const fileWatches = savedWatches.map((watch) => ({ ...watch, source: "saved" }));
  return dedupeWatches([...envWatches, ...fileWatches]);
}

function memberHasAllowedRole(message) {
  if (!config.allowedRoleIds.length) {
    return true;
  }
  const roles = message.member?.roles?.cache;
  if (!roles) {
    return false;
  }
  return config.allowedRoleIds.some((roleId) => roles.has(roleId));
}

function canUseCommands(message) {
  if (!message.guild || message.author.bot) {
    return false;
  }
  if (config.guildId && message.guildId !== config.guildId) {
    return false;
  }
  if (config.adminChannelId && message.channelId !== config.adminChannelId) {
    return false;
  }
  return memberHasAllowedRole(message);
}

async function sendAdminNotice(text) {
  if (!config.adminChannelId) {
    console.warn(text);
    return;
  }
  try {
    const channel = await client.channels.fetch(config.adminChannelId);
    if (channel?.isTextBased()) {
      await channel.send({
        content: text,
        allowedMentions: { parse: [], repliedUser: false },
      });
      return;
    }
  } catch (error) {
    console.warn("Failed to send admin notice:", error);
  }
  console.warn(text);
}

async function announceWatchError(watch, error) {
  const key = createWatchKey(watch);
  const message = `[watch error] ${watch.repository}@${watch.branch}: ${error.message}`;
  if (lastAdminErrors.get(key) === message) {
    return;
  }
  lastAdminErrors.set(key, message);
  await sendAdminNotice(`GitHub 감시 오류\n${watch.repository} @ ${watch.branch}\n${error.message}`);
}

async function fetchCurrentHead(watch) {
  return github.getLatestCommit(watch.repository, watch.branch);
}

function setHeadState(watch, latestCommit) {
  const key = createWatchKey(watch);
  runtimeState.branches[key] = {
    repository: watch.repository,
    branch: watch.branch,
    channelId: watch.channelId,
    lastSeenSha: latestCommit.sha,
    lastSeenAt: new Date().toISOString(),
  };
}

async function sendCommitAlert(watch, previousSha, latestCommit) {
  const channel = await client.channels.fetch(watch.channelId);
  if (!channel?.isTextBased()) {
    throw new Error(`Discord channel ${watch.channelId} is not text based.`);
  }

  let compare = null;
  if (previousSha && previousSha !== latestCommit.sha) {
    compare = await github.compareCommits(watch.repository, previousSha, latestCommit.sha).catch(() => null);
  }

  await channel.send(buildCommitAlertPayload(watch, previousSha, latestCommit, compare));
}

async function bootstrapWatch(watch) {
  const latestCommit = await fetchCurrentHead(watch);
  setHeadState(watch, latestCommit);
  saveRuntimeState(config.stateFile, runtimeState);
  return latestCommit;
}

async function pollWatches() {
  if (pollInFlight) {
    return {
      changedCount: 0,
      initializedCount: 0,
      errorCount: 0,
      skipped: true,
      watchCount: getAllWatches().length,
    };
  }

  pollInFlight = true;
  const result = {
    changedCount: 0,
    initializedCount: 0,
    errorCount: 0,
    skipped: false,
    watchCount: getAllWatches().length,
  };

  try {
    for (const watch of getAllWatches()) {
      try {
        const latestCommit = await fetchCurrentHead(watch);
        const previousSha = runtimeState.branches[createWatchKey(watch)]?.lastSeenSha || "";

        if (!previousSha) {
          setHeadState(watch, latestCommit);
          result.initializedCount += 1;
          continue;
        }

        if (previousSha !== latestCommit.sha) {
          await sendCommitAlert(watch, previousSha, latestCommit);
          result.changedCount += 1;
        }

        setHeadState(watch, latestCommit);
        lastAdminErrors.delete(createWatchKey(watch));
      } catch (error) {
        result.errorCount += 1;
        await announceWatchError(watch, error);
      }
    }
  } finally {
    saveRuntimeState(config.stateFile, runtimeState);
    pollInFlight = false;
  }

  return result;
}

function parseCommand(message) {
  const content = message.content.trim();
  if (!content.startsWith(config.commandPrefix)) {
    return null;
  }
  const rest = content.slice(config.commandPrefix.length).trim();
  const args = rest ? rest.split(/\s+/) : [];
  const action = (args.shift() || "help").toLowerCase();
  return { action, args };
}

function extractChannelTarget(args, message) {
  let channelId = message.mentions.channels.first()?.id || "";
  const filtered = [];

  for (const arg of args) {
    if (/^<#\d{17,20}>$/.test(arg)) {
      if (!channelId) {
        channelId = arg.slice(2, -1);
      }
      continue;
    }
    filtered.push(arg);
  }

  const lastArg = filtered[filtered.length - 1];
  if (!channelId && lastArg && /^\d{17,20}$/.test(lastArg)) {
    channelId = lastArg;
    filtered.pop();
  }

  return {
    args: filtered,
    channelId: channelId || message.channelId,
  };
}

function removeSavedWatch(targetWatch) {
  const targetKey = createWatchKey(targetWatch);
  const before = savedWatches.length;
  savedWatches = savedWatches.filter((watch) => createWatchKey(watch) !== targetKey);
  if (before === savedWatches.length) {
    return false;
  }
  delete runtimeState.branches[targetKey];
  savePersistedWatches(config.watchFile, savedWatches);
  saveRuntimeState(config.stateFile, runtimeState);
  return true;
}

async function handleAddCommand(message, args) {
  const parsed = extractChannelTarget(args, message);
  if (parsed.args.length < 2) {
    await message.reply({ content: buildHelpText(config.commandPrefix), allowedMentions: { parse: [], repliedUser: false } });
    return;
  }

  const watch = normalizeWatch({
    repository: parsed.args[0],
    branch: parsed.args[1],
    channelId: parsed.channelId,
  });

  const existing = getAllWatches().find((item) => createWatchKey(item) === createWatchKey(watch));
  if (existing) {
    await message.reply({
      content: `이미 감시 중입니다.\n${watch.repository} @ ${watch.branch} -> <#${watch.channelId}>`,
      allowedMentions: { parse: [], repliedUser: false },
    });
    return;
  }

  const latestCommit = await bootstrapWatch(watch);
  savedWatches = dedupeWatches([...savedWatches, watch]);
  savePersistedWatches(config.watchFile, savedWatches);

  await message.reply({
    content: buildWatchAddedText(watch, latestCommit),
    allowedMentions: { parse: [], repliedUser: false },
  });
}

async function handleRemoveCommand(message, args) {
  const parsed = extractChannelTarget(args, message);
  if (parsed.args.length < 2) {
    await message.reply({ content: buildHelpText(config.commandPrefix), allowedMentions: { parse: [], repliedUser: false } });
    return;
  }

  const watch = normalizeWatch({
    repository: parsed.args[0],
    branch: parsed.args[1],
    channelId: parsed.channelId,
  });

  const envManaged = config.startupWatches.some((item) => createWatchKey(item) === createWatchKey(watch));
  if (envManaged) {
    await message.reply({
      content: "이 감시는 WATCH_TARGETS 환경변수에서 온 항목이라 채팅 명령으로 지울 수 없습니다.",
      allowedMentions: { parse: [], repliedUser: false },
    });
    return;
  }

  const removed = removeSavedWatch(watch);
  await message.reply({
    content: removed
      ? buildWatchRemovedText(watch)
      : `일치하는 감시 대상을 찾지 못했습니다.\n${watch.repository} @ ${watch.branch} -> <#${watch.channelId}>`,
    allowedMentions: { parse: [], repliedUser: false },
  });
}

async function handleListCommand(message) {
  await message.reply({
    content: buildListText(getAllWatches()),
    allowedMentions: { parse: [], repliedUser: false },
  });
}

async function handleCheckCommand(message) {
  const result = await pollWatches({ manual: true });
  await message.reply({
    content: buildPollSummaryText(result),
    allowedMentions: { parse: [], repliedUser: false },
  });
}

async function handleTestCommand(message, args) {
  const parsed = extractChannelTarget(args, message);
  const channel = await client.channels.fetch(parsed.channelId);
  if (!channel?.isTextBased()) {
    throw new Error("테스트 메시지를 보낼 텍스트 채널을 찾지 못했습니다.");
  }

  const demoWatch = normalizeWatch({
    repository: "rupria/rupria_tools_bot_etc",
    branch: "main",
    channelId: parsed.channelId,
  });
  const now = new Date().toISOString();
  await channel.send(
    buildCommitAlertPayload(
      demoWatch,
      "1234567oldsha1234567oldsha1234567oldsha",
      {
        sha: "abcdef1234567890abcdef1234567890abcdef12",
        htmlUrl: "https://github.com/rupria/rupria_tools_bot_etc/commit/abcdef1234567890abcdef1234567890abcdef12",
        message: "테스트 알림 커밋 메시지",
        authorName: "git_T_bot",
        committedAt: now,
      },
      {
        totalCommits: 3,
        htmlUrl: "https://github.com/rupria/rupria_tools_bot_etc/compare/old...new",
      },
    ),
  );

  await message.reply({
    content: `테스트 알림을 <#${parsed.channelId}> 채널로 전송했습니다.`,
    allowedMentions: { parse: [], repliedUser: false },
  });
}

client.on("messageCreate", async (message) => {
  const command = parseCommand(message);
  if (!command) {
    return;
  }

  if (!canUseCommands(message)) {
    await message.reply({
      content: "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.",
      allowedMentions: { parse: [], repliedUser: false },
    });
    return;
  }

  try {
    if (command.action === "help") {
      await message.reply({ content: buildHelpText(config.commandPrefix), allowedMentions: { parse: [], repliedUser: false } });
      return;
    }
    if (command.action === "list" || command.action === "status") {
      await handleListCommand(message);
      return;
    }
    if (command.action === "add") {
      await handleAddCommand(message, command.args);
      return;
    }
    if (command.action === "remove") {
      await handleRemoveCommand(message, command.args);
      return;
    }
    if (command.action === "check") {
      await handleCheckCommand(message);
      return;
    }
    if (command.action === "test") {
      await handleTestCommand(message, command.args);
      return;
    }

    await message.reply({
      content: buildHelpText(config.commandPrefix),
      allowedMentions: { parse: [], repliedUser: false },
    });
  } catch (error) {
    await message.reply({
      content: `처리 중 오류가 났습니다.\n${error.message}`,
      allowedMentions: { parse: [], repliedUser: false },
    });
  }
});

client.once("ready", async () => {
  console.log(`Logged in as ${client.user.tag}`);
  if (config.startupNotify) {
    await sendAdminNotice(buildStartupText(getAllWatches(), config.pollIntervalMs));
  }
  await pollWatches();
  setInterval(() => {
    void pollWatches();
  }, config.pollIntervalMs);
});

client.login(config.botToken).catch((error) => {
  console.error("Bot login failed:", error);
  process.exitCode = 1;
});
