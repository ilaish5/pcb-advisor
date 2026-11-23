"""23/11 browser finding: after Check board the Rules and Layout pages threw RangeError (Invalid time value) because drcSummary read
the board record's ISO time stamp as a number. Runs drcSummary under node with the stamp the server really writes."""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest
import store

UI = pathlib.Path(__file__).resolve().parent.parent / "ui" / "js"


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


@pytest.mark.parametrize("ts", [store.now_ms(), "1764000000000", None])
def test_drc_summary_reads_the_servers_time_stamp(ts):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    prev = (UI / "views" / "previews.js").read_text(encoding="utf-8")
    outs = (UI / "views" / "outputs.js").read_text(encoding="utf-8")
    c = {"ts": ts, "total": 3, "complete": True, "stale": False}
    js = ("global.plural=(n,w)=>n+' '+w+(n===1?'':'s');global.whenText=s=>s;" + _fn(outs, "outAgo") + _fn(prev, "drcSummary")
          + f";console.log(JSON.stringify(drcSummary({json.dumps(c)})))")
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "t.js"
        f.write_text(js, encoding="utf-8")
        r = subprocess.run([node, str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["tone"] == "bad" and out["text"].startswith("Board DRC: 3 violations")
    if ts:
        assert out["text"].endswith("just now") or "ago" in out["text"] or "," in out["text"]
