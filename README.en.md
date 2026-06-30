# caffeine-pour-over

**English** · [한국어](README.md)

Hand-crafted macOS CLI tools. `install.sh` symlinks the scripts under `bin/` into `~/.local/bin`.

> Hand-crafted macOS CLI tools — **nosleep** (time-boxed sleep blocker with auto-revert), **after** (run a keystroke after a delay), and **pourover** (an interactive menu launcher for them).

## Requirements

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
```

### How it works

- On start it records the end time (epoch) and watcher PID in `/tmp/nosleep.state` — `status` computes the remaining time from there.
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

## Uninstall

```bash
sudo rm /etc/sudoers.d/nosleep
rm ~/.local/bin/nosleep ~/.local/bin/after ~/.local/bin/pourover
```

## License

[MIT](LICENSE)
