"""Crops the raw captures (run capture_ui.py for the app views; the Altium window shots come from the altium MCP screenshot tool) into the images the deck uses. Pixels are not changed, only cut; the raw files are not kept in git."""
from pathlib import Path
from PIL import Image

IMG = Path(__file__).resolve().parent / "img"
CENTER = (464, 16, 2444, 1984)          # the main panel of the app at 2x
CUTS = {
    "ui_live_idea.png": ("_raw_live_idea.png", (514, 940, 2394, 1760)),
    "ui_live_bom.png": ("_raw_live_bom.png", (464, 16, 2444, 876)),
    "ui_live_library.png": ("_raw_live_library.png", (464, 16, 2444, 876)),
    "ui_live_schematic.png": ("_raw_live_sch.png", (560, 720, 1780, 1240)),
    "ui_live_outputs_blocked.png": ("_raw_live_outputs.png", (464, 16, 2444, 800)),
    "ui_dark_outputs.png": ("_raw_dark_outputs.png", (464, 16, 2444, 900)),
    "ui_dark_dfm.png": ("_raw_dark_checks.png", CENTER),
    "ui_blink_chat.png": ("_raw_blink_pcb.png", (2464, 250, 3180, 1700)),
    "ui_blink_route.png": ("_raw_blink_pcb.png", (2464, 1022, 3180, 1700)),
    "ui_live_layout.png": ("_raw_live_pcb.png", CENTER),
}
if __name__ == "__main__":
    for out, (src, box) in CUTS.items():
        Image.open(IMG / src).crop(box).save(IMG / out, optimize=True)
        print(out)
