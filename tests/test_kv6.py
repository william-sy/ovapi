"""Tests for the KV6 live vehicle tracking module.

These are plain unit tests with no Home Assistant fixtures needed — kv6.py's
parsing/matching/expiry logic is pure Python by design, independent of the
thread/socket plumbing around it (see kv6.py's KV6LiveTracker._run).
"""
from __future__ import annotations

import time

import pytest

from custom_components.ovapi.kv6 import (
    KV6LiveTracker,
    KV6RawFix,
    decompress_kv6_payload,
    parse_kv6_message,
    rd_to_wgs84,
)

# Real KV6 messages captured from the live NDOVloket feed during development.
# Same BISON schema, two different serializations: KEOLIS uses a default
# namespace with no tag prefix, CXX prefixes every tag with "tmi8:". Both
# must parse identically.
KEOLIS_PAYLOAD_NO_PREFIX = (
    '<?xml version="1.0" encoding="utf-8"?><VV_TM_PUSH '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
    'xmlns="http://bison.connekt.nl/tmi8/kv6/msg">'
    "<SubscriberID>SYNTUS</SubscriberID><Version>BISON 8.1.2.0</Version>"
    "<DossierName>KV6posinfo</DossierName>"
    "<Timestamp>2026-07-04T20:47:08.9590298+02:00</Timestamp>"
    "<KV6posinfo><ONSTOP>"
    "<dataownercode>KEOLIS</dataownercode>"
    "<lineplanningnumber>5302</lineplanningnumber>"
    "<operatingday>2026-07-04</operatingday>"
    "<journeynumber>45780</journeynumber>"
    "<reinforcementnumber>0</reinforcementnumber>"
    "<userstopcode>50100410</userstopcode>"
    "<passagesequencenumber>0</passagesequencenumber>"
    "<timestamp>2026-07-04T20:47:07.946+02:00</timestamp>"
    "<source>VEHICLE</source><vehiclenumber>1017</vehiclenumber>"
    "<punctuality>0</punctuality><rd-x>138559</rd-x><rd-y>455934</rd-y>"
    "</ONSTOP></KV6posinfo></VV_TM_PUSH>"
)

CXX_PAYLOAD_TMI8_PREFIX = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<tmi8:VV_TM_PUSH xmlns:tmi8="http://bison.connekt.nl/tmi8/kv6/msg">'
    "<tmi8:SubscriberID>KV6OPG</tmi8:SubscriberID>"
    "<tmi8:Version>BISON 8.1.2.0</tmi8:Version>"
    "<tmi8:DossierName>KV6posinfo</tmi8:DossierName>"
    "<tmi8:Timestamp>2026-07-04T20:47:08+02:00</tmi8:Timestamp>"
    "<tmi8:KV6posinfo><tmi8:ONROUTE>"
    "<tmi8:dataownercode>CXX</tmi8:dataownercode>"
    "<tmi8:lineplanningnumber>U028</tmi8:lineplanningnumber>"
    "<tmi8:operatingday>2026-07-04</tmi8:operatingday>"
    "<tmi8:journeynumber>6135</tmi8:journeynumber>"
    "<tmi8:reinforcementnumber>0</tmi8:reinforcementnumber>"
    "<tmi8:omloopnumber>80801</tmi8:omloopnumber>"
    "<tmi8:userstopcode>50000203</tmi8:userstopcode>"
    "<tmi8:passagesequencenumber>0</tmi8:passagesequencenumber>"
    "<tmi8:timestamp>2026-07-04T20:47:07+02:00</tmi8:timestamp>"
    "<tmi8:source>VEHICLE</tmi8:source>"
    "<tmi8:vehiclenumber>9848</tmi8:vehiclenumber>"
    "<tmi8:punctuality>-31</tmi8:punctuality>"
    "<tmi8:distancesincelastuserstop>541</tmi8:distancesincelastuserstop>"
    "<tmi8:rd-x>136107</tmi8:rd-x><tmi8:rd-y>456101</tmi8:rd-y>"
    "</tmi8:ONROUTE></tmi8:KV6posinfo></tmi8:VV_TM_PUSH>"
)

