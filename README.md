# caffeine-pour-over

[English](README.en.md) · **한국어**

손으로 내려 만든(hand-drip) macOS CLI 도구 모음. `bin/` 아래 스크립트를 `install.sh`가 `~/.local/bin`에 심볼릭 링크한다.

> Hand-crafted macOS CLI tools — **nosleep** (time-boxed sleep blocker with auto-revert), **after** (run a keystroke after a delay), and **pourover** (an interactive menu launcher for them).

## paper-record: 3-Layer Paper Record

`paper-record`는 PDF를 한 가지 parser 결과로 합치지 않는다. 원본을 과학적 source of truth로
보존하고, 서로 독립적인 두 표현과 사람이 승인한 누적 읽기 기록을 만든다.

```text
paper.pdf                 원본 근거(항상 최종 권위)
├── 01_native.md          PyMuPDF4LLM text-layer 보존본
├── 02_structured.md      MinerU Hybrid 구조/layout 보존본
└── 03_canonical.md       LLM 제안 중 사람이 승인한 누적 working record
```

두 parser가 일치하면 `CROSS_CHECKED`일 뿐 사실 확정은 아니다. 충돌은 자동으로 승자를
고르지 않고 `UNRESOLVED`로 남긴다. `SOURCE_CONFIRMED`와 `VISUALLY_READ`는 해당 실행에
원본 PDF page나 asset을 명시적으로 전달했을 때만 가능하다. caption을 읽은 상태와 그림
본체를 본 상태도 분리한다.

### 설치와 자원

