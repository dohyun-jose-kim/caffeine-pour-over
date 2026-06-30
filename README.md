# caffeine-pour-over

손으로 내려 만든(hand-drip) macOS CLI 도구 모음. `bin/` 아래 스크립트를 `install.sh`가 `~/.local/bin`에 심볼릭 링크한다.

> Hand-crafted macOS CLI tools. Currently ships **nosleep** — a time-boxed sleep blocker with auto-revert.

## 요구 사항

- macOS (`pmset`, `osascript` 사용)
- zsh
- `~/.local/bin`이 `PATH`에 포함되어 있을 것

## 설치

```bash
git clone https://github.com/dohyun-jose-kim/caffeine-pour-over.git
cd caffeine-pour-over
./install.sh   # sudo 비밀번호 1회 필요 (sudoers 규칙 설치)
```

`install.sh`가 하는 일:

1. `bin/*`을 `~/.local/bin`에 심볼릭 링크
2. nosleep용 NOPASSWD sudoers 규칙 설치 (`/etc/sudoers.d/nosleep`)
3. 꼬여 있던 `disablesleep` 상태 초기화

## nosleep

시간 제한부 슬립 방지 도구. `pmset -a disablesleep`을 켰다가, 지정한 시간이 지나면 백그라운드 watcher가 자동으로 되돌린다.

### 기능

- **시간 제한부 슬립 방지** — 지정한 시간 동안 Mac이 잠들지 않게 하고, 시간이 끝나면 자동 복구. 알림(notification)으로 복구 사실을 알려준다.
- **뚜껑을 닫아도 잠들지 않음** — `caffeinate`와의 핵심 차이. `caffeinate`는 클램셸(뚜껑 닫힘) 슬립을 막지 못하지만, `disablesleep`은 막는다.
- **터미널 독립** — watcher는 disown된 백그라운드 프로세스라 터미널을 닫아도 살아남는다.
- **남은 시간 확인** (`status`) — 남은 시간, 종료 시각, 현재 pmset 상태를 보여준다.
- **연장** (`extend`) — 실행 중인 타이머의 종료 시각을 뒤로 미룬다.
- **즉시 해제** (`cancel`) — 타이머를 멈추고 바로 슬립을 복구한다.

### 사용법

```
nosleep              # 60분 (기본값)
nosleep 90           # 90분 (단위 없으면 분)
nosleep 1h30m        # h/m/s 조합 (예: 2h, 45s, 1h30m20s)
nosleep status       # 남은 시간 + pmset 상태
nosleep extend 30m   # 연장
nosleep cancel       # 즉시 해제
```

### 동작 방식

- 시작 시 종료 시각(epoch)과 watcher PID를 `/tmp/nosleep.state`에 기록 — `status`의 남은 시간은 여기서 계산.
- 복구는 `sudo -n pmset`으로 실행되므로 `/etc/sudoers.d/nosleep`의 NOPASSWD 규칙이 필수.
  규칙은 `pmset -a disablesleep 1`/`0` 두 명령에만 한정된다.
  (예전 zshrc 함수 버전은 sudo 캐시 5분 만료 때문에 5분 넘는 타이머가 전부 복구에 실패했다 — 이 규칙이 그 버그의 근본 수정.)

### 한계

- `disablesleep`은 NVRAM 설정이라 **재부팅해도 유지**되는데 watcher는 재부팅하면 사라진다.
  타이머 도중 재부팅했다면 `nosleep status`가 ⚠ 경고를 띄우니 `nosleep cancel`로 복구할 것.

## 제거

```bash
sudo rm /etc/sudoers.d/nosleep
rm ~/.local/bin/nosleep
```

## 라이선스

[MIT](LICENSE)
