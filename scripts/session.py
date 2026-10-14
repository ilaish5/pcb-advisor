"""
Conversations, and what each one remembers.

A project is a board; a session is one conversation about it. Sessions split,
the design does not: decisions.jsonl and threads.jsonl stay at project level,
so a decision taken in one conversation is visible in all of them. That is the
opposite of a chat app, and it is the point - you can open a clean conversation
about the layout without dragging 200 messages about the power supply behind
you, and without losing a single decision.

Each session carries a memory file: a small, bounded document holding what the
transcript would otherwise lose. It is NOT a summary of what was said - the
decisions are already sent in full on every turn, so restating them is waste.
It holds what nothing else records:

    the student's situation   "must fit a 30x20 mm enclosure", "budget $15"
    ruled out, and why        "no LDO: 1 W dissipated at 600 mA from 5 V"
    open promises             "agreed to check the connector's current rating"
    how they work             language, level, how much detail they want

One file per session, so deleting or exporting a conversation is a file
operation. The protocol is the folder.
"""
import datetime as dt
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspace  # noqa: E402

INDEX = "index.json"
MEMORY_SUFFIX = ".memory.md"

# Ordered by how much it would hurt to lose. When a memory will not fit even
# after the engine has been asked to compress it, sections are dropped from the
# bottom up - whole sections, never a sentence cut in half.
SECTIONS = (
    "The student's situation",
    "Ruled out, and why",
    "Open promises",
    "How they work",
)

MEMORY_TEMPLATE = """# Memory — {title}

_Rewritten by the advisor every {every} messages. You may edit it; it is yours._

""" + "\n\n".join(f"## {s}\n" for s in SECTIONS)


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- paths

def chats_dir(project=None):
    return workspace.project_dir(project) / "chats"


def index_path(project=None):
    return chats_dir(project) / INDEX


def chat_path(project, session):
    return chats_dir(project) / f"{_safe(session)}.jsonl"


def memory_path(project, session):
    return chats_dir(project) / f"{_safe(session)}{MEMORY_SUFFIX}"


def _safe(session):
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(session or "")).strip("-.") or "session"


# ---------------------------------------------------------------- index

def load_index(project=None):
    path = index_path(project)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_index(project, rows):
    path = index_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def list_all(project=None):
    """Every conversation, newest activity first, with live message counts and the last thing said."""
    rows = []
    for row in load_index(project):
        path = chat_path(project, row["id"])
        row = dict(row)
        row["messages"], row["last"] = _scan(path)
        row["exists"] = path.exists()
        rows.append(row)
    rows.sort(key=lambda r: r.get("updated", ""), reverse=True)
    return rows


def _scan(path):
    """(message count, last) in one pass. `last` is what the conversation list shows under the title:
    {role, text} of the newest message someone actually said (not a context card, an error or the
    server's note of a decision), cut to one line, or None."""
    if not path.exists():
        return 0, None
    count, last = 0, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = rec.get("text")
        if rec.get("role") in ("user", "agent") and isinstance(text, str) and text.strip() \
                and not rec.get("error") and not rec.get("decision"):
            last = {"role": rec["role"], "text": " ".join(text.split())[:200]}
    return count, last


def _count(path):
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


# ---------------------------------------------------------------- lifecycle

def create(project=None, title=None, anchor=None, sid=None):
    """A new conversation. The id is a timestamp so the folder sorts by itself.
    `anchor` (a refdes or a sheet id) makes it a part conversation; `sid` forces the id."""
    rows = load_index(project)
    base = _safe(sid) if sid else dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    sid, n = base, 2
    taken = {r["id"] for r in rows}
    while sid in taken or chat_path(project, sid).exists():
        sid, n = f"{base}-{n}", n + 1

    chat_path(project, sid).parent.mkdir(parents=True, exist_ok=True)
    chat_path(project, sid).touch()
    write_memory(project, sid, MEMORY_TEMPLATE.format(
        title=title or sid, every=workspace.get("agent.memory_every", 10)))

    row = {"id": sid, "title": title or "New conversation",
           "created": now(), "updated": now(), "compacted_at": 0}
    if anchor:
        row["anchor"] = anchor
    rows.append(row)
    save_index(project, rows)
    return sid


def current(project=None, session=None):
    """The session to use: the one asked for, else the most recent, else a new one."""
    if session:
        sid = _safe(session)
        if chat_path(project, sid).exists():
            return sid
    rows = list_all(project)
    if rows:
        return rows[0]["id"]
    return create(project, title="First conversation")


def touch(project, session, **fields):
    rows = load_index(project)
    for row in rows:
        if row["id"] == session:
            row.update(fields)
            row["updated"] = now()
            save_index(project, rows)
            return row
    row = {"id": session, "title": fields.get("title", "New conversation"),
           "created": now(), "updated": now(), "compacted_at": 0, **fields}
    rows.append(row)
    save_index(project, rows)
    return row


def rename(project, session, title):
    return touch(project, session, title=title)


def delete(project, session):
    sid = _safe(session)
    chat_path(project, sid).unlink(missing_ok=True)
    memory_path(project, sid).unlink(missing_ok=True)
    save_index(project, [r for r in load_index(project) if r["id"] != sid])
    return sid


# ---------------------------------------------------------------- messages

