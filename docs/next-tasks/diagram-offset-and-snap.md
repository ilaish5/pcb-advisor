# Task: diagram - cursor offset when creating shapes + connectors snap to shape points

Repo `C:\Users\Public\Documents\Altium\pcb-advisor` (your cwd). Python `.venv\Scripts\python`.
Hard limits: no git, no installs, no network, no browser/GUI, do not start `pcb.py serve`. Do not touch the
real-project folder or `.venv`. Files: `ui/diagram.js`, `scripts/store.py` (only if the connector schema needs
a field), `tests/test_diagram.py`. Keep everything else working (toolbars, pan, sanitizeModel, agent edits, undo).
User photo: `docs/next-tasks/offset-and-loose-connector.jpg` (cursor "+" at one place, the new block below/right of
it; a dashed connector whose ends float in empty space).

## 1. Shape is created away from the mouse
Creating a shape (click/drag with a shape tool, double-click, paste at cursor), placing a connector end, marquee
and dragging must all use ONE conversion from client coords to diagram coords:
`pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; pt.matrixTransform(viewportGroup.getScreenCTM().inverse())`
(or the equivalent from the <svg> element's own getBoundingClientRect + current pan/zoom - NOT the mount/wrapper
rect, which now includes the left icon rail and the zoom cluster). A click-placed shape is centred on the cursor;
a drag-placed shape spans exactly from press point to release point. Must stay correct at any zoom/pan, after the
group/split resize, and with the page scrolled. Remove any other ad-hoc conversion.

## 2. Connectors attach to points on shapes and follow them
- Every shape exposes connection points: 4 side midpoints (top/right/bottom/left) - plus the 4 corners for
  rectangles. While drawing or dragging a connector end, when the pointer is within ~16 px (screen) of a shape, show
  its points; the nearest point highlights and the end SNAPS to it (magnet). Release = attached
  (`{shape, side|point}` stored), dashed preview becomes solid.
- Hovering inside a shape without a specific point -> attach to the nearest side midpoint ("floating" attach is
  also fine if it stays attached).
- Attached ends follow the shape on move/resize/undo/agent edits; elbow routes recompute.
- Selecting a connector shows its two end handles; dragging an end re-attaches it to another point, or detaches
  only when dropped clearly away from any shape (> 24 px).
- A connector drawn from empty space onto a shape attaches that end; free ends are drawn as small hollow circles so
  the user sees they are loose.
Tests: static checks for getScreenCTM/createSVGPoint (single conversion helper used by create/drag/marquee/
connector), snap radius + highlight, attached-end recompute on move; validation accepts `{shape, point}`.
Done = `.venv\Scripts\python -m pytest -q` exit 0. Report (<= 8 lines).
