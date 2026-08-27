# Discord 실시간 연결 브리지

이 프로젝트는 특정 게임이나 메인 브랜치에 고정되지 않도록, Codex 채팅 다섯 개를 Discord 채널과 1:1로 연결한다. 저장소 이름과 브랜치 이름은 `CODEX_REPOSITORY_LABEL`, `CODEX_BRANCH_LABEL` 또는 현재 Git 상태를 기준으로 자동 반영된다.

| Codex 채팅 | Discord 채널 |
|---|---|
| QA·PM | `qa` |
| 총괄 | `전체` |
| 프로그래머 | `프로그래밍` |
| 기획 | `기획` |
| 아트 | `아트` |

## 보안 전제

- 개인이 관리하는 비공개 서버에서만 실행한다.
- Discord 일반 사용자 계정 자동화(self-bot)가 아니라 공식 Bot 계정을 사용한다.
- `Codex Operator` 역할을 가진 사용자만 명령할 수 있게 제한한다.
- 봇 토큰이 들어가는 `.env`와 `.connect/`는 Git에서 제외한다.
- 이 커넥터는 로컬 파일과 셸 명령을 실행할 수 있다. 관리 전용 `codex-admin` 채널은 운영자만 볼 수 있게 설정한다.

## 최초 설정

1. Discord Developer Portal에서 애플리케이션과 Bot을 만든다.
2. Bot 설정에서 `MESSAGE CONTENT INTENT`를 활성화한다.
3. 서버 설치 권한은 `View Channels`, `Send Messages`, `Read Message History`, `Use Application Commands`만 우선 부여한다. 기존 채널을 직접 매핑하므로 채널 생성/삭제 권한은 필수가 아니다.
4. 서버에 `Codex Operator` 역할을 만들고 본인에게만 부여한다.
5. 운영자만 접근 가능한 텍스트 채널 `codex-admin`을 하나 만든다.
6. Discord 설정에서 개발자 모드를 켜고 `codex-admin` 채널 ID와 `Codex Operator` 역할 ID를 복사한다.
7. `.env.example`을 `.env`로 복사한 뒤 Bot 토큰, 관리 채널 ID, 역할 ID를 입력한다.

토큰은 Discord나 Codex 채팅에 붙여 넣지 말고 로컬 `.env`에만 입력한다.

## 설치 및 실행

로컬 Windows에서는 PowerShell로, 호스팅 환경에서는 `npm start`로 실행할 수 있다.

```powershell
cd C:\path\to\git_T_bot
Copy-Item .env.example .env
notepad .env
powershell -ExecutionPolicy Bypass -File .\scripts\install-bridge.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-bridge.ps1
```

`npm start`는 시작 전에 `configure-bridge.py`를 자동 실행하므로 `.connect/config.json`을 따로 커밋할 필요가 없다. 호스팅 환경에서는 `.env` 파일 대신 대시보드 환경변수만 넣어도 된다.

실행 창을 닫으면 실시간 연결도 종료된다. 24시간 사용하려면 Windows에서는 작업 스케줄러에 `start-bridge.ps1`을 로그인 시 실행하도록 등록하거나, 호스팅 환경에서는 프로세스가 항상 켜져 있는 서비스로 올린다.

## 동작 확인

- `codex-admin`에서 `/status`를 실행한다.
- 각 역할 채널에서 `현재 역할과 진행 상태를 요약해줘`라고 입력한다.
- Codex Desktop의 같은 채팅에 사용자 요청과 답변이 이어지는지 확인한다.

봇이 메시지를 읽지 못하면 Developer Portal의 `MESSAGE CONTENT INTENT`, 채널 권한, `DISCORD_ALLOWED_ROLE_IDS`를 확인한다.

## 저장소 구분

여러 봇을 한 GitHub 저장소에 함께 두거나, 같은 Discord 서버에서 여러 작업 대상을 구분해야 할 때는 아래 값을 사용한다.