def load_chat(project, session):
    path = chat_path(project, session)
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(project, session, record):
    """Append-only, like every log here. The server is the only caller."""
    path = chat_path(project, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    fields = {}
    # the first thing the student says names the conversation, like a chat app
    row = next((r for r in load_index(project) if r["id"] == session), {})
    if record.get("role") == "user" and row.get("title") in (None, "", "New conversation"):
        fields["title"] = _title_from(record.get("text", ""))
    touch(project, session, **fields)
    return path


def _title_from(text):
    one = " ".join(str(text).split())[:48].strip()
    return one or "New conversation"


# ---------------------------------------------------------------- memory

def read_memory(project, session):
    path = memory_path(project, session)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_memory(project, session, text):
    path = memory_path(project, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def due_for_compaction(project, session):
    """How many messages have landed since the memory was last rewritten."""
    row = next((r for r in load_index(project) if r["id"] == session), {})
    since = _count(chat_path(project, session)) - int(row.get("compacted_at", 0))
    every = int(workspace.get("agent.memory_every", 10))
    return since >= every, since


def messages_since_compaction(project, session):
    row = next((r for r in load_index(project) if r["id"] == session), {})
    return load_chat(project, session)[int(row.get("compacted_at", 0)):]


def mark_compacted(project, session):
    return touch(project, session, compacted_at=_count(chat_path(project, session)))


def normalize(text, title=None, every=None):
    """Rebuild the file from the sections we recognise.

    An engine sometimes narrates before or after the document ("Here is the
    updated memory, 443 characters..."). Parsing for our own headings and
    reassembling means that chatter is dropped by construction rather than
    counted against the limit and pushing real content out.
    """
    head = MEMORY_TEMPLATE.split("## ")[0].format(
        title=title or "this conversation",
        every=every or workspace.get("agent.memory_every", 10))

    found = {}
    current_section = None
    for line in (text or "").splitlines():
        heading = re.match(r"^\s*#{2,3}\s*(.+?)\s*$", line)
        if heading:
            name = heading.group(1)
            current_section = next(
                (s for s in SECTIONS if s.lower() == name.lower()), None)
            continue
        if current_section is None or not line.strip():
            continue
        marked = re.match(r"^\s*[-*\u2022]\s*(.+)$", line)
        entry = (marked.group(1) if marked else line).strip()
        if entry:
            found.setdefault(current_section, {"bullets": [], "loose": []})[
                "bullets" if marked else "loose"].append(f"- {entry}")

    out = [head.rstrip(), ""]
    for name in SECTIONS:                       # always all four, in order
        out.append(f"## {name}")
        got = found.get(name) or {}
        # a line without a bullet marker is trailing chatter when real bullets
        # exist, and the section's only content when they do not
        out.extend(got.get("bullets") or got.get("loose") or [])
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def fit(text, limit=None):
    """Last resort only - the engine gets two chances to compress first.

    Degrade in whole units, never mid-sentence: drop the least costly sections,
    then drop whole bullets off the end of what is left. Keep at least the first
    section, because an empty memory is worse than a short one."""
    limit = int(limit or workspace.get("agent.memory_max_chars", 2000))
    text = text.rstrip() + "\n"
    if len(text) <= limit:
        return text, False

    head, chunks = _split_sections(text)
    while len(chunks) > 1 and len("".join([head] + [c for _, c in chunks])) > limit:
        chunks.pop()                      # the least costly section goes first

    out = "".join([head] + [c for _, c in chunks]).rstrip() + "\n"

    # Drop whole BULLETS off the end, never a heading. Taking the last line
    # blindly ate the heading too, so a file that overflowed by a little came
    # back as a header and nothing else - the next rewrite then had no structure
    # to merge into and the section was simply gone.
    while len(out) > limit:
        lines = out.rstrip().split("\n")
        bullets = [i for i, l in enumerate(lines) if l.lstrip().startswith("- ")]
        if not bullets:
            break
        del lines[bullets[-1]]
        out = "\n".join(lines).rstrip() + "\n"

    if len(out) > limit:
        # One bullet longer than the entire budget. Nothing is left to drop in
        # whole units, so this is the single place a sentence is cut - and it is
        # marked, so whoever reads it next can see that it was.
        out = out[:max(limit - 2, 1)].rstrip() + "…\n"
    return out, True


def _split_sections(text):
    parts = re.split(r"(?m)^(## .*)$", text)
    head = parts[0]
    chunks = []
    for i in range(1, len(parts), 2):
        chunks.append((parts[i], parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")))
    # keep the authored order, so dropping from the end drops the least costly
    order = {f"## {s}": i for i, s in enumerate(SECTIONS)}
    chunks.sort(key=lambda c: order.get(c[0].strip(), len(SECTIONS)))
    return head, chunks


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    proj = sys.argv[2] if len(sys.argv) > 2 else workspace.default_project()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "new":
        print(create(proj))
    elif cmd == "memory":
        print(read_memory(proj, current(proj)))
    else:
        for r in list_all(proj):
            due, since = due_for_compaction(proj, r["id"])
            print(f"{r['id']:20} {r['messages']:>4} msgs  "
                  f"{'compact due' if due else f'{since} since compaction':16}  {r['title']}")
