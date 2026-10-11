"""
Tests for scripts/jlc.py:
- Parsed fields from recorded JLC response shape
- Disk cache hit on second call (transport called once)
- TTL expiry re-triggers transport
- Network / HTTP errors raise JLCError
- Alternatives ordering (Basic/Preferred first) and exclusion (current code, out-of-stock, package mismatch)
"""
import time
import pytest

import jlc


def _sample_item(code="C2829308", mpn="STM32G0B1KET6", brand="STMicroelectronics",
                 package="LQFP-32(7x7)", stock=42, lib_type="expand", preferred=False,
                 prices=None, access_id="8588894524206276608", url="https://lcsc.com/doc.pdf"):
    return {
        "componentCode": code,
        "componentModelEn": mpn,
        "componentBrandEn": brand,
        "componentSpecificationEn": package,
        "describe": f"{brand} {mpn} {package}",
        "stockCount": stock,
        "componentPrices": prices or [
            {"startNumber": 1, "endNumber": 9, "productPrice": 6.5},
            {"startNumber": 10, "endNumber": 99, "productPrice": 5.8},
            {"startNumber": 100, "endNumber": -1, "productPrice": 5.2},
        ],
        "componentLibraryType": lib_type,
        "preferredComponentFlag": preferred,
        "dataManualFileAccessId": access_id,
        "dataManualUrl": url,
    }


def _response_envelope(items):
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "componentPageInfo": {
                "list": items
            }
        }
    }


def test_jlc_fields_parsed_correctly(home):
    raw = _response_envelope([_sample_item()])

    def fake_transport(url, body, **kw):
        return raw

    res = jlc.search("STM32G0B1KET6", transport=fake_transport)
    assert len(res) == 1
    p = res[0]
    assert p["code"] == "C2829308"
    assert p["mpn"] == "STM32G0B1KET6"
    assert p["manufacturer"] == "STMicroelectronics"
    assert p["package"] == "LQFP-32(7x7)"
    assert p["stock"] == 42
    assert p["library_type"] == "Extended"
    assert "https://jlcpcb.com/api/file/downloadByFileSystemAccessId/8588894524206276608" in p["datasheet_url"]
    assert p["exact"] is True
    assert len(p["price_breaks"]) == 3
    assert p["price_breaks"][0] == {"min": 1, "max": 9, "price": 6.5}
    assert p["price_breaks"][1] == {"min": 10, "max": 99, "price": 5.8}
    assert p["price_breaks"][2] == {"min": 100, "max": -1, "price": 5.2}
    assert "checked_at" in p


def test_jlc_part_library_types(home):
    items = [
        _sample_item(code="C1", mpn="PART-BASIC", lib_type="base", preferred=False),
        _sample_item(code="C2", mpn="PART-PREF", lib_type="expand", preferred=True),
        _sample_item(code="C3", mpn="PART-EXT", lib_type="expand", preferred=False),
    ]

    def fake_transport(url, body, **kw):
        return _response_envelope(items)

    p1 = jlc.part("PART-BASIC", transport=fake_transport)
    assert p1["library_type"] == "Basic"
    assert p1["exact"] is True

    p2 = jlc.part("PART-PREF", transport=fake_transport)
    assert p2["library_type"] == "Preferred"

    p3 = jlc.part("PART-EXT", transport=fake_transport)
    assert p3["library_type"] == "Extended"


def test_jlc_cache_hit_on_second_call(home):
    calls = []

    def counting_transport(url, body, **kw):
        calls.append(body)
        return _response_envelope([_sample_item(code="C_CACHE", mpn="CACHE-TEST")])

    res1 = jlc.search("CACHE-TEST", transport=counting_transport)
    assert len(calls) == 1
    assert res1[0]["code"] == "C_CACHE"

    # Second call should hit disk cache and NOT call transport
    res2 = jlc.search("CACHE-TEST", transport=counting_transport)
    assert len(calls) == 1
    assert res2[0]["code"] == "C_CACHE"


def test_jlc_cache_ttl_expiry(home, monkeypatch):
    calls = []
    fake_time = [1000000.0]

    monkeypatch.setattr(time, "time", lambda: fake_time[0])

    def counting_transport(url, body, **kw):
        calls.append(body)
        return _response_envelope([_sample_item(code="C_EXP", mpn="EXP-TEST")])

    jlc.search("EXP-TEST", transport=counting_transport)
    assert len(calls) == 1

    # Advance time beyond 6 hours (6 * 3600 = 21600 seconds)
    fake_time[0] += 25000.0

    # Next call should detect expired cache and re-call transport
    jlc.search("EXP-TEST", transport=counting_transport)
    assert len(calls) == 2


def test_jlc_transport_error_raises_jlc_error(home):
    def failing_transport(url, body, **kw):
        raise ConnectionResetError("Connection lost")

    with pytest.raises(jlc.JLCError) as exc_info:
        jlc.search("FAIL-TEST", transport=failing_transport)
    assert "Connection lost" in str(exc_info.value) or "Transport failed" in str(exc_info.value)

    def bad_code_transport(url, body, **kw):
        return {"code": 500, "msg": "Internal Server Error"}

    with pytest.raises(jlc.JLCError):
        jlc.search("FAIL-CODE", transport=bad_code_transport)


def test_jlc_alternatives_ordering_and_exclusion(home):
    all_hits = [
        # Current part: should be excluded by code and mpn
        _sample_item(code="C1001", mpn="CAP-ORIG", package="0603", stock=1000, lib_type="expand"),
        # Extended part matching package
        _sample_item(code="C1002", mpn="CAP-EXT-STOCK", package="0603", stock=200, lib_type="expand", preferred=False),
        # Basic part matching package
        _sample_item(code="C1003", mpn="CAP-BASIC-STOCK", package="0603", stock=500, lib_type="base", preferred=False),
        # Preferred part matching package
        _sample_item(code="C1004", mpn="CAP-PREF-STOCK", package="0603", stock=400, lib_type="expand", preferred=True),
        # Part with mismatching package: should be excluded
        _sample_item(code="C1005", mpn="CAP-0805", package="0805", stock=800, lib_type="base"),
        # Part with 0 stock: should be excluded
        _sample_item(code="C1006", mpn="CAP-NOSTOCK", package="0603", stock=0, lib_type="base"),
    ]

    def transport(url, body, **kw):
        return _response_envelope(all_hits)

    line = {
        "key": "C1",
        "code": "C1001",
        "mpn": "CAP-ORIG",
        "package": "0603",
        "value": "100nF",
    }

    alts = jlc.alternatives(line, n=5, transport=transport)

    codes = [a["code"] for a in alts]
    # Current code C1001 excluded
    assert "C1001" not in codes
    # Different package C1005 excluded
    assert "C1005" not in codes
    # Zero stock C1006 excluded
    assert "C1006" not in codes

    # Basic/Preferred must come first before Extended
    # C1003 is Basic, C1004 is Preferred, C1002 is Extended
    assert codes[0] in ("C1003", "C1004")
    assert codes[1] in ("C1003", "C1004")
    assert codes[2] == "C1002"
