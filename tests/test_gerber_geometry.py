"""R2 / W37: mask web, copper to NPTH and copper to routed edge, found from the Gerber / Excellon text with the position; clean twins stay quiet."""
import gerber_geometry as gg


def G(body, aps):
    head = ["%FSLAX46Y46*%", "%MOMM*%", "%LPD*%"] + [f"%ADD{k}{v}*%" for k, v in aps.items()]
    return "\n".join(head + body + ["M02*"]) + "\n"


def xy(x, y):
    return f"X{round(x * 1e6)}Y{round(y * 1e6)}"


OUTLINE = G(["D10*", xy(0, 0) + "D02*", xy(50, 0) + "D01*", xy(50, 40) + "D01*", xy(0, 40) + "D01*", xy(0, 0) + "D01*"], {"10": "C,0.100"})
NPTH = "M48\nMETRIC,TZ\nT1C3.200\n%\nG90\nG05\nT1\nX20.000Y20.000\nM30\n"


def run(mask_gap=None, npth_d=None, edge_d=None):
    cu, mk = ["D11*"], ["D11*"]
    if mask_gap is not None:
        for x in (10, 11.1 + mask_gap):
            mk.append(xy(x, 30) + "D03*")
    cu += ["D10*"]
    if npth_d is not None:
        tx = 20 + 1.6 + npth_d + 0.125
        cu += [xy(tx, 17) + "D02*", xy(tx, 23) + "D01*"]
    if edge_d is not None:
        cu += [xy(10, edge_d + 0.125) + "D02*", xy(15, edge_d + 0.125) + "D01*"]
    files = {"mask": [G(mk, {"11": "R,1.100X0.700"})], "copper": [G(cu, {"10": "C,0.250", "11": "R,1.000X0.600"})],
             "outline": [OUTLINE], "npth": [NPTH]}
    return gg.problems(files)


def test_mask_web_found_with_position_and_twin_quiet():
    msgs, _ = run(mask_gap=0.05)
    assert len(msgs) == 1 and "mask web" in msgs[0] and "X 10.5" in msgs[0]
    assert run(mask_gap=0.12)[0] == []


def test_copper_to_npth():
    msgs, _ = run(npth_d=0.1)
    assert len(msgs) == 1 and "non-plated" in msgs[0] and "X 21.8" in msgs[0] and "Y 20.00" in msgs[0]
    assert run(npth_d=0.3)[0] == []


def test_copper_to_edge_reports_the_middle_of_the_track():
    msgs, _ = run(edge_d=0.08)
    assert len(msgs) == 1 and "routed board edge" in msgs[0] and "X 12.50" in msgs[0]
    assert run(edge_d=0.3)[0] == []


def test_the_zip_description_lists_geometry_findings_without_blocking(tmp_path):
    import zipfile
    import jlc_upload
    z = tmp_path / "x_gerbers.zip"
    mk = G(["D11*", xy(10, 30) + "D03*", xy(11.15, 30) + "D03*"], {"11": "R,1.100X0.700"})
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("B.GTS", mk)
    with zipfile.ZipFile(z) as f:
        out = jlc_upload.geometry_problems(f, [{"name": "B.GTS", "group": "mask"}], [])
    assert out and out[0]["level"] == "geometry" and "mask web" in out[0]["why"]


def test_macro_aperture_is_reported_as_not_checked():
    t = "%FSLAX46Y46*%\n%MOMM*%\n%AMTHERM*1,1,1,0,0*%\n%ADD10THERM,1*%\nD10*\nX1000000Y1000000D03*\nM02*\n"
    _, skipped = gg.problems({"copper": [t], "outline": [OUTLINE]})
    assert any("macro" in s for s in skipped)
