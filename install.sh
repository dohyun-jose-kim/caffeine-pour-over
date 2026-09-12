#!/bin/bash
# caffeine-pour-over 도구 설치:
#  1. bin/* 을 ~/.local/bin 에 심볼릭 링크
#  2. nosleep용 NOPASSWD sudoers 규칙 설치 (pmset disablesleep 두 명령만 허용)
#  3. 꼬여 있던 disablesleep 상태 초기화
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p "$HOME/.local/bin"
for tool in bin/*; do
  chmod +x "$tool"
  ln -sf "$PWD/$tool" "$HOME/.local/bin/$(basename "$tool")"
  echo "✓ linked: ~/.local/bin/$(basename "$tool") -> $PWD/$tool"
done

# $USER는 환경변수라 신뢰할 수 없다 — sudoers 규칙을 만드는 자리이므로
# 엉뚱한 계정에 NOPASSWD가 붙지 않도록 id -un 을 쓴다.
RULE="$(id -un) ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 1, /usr/bin/pmset -a disablesleep 0"
TMP=$(mktemp)
echo "$RULE" > "$TMP"
sudo visudo -cf "$TMP"   # 문법 검증 실패 시 set -e로 여기서 중단
sudo install -m 440 -o root -g wheel "$TMP" /etc/sudoers.d/nosleep
rm -f "$TMP"
echo "✓ sudoers: /etc/sudoers.d/nosleep"

sudo pmset -a disablesleep 0
# 새 경로($TMPDIR)와 구버전 경로(/tmp) 양쪽을 정리한다.
rm -f "${TMPDIR:-/tmp}/nosleep.state" /tmp/nosleep.state
echo "✓ reset: sleep re-enabled, stale state cleared"
echo
echo "Done. 확인: nosleep 1m && nosleep status"
