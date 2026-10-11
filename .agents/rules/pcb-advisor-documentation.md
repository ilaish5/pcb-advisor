# DOCUMENTS
You read from `shared/datasheets/` and `projects/<name>/sources/`. Each document has a `.json` sidecar (url,
sha256, bytes) and may have an extracted `.txt`.

- Every factual claim about a part cites a source with `{{src:file|locator}}`.
- A quoted sentence must pass `python scripts/sources.py verify <file> "<quote>"` before you show it.
- To add a datasheet, run `python scripts/sources.py get <project> <url> [name]`. It records the url and
  sha256, which is what makes it citable. Do not download with curl.
- Stock and price are never stated from memory. They always come from `check_availability.py`, with a time.
- Trace widths come from `scripts/trace_width.py`. Never estimate one.
