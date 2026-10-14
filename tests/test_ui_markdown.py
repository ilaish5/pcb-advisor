"""The general reference documents (shared/reference/*.md) are read in the side sheet as documents, not as raw text:
ui/js/markdown.js turns them into a small, safe set of tags. The renderer is browser code; with a Chromium browser on
the machine (Edge or Chrome) these tests run the real file in it, and without one they skip. The wiring is checked as text."""
import html
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from ui_source import UI, ui_html, ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
MARKDOWN = (UI / "js" / "markdown.js").read_text(encoding="utf-8")
VIEWER = (UI / "js" / "viewer.js").read_text(encoding="utf-8")
VIEWER_CSS = (UI / "styles" / "viewer.css").read_text(encoding="utf-8")
CORE = (UI / "js" / "core.js").read_text(encoding="utf-8")
REFERENCE = REPO / "shared" / "reference"


# ---------------------------------------------------------------- wiring, as text

def test_the_renderer_loads_after_core_and_before_the_viewer():
    order = re.findall(r'<script src="/ui/js/([\w/.-]+)"', ui_html())
    assert order.index("core.js") < order.index("markdown.js") < order.index("viewer.js")


def test_a_markdown_source_is_drawn_as_a_document_and_a_citation_scrolls_to_its_section():
    assert "const md = ext === '.md' && !isExport;" in VIEWER, "an export that happens to be .md stays raw text"
    assert "md ? docMarkdownHTML(text) : docTextHTML(text)" in VIEWER
    assert "mdToHTML(docCut(text))" in VIEWER and 'class="md"' in VIEWER
    assert "if (md) docReveal(body(), tabObj.where);" in VIEWER
    assert "mdFindSection(box, where)" in VIEWER and "md-hit" in VIEWER
    assert "docSourceSub(name, tabObj.where)" in VIEWER, "the header says what was cited"
    assert "DOC_TEXT_CHARS" in VIEWER and "docCut(" in VIEWER, "a huge file is cut, as plain text is"


def test_the_renderer_only_makes_http_links_and_escapes_what_it_prints():
    assert "/^https?:\\/\\//i.test(m[3])" in MARKDOWN, "a link needs an http(s) address"
    assert 'target="_blank" rel="noopener noreferrer"' in MARKDOWN
    assert "innerHTML" not in MARKDOWN and "eval(" not in MARKDOWN and "Function(" not in MARKDOWN
    # what the source holds reaches a template only through esc() or mdInline(): never ${m[2]}, ${raw}, ${text} (m[1] of a page marker is digits only)
    assert not re.search(r"\$\{\s*(?:m\[[2-9]\]|raw\b|text\b|l\b|lines?\b|c\b)", MARKDOWN)


def test_the_document_styles_use_tokens_and_cover_every_class_the_renderer_makes():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", VIEWER_CSS) and "rgb" not in VIEWER_CSS
    for cls in re.findall(r'class="(md-[\w-]+|a-\w+)', MARKDOWN) + ["md", "md-hit", "md-page"]:
        assert "." + cls in VIEWER_CSS, f".{cls} has no rule"


# ---------------------------------------------------------------- the real renderer, in a browser

def find_browser():
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    for path in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(path):
            return path
    return None


