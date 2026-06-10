# 10_hand-drip-caffeine

손으로 내려 만든 macOS CLI 도구 모음. `bin/` 아래 스크립트를 `install.sh`가 `~/.local/bin`에 링크한다.

## 설치

```bash
./install.sh   # sudo 비밀번호 1회 필요 (sudoers 규칙 설치)
```

## nosleep

시간 제한부 슬립 방지. `pmset -a disablesleep`을 켰다가 시간이 되면 백그라운드 watcher가 자동으로 되돌린다. 뚜껑을 닫아도 잠들지 않는다 (`caffeinate`와의 차이점).

```
nosleep              # 60분
nosleep 90           # 90분 (단위 없으면 분)
nosleep 1h30m        # h/m/s 조합
nosleep status       # 남은 시간 (MM:SS) + pmset 상태
nosleep extend 30m   # 연장
nosleep cancel       # 즉시 해제
```

### 동작 방식

- 시작 시 종료 시각(epoch)과 watcher PID를 `/tmp/nosleep.state`에 기록 — `status`의 남은 시간은 여기서 계산.
- watcher는 disown된 백그라운드 프로세스라 **터미널을 닫아도 살아남는다**.
- 복구는 `sudo -n pmset`으로 실행되므로 `/etc/sudoers.d/nosleep`의 NOPASSWD 규칙이 필수.
  규칙은 `pmset -a disablesleep 1`/`0` 두 명령에만 한정된다.
  (예전 zshrc 함수 버전은 sudo 캐시 5분 만료 때문에 5분 넘는 타이머가 전부 복구에 실패했다 — 이 규칙이 그 버그의 근본 수정.)

### 한계

- `disablesleep`은 NVRAM 설정이라 **재부팅해도 유지**되는데 watcher는 재부팅하면 사라진다.
  타이머 도중 재부팅했다면 `nosleep status`가 ⚠ 경고를 띄우니 `nosleep cancel`로 복구할 것.

### 제거

```bash
sudo rm /etc/sudoers.d/nosleep
rm ~/.local/bin/nosleep
```
