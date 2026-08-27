# rupria_tools_bot_etc

여러 Discord 봇과 운영 도구를 한 저장소에서 관리하는 용도다.

## Bots

- `bots/git_T_bot`
  - GitHub 브랜치 감시 Discord 봇
  - GitHub 기본 브랜치: `main`
  - DisHost 시작 파일: `bots/git_T_bot/main.py`

## DisHost 메모

- GitHub 가져오기로 연결할 때 저장소는 `rupria/rupria_tools_bot_etc`, 브랜치는 `main`을 사용한다.
- 모노레포 하위 폴더 배포가 필요하면 서비스 작업 디렉터리를 `bots/git_T_bot`으로 맞춘다.
- 루트 [dishost.yml](C:/Users/katzm/Desktop/u/rupria_tools_bot_etc/dishost.yml) 은 현재 `bots/git_T_bot` 서비스에 맞춰져 있다.
