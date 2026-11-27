"""R2 / W37: the geometry check on Gerber and Excellon text in Altium's own syntax (modal coordinates, `X..Y..D02*` then a bare `D03*`
flash, macro apertures described by an AMPARAMS comment, a pour as a dark region with clear regions cut out, INCH,LZ drill files).
The text is built here, never taken from a project."""
import gerber_geometry as gg

HEAD = ["G04*", "G04 #@! TF.GenerationSoftware,Altium Limited,Altium Designer,26.8.1 (31)*", "%FSLAX24Y24*%", "%MOIN*%", "G70*", "G01*", "G75*"]
AMP = ("G04:AMPARAMS|DCode=22|XSize=44.4mil|YSize=59.1mil|CornerRadius=11.9mil|HoleSize=0mil|Usage=FLASHONLY|Rotation=0.000|XOffset=0mil|"
       "YOffset=0mil|HoleType=Round|Shape=RoundedRectangle|*")


def gerber(body, extra_head=()):
    return "\n".join(HEAD + list(extra_head) + ["%LPD*%"] + body + ["M02*"]) + "\n"


def test_mask_openings_flashed_the_altium_way_are_read():
    body = ["D21*", "X10000Y20000D02*", "D03*", "Y20454D02*", "D03*"]          # modal X, bare D03: pitch 0.0454 in over 0.0434 in openings
    t = gerber(body, ["%ADD21R,0.0532X0.0434*%"])
    p = gg.parse_layer(t)
    assert len(p["shapes"]) == 2
    msgs, skipped = gg.problems({"mask": [t]})
    assert len(msgs) == 1 and "mask web" in msgs[0] and "X 25.40" in msgs[0] and skipped == []


def test_macro_openings_use_their_amparams_size():
    body = ["D22*", "X10000Y20000D02*", "D03*", "X10532D02*", "D03*"]          # 44.4 mil wide, 53.2 mil apart: a gap of 8.8 mil
    t = gerber(body, [AMP, "%AMROUNDEDRECTD22*", "21,1,0.0444,0.0353,0,0,0.0*", "%", "%ADD22ROUNDEDRECTD22*%"])
    assert len(gg.parse_layer(t)["shapes"]) == 2
    assert gg.problems({"mask": [t]})[0] == []                               # 0.22 mm of dam: fine
    body = ["D22*", "X10000Y20000D02*", "D03*", "X10480D02*", "D03*"]          # 3.6 mil: 0.09 mm
    t = gerber(body, [AMP, "%AMROUNDEDRECTD22*", "21,1,0.0444,0.0353,0,0,0.0*", "%", "%ADD22ROUNDEDRECTD22*%"])
    assert len(gg.problems({"mask": [t]})[0]) == 1


def test_a_layer_with_no_readable_shape_is_listed_not_green():
    t = gerber(["D99*", "X10000Y20000D03*"])
    msgs, skipped = gg.problems({"mask": [t]})
    assert msgs == [] and any("no readable shape" in s for s in skipped)


def _pour(half):
    c = 5000
    return ["G36*", "X0Y0D02*", "X10000D01*", "Y10000D01*", "X0D01*", "Y0D01*", "G37*", "%LPC*%", "G36*",
            f"X{c - half}Y{c - half}D02*", f"X{c + half}D01*", f"Y{c + half}D01*", f"X{c - half}D01*", f"Y{c - half}D01*", "G37*", "%LPD*%"]


NPTH = "M48\n;Layer_Color=9474304\n;FILE_FORMAT=2:4\nINCH,LZ\n;TYPE=NON_PLATED\nT01F00S00C0.1260\n%\nT01\nX005000Y005000\nM30\n"


def test_pour_copper_around_an_npth_is_seen_through_its_clear_cutout():
    near = gerber(_pour(689) + ["%ADD10C,0.0100*%"])                           # cutout wall 0.0689 in from the hole centre; the hole is 0.063 in: 0.15 mm
    msgs, _ = gg.problems({"copper": [near], "npth": [NPTH]})
    assert len(msgs) == 1 and "non-plated" in msgs[0] and "X 12.70" in msgs[0]
    far = gerber(_pour(1000))
    assert gg.problems({"copper": [far], "npth": [NPTH]})[0] == []


def test_a_pour_over_the_hole_with_no_cutout_is_flagged():
    solid = gerber(["G36*", "X0Y0D02*", "X10000D01*", "Y10000D01*", "X0D01*", "Y0D01*", "G37*"])
    msgs, _ = gg.problems({"copper": [solid], "npth": [NPTH]})
    assert len(msgs) == 1 and "0.00 mm" in msgs[0]


def test_the_hole_size_flash_altium_writes_at_an_npth_is_not_copper_near_it():
    t = gerber(["%ADD10C,0.1260*%", "D10*", "X5000Y5000D02*", "D03*"])
    assert gg.problems({"copper": [t], "npth": [NPTH]})[0] == []


def test_copper_pad_flashed_the_altium_way_near_the_edge():
    outline = gerber(["%ADD14C,0.0059*%", "D14*", "X0Y0D02*", "Y7874D01*", "X11811D01*", "Y0D01*", "X0D01*"])
    pad_close = gerber(["%ADD21R,0.0532X0.0434*%", "D21*", "X5000Y230D02*", "D03*"])     # lower pad side 0.0013 in from the edge: 0.03 mm
    assert len(gg.problems({"copper": [pad_close], "outline": [outline]})[0]) == 1


def test_the_excellon_inch_lz_file_is_read_with_its_format():
    assert gg.parse_npth(NPTH) == [(12.7, 12.7, 0.126 * 25.4)]
    t = "M48\n;FILE_FORMAT=2:4\nINCH,LZ\nT01F00S00C0.1260\n%\nT01\nX011Y02\nM30\n"
    (x, y, d), = gg.parse_npth(t)
    assert abs(x - 27.94) < 1e-6 and abs(y - 50.8) < 1e-6            # 2:4, leading zeros kept: X011 = 01.1000 in, Y02 = 02.0000 in
    t = "M48\n;FILE_FORMAT=2:4\nINCH,LZ\nT01F00S00C0.1260\n%\nT01\nX004449Y003031\nY005669\nM30\n"
    assert [(round(a, 3), round(b, 3)) for a, b, _ in gg.parse_npth(t)] == [(11.3, 7.699), (11.3, 14.399)]
