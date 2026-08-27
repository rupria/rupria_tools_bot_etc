const { EmbedBuilder } = require("discord.js");

function shortSha(value) {
  return String(value || "").slice(0, 7);
}

function firstLine(text) {
  return String(text || "").split(/\r?\n/, 1)[0].trim();
}

function truncate(text, maxLength) {
  const value = String(text || "");
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 3)}...`;
}

function buildCommitAlertPayload(watch, previousSha, latestCommit, compare) {
  const summary = compare?.totalCommits
    ? `${compare.totalCommits}개 커밋 반영`
    : "새 커밋 반영";

  const lines = [
    `[커밋 열기](${latestCommit.htmlUrl})`,
  ];
  if (compare?.htmlUrl) {
    lines.push(`[변경 보기](${compare.htmlUrl})`);
  }

  const embed = new EmbedBuilder()
    .setColor(0xdb3a34)
    .setTitle("브랜치 업데이트 알림")
    .setDescription(`${truncate(firstLine(latestCommit.message), 180)}\n${lines.join(" | ")}`)
    .addFields(
      { name: "저장소", value: watch.repository, inline: true },
      { name: "브랜치", value: watch.branch, inline: true },
      { name: "작성자", value: latestCommit.authorName, inline: true },
      { name: "이전 SHA", value: previousSha ? shortSha(previousSha) : "-", inline: true },
      { name: "현재 SHA", value: shortSha(latestCommit.sha), inline: true },
      { name: "반영 수", value: summary, inline: true },
    )
    .setTimestamp(new Date(latestCommit.committedAt))
    .setFooter({ text: "GitHub 브랜치 HEAD 변경을 감지했습니다." });

  return {
    embeds: [embed],
    allowedMentions: { parse: [] },
  };
}

function buildHelpText(prefix) {
  return [
    "사용 가능한 명령",
    `${prefix} list`,
    `${prefix} add owner/repo branch [#channel]`,
    `${prefix} remove owner/repo branch [#channel]`,
    `${prefix} check`,
    `${prefix} test [#channel]`,
  ].join("\n");
}

function buildListText(watches) {
  if (!watches.length) {
    return "현재 등록된 감시 대상이 없습니다.";
  }
  return [
    `현재 감시 대상 ${watches.length}개`,
    ...watches.map((watch, index) => {
      const source = watch.source === "env" ? "env" : "saved";
      return `${index + 1}. ${watch.repository} @ ${watch.branch} -> <#${watch.channelId}> [${source}]`;
    }),
  ].join("\n");
}

function buildStartupText(watches, pollIntervalMs) {
  return [
    "git_T_bot 실행됨",
    `감시 대상: ${watches.length}개`,
    `주기: ${Math.round(pollIntervalMs / 1000)}초`,
  ].join("\n");
}

function buildWatchAddedText(watch, latestCommit) {
  return [
    "감시를 추가했습니다.",
    `${watch.repository} @ ${watch.branch} -> <#${watch.channelId}>`,
    `기준 SHA: ${shortSha(latestCommit.sha)}`,
  ].join("\n");
}

function buildWatchRemovedText(watch) {
  return [
    "감시를 제거했습니다.",
    `${watch.repository} @ ${watch.branch} -> <#${watch.channelId}>`,
  ].join("\n");
}

function buildPollSummaryText(result) {
  if (result.skipped) {
    return "이미 점검이 진행 중이라 이번 요청은 건너뛰었습니다.";
  }
  return [
    "점검 완료",
    `감시 대상: ${result.watchCount}개`,
    `초기화: ${result.initializedCount}개`,
    `새 알림: ${result.changedCount}개`,
    `오류: ${result.errorCount}개`,
  ].join("\n");
}

module.exports = {
  buildCommitAlertPayload,
  buildHelpText,
  buildListText,
  buildPollSummaryText,
  buildStartupText,
  buildWatchAddedText,
  buildWatchRemovedText,
  shortSha,
};
