#!/usr/bin/env bash
# pcb-advisor installer for macOS / Linux. Safe to run again: a second run repairs, it never duplicates or deletes.
#
#   curl -fsSL https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.sh | bash
#   ./install.sh                      (from a clone or an unpacked ZIP: repairs it in place)
#
# What it does: finds Python 3.10+ (offers Homebrew if missing), gets the code (git clone, or the ZIP when git is
# missing), makes .venv, installs requirements, detects Claude Code or Antigravity (asks which to install) and offers the sign-in, runs
# `pcb.py doctor`, and starts the server. Questions default to YES (Enter); answers come from the terminal even under `curl | bash`.
#
# Settings (environment): PCB_DIR target folder (default: this clone, or ~/pcb-advisor) | PCB_REPO clone source
# (default the GitHub URL; a local path works) | PCB_REF branch or tag to check out | PCB_YES=1 no questions |
# PCB_ENGINE=claude|agy choose the AI engine without asking (nothing installed and PCB_YES=1 means claude) |
# PCB_NO_ENGINE=1 skip the engine install and sign-in (PCB_NO_CLAUDE=1 is the same) | PCB_NO_START=1 do not start the server | PCB_NO_GIT=1 act as if
# git is missing (ZIP route) | PCB_ZIP_URL ZIP address or path (default: the GitHub ZIP of PCB_REF).
set -u

REPO_URL="${PCB_REPO:-https://github.com/ilaish5/pcb-advisor.git}"
REF="${PCB_REF:-}"
ZIP_URL="${PCB_ZIP_URL:-https://github.com/ilaish5/pcb-advisor/archive/refs/heads/${REF:-main}.zip}"

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Y/n with Enter = yes. Reads /dev/tty (stdin is the script itself under `curl | bash`); no terminal = the default.
ask() {
  [ "${PCB_YES:-}" = "1" ] && return 0
  if { : </dev/tty; } 2>/dev/null; then
    printf '%s [Y/n] ' "$1" >/dev/tty
    local a=""
    read -r a </dev/tty || a=""
    case "$a" in n|N|no|NO|No) return 1 ;; *) return 0 ;; esac
  fi
  return 0
}

# ---- where
if [ -n "${PCB_DIR:-}" ]; then
  DIR="$PCB_DIR"
else
  HERE=""
  [ -f "$0" ] && HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
  if [ -n "$HERE" ] && [ -f "$HERE/pcb.py" ]; then DIR="$HERE"; else DIR="$HOME/pcb-advisor"; fi
fi

# ---- 1. Python 3.10+
step "Python"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  p="$(command -v "$c" 2>/dev/null)" || continue
  if "$p" -c 'import sys; sys.exit(sys.version_info < (3,10))' >/dev/null 2>&1; then PY="$p"; break; fi