# A DEPARTURE message with no rd-x/rd-y at all — common; a bus that hasn't
# started moving yet reports events without a position fix.
NO_POSITION_PAYLOAD = (
    '<?xml version="1.0" encoding="utf-8"?><VV_TM_PUSH '
    'xmlns="http://bison.connekt.nl/tmi8/kv6/msg">'
    "<KV6posinfo><DEPARTURE>"
    "<dataownercode>ARR</dataownercode>"
    "<lineplanningnumber>22704</lineplanningnumber>"
    "<operatingday>2026-07-04</operatingday>"
    "<journeynumber>6858</journeynumber>"
    "<userstopcode>63145620</userstopcode>"
    "<timestamp>2026-07-04T21:52:00+02:00</timestamp>"
    "<source>VEHICLE</source><punctuality>0</punctuality>"
    "</DEPARTURE></KV6posinfo></VV_TM_PUSH>"
)


def test_parse_kv6_message_no_namespace_prefix() -> None:
    """A default-namespace (unprefixed) payload parses correctly."""
    fixes = parse_kv6_message(KEOLIS_PAYLOAD_NO_PREFIX)
    assert len(fixes) == 1
    fix = fixes[0]
    assert fix.data_owner_code == "KEOLIS"
    assert fix.line_planning_number == "5302"
    assert fix.journey_number == "45780"
    assert fix.operation_date == "2026-07-04"
    assert fix.message_type == "ONSTOP"
    assert fix.fields["rd-x"] == "138559"
    assert fix.fields["rd-y"] == "455934"


def test_parse_kv6_message_tmi8_prefix() -> None:
    """A tmi8:-prefixed payload for the identical schema parses identically."""
    fixes = parse_kv6_message(CXX_PAYLOAD_TMI8_PREFIX)
    assert len(fixes) == 1
    fix = fixes[0]
    assert fix.data_owner_code == "CXX"
    assert fix.line_planning_number == "U028"
    assert fix.journey_number == "6135"
    assert fix.message_type == "ONROUTE"
    assert fix.fields["vehiclenumber"] == "9848"
    assert fix.fields["omloopnumber"] == "80801"


def test_parse_kv6_message_skips_messages_without_position() -> None:
    """A message with no rd-x/rd-y (vehicle not yet moving) is skipped."""
    fixes = parse_kv6_message(NO_POSITION_PAYLOAD)
    assert fixes == []


def test_parse_kv6_message_skips_messages_missing_required_fields() -> None:
    """A message missing any of owner/line/journey/day is skipped."""
    payload = (
        '<?xml version="1.0" encoding="utf-8"?><VV_TM_PUSH '
        'xmlns="http://bison.connekt.nl/tmi8/kv6/msg">'
        "<KV6posinfo><ONROUTE>"
        "<dataownercode>ARR</dataownercode>"
        "<rd-x>136107</rd-x><rd-y>456101</rd-y>"
        "</ONROUTE></KV6posinfo></VV_TM_PUSH>"
    )
    assert parse_kv6_message(payload) == []


def test_decompress_kv6_payload_roundtrip() -> None:
    """gzip+utf-8-sig decoding roundtrips, including a leading BOM."""
    import gzip

    original = "﻿<xml>hello</xml>"
    compressed = gzip.compress(original.encode("utf-8-sig"))
    assert decompress_kv6_payload(compressed) == original


@pytest.mark.parametrize(
    ("x", "y", "expected_lat", "expected_lon"),
    [
        # RD origin (Amersfoort) — the standard reference point for this formula.
        (155000.0, 463000.0, 52.155172, 5.387204),
        # A real captured KV6 fix near Rosmalen, cross-checked against pyproj's
        # full PROJ transform (agreement was ~0.3m across this and several
        # other real captured points before choosing this formula).
        (149247.0, 412224.0, 51.698757, 5.303985),
    ],
)
def test_rd_to_wgs84_accuracy(
    x: float, y: float, expected_lat: float, expected_lon: float
) -> None:
    """RD->WGS84 conversion matches known reference points within ~1m."""
    lat, lon = rd_to_wgs84(x, y)
    assert lat == pytest.approx(expected_lat, abs=1e-5)
    assert lon == pytest.approx(expected_lon, abs=1e-5)


