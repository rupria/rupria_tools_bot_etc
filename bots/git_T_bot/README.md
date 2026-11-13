# 중앙 GitHub → Discord 알림 봇

Discord에서 저장소, 브랜치, 사용자, 알림 채널을 등록하면 봇이 대상 브랜치를 20초마다 확인하고 새 push를 알려준다. Dishost 무료 플랜을 기준으로 GitHub 웹훅 없이 동작한다.

## 명령어

```text
/github_watch repository:rupria/gitproject branch:main user:* channel:#알림
/github_watches repository:* branch:* user:*
/github_branches repository:rupria/gitproject branch:* user:*
/github_status
/github_unwatch repository:rupria/gitproject branch:main user:* channel:#알림
```

- `repository`: `.git`이 있거나 없는 GitHub 주소 또는 `owner/repo`. 여러 대상은 쉼표로 구분
- `branch`: 감시할 브랜치. 여러 대상은 쉼표로 구분
- `user`: GitHub ID나 커밋 이메일. 여러 명은 쉼표로 구분하고 전체는 `*`
- `channel`: 생략하면 명령을 실행한 현재 채널
- 서버와 채널마다 여러 저장소·브랜치 조합을 독립적으로 등록 가능
- 등록 명령은 GitHub API 성공을 기다리지 않는다. 다음 정상 폴링에서 기준 SHA를 초기화한다.

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
- GitHub `ETag` 조건부 요청으로 변경이 없는 조회는 캐시된 응답을 재사용
- `401 Bad credentials`는 5분간 재시도를 멈춰 잘못된 토큰으로 API를 반복 호출하지 않음
- 네트워크 오류와 GitHub `5xx`는 15초부터 최대 5분까지 지수 백오프
- `/github_status`에서 최근 GitHub 응답, 정상 조회 시각, 백오프와 폴링 오류 확인
- 폴링 한 주기가 예외로 실패해도 다음 주기에 작업을 계속 실행
- 감시 설정과 실행 상태는 원자적으로 저장하고 이전 정상본을 `.bak`으로 유지

## 실행

```powershell
python -m pip install discord.py aiohttp python-dotenv
python main.py
```

Dishost에서는 시작 파일을 `bots/git_T_bot/main.py`로 지정한다. 검증 중에는 GitHub `dev` 브랜치를 배포 대상으로 사용한다.

## 여러 저장소 추적

저장소마다 한 번씩 기존 등록 명령을 실행한다.

```text
/github_watch repository:owner/project-a branch:main user:user1
/github_watch repository:owner/project-b branch:main,dev user:user1,user2
```

각 저장소의 마지막 커밋 SHA는 독립적으로 저장된다. 등록 이전 커밋은 알리지 않고 등록 완료 이후의 push부터 전송한다.