done
if [ -z "$PY" ] && [ "$(uname)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
  if ask "Python 3.10 or newer was not found. Install it with Homebrew?"; then
    brew install python@3.12 || true
    p="$(brew --prefix python@3.12 2>/dev/null)/bin/python3.12"
    [ -x "$p" ] && PY="$p"
  fi
fi
[ -n "$PY" ] || die "Python 3.10 or newer is required. Get it from https://www.python.org/downloads/ (Linux: your package manager), then run this again."
say "using $("$PY" --version) at $PY"

# ---- 2. the code
step "pcb-advisor code in $DIR"
HAVE_GIT=1
command -v git >/dev/null 2>&1 || HAVE_GIT=0
[ "${PCB_NO_GIT:-}" = "1" ] && HAVE_GIT=0
if [ -d "$DIR/.git" ] && [ "$HAVE_GIT" = 1 ]; then
  if [ -z "$(git -C "$DIR" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    git -C "$DIR" pull --ff-only >/dev/null 2>&1 && say "up to date (git pull)" || say "kept the current version (could not pull; this is fine offline)"
  else
    say "you have local edits, so the code was left as it is"
  fi
elif [ -f "$DIR/pcb.py" ] && [ ! -d "$DIR/.git" ] && [ "$HAVE_GIT" = 1 ] \
     && ask "This folder is a ZIP copy. Turn it into a git clone so the in-app Update works? (projects and settings stay)"; then
  # reset --hard rewrites only the tool's own files; projects/, config.json and .venv are untracked and untouched.
  BR="${REF:-main}"
  if git -C "$DIR" init -q && git -C "$DIR" remote add origin "$REPO_URL" \
     && git -C "$DIR" fetch -q origin "$BR" && git -C "$DIR" reset -q --hard FETCH_HEAD \
     && git -C "$DIR" branch -q -M "$BR" && git -C "$DIR" branch -q -u "origin/$BR" >/dev/null 2>&1; then
    say "now a git clone on $BR: Update works"
  else
    rm -rf "$DIR/.git"
    say "could not turn it into a clone (network?); kept the ZIP copy as it was"
  fi
elif [ -f "$DIR/pcb.py" ]; then
  say "found an existing install, keeping it"
elif [ "$HAVE_GIT" = 1 ]; then
  [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ] && die "$DIR exists and is not pcb-advisor. Pick another folder: PCB_DIR=/some/folder"
  git clone "$REPO_URL" "$DIR" || die "git clone failed (network, or a proxy: set HTTPS_PROXY)."
  [ -n "$REF" ] && git -C "$DIR" checkout "$REF" >/dev/null 2>&1
else
  say "WARNING: git is not installed, so this uses the ZIP download. Everything works, but the in-app Update stays off."
  say "         To get Update later, install git (macOS: xcode-select --install) and run this installer again."
  [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ] && die "$DIR exists and is not pcb-advisor. Pick another folder: PCB_DIR=/some/folder"
  command -v unzip >/dev/null 2>&1 || die "unzip is needed for the ZIP route"
  TMP="$(mktemp -d)" || die "could not make a temp folder"
  case "$ZIP_URL" in
    http*|file:*) curl -fsSL "$ZIP_URL" -o "$TMP/src.zip" || die "download failed: $ZIP_URL" ;;
    *) cp "$ZIP_URL" "$TMP/src.zip" || die "cannot read $ZIP_URL" ;;
  esac
  unzip -q "$TMP/src.zip" -d "$TMP/x" || die "the ZIP could not be unpacked"
  SRC="$(find "$TMP/x" -maxdepth 2 -name pcb.py -exec dirname {} \; | head -n 1)"
  [ -n "$SRC" ] || die "the ZIP does not contain pcb.py"
  mkdir -p "$DIR" && cp -R "$SRC"/. "$DIR"/ || die "could not copy into $DIR"
  rm -rf "$TMP"
fi
[ -f "$DIR/pcb.py" ] || die "pcb.py is missing in $DIR"
cd "$DIR" || die "cannot enter $DIR"

# ---- 3. venv + requirements + workspace
step "Private Python environment"
if [ -d .venv ] && ! .venv/bin/python -m pip --version >/dev/null 2>&1; then rm -rf .venv; fi
[ -d .venv ] || "$PY" -m venv .venv || die "could not create .venv (Debian/Ubuntu: sudo apt install python3-venv)"
.venv/bin/python -m pip install --quiet --upgrade pip || say "pip upgrade skipped"
.venv/bin/python -m pip install --quiet -r requirements.txt || die "installing requirements failed (network or proxy?)"
.venv/bin/python pcb.py init || die "pcb.py init failed"

