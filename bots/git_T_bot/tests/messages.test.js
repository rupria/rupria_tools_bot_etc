const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildListText,
  buildPollSummaryText,
  buildWatchAddedText,
  shortSha,
} = require("../src/messages");

test("shortSha returns seven characters", () => {
  assert.equal(shortSha("abcdef1234567890"), "abcdef1");
});

test("buildListText includes source and branch", () => {
  const text = buildListText([
    {
      repository: "rupria/rupria_tools_bot_etc",
      branch: "main",
      channelId: "12345678901234567",
      source: "saved",
    },
  ]);

  assert.match(text, /main/);
  assert.match(text, /\[saved\]/);
});

test("buildWatchAddedText includes sha", () => {
  const text = buildWatchAddedText(
    {
      repository: "rupria/rupria_tools_bot_etc",
      branch: "main",
      channelId: "12345678901234567",
    },
    { sha: "abcdef1234567890" },
  );

  assert.match(text, /abcdef1/);
});

test("buildPollSummaryText reflects counts", () => {
  const text = buildPollSummaryText({
    skipped: false,
    watchCount: 3,
    initializedCount: 1,
    changedCount: 2,
    errorCount: 0,
  });

  assert.match(text, /감시 대상: 3개/);
  assert.match(text, /새 알림: 2개/);
});