def run_in_browser(tmp_path, cases, finds, docs):
    """mdToHTML of each case, mdFindSection of each (document, citation) pair, and mdToHTML of every real document."""
    browser = find_browser()
    if not browser:
        pytest.skip("no Chromium browser to run ui/js/markdown.js in")
    esc = re.search(r"^const esc = .*$", CORE, re.M).group(0)
    payload = json.dumps({"cases": cases, "finds": finds, "docs": docs}).replace("<", "\\u003c")
    page = tmp_path / "md.html"
    page.write_text(f"""<!doctype html><meta charset="utf-8"><pre id="out"></pre>
<script>{esc}</script><script>{MARKDOWN.replace("</script", "<\\/script")}</script>
<script>
const input = {payload};
const out = {{cases: {{}}, finds: [], docs: {{}}}};
for (const [k, v] of Object.entries(input.cases)) out.cases[k] = mdToHTML(v);
for (const [doc, where] of input.finds) {{
  const box = document.createElement('div');
  box.innerHTML = mdToHTML(input.cases[doc]);
  const el = mdFindSection(box, where);
  out.finds.push(el ? (el.dataset.h || 'page ' + el.dataset.page) : null);
}}
for (const [k, v] of Object.entries(input.docs)) {{
  try {{ out.docs[k] = mdToHTML(v); }} catch (e) {{ out.docs[k] = 'THROWS ' + e.message; }}
}}
document.getElementById('out').textContent = JSON.stringify(out);
</script>""", encoding="utf-8")
    run = subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={tmp_path / 'profile'}",
                          "--allow-file-access-from-files", "--dump-dom", page.as_uri()],
                         capture_output=True, encoding="utf-8", timeout=120)
    match = re.search(r'<pre id="out">(.*?)</pre>', run.stdout, re.S)
    assert match, f"the page did not run: {run.stderr[-400:]}"
    return json.loads(html.unescape(match.group(1)))


CASES = {
    "escape": 'Hello <script>alert(1)</script> & "quoted" <img src=x onerror=alert(1)>\n',
    "links": "[ok](https://a.b/c?x=1&y=2) [bad](javascript:alert(1)) [rel](AGENTS.md) see https://jlcpcb.com/capabilities. and (https://x.y/z).",
    "inline": "A **bold** and *italic* and `co<de>` and 2*3*4 and snake_case_name and a_b",
    "headings": '# Title\n## 19.3.2 Rule Priorities\n### [17] Impedance\n#### 1.3.3.1 Docked Mode\n## " onmouseover="x\n',
    "lists": "- a\n  - b\n  - c\n- d\n\n1. one\nwrapped\n2. two\n\n*Figure*\n\n5. five\n6. six\n",
    "table": "## T\n| Item | Value |\n|---|--:|\n| a \\| b | https://x.y/z |\n| c | <b>1</b> |\n\nafter\n",
    "blocks": "<!-- p.14 -->\n\n<!-- other\ncomment -->\n\n> Source: `x`\n> more\n\n---\n\n```\n<b>raw</b>\n```\n",
    "doc": "# AD20 Essentials - Module 19: PCB Rules\n\n<!-- p.187 -->\n\n## 19.3 Rules\n\n### 19.3.2 Rule Priorities\n\ntext\n\n"
           "## Traces and spacing\n\ntext\n\n## [17] Calculating Characteristic Impedance and Trace Width\n",
}


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    docs = {p.relative_to(REFERENCE).as_posix(): p.read_text(encoding="utf-8") for p in REFERENCE.rglob("*.md")
            if p.name not in ("AGENTS.md", "README.md")}
    finds = [["doc", w] for w in ("§ 19.3.2 Rule Priorities", "19.3.2", "§ [17] Calculating Characteristic Impedance and Trace Width", "[17]",
                                  "§ Traces and spacing", "traces and spacing", "Module 19, PCB Rules", "(PDF p.187)", "p.187", "§ No such heading", "")]
    return run_in_browser(tmp_path_factory.mktemp("md"), CASES, finds, docs)


def test_the_source_is_never_markup(rendered):
    out = rendered["cases"]["escape"]
    assert out == "<p>Hello &lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quoted&quot; &lt;img src=x onerror=alert(1)&gt;</p>"
    assert "<script" not in out and "<img" not in out
    assert "<b>raw</b>" not in rendered["cases"]["blocks"] and "&lt;b&gt;raw&lt;/b&gt;" in rendered["cases"]["blocks"]
    assert "<b>1</b>" not in rendered["cases"]["table"]


