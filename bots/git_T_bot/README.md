# 중앙 GitHub → Discord 알림 봇

Discord 채널에서 저장소 링크와 감시 사용자만 등록하면, 봇이 해당 저장소의 기본 브랜치를 20초마다 확인하고 새 push를 알려준다. Dishost 무료 플랜을 기준으로 GitHub 웹훅 없이 동작한다.

## 명령어

기존 명령 형식을 그대로 사용한다.

```text
/github_watch repository:https://github.com/rupria/gitproject.git users:rupria
/github_unwatch repository:https://github.com/rupria/gitproject.git
/github_watches
```

- `repository`: `.git`이 있거나 없는 GitHub 주소 또는 `owner/repo`
- `users`: GitHub ID나 커밋 이메일. 여러 명은 쉼표로 구분
- 모든 사용자를 감시하려면 `users:*`
- 저장소의 기본 브랜치는 자동으로 선택
- 명령을 실행한 현재 Discord 채널에 등록
- 같은 채널에 여러 저장소를 각각 등록할 수 있음

## 알림 내용

- push한 GitHub 계정 및 커밋 작성자
- 커밋 메시지와 링크
- 변경 파일
- 파일별 추가·삭제 줄 수
- 전체 변경 비교 링크

## Dishost 무료 플랜 설정

다음 환경변수가 필요하다.

```text
DISCORD_BOT_TOKEN=Discord 봇 토큰
GITHUB_TOKEN=GitHub 토큰
POLLING_ENABLED=true
WATCH_POLL_INTERVAL_MS=20000
```

20초 polling에서는 `GITHUB_TOKEN`이 필수다. 토큰 없이 익명 요청을 반복하지 않도록 시작 단계에서 설정 오류로 중단한다.

403 또는 429 응답을 받으면 다음 동작을 적용한다.

- GitHub의 `Retry-After` 헤더 우선 적용
- 호출 한도가 소진됐으면 `X-RateLimit-Reset` 시각까지 API 요청 중단
- 별도 재시도 정보가 없으면 60초간 대기
- 동일 저장소와 브랜치가 여러 사용자·채널에 등록돼도 한 polling 주기에는 한 번만 조회

## 실행

```powershell
python -m pip install discord.py aiohttp python-dotenv
python main.py
```

Dishost에서는 시작 파일을 `bots/git_T_bot/main.py`로 지정한다. GitHub `main` push 자동 배포를 사용하면 새 커밋 배포 후 슬래시 명령이 다시 동기화된다.

## 여러 저장소 추적

저장소마다 한 번씩 기존 등록 명령을 실행한다.

```text
/github_watch repository:https://github.com/owner/project-a users:user1
/github_watch repository:https://github.com/owner/project-b users:user1,user2
```

각 저장소의 마지막 커밋 SHA는 독립적으로 저장된다. 등록 이전 커밋은 알리지 않고 등록 완료 이후의 push부터 전송한다.
