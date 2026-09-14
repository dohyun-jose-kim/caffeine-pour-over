# caffeine-pour-over

**English** · [한국어](README.md)

Hand-crafted macOS CLI tools. `install.sh` symlinks the scripts under `bin/` into `~/.local/bin`.

> Hand-crafted macOS CLI tools — **nosleep** (time-boxed sleep blocker with auto-revert), **after** (run a keystroke after a delay), and **pourover** (an interactive menu launcher for them).

## paper-record: Three-Layer Paper Records

`paper-record` does not collapse a PDF into one parser's answer. It keeps the original as the
scientific source of truth, preserves two independent representations, and builds a cumulative
record only from human-approved LLM proposals.

```text
paper.pdf                 authoritative original evidence
├── 01_native.md          PyMuPDF4LLM text-layer preservation
├── 02_structured.md      MinerU Hybrid structure/layout preservation
└── 03_canonical.md       approved cumulative working record
```

Parser agreement means `CROSS_CHECKED`, not proven true. Conflicts remain `UNRESOLVED`; the
system never automatically chooses a winner. `SOURCE_CONFIRMED` and `VISUALLY_READ` require an
original PDF page or asset explicitly supplied to that read. Caption-read and image-body-read
states remain separate.

### Installation and resources

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --extra mineru --extra test
uv run paper-record doctor
```

Models may be downloaded explicitly before the first ingest:

```bash
uv run --extra mineru mineru-models-download --source auto --model_type all
```

MinerU's official guidance lists at least 16 GB RAM (32 GB recommended) and 20 GB or more of
free SSD space for local hybrid/pipeline use. macOS 14 or newer is required, with acceleration
attempted on Apple Silicon; Docker on macOS is not recommended because it cannot use the expected
acceleration. The first model download needs network access and several additional GB of cache,
and `hybrid-engine/high` can take minutes for a long paper. Check the current
[MinerU quick start](https://github.com/opendatalab/MinerU/blob/master/docs/en/quick_start/index.md)
and [model source guide](https://github.com/opendatalab/MinerU/blob/master/docs/en/usage/model_source.md).

### Complete workflow

```bash
# Create 01 + 02 and an empty 03 scaffold; default: papers/<pdf-stem>/
paper-record ingest /path/to/paper.pdf
paper-record ingest /path/to/paper.pdf --id smith-2026 --root papers

# Read both Markdown records and current 03; create a proposal without changing canonical
paper-record read papers/smith-2026 --provider codex \
  --purpose "Initial full-paper reading"
paper-record read papers/smith-2026 --provider claude --model <model>

# Approve all, or reject the whole proposal and enter accept/reject/feedback item review
paper-record review papers/smith-2026 --read-id READ-0001
paper-record review papers/smith-2026 --read-id READ-0001 --approve-all

# Explicitly supply original evidence for one unresolved item
paper-record resolve papers/smith-2026 UNRESOLVED-0001 --pages 7-8
paper-record resolve papers/smith-2026 UNRESOLVED-0001 \
  --assets assets/tables/table_002.png

