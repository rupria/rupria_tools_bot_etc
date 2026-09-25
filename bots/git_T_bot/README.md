# git_T_bot

이 봇은 GitHub `push` 웹훅을 받아 저장소·브랜치·사용자 조건에 맞는 커밋 알림을 Discord 채널로 보냅니다.

20초 polling은 사용하지 않습니다. 상시 실행되는 공개 HTTPS 웹 서비스에서 GitHub가 전달한 이벤트를 바로 처리합니다.

## 하는 일

- 저장소별 구분
- 브랜치별 구분
- 사용자별 감지 필터
- 채널별 알림 분리
- GitHub API polling 없이 실시간 push 수신
- 저장소별 웹훅 서명 검증과 중복 전송 방지
- 재시작 후에도 감시 대상 유지
- `main`, `dev`, `release` 등의 브랜치를 각각 따로 감시

## 명령어

관리 채널에서 아래 형식으로 사용합니다.

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

/github_webhook_setup repository:owner/repo
/github_status
/github_watches repository:* branch:* user:*
/github_branches repository:owner/repo,owner/repo2 branch:main,test user:rupria,teammate
/github_watch repository:owner/repo,owner/repo2 branch:main,test user:rupria,teammate channel:#alerts
/github_unwatch repository:owner/repo,owner/repo2 branch:main,test user:rupria,teammate channel:#alerts
```

### 명령어 사용 규칙

- `*`는 전체를 뜻합니다.
- 여러 저장소, 브랜치, 사용자는 쉼표로 한 번에 입력할 수 있습니다.
- 채널을 따로 적지 않으면 현재 채널에 연결합니다.
- 같은 봇을 여러 Discord 서버에 초대해도 조회 명령은 현재 서버에 연결된 채널 감시만 보여줍니다.
- 사용자를 따로 적지 않으면 `*`로 저장되어 모든 작성자를 감지합니다.
- `!watch branches`는 저장소와 브랜치별로 묶어서 현재 감시 현황을 보여줍니다.
- `!watch branches owner/repo`와 `/github_branches`는 실제 GitHub 브랜치 목록과 현재 연결된 감시 상태를 함께 보여줍니다.
- `DISCORD_ALLOWED_ROLE_IDS`를 설정하면 해당 역할만 명령을 사용할 수 있습니다.
- `DISCORD_ADMIN_CHANNEL_ID`를 설정하면 지정한 채널에서만 명령을 받습니다.
- Discord 서버 관리자 권한이 있으면 서버·채널·역할 제한 없이 바로 사용할 수 있습니다.
- 저장소 관리자는 저장소마다 웹훅을 한 번 설치해야 합니다.
- `/github_webhook_setup` 결과는 본인에게만 표시되며, 출력된 Secret은 외부에 공유하지 않습니다.
- Payload URL과 Secret은 Discord 서버별로 분리되며, 해당 서버의 채널 구독에만 알림을 전달합니다.
- `/github_watch`는 API 조회 없이 구독을 저장하므로 웹훅 설치 전에도 등록할 수 있습니다.
- `branch:*`로 등록하면 해당 저장소의 모든 브랜치 push를 감지합니다.

## 환경 변수

| 변수 | 설명 |
|---|---|
| `DISCORD_BOT_TOKEN` | Discord 봇 토큰 |
| `DISCORD_GUILD_ID` | 사용할 서버 ID |
| `DISCORD_ADMIN_CHANNEL_ID` | 관리 명령을 받을 채널 ID |
| `DISCORD_ALLOWED_ROLE_IDS` | 쉼표로 구분한 관리 역할 ID |
| `GITHUB_TOKEN` | 선택값. `/github_branches` 등 GitHub 조회 명령에만 사용 |
| `GITHUB_WEBHOOK_MASTER_SECRET` | 저장소별 웹훅 Secret을 파생하는 서버 비밀키 |
| `GITHUB_WEBHOOK_PUBLIC_URL` | 외부에서 접근 가능한 서비스의 HTTPS 주소 |
| `GITHUB_WEBHOOK_PATH` | 웹훅 수신 경로. 기본값 `/webhooks/github` |
| `WEBHOOK_HOST` | 수신 주소. 기본값 `0.0.0.0` |
| `PORT` 또는 `WEBHOOK_PORT` | 웹 서버 포트. 기본값 `8080` |
| `WATCH_TARGETS` | 시작할 때 미리 등록할 감시 목록 |
| `COMMAND_PREFIX` | 명령어 접두사. 기본값 `!` |
| `STARTUP_NOTIFY` | 시작 시 관리 채널에 상태 알림을 보낼지 여부 |

`WATCH_TARGETS`는 다음 형식을 사용합니다.

```text
owner/repo|branch|channel_id
owner/repo|branch|channel_id|user
```

## 로컬 실행

```powershell
Copy-Item .env.example .env
notepad .env

python -m pip install discord.py aiohttp python-dotenv
python main.py
```

실행 후 `http://localhost:8080/health`에서 수신 서버 상태를 확인할 수 있습니다. 로컬에서 실제 GitHub 웹훅을 받으려면 HTTPS 터널 또는 공개 프록시가 필요합니다.

