# git_T_bot

이 봇은 GitHub 저장소와 브랜치를 20초마다 확인해 새 커밋을 등록된 Discord 채널에 알린다. Dishost 무료 플랜에서는 외부 웹훅 주소가 제공되지 않으므로 polling을 기본으로 사용하며, 공개 주소가 있는 환경에서는 `push` 웹훅으로도 동작한다.

## 하는 일

- 저장소별 구분
- 브랜치별 구분
- 사용자별 감지 필터
- 채널별 알림 분리
- 재시작 후에도 감시 대상 유지
- `main`, `dev`, `release` 같은 브랜치를 각각 따로 감시

## 명령어

관리 채널에서 아래 형식으로 쓴다.

```text
!watch list
!watch list owner/repo *
!watch branches
!watch branches owner/repo
!watch branches owner/repo main rupria
!watch add owner/repo main
!watch add owner/repo,owner/repo2 main,test rupria,teammate #alerts
!watch remove owner/repo,owner/repo2 main,test
!watch check
!watch test
/github_watches repository:* branch:* user:*
/github_branches repository:owner/repo,owner/repo2 branch:main,test user:rupria,teammate
/github_watch repository:owner/repo,owner/repo2 branch:main,test user:rupria,teammate channel:#alerts
/github_unwatch repository:owner/repo,owner/repo2 branch:main,test user:rupria,teammate channel:#alerts
```

- `*`는 전체를 뜻한다.
- 여러 레포지토리, 브랜치, 사용자는 쉼표로 한 번에 입력할 수 있다.
- 채널을 따로 적지 않으면 현재 채널에 연결한다.
- 같은 봇을 여러 Discord 서버에 초대해도 조회 명령은 현재 서버에 연결된 채널 감시만 보여준다.
- 사용자를 따로 적지 않으면 `*`로 저장되어 모든 작성자를 감지한다.
- `!watch branches`는 저장소와 브랜치별로 묶어서 현재 감시 현황을 보여준다.
- `!watch branches owner/repo`와 `/github_branches`는 실제 GitHub 브랜치 목록과 현재 연결된 감시 상태를 함께 보여준다.
- `DISCORD_ALLOWED_ROLE_IDS`를 넣으면 해당 역할만 명령을 쓸 수 있다.
- `DISCORD_ADMIN_CHANNEL_ID`를 넣으면 그 채널에서만 명령을 받는다.
- Discord 서버 관리자 권한이 있으면 서버/채널/역할 제한 없이 바로 사용할 수 있다.

## 환경 변수

- `DISCORD_BOT_TOKEN`: Discord 봇 토큰
- `DISCORD_GUILD_ID`: 사용할 서버 ID
- `DISCORD_ADMIN_CHANNEL_ID`: 관리 명령을 받을 채널 ID
- `DISCORD_ALLOWED_ROLE_IDS`: 쉼표로 구분한 관리 역할 ID
- `GITHUB_TOKEN`: GitHub API 토큰. private 저장소 조회와 변경 파일·줄 수 비교에 필요
- `GITHUB_WEBHOOK_SECRET`: GitHub 웹훅과 봇 양쪽에 동일하게 넣을 임의의 비밀 문자열
- `GITHUB_WEBHOOK_PATH`: 웹훅 수신 경로. 기본값 `/github/webhook`
- `PORT`: Dishost가 연결할 HTTP 포트. 기본값 `8080`
- `WEBHOOK_HOST`: 기본값 `0.0.0.0`
- `POLLING_ENABLED`: 주기 조회 사용 여부. Dishost 무료 플랜 기본값 `true`
- `WATCH_POLL_INTERVAL_MS`: 조회 주기. 기본값 `20000`(20초)
- `WATCH_TARGETS`: 시작할 때 미리 붙일 감시 목록. `owner/repo|branch|channel_id` 또는 `owner/repo|branch|channel_id|user` 형식
- `COMMAND_PREFIX`: 기본값 `!`이고 실제 명령은 `!watch ...`
- `STARTUP_NOTIFY`: 시작 시 관리 채널에 상태 알림 전송 여부

## 로컬 실행

```powershell
Copy-Item .env.example .env
notepad .env
python -m pip install discord.py aiohttp python-dotenv
python main.py
```

## GitHub 웹훅 등록

감시할 각 GitHub 저장소의 `Settings > Webhooks > Add webhook`에서 다음과 같이 등록한다.

1. Payload URL: `https://<Dishost 서비스 공개 주소>/github/webhook`
2. Content type: `application/json`
3. Secret: Dishost의 `GITHUB_WEBHOOK_SECRET`과 동일한 값
4. 이벤트: `Just the push event`
5. Active: 활성화

GitHub의 `ping` 요청이 HTTP 200을 받으면 연결된 것이다. `/health`에서는 서비스와 Discord 연결 상태를 확인할 수 있다. 감시 명령으로 저장소를 추가하더라도 해당 저장소의 GitHub 웹훅은 별도로 한 번 등록해야 한다.

## Dishost 배포

2026년 8월 27일 기준, 현재 연결된 Dishost 서비스 화면에서는 Python 이미지를 사용하고 `GIT_ADDRESS`, `BRANCH`, `STARTUP_FILE`, `PY_PACKAGES`를 시작 설정에서 받는다. 그래서 이 봇도 Python 기준으로 맞춰두었다.

권장 순서:

1. Dishost 서비스에서 GitHub 저장소 `rupria/rupria_tools_bot_etc` 연결
2. 브랜치 `main` 선택
3. 시작 파일을 `bots/git_T_bot/main.py`로 설정
4. Python 패키지에 `discord.py aiohttp python-dotenv` 입력
5. 무료 플랜은 환경 변수에 `DISCORD_BOT_TOKEN`, `GITHUB_TOKEN`, `POLLING_ENABLED=true`, `WATCH_POLL_INTERVAL_MS=20000` 입력
6. Push 시 자동 배포 활성화

## 완료 알림 기준

이 버전은 로컬 Codex 세션을 읽지 않는다. 등록된 저장소·브랜치에 GitHub `push` 웹훅이 오면 그 커밋을 작업 완료 신호로 보고 알림을 보낸다.
