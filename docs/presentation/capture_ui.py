"""Captures real screenshots of the running app (read-only: GET pages with ?project=&tab=/page= only).
Usage: python capture_ui.py <name>=<project>:<tab|page=x> ...   (default list below)
Needs headless Edge. The app server is not started or restarted here; it must already run on 127.0.0.1:8931.
"""
import os
import subprocess
import sys
from pathlib import Path

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUT = Path(__file__).resolve().parent / "img"
BASE = os.environ.get("ADVISOR_URL", "http://127.0.0.1:8931/")
DEFAULT = {
    "live_idea": ("Live-STM32", "tab=idea"), "live_bom": ("Live-STM32", "tab=bom"), "live_sch": ("Live-STM32", "tab=sch"),
    "live_pcb": ("Live-STM32", "tab=pcb"), "live_rules": ("Live-STM32", "tab=rules"), "live_outputs": ("Live-STM32", "tab=outputs"),
    "live_checks": ("Live-STM32", "tab=checks"), "live_library": ("Live-STM32", "page=library"),
    "dark_idea": ("Dark-sensor-LED", "tab=idea"), "dark_bom": ("Dark-sensor-LED", "tab=bom"), "dark_sch": ("Dark-sensor-LED", "tab=sch"),
    "dark_pcb": ("Dark-sensor-LED", "tab=pcb"), "dark_outputs": ("Dark-sensor-LED", "tab=outputs"), "dark_checks": ("Dark-sensor-LED", "tab=checks"),
    "blink_idea": ("Blinker-555", "tab=idea"), "blink_bom": ("Blinker-555", "tab=bom"), "blink_sch": ("Blinker-555", "tab=sch"),
    "blink_pcb": ("Blinker-555", "tab=pcb"), "blink_outputs": ("Blinker-555", "tab=outputs"), "blink_checks": ("Blinker-555", "tab=checks"),
}


def shot(name, project, query, size="1600,1000"):
    OUT.mkdir(exist_ok=True)
    dest = OUT / f"_raw_{name}.png"
    subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=10000", "--force-device-scale-factor=2",
                    f"--screenshot={dest}", f"--window-size={size}", f"{BASE}?project={project}&{query}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    return dest


if __name__ == "__main__":
    jobs = DEFAULT
    if len(sys.argv) > 1:
        jobs = {}
        for a in sys.argv[1:]:
            n, rest = a.split("=", 1)
            proj, q = rest.split(":", 1)
            jobs[n] = (proj, q)
    for n, (p, q) in jobs.items():
        print(shot(n, p, q))
