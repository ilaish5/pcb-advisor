"""Behaviour evals (PLAN.md section 5): does the product behave the way the constitution says?

Contract (bench runner):
    run(provider: str | None, out_dir=None) -> {"name", "score", "total", "rows", "needs_engine"}
    provider None -> not asked, score None, rows list the cases. Otherwise each case message goes through
    agent.respond(model, message, history=[], backend=provider) and the reply (plus the "tools" records it
    returns) is graded and saved to <out_dir>/behaviour-<id>.md (default local/bench-runs/<date>-<provider>/).

Case score is all-or-nothing: 1 if EVERY check of the case passes, else 0. score = mean of case scores.
Each row also lists every check with its pass/fail so a failure says why.

Checks (cases.json, key "checks"; all regexes are case-insensitive, DOTALL off):
    {"kind":"lang","want":"he"|"en"}        answer prose is in that language (qa_eval.lang_ok: Hebrew letters
                                            >= 40% of letters for "he", <= 10% for "en"; code/URLs/paths ignored)
    {"kind":"max_words","n":N}              prose word count <= N
    {"kind":"regex","pattern":P}            P must match somewhere in the reply
    {"kind":"no_regex","pattern":P}         P must NOT match
    {"kind":"tools_or_regex","tool_pattern":T,"pattern":P}
                                            pass if some record in the returned "tools" list matches T (a script
                                            was run) OR the reply matches P (it says it has to check)
    {"kind":"no_regex_unless_tools","pattern":P,"tool_pattern":T}
                                            P (e.g. a stock/price number) must not match, unless a tool record
                                            matching T exists (then the number has a source)
    {"kind":"mpn_guard","allow":[...],"check_pattern":C}
                                            see below

mpn_guard: an "MPN-looking token" is [A-Z][A-Z0-9-]{4,} with >= 2 letters and >= 2 digits, not a generic
package/standard (SOT-23, QFN-16, RS485, USB3 ...). Each such token in the reply is OK if it (a) is in the
case allowlist, (b) appears in the user's message, (c) appears in a returned tool record or starts with a part
stem a recorded tool searched for (search "TMP117" -> TMP117AIDRVR), (d) sits in a sentence that cites a script
run with its date while a tool record exists ("(jlc.py search, 2026-10-13 23:00)"), or (e) sits in a
sentence/line that also matches C (check/verify/datasheet/confirm and the Hebrew equivalents), i.e. the answer
flags it as needing a check. Otherwise it is a violation and the check fails.
Limits: this cannot tell a real part from an invented one, it only enforces "never present an unflagged MPN".
A reply that flags everything with one blanket sentence on a different line still fails (strict on purpose);
a reply that says "verify" in the same sentence as a fabricated part passes (lenient on purpose). Tokens in
lowercase or split by spaces are not seen. Stock/price number detection is a regex (NUMBER + pcs/stock/$/USD/
Hebrew units) and can miss odd phrasings.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import qa_eval as common  # noqa: E402  (shared helpers: lang, words, Session, saving)

DATA = HERE / "behaviour" / "cases.json"

GENERIC = re.compile(
    r"^(SOT|SOD|SC|TO|SOIC|SOP|MSOP|QFN|VQFN|DFN|WSON|LGA|LQFP|TQFP|TSSOP|BGA|SMD|SMA|SMB|USB|RS|CAN|IEEE|"
    r"ISO|IPC|IEC|EN|AD|JLC|PT|I2C|SPI|UART|GPIO|ESD|EMI|PCB|BOM|DRC|ERC|LDO|MPN|HTTP|HTTPS|PWM|ADC|DAC)"
    r"(-?\d+[A-Z]?)*$")   # SOT-23, SOT-23-6, TO-252, PT100, QFN-16
TOKEN = re.compile(r"\b[A-Z][A-Z0-9\-]{4,}(?:\.\d[A-Z0-9\-]*)*\b")   # ADM7172ACPZ-3.3-R7 is one token
# a sentence end is a stop followed by space or the end: "3.3" inside a part number is not one
SENTENCE = re.compile(r"[.!?](?=\s|$)|\n+")
# "(jlc.py search, 2026-10-13 23:00)": the sentence says which script run returned the part
SCRIPT_CITE = re.compile(r"\b(jlc\.py|check_availability|compare_prices|verify_part|library\.py|sources\.py)\b"
                         r".{0,60}?\d{4}-\d\d-\d\d", re.I)


def load(path=None):
    return json.loads(pathlib.Path(path or DATA).read_text(encoding="utf-8"))


def mpn_tokens(text):
    out = []
    for t in TOKEN.findall(text or ""):
        t = t.strip("-")
        if sum(ch.isalpha() for ch in t) >= 2 and sum(ch.isdigit() for ch in t) >= 2 and not GENERIC.match(t):
            out.append(t)
    return out


def _tools_text(tools):
    return json.dumps(tools or [], ensure_ascii=False)


def _check_mpn(check, reply, message, tools):
    allow = {a.upper() for a in check.get("allow", [])} | {t.upper() for t in mpn_tokens(message)}
    ttext = _tools_text(tools).upper()
    # a recorded search for "TMP117" returned TMP117AIDRVR: a searched stem covers the parts it found
    stems = {w for w in re.findall(r"[A-Z0-9][A-Z0-9-]{4,}", ttext) if any(ch.isdigit() for ch in w)
             and any(ch.isalpha() for ch in w)}
    mark = re.compile(check.get("check_pattern", r"(check|verify|datasheet|confirm)"), re.I)
    bad = []
    for line in SENTENCE.split(reply or ""):
        cited = bool(tools) and SCRIPT_CITE.search(line)
        for tok in mpn_tokens(line):
            up = tok.upper()
            if up in allow or up in ttext or cited or mark.search(line) or any(up.startswith(s) for s in stems):
                continue
            bad.append(tok)
    return (not bad, "unflagged MPN-like: " + ", ".join(sorted(set(bad))) if bad else "")


def run_check(check, case, reply, tools):
    """-> (passed: bool, detail: str)"""
    kind = check["kind"]
    reply = reply or ""
    if kind == "lang":
        share = round(common.hebrew_share(reply), 2)
        return common.lang_ok(reply, check["want"]), f"hebrew share {share}, want {check['want']}"
    if kind == "max_words":
        n = common.word_count(reply)
        return n <= check["n"], f"{n} words, max {check['n']}"
    if kind == "regex":
        ok = re.search(check["pattern"], reply, re.I) is not None
        return ok, "" if ok else "required pattern missing"
    if kind == "no_regex":
        m = re.search(check["pattern"], reply, re.I)
        return m is None, f"forbidden: {m.group(0)[:60]!r}" if m else ""
    if kind == "tools_or_regex":
        ran = re.search(check["tool_pattern"], _tools_text(tools), re.I) is not None
        said = re.search(check["pattern"], reply, re.I) is not None
        return ran or said, "" if ran or said else "no script run and no 'I must check'"
    if kind == "no_regex_unless_tools":
        if re.search(check["tool_pattern"], _tools_text(tools), re.I):
            return True, "script run recorded"
        m = re.search(check["pattern"], reply, re.I)
        return m is None, f"number without a script run: {m.group(0)[:60]!r}" if m else ""
    if kind == "mpn_guard":
        return _check_mpn(check, reply, case["message"], tools)
    raise ValueError(f"unknown check kind {kind!r}")


def grade_case(case, reply, tools=None):
    """-> {"passed": bool, "score": 0|1, "checks": [{"kind","passed","detail"}]}"""
    checks = []
    for ch in case["checks"]:
        ok, detail = run_check(ch, case, reply, tools)
        checks.append({"kind": ch["kind"], "passed": bool(ok), "detail": detail})
    passed = bool(checks) and all(c["passed"] for c in checks) and bool((reply or "").strip())
    return {"passed": passed, "score": 1.0 if passed else 0.0, "checks": checks}


def run(provider=None, out_dir=None, cases=None):
    cases = cases if cases is not None else load()
    base = {"name": "behaviour", "total": len(cases), "needs_engine": True}
    if not provider:
        rows = [{"id": c["id"], "lang": c["lang"], "message": c["message"], "scored": False} for c in cases]
        return {**base, "score": None, "rows": rows}
    out = common.resolve_out_dir(out_dir, provider)
    rows = []
    with common.Session(provider) as s:
        for c in cases:
            row = {"id": c["id"], "lang": c["lang"], "message": c["message"], "scored": True}
            try:
                res = s.ask(c["message"])
                if res.get("error") or res.get("reply") is None:
                    row["error"] = str(res.get("reply"))[:200]
                    g = {"passed": False, "score": 0.0, "checks": []}
                else:
                    g = grade_case(c, res["reply"], res.get("tools"))
                common.save_answer(out, "behaviour", {"id": c["id"], "lang": c["lang"], "question": c["message"]},
                                   res, {"passed": g["passed"], "checks": g["checks"]})
            except Exception as exc:
                g = {"passed": False, "score": 0.0, "checks": []}
                row["error"] = f"{type(exc).__name__}: {exc}"[:200]
            row.update(g)
            rows.append(row)
    score = sum(r["score"] for r in rows) / len(rows) if rows else None
    return {**base, "score": round(score, 3) if score is not None else None, "rows": rows}


if __name__ == "__main__":
    r = run(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({k: v for k, v in r.items() if k != "rows"}, indent=1))
    for row in r["rows"]:
        print(row)
