"""Live (behaviour) harness: start the product server at a given commit, seed projects, drive the page, inject faults.

Never imports product code (A2): the product runs as a separate process from a git worktree, and everything here talks to it
over HTTP, through a real browser, or through files it writes."""