## GitHub 웹훅 등록

1. Discord에서 `/github_webhook_setup repository:owner/repo`를 실행합니다.
2. 저장소의 `Settings > Webhooks > Add webhook`으로 이동합니다.
3. 명령에서 받은 Payload URL과 Secret을 입력합니다.
   - 명령이 출력한 URL은 완성된 주소이므로 끝에 `/github`를 추가하지 않습니다.
4. Content type은 `application/json`, 이벤트는 `Just the push event`, SSL 검증은 활성화합니다.
5. GitHub의 ping이 성공하면 `/github_status`의 수신 확인 저장소 수가 증가합니다.
6. `/github_watch`로 브랜치·사용자·채널 구독을 추가합니다.

## Dishost 배포

2026년 8월 27일 기준, 현재 연결된 Dishost 서비스 화면에서는 Python 이미지를 사용하고 `GIT_ADDRESS`, `BRANCH`, `STARTUP_FILE`, `PY_PACKAGES`를 시작 설정에서 받습니다. 따라서 이 봇도 Python 기준으로 구성되어 있습니다.

권장 순서:

1. Dishost 서비스에서 GitHub 저장소 `rupria/rupria_tools_bot_etc`를 연결합니다.
2. 개발 검증 중에는 브랜치 `dev`를 선택합니다.
3. 시작 파일을 `bots/git_T_bot/main.py`로 설정합니다.
4. Python 패키지에 `discord.py aiohttp python-dotenv`를 입력합니다.
5. 환경 변수를 입력합니다.
6. 공개 HTTPS 주소를 `GITHUB_WEBHOOK_PUBLIC_URL`에 입력합니다.
7. Push 시 자동 배포를 활성화합니다.

## 완료 알림 기준

이 버전은 로컬 Codex 세션을 읽지 않습니다. GitHub가 전달한 `push` 이벤트를 작업 완료 신호로 판단하여 알림을 보냅니다.

개발 브랜치의 변경 기록은 [Update_His.md](./Update_His.md)에서 날짜별로 관리합니다.

## 운영 히스토리

### 2026-09-07: 2026-09-06 이전 최신 버전으로 롤백

- 롤백 기준 커밋: [`70a6102`](https://github.com/rupria/rupria_tools_bot_etc/commit/70a6102ce2003feefa337ee55f670784057fbc66) (`Scope watch listings to the current Discord server`)
- 기준 커밋 시각: 2026-08-28 10:39 KST
- 처리 방식: `main` 브랜치를 기준 커밋으로 강제 이동
- 롤백 사유: 2026-09-07 변경 버전에서 Dishost 기동 및 봇 기능이 정상 작동하지 않아, 2026-09-06 이전의 마지막 동작 기준점으로 복구

### GitHub API 403 재발 가능성 분석

현재 버전은 20초마다 모든 감시 항목을 순회하면서 GitHub REST API로 브랜치의 최신 커밋을 조회합니다.

- 감시 항목 1개당 기본 호출량: 시간당 약 180회
- 토큰이 적용되지 않은 익명 요청 제한: 시간당 60회이므로 감시 항목 1개도 약 20분 후 403 발생 가능
- 일반 인증 토큰 제한: 시간당 5,000회이므로 다른 API 사용량을 제외해도 약 27개 감시 항목부터 한도 초과 가능
- 감시 키가 `저장소 + 브랜치 + 사용자 + 채널`로 구성되어 있어, 같은 저장소와 브랜치라도 사용자 또는 채널이 다르면 동일 GitHub API를 중복 호출
- 새로운 Push 감지 시 커밋 비교 API를 추가 호출
- 403/429 응답의 `Retry-After`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`을 처리하지 않아 오류 발생 후에도 20초마다 재요청

따라서 403 방지를 위한 후속 개선 시 다음 항목이 필요합니다.

1. 한 polling 주기 안에서 `저장소 + 브랜치`별 최신 커밋 조회 결과를 공유합니다.
2. 비교 결과도 `저장소 + 이전 SHA + 최신 SHA`별로 공유합니다.
3. 403/429 응답 시 GitHub 응답 헤더에 따라 다음 호출까지 대기합니다.
4. `GITHUB_TOKEN`이 실제 Dishost 프로세스에 전달되는지 시작 로그에서 값 노출 없이 확인합니다.
5. 실제 감시 개수는 Dishost 내부 `data/watchers.json`에서 확인합니다. 이 파일은 Git에서 제외됩니다.

참고: [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)




### 시연 이미지
--- 
### 채팅알람
<img width="524" height="808" alt="{4220283D-894B-4419-B392-8535437F1419}" src="https://github.com/user-attachments/assets/66c0fc7d-3a01-4180-b1b4-a6a8a8a79576" />


### 명령어 사용
<img width="1243" height="389" alt="{52061894-9F9A-490F-AFE7-256ED43376D5}" src="https://github.com/user-attachments/assets/369d0be9-5410-4166-9c2b-ca4592a574f0" />
