# git_T_bot

이 봇은 GitHub 저장소와 브랜치를 감시하다가 새 커밋이 올라오면 Discord 채널에 알림을 보낸다. `작업 완료`를 GitHub 브랜치 업데이트로 판단하는 구조라서, Dishost처럼 일반적인 Discord 봇 호스팅에도 맞는다.

## 하는 일

- 저장소별 구분
- 브랜치별 구분
- 채널별 알림 분리
- 재시작 후에도 감시 대상 유지
- `main`, `dev`, `release` 같은 브랜치를 각각 따로 감시

## 명령어

관리 채널에서 아래 형식으로 쓴다.

```text
!watch list
!watch add owner/repo main
!watch add owner/repo dev #alerts
!watch remove owner/repo main
!watch check
!watch test
```

- 채널을 따로 적지 않으면 현재 채널에 연결한다.
- `DISCORD_ALLOWED_ROLE_IDS`를 넣으면 해당 역할만 명령을 쓸 수 있다.
- `DISCORD_ADMIN_CHANNEL_ID`를 넣으면 그 채널에서만 명령을 받는다.

## 환경 변수

- `DISCORD_BOT_TOKEN`: Discord 봇 토큰
- `DISCORD_GUILD_ID`: 사용할 서버 ID
- `DISCORD_ADMIN_CHANNEL_ID`: 관리 명령을 받을 채널 ID
- `DISCORD_ALLOWED_ROLE_IDS`: 쉼표로 구분한 관리 역할 ID
- `GITHUB_TOKEN`: GitHub API 토큰. private 저장소나 잦은 polling이면 권장
- `WATCH_POLL_INTERVAL_MS`: 감시 주기
- `WATCH_TARGETS`: 시작할 때 미리 붙일 감시 목록. `owner/repo|branch|channel_id` 형식
- `COMMAND_PREFIX`: 기본값 `!watch`
- `STARTUP_NOTIFY`: 시작 시 관리 채널에 상태 알림 전송 여부

## 로컬 실행

```powershell
Copy-Item .env.example .env
notepad .env
npm install
npm start
```

## Dishost 배포

2026년 8월 27일 기준 Dishost 문서는 GitHub 자동 배포와 모노레포 하위 디렉터리 `workdir`를 지원한다. 이 저장소에서는 `bots/git_T_bot` 폴더를 서비스 작업 디렉터리로 잡으면 된다.

권장 순서:

1. Dishost 서비스에서 GitHub 저장소 `rupria/rupria_tools_bot_etc` 연결
2. 브랜치 `main` 선택
3. 작업 디렉터리를 `bots/git_T_bot`으로 설정
4. 환경 변수 입력
5. 자동 재배포 활성화
6. 시작 명령은 `npm start`

## 완료 알림 기준

이 버전은 로컬 Codex 세션을 읽지 않는다. 대신 감시 중인 브랜치 HEAD가 바뀌면 그 커밋을 작업 완료 신호로 보고 알림을 보낸다.
