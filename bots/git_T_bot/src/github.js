class GitHubApiError extends Error {
  constructor(message, status, details = "") {
    super(message);
    this.name = "GitHubApiError";
    this.status = status;
    this.details = details;
  }
}

function splitRepository(repository) {
  const parts = repository.split("/");
  if (parts.length !== 2) {
    throw new Error(`GitHub 저장소 형식이 아닙니다: ${repository}`);
  }
  return {
    owner: parts[0],
    repo: parts[1],
  };
}

class GitHubClient {
  constructor(token) {
    this.token = token || "";
  }

  async request(endpoint) {
    const headers = {
      Accept: "application/vnd.github+json",
      "User-Agent": "git_T_bot/1.0",
      "X-GitHub-Api-Version": "2022-11-28",
    };
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    const response = await fetch(`https://api.github.com${endpoint}`, { headers });
    if (!response.ok) {
      const details = await response.text();
      throw new GitHubApiError(
        `GitHub API 요청 실패 (${response.status})`,
        response.status,
        details.slice(0, 400),
      );
    }
    return response.json();
  }

  async getLatestCommit(repository, branch) {
    const { owner, repo } = splitRepository(repository);
    const data = await this.request(
      `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/commits/${encodeURIComponent(branch)}`,
    );

    return {
      sha: String(data.sha),
      htmlUrl: String(data.html_url),
      message: String(data.commit?.message || ""),
      authorName: String(data.author?.login || data.commit?.author?.name || "unknown"),
      committedAt: String(data.commit?.author?.date || new Date().toISOString()),
    };
  }

  async compareCommits(repository, previousSha, latestSha) {
    const { owner, repo } = splitRepository(repository);
    const data = await this.request(
      `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/compare/${encodeURIComponent(previousSha)}...${encodeURIComponent(latestSha)}`,
    );
    return {
      htmlUrl: String(data.html_url),
      totalCommits: Number.isFinite(data.total_commits) ? data.total_commits : 0,
    };
  }
}

module.exports = {
  GitHubApiError,
  GitHubClient,
  splitRepository,
};