Python 3.12와 [uv](https://docs.astral.sh/uv/)가 필요하다. 저장소에서 다음을 실행한다.

```bash
uv sync --extra mineru --extra test
uv run paper-record doctor
```

첫 실행 전에 모델을 명시적으로 받을 수도 있다.

```bash
uv run --extra mineru mineru-models-download --source auto --model_type all
```

MinerU 공식 요구사항은 local hybrid/pipeline 계열에 RAM 최소 16 GB(32 GB 권장), SSD 여유
20 GB 이상을 제시한다. macOS는 14 이상이 필요하며 Apple Silicon에서 가속을 시도한다.
macOS Docker 배포는 가속 장치를 쓸 수 없어 권장되지 않는다. 첫 모델 다운로드에는
네트워크와 수 GB 이상의 추가 cache가 필요하고, 긴 논문의 `hybrid-engine/high` 처리는
수 분 이상 걸릴 수 있다. 자세한 최신 값은
[MinerU quick start](https://github.com/opendatalab/MinerU/blob/master/docs/en/quick_start/index.md)와
[model source 문서](https://github.com/opendatalab/MinerU/blob/master/docs/en/usage/model_source.md)를
확인한다.

### 전체 사용 흐름

```bash
# 01 + 02 + 빈 03 scaffold 생성. 기본 위치: papers/<pdf-stem>/
paper-record ingest /path/to/paper.pdf
paper-record ingest /path/to/paper.pdf --id smith-2026 --root papers

# 두 Markdown과 현재 03을 읽되 canonical은 변경하지 않고 proposal만 생성
paper-record read papers/smith-2026 --provider codex \
  --purpose "Initial full-paper reading"
paper-record read papers/smith-2026 --provider claude --model <model>

# 전체 승인 또는 대화형 전체 거절 → 항목별 accept/reject/feedback
paper-record review papers/smith-2026 --read-id READ-0001
paper-record review papers/smith-2026 --read-id READ-0001 --approve-all

# unresolved 항목에 한해서만 원본 page/asset을 명시적으로 공급
paper-record resolve papers/smith-2026 UNRESOLVED-0001 --pages 7-8
paper-record resolve papers/smith-2026 UNRESOLVED-0001 \
  --assets assets/tables/table_002.png

paper-record status papers/smith-2026
```

`read`는 `manifest.yaml`, `01_native.md`, `02_structured.md`, 현재 `03_canonical.md`를
provider에 보낸다. `--pages`/`--assets`를 사용한 경우 선택한 이미지도 함께 전송한다.
긴 입력은 양쪽 page marker를 기준으로 전 페이지를 배치 처리하며 자르지 않는다. Codex와
Claude CLI의 기존 로그인을 사용하고 자격 증명은 저장하지 않는다. provider에는 read-only,
비대화형, 임시 세션 옵션을 적용하지만, 외부 API를 사용하는 경우 전송된 논문 내용은 해당
provider의 보존·개인정보 정책을 따른다.

proposal은 `.paper-record/reviews/READ-NNNN/`에 보존된다. `review` 전에는 03이 바뀌지
않으며, 승인된 항목과 Reading Ledger 한 건만 원자적으로 반영된다. 전부 거절해도 “읽고
검토했음”은 ledger에 남는다. 이후 PDF/parser revision 또는 canonical version/input hash가
달라지면 예전 proposal은 stale로 거부된다. 실패한 parser revision과 LLM 응답도 삭제하지
않으므로 원인을 고친 뒤 같은 명령을 재실행할 수 있다.

운영 로그는 `.paper-record/logs/events.jsonl`의 append-only JSON 객체다. 단계, 시각,
상태, revision/version, artifact path/hash를 기록하되 prompt, 논문 본문, API key/token,
환경변수는 기록하지 않거나 redaction한다. `03_canonical.md`의 `Canonical Notes` marker
사이에 적은 사용자 메모는 machine update 후에도 유지된다.

현재 v1은 parser 중 정답 자동 선택, 외부 문헌 fact-checking, vector DB/RAG, ingest 중
자동 그림 해석, PDF를 대체하는 canonical, 무인 공개를 하지 않는다. MinerU 결과의 page
marker는 content-list anchor에 기반한 best-effort이며 복잡한 layout은 원본 visual로
재확인해야 한다.

## 기존 macOS 도구 요구 사항

- macOS (`pmset`, `osascript` 사용)
- zsh
- `~/.local/bin`이 `PATH`에 포함되어 있을 것
- (선택) iTerm2 — `after --target iterm`을 쓸 때

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

## pourover

도구 이름을 외울 필요 없이, `pourover`만 실행하면 `bin/`의 도구가 번호로 뜬다. 도구를 고르면 동작·시간·타겟까지 객관식으로 물어본 뒤 실행한다. 의존성 없는 순수 zsh 메뉴.

### 사용법

```
pourover       # 도구 목록 → 동작/인자를 번호로 골라 실행
pourover -h    # 도움말
pourover --version  # 버전
```

`q`를 입력하면 어느 단계에서든 취소된다.

### 동작 방식

- `bin/`의 실행 가능한 파일을 자동으로 수집해 목록에 띄운다(자기 자신 제외). 새 도구를 `bin/`에 추가하면 메뉴에 자동으로 나타난다.
- `nosleep`·`after`는 시간 프리셋·타겟까지 골라주는 큐레이션 메뉴를 제공한다. 그 밖의 도구는 `--help`(또는 `help`)를 보여준 뒤 인자를 직접 입력받는 폴백으로 실행된다.

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
nosleep --version    # 버전
```
### 예시 
<img width="585" height="492" alt="image" src="https://github.com/user-attachments/assets/7182a0a5-0310-4a0f-a398-3b9395bc5543" />


### 동작 방식

- 시작 시 종료 시각(epoch)과 watcher PID를 `$TMPDIR/nosleep.state`(사용자 전용 디렉터리)에 기록 — `status`의 남은 시간은 여기서 계산.
- 복구는 `sudo -n pmset`으로 실행되므로 `/etc/sudoers.d/nosleep`의 NOPASSWD 규칙이 필수.
  규칙은 `pmset -a disablesleep 1`/`0` 두 명령에만 한정된다.
  (예전 zshrc 함수 버전은 sudo 캐시 5분 만료 때문에 5분 넘는 타이머가 전부 복구에 실패했다 — 이 규칙이 그 버그의 근본 수정.)

### 한계

- `disablesleep`은 NVRAM 설정이라 **재부팅해도 유지**되는데 watcher는 재부팅하면 사라진다.
  타이머 도중 재부팅했다면 `nosleep status`가 ⚠ 경고를 띄우니 `nosleep cancel`로 복구할 것.

## after

지정한 시간이 지나면 **액션 1회**를 실행하는 예약 도구. nosleep과 같은 disown 패턴이라 터미널을 닫아도 예약이 살아남는다. 지금은 `enter`(Return 키 전송) 액션을 지원한다.

> **쓰는 맥락** — 예: Claude 세션이 사용량 한도에 걸려 ~1시간 기다려야 할 때, `nosleep 3h`로 Mac을 깨워두고 `after 65m enter`로 재개 Enter를 미리 예약한다.

### 사용법

```
after 65m enter                  # 65분 뒤 맨 앞 창에 Enter (frontmost, 기본)
after 65m enter --target iterm   # 지금 이 iTerm2 세션에 Enter (포커스 무관)
after 1h5m enter                 # h/m/s 조합, 숫자만이면 분 (예: 90, 2h, 30s)
after --version                  # 버전
```

예약하면 발사 시각과 pid를 출력한다. **취소**는 그 pid를 `kill`.

### 타겟 두 가지

- **`frontmost`** (기본) — 발사 시점에 **맨 앞** 앱으로 Enter를 보낸다(System Events). 가장 간단하지만 그 순간 대상 창이 맨 앞 + 터미널에 포커스돼 있어야 한다. VS Code 통합 터미널처럼 외부 입력 주입 API가 없는 환경이 여기 해당 — 자리 비울 때 그 창을 맨 앞에 둔 채 두면 된다. 첫 실행 시 **Accessibility 권한** 필요.
- **`iterm`** — **예약하는 순간**의 iTerm2 현재 세션을 id로 붙잡아 두었다가, 발사 때 그 세션에 직접 쓴다. 포커스·맨앞과 무관하게 정확하다. 반드시 **그 iTerm2 세션에서 실행**할 것. 첫 실행 시 **자동화(Apple Events) 권한** 필요.

### 동작 방식

- 예약 즉시 disown된 백그라운드 프로세스가 떠서 `sleep` 후 액션을 1회 실행한다. 상태 파일 없음 (fire-once).
- `--target iterm`은 예약 순간의 iTerm2 현재 세션 id를 캡처해 두었다가, 발사 때 모든 창/탭/세션을 훑어 그 id로 다시 찾아 입력한다.

### 한계

- `frontmost`는 발사 순간 다른 창이 포커스를 가져갔으면 엉뚱한 곳에 Enter가 간다 — 정확함이 필요하면 `iterm`을 쓸 것.
- 권한(Accessibility/자동화)이 거부돼 있으면 조용히 실패한다(Enter가 안 감). 한 번 허용해 두면 이후엔 자동.
- 대기 중 시스템이 실제로 잠들면 발사가 그만큼 늦어진다 — `nosleep`을 같이 걸어두면 해결된다.

## 버전

`VERSION` 파일 한 줄이 단일 진실이고, 세 도구가 모두 그 파일을 읽는다.

```
$ nosleep --version
nosleep (caffeine-pour-over) 1.4.0
```

`install.sh`가 심볼릭 링크를 걸기 때문에 **저장소의 체크아웃 상태가 곧 설치 버전**이다.
릴리스 태그를 벗어난 커밋을 체크아웃해 두면 그 사실이 버전에 드러난다.

```
$ nosleep --version
nosleep (caffeine-pour-over) 1.4.0+dev.aa66d77
```

`after --version`·`pourover --version`도 같은 형식이며, `pourover` 헤더에도 버전이 뜬다.

## 제거

```bash
sudo rm /etc/sudoers.d/nosleep
rm ~/.local/bin/nosleep ~/.local/bin/after ~/.local/bin/pourover
```

## 라이선스

[MIT](LICENSE)