여러 봇을 한곳에 모을 때는 브랜치만 나누기보다 `bots/git_T_bot`, `bots/another_bot`처럼 폴더를 나누는 편이 낫다. 브랜치는 `main`, `dev`, `release`처럼 변경 흐름을 나누는 용도로 두고, 봇 자체의 정체성은 폴더명과 `CODEX_WORKSPACE_DISPLAY_NAME`, `CODEX_THREAD_PREFIX`로 구분하는 구성이 관리가 쉽다.

- `CODEX_REPOSITORY_LABEL`: 알림과 스레드에 표시할 저장소 이름. 비워 두면 `origin` remote 또는 작업 폴더 이름을 사용한다.
- `CODEX_BRANCH_LABEL`: 알림과 스레드에 표시할 브랜치 이름. 비워 두면 현재 Git 브랜치를 사용한다.
- `CODEX_THREAD_PREFIX`: 자동 생성 규칙 대신 직접 지정할 스레드 접두사.
- `CODEX_WORKSPACE_DISPLAY_NAME`: Codex 커넥터에 표시할 작업공간 이름.
- `CODEX_INSTANCE_SLUG`, `CODEX_COMPUTER_ID`, `CODEX_COMPUTER_DISPLAY_NAME`: 여러 브리지를 같은 PC에서 돌릴 때 충돌을 줄이기 위한 식별자.
- `DISCORD_COMPLETION_ALERT_ROUTES`: 완료 알림을 보낼 채널 매핑. `요청채널ID:알림채널ID` 형식을 쉼표로 구분한다.

예를 들어 이 봇을 `rupria/rupria_tools_bot_etc`에 올리되, `git_T_bot` 하위 프로젝트로 구분하고 싶다면 `.env`에서 다음처럼 지정할 수 있다.

```text
CODEX_REPOSITORY_LABEL=rupria/rupria_tools_bot_etc
CODEX_BRANCH_LABEL=main
CODEX_THREAD_PREFIX=rupria_tools_bot_etc/git_T_bot@main
CODEX_WORKSPACE_DISPLAY_NAME=git_T_bot
CODEX_INSTANCE_SLUG=git-t-bot
DISCORD_COMPLETION_ALERT_ROUTES=1534567179532636240:1534567179532636240,1534504029080518706:1534504029080518706
```

## 작업 완료 알림

브리지를 실행하면 완료 알림 모니터도 함께 시작된다. `아트`에서 요청한 작업은 `아트` 채널에만, `프로그래머`에서 요청한 작업은 `프로그래머` 채널에만 다음 정보를 전송한다. 다른 역할의 작업 완료 알림은 두 채널에 섞지 않는다.

- 완료 여부
- 저장소 이름
- 브랜치 이름
- 담당 Codex 채팅
- 원래 요청한 Discord 채널 링크
- 소요 시간과 완료 시각
- 완료 응답에 GitHub 커밋·브랜치·PR 링크가 있으면 해당 링크(최대 3개)

요청 내용과 답변 본문은 알림 채널로 복사하지 않는다. 알림은 새로운 `task_complete` 이벤트만 대상으로 하므로 봇 재시작 전에 끝난 과거 작업은 다시 알리지 않는다.

알림을 모바일 푸시로 받으려면 Discord의 `아트`와 `프로그래머` 채널 알림 설정을 `모든 메시지`로 설정한다. 실행 상태는 다음 로그에서 확인할 수 있다.

```text
<workspace-root>\.connect\completion-alert.stdout.log
<workspace-root>\.connect\completion-alert.stderr.log
```

## DisHost 참고

DisHost는 GitHub 자동 배포와 모노레포 하위 디렉터리를 지원한다. 이 봇을 `rupria/rupria_tools_bot_etc` 같은 공용 저장소에 넣는다면 `bots/git_T_bot`처럼 분리하고, 서비스 작업 디렉터리를 그 하위 폴더로 맞추면 된다.

다만 이 브리지는 `codex-discord-connector`의 direct mode 위에서 동작하므로, 배포 대상 호스트에도 `Codex CLI`, `CODEX_HOME`, Codex 인증 상태, 세션 접근 권한이 있어야 한다. 단순 Discord 봇 호스팅처럼 토큰만 넣는 구조가 아니라는 점을 먼저 확인해야 한다.
