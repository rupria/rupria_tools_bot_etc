# Update_His

개발 브랜치의 변경사항을 날짜별로 기록합니다. 운영 중인 `main` 브랜치는 검증이 끝날 때까지 기존 버전을 유지합니다.

## 2026-09-25

### 문제점

- 20초 polling으로 감시 대상마다 GitHub REST API를 반복 호출해 `403`, `429`, 인증 실패의 영향을 받았습니다.
- 같은 저장소와 브랜치를 여러 사용자 또는 채널에서 감시하면 동일 조회가 중복될 수 있었습니다.
- API가 일시적으로 실패하면 커밋 알림도 함께 중단되었습니다.
- 저장소 등록과 실제 커밋 감지가 모두 API 상태에 의존했습니다.

### 해결 히스토리

1. 운영 중인 `main`과 개발 작업을 분리하기 위해 `dev` 전용 worktree를 구성했습니다.
2. GitHub `push` 웹훅을 받는 HTTPS 엔드포인트를 봇 프로세스에 추가했습니다.
3. 저장소마다 파생되는 비밀키와 `X-Hub-Signature-256`을 사용해 요청 서명을 검증하도록 구성했습니다.
4. Discord 서버별 전용 URL과 비밀키를 사용해 다른 서버의 구독으로 이벤트가 넘어가지 않도록 격리했습니다.
5. `X-GitHub-Delivery`를 저장해 동일 이벤트의 중복 처리를 방지했습니다.
6. 수신 요청은 큐에 넣고 즉시 `202 Accepted`를 반환한 뒤 Discord 알림을 비동기로 처리하도록 변경했습니다.

### 개선 내역

- `/github_watch`는 GitHub API를 호출하지 않고 저장소·브랜치·사용자·채널 구독만 저장합니다.
- 한 저장소에 설치한 웹훅 하나로 여러 브랜치, 사용자, Discord 채널을 동시에 처리합니다.
- 웹훅 payload의 저장소, 브랜치, 커밋 작성자를 기존 구독 조건과 비교합니다.
- 커밋 목록, 비교 링크, 변경 파일명을 기존 Discord 임베드 형식으로 표시합니다.
- `/github_branches`처럼 실제 GitHub 조회가 필요한 명령만 선택적으로 API를 사용합니다.
- 서비스 루트와 `/health`에서 웹 서버 상태를 확인할 수 있습니다.

### 업데이트 내역

- `/github_webhook_setup repository:owner/repo` 명령 추가
- `/github_status` 웹훅 상태 명령 추가
- `GITHUB_WEBHOOK_MASTER_SECRET`, `GITHUB_WEBHOOK_PUBLIC_URL`, `GITHUB_WEBHOOK_PATH` 환경변수 추가
- `PORT` 또는 `WEBHOOK_PORT`를 사용하는 웹 서버 추가
- `WATCH_POLL_INTERVAL_MS`와 상시 polling 제거
- Dishost 배포 브랜치를 `dev`로 변경
- 기존 `/github_watch`, `/github_watches`, `/github_unwatch`, `/github_branches` 명령 유지