def test_only_http_addresses_become_links(rendered):
    out = rendered["cases"]["links"]
    assert '<a href="https://a.b/c?x=1&amp;y=2" target="_blank" rel="noopener noreferrer">ok</a>' in out
    assert "javascript" not in re.findall(r'href="([^"]*)"', out) and not any(h.startswith("javascript") for h in re.findall(r'href="([^"]*)"', out))
    assert "<a " not in out.split("[rel]")[0].split("bad")[1] if "[rel]" in out else True
    assert re.findall(r'href="([^"]*)"', out) == ["https://a.b/c?x=1&amp;y=2", "https://jlcpcb.com/capabilities", "https://x.y/z"]
    assert "capabilities</a>." in out and "z</a>)." in out, "a full stop or bracket after an address is not part of it"


def test_inline_marks(rendered):
    out = rendered["cases"]["inline"]
    assert "<strong>bold</strong>" in out and "<em>italic</em>" in out and "<code>co&lt;de&gt;</code>" in out
    assert "2*3*4" in out and "snake_case_name" in out and "a_b" in out, "a multiplication sign and underscores are text"


def test_headings_carry_their_text_for_citations(rendered):
    out = rendered["cases"]["headings"]
    assert '<h3 class="md-h1" data-h="Title">Title</h3>' in out
    assert '<h4 class="md-h2" data-h="19.3.2 Rule Priorities">19.3.2 Rule Priorities</h4>' in out
    assert 'data-h="[17] Impedance"' in out and '<h6 class="md-h4" data-h="1.3.3.1 Docked Mode">' in out
    assert 'data-h="&quot; onmouseover=&quot;x"' in out, "a heading cannot break out of its attribute"


def test_lists_nest_wrap_and_keep_their_numbers(rendered):
    out = rendered["cases"]["lists"]
    assert "<ul><li>a<ul><li>b</li><li>c</li></ul></li><li>d</li></ul>" in out
    assert "<ol><li>one wrapped</li><li>two</li></ol>" in out, "a hard-wrapped item is one item"
    assert '<ol start="5"><li>five</li><li>six</li></ol>' in out, "numbering that continues after a figure keeps its number"


def test_a_table_is_a_table(rendered):
    out = rendered["cases"]["table"]
    assert out.count("<table") == 1 and out.count("<tr>") == 3 and "<th>Item</th>" in out and '<th class="a-right">Value</th>' in out
    assert "<td>a | b</td>" in out and '<td class="a-right"><a href="https://x.y/z"' in out
    assert out.endswith("<p>after</p>")


def test_page_markers_quotes_rules_and_code(rendered):
    out = rendered["cases"]["blocks"]
    assert '<div class="md-page" data-page="14"><span>Page 14</span></div>' in out
    assert "comment" not in out and "<!--" not in out, "any other comment is dropped, however many lines it spans"
    assert "<blockquote><p>Source: <code>x</code> more</p></blockquote>" in out
    assert "<hr>" in out and '<pre class="md-code"><code>&lt;b&gt;raw&lt;/b&gt;</code></pre>' in out


def test_a_citation_finds_its_heading_or_page(rendered):
    assert rendered["finds"] == ["19.3.2 Rule Priorities", "19.3.2 Rule Priorities",
                                 "[17] Calculating Characteristic Impedance and Trace Width", "[17] Calculating Characteristic Impedance and Trace Width",
                                 "Traces and spacing", "Traces and spacing", "AD20 Essentials - Module 19: PCB Rules", "page 187", "page 187", None, None]


def test_every_real_reference_document_renders(rendered):
    docs = rendered["docs"]
    assert len(docs) >= 38
    for name, out in docs.items():
        text = (REFERENCE / name).read_text(encoding="utf-8")
        assert not out.startswith("THROWS"), f"{name}: {out}"
        assert "<!--" not in out and "<script" not in out, name
        assert out.count("<table") == len(re.findall(r"^\s*\|?\s*:?-{3,}:?\s*\|", text, re.M)), f"{name}: every table is drawn"
        assert out.count("<h") >= len(re.findall(r"^#{1,6} ", text, re.M)), name
        assert out.count('class="md-page"') == len(re.findall(r"^<!-- p\.\d+ -->", text, re.M)), name
