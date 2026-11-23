# Testing

The suite (`tests/`, about 3400 pytest tests) is split by what a test needs.

| Marker    | Needs                                                   | Where it runs                          |
|-----------|---------------------------------------------------------|----------------------------------------|
| (none)    | Python, node (UI tests), git                            | CI on every push and pull request      |
| `windows` | Windows itself (Windows API, case-insensitive folders)  | the Windows PC                         |
| `altium`  | a live Altium Designer answering the bridge             | the Windows PC with Altium, `PCB_ADVISOR_ALTIUM=1` |

`tests/conftest.py` skips `windows` tests where `os.name != "nt"`, and `altium` tests unless `PCB_ADVISOR_ALTIUM=1`,
each with the reason. Nothing that passes on Linux is marked.

## CI (portable set)

```bash
python -m pytest -q -rfE -m "not windows and not altium" -o faulthandler_timeout=600 < /dev/null
```

Runs from `.github/workflows/tests.yml` on ubuntu-latest, Python 3.12, node LTS, on every push and pull request.
Results: the repository's **Actions** tab, workflow **tests**; the junit xml is the run's `pytest-junit` artifact.

## Windows PC (platform set)

```bat
python -m pytest -q -m "windows or altium" < NUL
```

With Altium open, `set PCB_ADVISOR_ALTIUM=1` first, or the `altium` tests are skipped.
