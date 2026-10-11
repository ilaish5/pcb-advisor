"""Load and validate benchmark fixtures (scripts/bench/fixtures/NN-slug/incident.json)."""
import json
import pathlib

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
STAGES = "ABCDEF"
DETECTOR_STAGES = tuple(f"I{n}" for n in range(4, 11))


class IncidentError(ValueError):
    """A fixture is malformed; the message names the file and the key."""


def _fail(path, key, why):
    raise IncidentError(f"{path}: key '{key}' {why}")


def _is_str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def validate(data, path="incident.json", folder=None):
    """Raise IncidentError unless `data` matches the schema. Returns data."""
    if not isinstance(data, dict):
        raise IncidentError(f"{path}: top level must be an object")
    for key, typ in (("id", int), ("slug", str), ("title", str), ("question", str),
                     ("notes", str), ("target_stage", str), ("detector_stage", str)):
        if key not in data:
            _fail(path, key, "is missing")
        if not isinstance(data[key], typ) or isinstance(data[key], bool):
            _fail(path, key, f"must be {typ.__name__}")
    for key in ("pain", "state"):
        if key not in data:
            _fail(path, key, "is missing")
        if not _is_str_list(data[key]):
            _fail(path, key, "must be a list of strings")
    if data["target_stage"] not in tuple(STAGES):
        _fail(path, "target_stage", f"must be one of {', '.join(STAGES)}")
    if data["detector_stage"] not in DETECTOR_STAGES:
        _fail(path, "detector_stage", f"must be one of {', '.join(DETECTOR_STAGES)}")
    reality = data.get("reality")
    if not isinstance(reality, dict):
        _fail(path, "reality", "is missing or not an object")
    for k in ("stage", "when"):
        if not isinstance(reality.get(k), str):
            _fail(path, f"reality.{k}", "is missing or not a string")
    if reality["stage"] not in tuple(STAGES):
        _fail(path, "reality.stage", f"must be one of {', '.join(STAGES)}")
    if not _is_str_list(reality.get("evidence")):
        _fail(path, "reality.evidence", "must be a list of strings")
    expect = data.get("expect")
    if not isinstance(expect, dict):
        _fail(path, "expect", "is missing or not an object")
    if not isinstance(expect.get("code"), str) or not expect["code"]:
        _fail(path, "expect.code", "is missing or not a non-empty string")
    if not _is_str_list(expect.get("refs")):
        _fail(path, "expect.refs", "must be a list of strings")
    kw = expect.get("keywords")
    if not isinstance(kw, list) or not all(_is_str_list(g) and g for g in kw):
        _fail(path, "expect.keywords", "must be a list of non-empty lists of strings")
    if folder is not None:
        for name in data["state"]:
            if not (pathlib.Path(folder) / name).is_file():
                _fail(path, "state", f"names '{name}', which is not in the fixture folder")
    return data


def load_one(folder):
    folder = pathlib.Path(folder)
    path = folder / "incident.json"
    if not path.is_file():
        raise IncidentError(f"{path}: file is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IncidentError(f"{path}: not valid JSON ({exc})") from exc
    validate(data, str(path), folder)
    data["_dir"] = str(folder)
    return data


def load_all(fixtures=None):
    """(incidents sorted by id, problems). A broken fixture is reported, not fatal."""
    root = pathlib.Path(fixtures) if fixtures else FIXTURES
    found, problems = [], []
    if not root.is_dir():
        return found, [f"{root}: fixtures folder not found"]
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            found.append(load_one(folder))
        except IncidentError as exc:
            problems.append(str(exc))
    found.sort(key=lambda i: i["id"])
    return found, problems
