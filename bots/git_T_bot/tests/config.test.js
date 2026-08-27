const test = require("node:test");
const assert = require("node:assert/strict");

const {
  createWatchKey,
  dedupeWatches,
  normalizeRepository,
  parseWatchTargets,
} = require("../src/config");

test("normalizeRepository handles GitHub URL", () => {
  assert.equal(
    normalizeRepository("https://github.com/rupria/rupria_tools_bot_etc.git"),
    "rupria/rupria_tools_bot_etc",
  );
});

test("parseWatchTargets reads multiple watches", () => {
  const watches = parseWatchTargets(
    "rupria/rupria_tools_bot_etc|main|12345678901234567,rupria/rupria_tools_bot_etc|dev|12345678901234568",
  );

  assert.equal(watches.length, 2);
  assert.equal(watches[0].branch, "main");
  assert.equal(watches[1].branch, "dev");
});

test("dedupeWatches removes duplicate repo branch channel combinations", () => {
  const watches = dedupeWatches([
    { repository: "rupria/rupria_tools_bot_etc", branch: "main", channelId: "12345678901234567" },
    { repository: "https://github.com/rupria/rupria_tools_bot_etc", branch: "main", channelId: "12345678901234567" },
  ]);

  assert.equal(watches.length, 1);
  assert.equal(
    createWatchKey(watches[0]),
    "rupria/rupria_tools_bot_etc::main::12345678901234567",
  );
});
