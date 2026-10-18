"""Run the replay benchmark and write docs/BENCHMARK.md."""
import datetime
import importlib
import pathlib
import re
import subprocess

from . import detectors, incidents

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
DOCS = REPO / "docs"
EVAL_MODULES = ("qa_eval", "behaviour")
HISTORY_HEADER = "## History"


def build_prompt(incident):
    parts = [incident["question"], ""]
    for name in incident["state"]:
        text = (pathlib.Path(incident["_dir"]) / name).read_text(encoding="utf-8", errors="replace")
        parts += [f"File: {name}", "```", text.rstrip("\n"), "```", ""]
    parts.append("Answer as the advisor would, briefly.")
    return "\n".join(parts)


def keywords_hit(answer, groups):
    low = re.sub(r"[*_`]", "", answer).lower()   # "A7670**C**" in Markdown is still A7670C
    return all(any(k.lower() in low for k in g) for g in groups)


def earlier(incident, caught):
    return bool(caught) and incident["target_stage"] < incident["reality"]["stage"]


def _engine_answer(incident, engine, repo, home):
    import gateway
    req = gateway.Request(build_prompt(incident), timeout=300,
                          options={"cwd": str(home), "add_dirs": [str(repo)]})
    return gateway.route(req, None if engine == "active" else engine)


def run_incidents(items, engine=None, repo=None, runs_dir=None, today=None):
    """Score every incident. engine: None (deterministic only), "active", or a provider name."""
    repo = pathlib.Path(repo or REPO)
    today = today or datetime.date.today().isoformat()
    home = prov_id = out_dir = None
    engine_ok = False
    errors_global = []
    if engine:
        import gateway
        import runtime_pack
        prov_id = gateway.resolve(None if engine == "active" else engine)
        try:
            home = runtime_pack.sync()
            engine_ok = True
        except runtime_pack.RuntimePackError as exc:
            errors_global.append(f"runtime pack: {exc}")
        out_dir = pathlib.Path(runs_dir or REPO / "local" / "bench-runs") / f"{today}-{prov_id}"
    rows = []
    for inc in items:
        row = {"id": inc["id"], "slug": inc["slug"], "title": inc["title"],
               "reality": inc["reality"]["stage"], "target": inc["target_stage"],
               "det": False, "engine": None, "errors": []}
        res = detectors.run_all(pathlib.Path(inc["_dir"]), inc)
        row["errors"] += res["errors"]
        row["findings"] = res["findings"]
        row["det"] = detectors.caught(res["findings"], inc["expect"])
        if engine and engine_ok:
            try:
                r = _engine_answer(inc, engine, repo, home)
                if r.error:
                    row["engine"] = False
                    row["errors"].append(f"engine: {r.error}")
                else:
                    row["engine"] = keywords_hit(r.text, inc["expect"]["keywords"])
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / f"{inc['id']:02d}-{inc['slug']}.md").write_text(
                        f"# {inc['title']}\n\nprovider: {prov_id}\ncaught: {row['engine']}\n\n"
                        f"## Question\n\n{inc['question']}\n\n## Answer\n\n{r.text}\n",
                        encoding="utf-8")
            except Exception as exc:                   # noqa: BLE001
                row["engine"] = False
                row["errors"].append(f"engine: {type(exc).__name__}: {exc}")
        row["earlier"] = earlier(inc, row["det"] or row["engine"])
        rows.append(row)
    return {"rows": rows, "provider": prov_id, "errors": errors_global, "out_dir": out_dir}


def run_evals(provider, out_dir=None):
    """out_dir: the incidents' folder, so a run that passes midnight stays in one folder."""
    out = []
    here = pathlib.Path(__file__).resolve().parent
    for name in EVAL_MODULES:
        if not (here / f"{name}.py").is_file():
            continue
        try:
            mod = importlib.import_module(f"{__package__}.{name}")
            out.append(mod.run(provider, out_dir=out_dir))
        except ImportError:
            continue
        except Exception as exc:                       # noqa: BLE001
            out.append({"name": name, "score": None, "total": 0, "rows": [],
                        "needs_engine": False, "error": f"{type(exc).__name__}: {exc}"})
    return out


def _mark(v):
    return "-" if v is None else ("yes" if v else "no")


def totals(rows, engine_run):
    n = len(rows)
    det = sum(1 for r in rows if r["det"])
    eng = sum(1 for r in rows if r["engine"])
    early = sum(1 for r in rows if r["earlier"])
    eng_s = f"engine caught {eng}/{n}" if engine_run else "engine not run"
    return f"deterministic caught {det}/{n}, {eng_s}, earlier than reality {early}"


def table(rows):
    lines = ["| # | Incident | Reality | Target | Det | Engine | Earlier | Errors |",
             "|--:|---|:-:|:-:|:-:|:-:|:-:|---|"]
    for r in rows:
        err = "; ".join(r["errors"]).replace("|", "/").replace("\n", " ")[:120]
        lines.append(f"| {r['id']} | {r['title']} | {r['reality']} | {r['target']} | "
                     f"{_mark(r['det'])} | {_mark(r['engine'])} | {_mark(r['earlier'])} | {err} |")
    return "\n".join(lines)


def git_hash(repo=REPO):
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:                                  # noqa: BLE001
        return "unknown"


def read_history(path):
    path = pathlib.Path(path)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    if HISTORY_HEADER not in text:
        return []
    tail = text.split(HISTORY_HEADER, 1)[1]
    return [l for l in tail.splitlines() if l.startswith("- ")]


def render(result, evals, mode, when, commit, problems, history):
    rows = result["rows"]
    summary = totals(rows, result["provider"] is not None)
    out = ["# Benchmark: real-incident replay", "",
           f"- date: {when}", f"- commit: {commit}", f"- mode: {mode}", "",
           "## Scores", "", table(rows), "", f"**{summary}**", ""]
    if problems or result["errors"]:
        out += ["## Problems", ""] + [f"- {p}" for p in problems + result["errors"]] + [""]
    if evals:
        out += ["## Evals", ""]
        for e in evals:
            sc = "n/a" if e.get("score") is None else f"{e['score']:.2f}"
            extra = " (needs an engine)" if e.get("needs_engine") and result["provider"] is None else ""
            err = f" ERROR {e['error']}" if e.get("error") else ""
            out.append(f"- {e['name']}: score {sc} over {e.get('total', 0)}{extra}{err}")
        out.append("")
    history = history + [f"- {when} {commit} {mode}: {summary}"]
    out += [HISTORY_HEADER, ""] + history + [""]
    return "\n".join(out), summary


def run(fixtures=None, engine=None, evals=False, only=None, out_md=None, runs_dir=None,
        repo=None, today=None, now=None):
    items, problems = incidents.load_all(fixtures)
    if only:
        items = [i for i in items if i["id"] in set(only)]
    result = run_incidents(items, engine, repo, runs_dir, today)
    eval_res = run_evals(result["provider"], result["out_dir"]) if evals else []
    mode = f"engine:{result['provider']}" if engine else "deterministic"
    out_md = pathlib.Path(out_md or DOCS / "BENCHMARK.md")
    when = now or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text, summary = render(result, eval_res, mode, when, git_hash(), problems, read_history(out_md))
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(text, encoding="utf-8")
    return {"text": text, "summary": summary, "rows": result["rows"], "problems": problems,
            "evals": eval_res, "path": str(out_md)}