class _FakeHass:
    """Minimal stand-in so KV6LiveTracker can be constructed without real HA."""


def _make_fix(
    data_owner_code: str,
    line_planning_number: str,
    journey_number: str,
    rd_x: str = "136107",
    rd_y: str = "456101",
) -> KV6RawFix:
    return KV6RawFix(
        data_owner_code=data_owner_code,
        line_planning_number=line_planning_number,
        journey_number=journey_number,
        operation_date="2026-07-04",
        message_type="ONROUTE",
        fields={"rd-x": rd_x, "rd-y": rd_y, "punctuality": "0"},
    )


def test_ingest_keys_by_line_planning_number_not_journey_number_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the Arriva cross-concession collision bug.

    A national operator (e.g. Arriva, data owner "ARR") reuses journey
    numbers across unrelated regional concessions. Two real vehicles on
    different lines can share the same (data_owner_code, journey_number) on
    the same day — matching on that pair alone silently overwrites one
    vehicle's position with the other's, putting a bus tens of km from where
    it actually is. The key must include line_planning_number too.
    """
    monkeypatch.setattr("custom_components.ovapi.kv6.dispatcher_send", lambda *a, **k: None)
    tracker = KV6LiveTracker(_FakeHass(), "test-entry")  # type: ignore[arg-type]

    fix_line_a = _make_fix("ARR", "22704", "6856", rd_x="149247", rd_y="412224")
    fix_line_b = _make_fix("ARR", "99999", "6856", rd_x="136107", rd_y="456101")

    tracker._ingest(fix_line_a)  # noqa: SLF001 - exercising internal ingest directly, no socket needed
    tracker._ingest(fix_line_b)  # noqa: SLF001

    position_a = tracker.get_position("ARR", "22704", "6856", "2026-07-04")
    position_b = tracker.get_position("ARR", "99999", "6856", "2026-07-04")

    assert position_a is not None
    assert position_b is not None
    assert (position_a.latitude, position_a.longitude) != (position_b.latitude, position_b.longitude)


def test_get_position_returns_none_when_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fix older than VEHICLE_MAX_AGE is treated as gone."""
    monkeypatch.setattr("custom_components.ovapi.kv6.dispatcher_send", lambda *a, **k: None)
    tracker = KV6LiveTracker(_FakeHass(), "test-entry")  # type: ignore[arg-type]
    tracker._ingest(_make_fix("ARR", "22704", "6856"))  # noqa: SLF001

    fresh = tracker.get_position("ARR", "22704", "6856", "2026-07-04")
    assert fresh is not None

    # Backdate the stored fix past VEHICLE_MAX_AGE without waiting in real time.
    key = ("ARR", "22704", "6856", "2026-07-04")
    stale = tracker._positions[key]  # noqa: SLF001
    object.__setattr__(stale, "timestamp", time.time() - 999)

    assert tracker.get_position("ARR", "22704", "6856", "2026-07-04") is None


def test_get_position_missing_key_parts_returns_none() -> None:
    """Any missing key component (e.g. no journey number yet) returns None."""
    tracker = KV6LiveTracker(_FakeHass(), "test-entry")  # type: ignore[arg-type]
    assert tracker.get_position("ARR", "22704", None, "2026-07-04") is None
    assert tracker.get_position(None, None, None, None) is None


def test_update_subscriptions_is_a_plain_setter() -> None:
    """update_subscriptions has no side effects beyond storing the set."""
    tracker = KV6LiveTracker(_FakeHass(), "test-entry")  # type: ignore[arg-type]
    tracker.update_subscriptions({"ARR", "GVB"})
    assert tracker._wanted_owners == {"ARR", "GVB"}  # noqa: SLF001
    tracker.update_subscriptions(set())
    assert tracker._wanted_owners == set()  # noqa: SLF001