# ---- 4. AI engine (Claude Code or Antigravity) + sign-in
CLAUDE=""
AGY=""
find_claude() {
  CLAUDE="$(command -v claude 2>/dev/null)"
  [ -z "$CLAUDE" ] && [ -x "$HOME/.local/bin/claude" ] && CLAUDE="$HOME/.local/bin/claude"
  return 0
}
find_agy() {
  AGY="$(command -v agy 2>/dev/null)"
  [ -z "$AGY" ] && [ -x "$HOME/.local/bin/agy" ] && AGY="$HOME/.local/bin/agy"
  return 0
}
# agent.provider as the person set it in the workspace config.json (empty = never set, so the default applies).
set_provider() {
  .venv/bin/python - <<'PYEOF' 2>/dev/null
import json, os, pathlib
cfg = os.environ.get("PCB_ADVISOR_CONFIG") or str(pathlib.Path(os.environ.get("PCB_ADVISOR_HOME") or ".") / "config.json")
try:
    print(json.loads(pathlib.Path(cfg).read_text(encoding="utf-8")).get("agent", {}).get("provider", "") or "")
except (OSError, ValueError, AttributeError):
    print("")
PYEOF
}
# True when a person can answer (a terminal, and no PCB_YES).
can_prompt() {
  [ "${PCB_YES:-}" = "1" ] && return 1
  { : </dev/tty; } 2>/dev/null
}
if [ "${PCB_NO_CLAUDE:-}" != "1" ] && [ "${PCB_NO_ENGINE:-}" != "1" ]; then
  step "AI engine (Claude Code or Antigravity)"
  find_claude
  find_agy
  ENGINE=""          # claude or agy
  SETPROV=0          # write agent.provider to the config
  ASKED=0            # the person already said which one, so no second install question
  EXPLICIT="$(set_provider)"
  if [ "${PCB_ENGINE:-}" = "claude" ] || [ "${PCB_ENGINE:-}" = "agy" ]; then
    ENGINE="$PCB_ENGINE"; SETPROV=1
  elif [ "$EXPLICIT" = "antigravity" ]; then ENGINE=agy; say "The workspace is set to Antigravity; keeping it."
  elif [ "$EXPLICIT" = "claude_code" ]; then ENGINE=claude; say "The workspace is set to Claude Code; keeping it."
  elif [ -n "$CLAUDE" ] && [ -n "$AGY" ]; then ENGINE=claude; say "Both found; using Claude Code. Switch in Settings > Engine."
  elif [ -n "$AGY" ]; then ENGINE=agy; SETPROV=1; say "Only Antigravity (agy) found; setting it as the engine."
  elif [ -n "$CLAUDE" ]; then ENGINE=claude
  else
    PICK=1
    if can_prompt; then
      say "Which AI engine do you have an account for?"
      say "  1) Claude Code (Claude Pro/Max)"
      say "  2) Antigravity (Google account)"
      printf 'Enter = 1: ' >/dev/tty
      read -r PICK </dev/tty || PICK=1
    fi
    if [ "$PICK" = "2" ]; then ENGINE=agy; SETPROV=1; else ENGINE=claude; fi
    ASKED=1
  fi
  if [ "$ENGINE" = "claude" ] && [ -z "$CLAUDE" ]; then
    if [ "$ASKED" = 1 ] || ask "Claude Code is not installed. Install it now (official installer)?"; then
      curl -fsSL https://claude.ai/install.sh | bash || say "The Claude Code installer failed. See docs/ENGINES.md."
      export PATH="$HOME/.local/bin:$PATH"
      find_claude
    fi
  fi
  if [ "$ENGINE" = "agy" ] && [ -z "$AGY" ]; then
    # No official mac/linux installer address is documented, so point at the docs instead of guessing one.
    say "Antigravity (agy) is not installed. Install it as described in docs/ENGINES.md, then run ./install.sh again."
  fi
  if [ "$SETPROV" = 1 ]; then
    if [ "$ENGINE" = "agy" ]; then PROV=antigravity; else PROV=claude_code; fi
    .venv/bin/python pcb.py config agent.provider "$PROV" >/dev/null && say "engine set to $PROV"
  fi
  if [ "$ENGINE" = "claude" ] && [ -n "$CLAUDE" ]; then
    say "found $CLAUDE"
    if ! "$CLAUDE" auth status >/dev/null 2>&1; then
      if { : </dev/tty; } 2>/dev/null || [ "${PCB_YES:-}" = "1" ]; then
        if ask "Sign in to Claude now? (a browser window opens; finish there)"; then
          "$CLAUDE" auth login </dev/tty || say "Sign-in did not finish. You can do it later: claude auth login"
          "$CLAUDE" auth status >/dev/null 2>&1 && say "signed in" || say "still not signed in; the app will show how to fix it"
        fi
      fi
    else
      say "signed in"
    fi
  elif [ "$ENGINE" = "agy" ] && [ -n "$AGY" ]; then
    say "found $AGY"
    # agy has no status command: the first run opens the Google sign-in in the browser.
    say "To sign in: run \`agy\` once and sign in with your Google account in the browser, then exit it."
    if can_prompt && ask "Run agy now to sign in?"; then "$AGY" </dev/tty || true; fi
  fi
fi

# ---- 5. doctor, then start
step "Checking everything"
.venv/bin/python pcb.py doctor --exit-start
RC=$?
if [ "$RC" -ne 0 ]; then
  say ""
  say "The server cannot start yet. Fix the FIX lines above, then run ./install.sh again."
  exit 1
fi
say ""
say "Installed in $DIR. Next time: cd \"$DIR\" && ./start.sh"
if [ "${PCB_NO_START:-}" = "1" ]; then exit 0; fi
step "Starting pcb-advisor (http://localhost:${PCB_ADVISOR_PORT:-8931}). Stop with Ctrl+C."
exec ./start.sh </dev/null
