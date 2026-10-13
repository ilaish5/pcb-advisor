"""Idea-stage benchmark detectors: read requirements.md of a fixture, apply scripts/checks/idea.py."""
from bench.detectors import register
from checks import idea


@register("mcu_no_usb_dfu")
def usb_flash_without_rom_dfu(fixture_dir, incident):
    p = fixture_dir / "requirements.md"
    if not p.exists():
        return []
    return [{"code": f["id"], "refs": f["refs"], "message": f["message"],
             "source": "checks.idea.check_flashing_plan"}
            for f in idea.check_flashing_plan(p.read_text(encoding="utf-8"))]