paper-record status papers/smith-2026
```

`read` sends `manifest.yaml`, `01_native.md`, `02_structured.md`, and the current
`03_canonical.md` to the provider. Images selected by `--pages` or `--assets` are sent too. Long
inputs are split on aligned page markers with complete coverage and no silent truncation. Codex
and Claude use their existing CLI authentication; credentials are not persisted. The adapters use
read-only, noninteractive, ephemeral options, but material sent to an external API remains subject
to that provider's retention and privacy policy.

Proposals live under `.paper-record/reviews/READ-NNNN/`. Reading never changes 03. Review applies
only accepted items plus one Reading Ledger entry via an atomic replacement. A fully rejected
read still records that the read and review happened. A changed PDF/parser revision, canonical
version, or input hash makes an older proposal stale. Failed parser revisions and rejected/invalid
LLM responses remain inspectable and can be retried after correcting the cause.

Operational events are append-only JSON objects in `.paper-record/logs/events.jsonl`. They record
stages, timestamps, status, revisions/versions, and artifact paths/hashes, while prompts, paper
bodies, API keys/tokens, credentials, and environment values are omitted or redacted. User text
between the `Canonical Notes` markers survives machine-managed updates.

Version 1 does not automatically choose the correct parser, fact-check against outside literature,
build vector/RAG indexes, interpret figures during ingest, replace the PDF with canonical, or
publish paper contents unattended. Structured page markers are best-effort anchors from MinerU's
content list; verify complex layouts against original visual evidence.

## Existing macOS tool requirements

- macOS (uses `pmset`, `osascript`)
- zsh
- `~/.local/bin` on your `PATH`
- (optional) iTerm2 — for `after --target iterm`

## Install

```bash
git clone https://github.com/dohyun-jose-kim/caffeine-pour-over.git
cd caffeine-pour-over
./install.sh   # prompts for the sudo password once (installs the sudoers rule)
```

What `install.sh` does:

1. Symlinks `bin/*` into `~/.local/bin`
2. Installs a NOPASSWD sudoers rule for nosleep (`/etc/sudoers.d/nosleep`)
3. Resets any stuck `disablesleep` state

## pourover

No need to memorize tool names — just run `pourover` and the tools under `bin/` show up as a numbered list. Pick one and it asks for the action, duration, and target as multiple choice, then runs it. A dependency-free, pure-zsh menu.

### Usage

```
pourover       # tool list → pick action/args by number, then run
pourover -h    # help
pourover --version  # version
```

Type `q` to cancel at any step.

### How it works

- It auto-collects the executable files under `bin/` into the list (excluding itself). Add a new tool to `bin/` and it shows up in the menu automatically.
- `nosleep` and `after` get curated menus that pick the duration/target for you. Any other tool falls back to showing its `--help` (or `help`) and then prompting you to type the arguments directly.

## nosleep

A time-boxed sleep blocker. It turns on `pmset -a disablesleep`, then a background watcher reverts it automatically once the timer runs out.

### Features

- **Time-boxed sleep prevention** — keeps the Mac awake for a set duration, then auto-reverts. A notification announces the revert.
- **Stays awake with the lid closed** — the key difference from `caffeinate`. `caffeinate` can't block clamshell (lid-closed) sleep, but `disablesleep` can.
- **Terminal-independent** — the watcher is a disowned background process, so it survives closing the terminal.
- **Check remaining time** (`status`) — shows time left, end time, and the current pmset state.
- **Extend** (`extend`) — pushes back the end time of a running timer.
- **Cancel** (`cancel`) — stops the timer and reverts sleep immediately.

### Usage

```
nosleep              # 60 minutes (default)
nosleep 90           # 90 minutes (bare number = minutes)
nosleep 1h30m        # h/m/s combo (e.g. 2h, 45s, 1h30m20s)
nosleep status       # time remaining + pmset state
nosleep extend 30m   # extend
nosleep cancel       # revert now
nosleep --version    # version
```

### How it works

- On start it records the end time (epoch) and watcher PID in `$TMPDIR/nosleep.state` (a per-user directory) — `status` computes the remaining time from there.
- The revert runs via `sudo -n pmset`, so the NOPASSWD rule in `/etc/sudoers.d/nosleep` is required. The rule is limited to just the two commands `pmset -a disablesleep 1`/`0`.
  (The old zshrc-function version failed to revert any timer longer than 5 minutes because the sudo credential cache expired — this rule is the root-cause fix.)

### Limitations

- `disablesleep` is an NVRAM setting, so it **persists across reboot**, but the watcher does not survive a reboot. If you reboot mid-timer, `nosleep status` shows a ⚠ warning — run `nosleep cancel` to revert.

## after

Schedules a **single action** to run after a delay. Like nosleep, it uses a disowned-process pattern, so the schedule survives closing the terminal. It currently supports the `enter` action (sends a Return key).

> **When to use it** — e.g. when a Claude session hits its usage limit and you have to wait ~1 hour: keep the Mac awake with `nosleep 3h` and pre-schedule the resume Enter with `after 65m enter`.

### Usage

```
after 65m enter                  # Enter to the frontmost window in 65 min (frontmost, default)
after 65m enter --target iterm   # Enter to this iTerm2 session (focus-independent)
after 1h5m enter                 # h/m/s combo, bare number = minutes (e.g. 90, 2h, 30s)
after --version                  # version
```

Scheduling prints the fire time and a pid. **Cancel** by `kill`-ing that pid.

### Two targets

- **`frontmost`** (default) — sends Enter to the **frontmost** app at fire time (System Events). Simplest, but at that moment the target window must be frontmost and the terminal focused. Environments with no external input-injection API — like the VS Code integrated terminal — fall here: just leave that window frontmost while you step away. Needs **Accessibility permission** on first run.
- **`iterm`** — captures the **current iTerm2 session at schedule time** (by id) and writes directly to that session at fire time. Accurate regardless of focus. Run it **from the iTerm2 session you want to target**. Needs **Automation (Apple Events) permission** on first run.

### How it works

- Scheduling immediately spawns a disowned background process that `sleep`s and then runs the action once. No state file (fire-once).
- `--target iterm` captures the current iTerm2 session id at schedule time, then at fire time walks every window/tab/session to find that id and types into it.

### Limitations

- `frontmost` sends Enter to the wrong place if another window grabbed focus by fire time — use `iterm` when accuracy matters.
- If the permission (Accessibility/Automation) is denied, it fails silently (no Enter). Grant it once and it's automatic afterward.
- If the system actually sleeps while waiting, the fire is delayed by that much — pair it with `nosleep` to avoid this.

## Version

A single line in the `VERSION` file is the source of truth; all three tools read it.

```
$ nosleep --version
nosleep (caffeine-pour-over) 1.3.0
```

Because `install.sh` symlinks the scripts, **the repo's checkout state is the installed
version**. If you check out a commit past the release tag, the version says so.

```
$ nosleep --version
nosleep (caffeine-pour-over) 1.3.0+dev.aa66d77
```

`after --version` and `pourover --version` use the same format, and `pourover` shows the
version in its header too.

## Uninstall

```bash
sudo rm /etc/sudoers.d/nosleep
rm ~/.local/bin/nosleep ~/.local/bin/after ~/.local/bin/pourover
```

## License

[MIT](LICENSE)
