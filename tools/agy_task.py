"""Dev helper, not part of the advisor: run one implementation task on agy (headless) and print its final answer.

    python tools/agy_task.py <brief.md> [--timeout 1500] [--add-dir DIR ...]

cwd = the pcb-advisor repo. The brief goes on stdin as one stream-json user line.
Writes the raw stream to <brief>.log next to the brief.
"""
import json, pathlib, shutil, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = str(pathlib.Path(__file__).resolve().parent.parent)
args = sys.argv[1:]
brief = pathlib.Path(args.pop(0))
timeout = 1500
if "--timeout" in args:
    i = args.index("--timeout"); timeout = int(args[i + 1]); del args[i:i + 2]
adds = []
while "--add-dir" in args:
    i = args.index("--add-dir"); adds += ["--add-dir", args[i + 1]]; del args[i:i + 2]

cmd = [shutil.which("agy"), "-p=", "--input-format", "stream-json", "--output-format", "stream-json",
       "--dangerously-skip-permissions", "--print-timeout", f"{timeout}s", *adds]
line = json.dumps({"event": "user", "message": {"role": "user", "content": brief.read_text(encoding="utf-8")}})
p = subprocess.run(cmd, input=line + "\n", capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=REPO, timeout=timeout + 120)
log = brief.with_suffix(".log")
log.write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
resp, denied, status = "", [], None
for ln in p.stdout.splitlines():
    try:
        ev = json.loads(ln)
    except ValueError:
        continue
    if ev.get("event") == "result":
        r = ev.get("result") or {}
        resp = r.get("response") or ""
        denied = r.get("denied_actions") or []
        status = r.get("status")
print(f"exit={p.returncode} status={status} denied={denied} log={log}")
print(resp[-6000:])
