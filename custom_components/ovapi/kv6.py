"""Live vehicle GPS position tracking via GOVI/NDOVloket's public KV6 feed.

KV6 is a separate real-time data source from the KV7/8-Turbo schedule API
this integration otherwise uses (see api.py / API_BASE_URL): it's a ZeroMQ
pub/sub stream of gzip-compressed BISON XML, published per data owner at
KV6_ENDPOINT under the topic "/{DataOwnerCode}/KV6posinfo". Vehicles report
their position, in Dutch RD coordinates, whenever they're actively driving a
trip — this module subscribes on the integration's behalf (pyzmq is sync,
not asyncio-native, hence the dedicated background thread), matches fixes
back to a specific upcoming passage, and converts RD to WGS84 for display.

This entire module is only ever imported when a user opts in via
CONF_ENABLE_LIVE_TRACKING (see __init__.py) — most installs never load it.
"""
from __future__ import annotations

import gzip
import io
import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.helpers.dispatcher import dispatcher_send

from .const import DOMAIN, KV6_ENDPOINT, KV6_RECV_TIMEOUT_MS, VEHICLE_MAX_AGE

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# RD (EPSG:28992) -> WGS84 approximate polynomial conversion, commonly known
# as the "Bonfire" formula. Verified this session against pyproj's full PROJ
# transform across the RD origin, several real captured KV6 fixes, and the
# extremes of the Dutch grid (Zeeland/Groningen) — agreement was a stable
# ~0.3m everywhere, comfortably within "good enough for a map pin." Chosen
# over depending on pyproj, which bundles the full PROJ C library plus an
# embedded geodata database for what is here a single coordinate conversion
# — real weight on constrained hardware (Raspberry Pi, HA Yellow) this
# integration needs to keep running on.
_RD_X0, _RD_Y0 = 155000.0, 463000.0
_RD_PHI0, _RD_LAM0 = 52.15517440, 5.38720621
_RD_PHI_TERMS: tuple[tuple[int, int, float], ...] = (
    (0, 1, 3235.65389), (2, 0, -32.58297), (0, 2, -0.24750),
    (2, 1, -0.84978), (0, 3, -0.06550), (2, 2, -0.01709),
    (1, 0, -0.00738), (4, 0, 0.00530), (2, 3, -0.00039),
    (4, 1, 0.00033), (1, 1, -0.00012),
)
_RD_LAM_TERMS: tuple[tuple[int, int, float], ...] = (
    (1, 0, 5260.52916), (1, 1, 105.94684), (1, 2, 2.45656),
    (3, 0, -0.81885), (1, 3, 0.05594), (3, 1, -0.05607),
    (0, 1, 0.01199), (3, 2, -0.00256), (1, 4, 0.00128),
    (0, 2, 0.00022), (2, 0, -0.00022), (5, 0, 0.00026),
)


def rd_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convert Dutch RD (EPSG:28992) coordinates to (latitude, longitude)."""
    dx = (x - _RD_X0) * 1e-5
    dy = (y - _RD_Y0) * 1e-5
    dphi = sum(c * dx**p * dy**q for p, q, c in _RD_PHI_TERMS)
    dlam = sum(c * dx**p * dy**q for p, q, c in _RD_LAM_TERMS)
    return _RD_PHI0 + dphi / 3600, _RD_LAM0 + dlam / 3600


def _localname(tag: str) -> str:
    """Strip an XML namespace prefix.

    Different data owners serialize KV6posinfo with a "tmi8:" prefix or none
    at all for the identical schema — matching must be namespace-agnostic.
    """
    return tag.split("}")[-1]


def decompress_kv6_payload(raw: bytes) -> str:
    """Gzip-decompress one KV6 ZeroMQ message body."""
    return gzip.GzipFile(fileobj=io.BytesIO(raw)).read().decode("utf-8-sig")


@dataclass(frozen=True)
class KV6RawFix:
    """One parsed KV6 message that carries a GPS fix."""

    data_owner_code: str
    line_planning_number: str
    journey_number: str
    operation_date: str
    message_type: str
    fields: dict[str, str]


def parse_kv6_message(payload: str) -> list[KV6RawFix]:
    """Parse one KV6 XML payload into fixes that carry a GPS position."""
    from xml.etree import ElementTree as ET

    fixes: list[KV6RawFix] = []
    root: Element = ET.fromstring(payload)
    for kv6 in root.iter():
        if _localname(kv6.tag) != "KV6posinfo":
            continue
        for msg in kv6:
            fields = {_localname(child.tag).lower(): (child.text or "").strip() for child in msg}
            if "rd-x" not in fields or "rd-y" not in fields:
                continue
            owner = fields.get("dataownercode")
            line = fields.get("lineplanningnumber")
            journey = fields.get("journeynumber")
            day = fields.get("operatingday")
            if not (owner and line and journey and day):
                continue
            fixes.append(KV6RawFix(owner, line, journey, day, _localname(msg.tag), fields))
    return fixes


@dataclass(frozen=True)
class KV6VehiclePosition:
    """A live vehicle position, matched to a specific trip.

    Field names are deliberately "latitude"/"longitude", not "lat"/"lon":
    diagnostics.py's existing TO_REDACT set matches on those exact key names
    recursively, so any dict built from this dataclass has coordinates
    redacted automatically with no changes needed there.
    """

    data_owner_code: str
    line_planning_number: str
    journey_number: str
    operation_date: str
    latitude: float
    longitude: float
    punctuality: int
    vehicle_number: str | None
    omloop_number: str | None
    message_type: str
    timestamp: float  # time.time() when ingested


PositionKey = tuple[str, str, str, str]


class KV6LiveTracker:
    """Background KV6 subscriber and thread-safe live-position cache.

    One instance per config entry. Owns a dedicated thread running its own
    ZeroMQ SUB socket (pyzmq is sync, zmq objects can't cross threads) and
    notifies entities of updates via Home Assistant's dispatcher, which is
    safe to call from a non-event-loop thread.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the tracker (does not start the thread yet)."""
        self._hass = hass
        self._entry_id = entry_id
        self._lock = threading.Lock()
        self._positions: dict[PositionKey, KV6VehiclePosition] = {}
        self._wanted_owners: set[str] = set()
        self._subscribed_owners: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def signal_name(self) -> str:
        """Dispatcher signal fired whenever a new position is ingested."""
        return f"{DOMAIN}_{self._entry_id}_kv6_update"

    def update_subscriptions(self, data_owner_codes: set[str]) -> None:
        """Set which data owners' KV6 topics are currently relevant.

        Called from the coordinator's event-loop code every poll cycle,
        fed by DataOwnerCode values it already fetched — no separate HTTP
        call. Pure in-memory set assignment under a lock; safe to call
        directly from the event loop.
        """
        with self._lock:
            self._wanted_owners = set(data_owner_codes)

    def get_position(
        self,
        data_owner_code: str | None,
        line_planning_number: str | None,
        journey_number: str | None,
        operation_date: str | None,
    ) -> KV6VehiclePosition | None:
        """Look up the latest known position for a specific trip, if fresh."""
        if not (data_owner_code and line_planning_number and journey_number and operation_date):
            return None
        key: PositionKey = (data_owner_code, line_planning_number, journey_number, operation_date)
        with self._lock:
            position = self._positions.get(key)
        if position is None or time.time() - position.timestamp > VEHICLE_MAX_AGE:
            return None
        return position

    def _ingest(self, fix: KV6RawFix) -> None:
        """Store one parsed fix and notify entities of the update.

        Keying by (data_owner_code, line_planning_number, journey_number,
        operation_date) — never journey_number alone — is what prevents a
        national operator's journey-number reuse across unrelated regional
        concessions from silently matching a vehicle to the wrong trip.
        """
        try:
            latitude, longitude = rd_to_wgs84(float(fix.fields["rd-x"]), float(fix.fields["rd-y"]))
        except (KeyError, ValueError) as err:
            _LOGGER.debug("Skipping KV6 fix with invalid RD coordinates: %s", err)
            return

        position = KV6VehiclePosition(
            data_owner_code=fix.data_owner_code,
            line_planning_number=fix.line_planning_number,
            journey_number=fix.journey_number,
            operation_date=fix.operation_date,
            latitude=latitude,
            longitude=longitude,
            punctuality=int(fix.fields.get("punctuality") or 0),
            vehicle_number=fix.fields.get("vehiclenumber") or None,
            omloop_number=fix.fields.get("omloopnumber") or None,
            message_type=fix.message_type,
            timestamp=time.time(),
        )
        key: PositionKey = (
            fix.data_owner_code,
            fix.line_planning_number,
            fix.journey_number,
            fix.operation_date,
        )
        with self._lock:
            self._positions[key] = position

        dispatcher_send(self._hass, self.signal_name)

    def _run(self) -> None:
        """Subscriber thread body: owns its own zmq context/socket."""
        import zmq  # local import — only loaded into memory when tracking is enabled

        context = zmq.Context()
        subscriber = context.socket(zmq.SUB)
        subscriber.connect(KV6_ENDPOINT)
        subscriber.setsockopt(zmq.RCVTIMEO, KV6_RECV_TIMEOUT_MS)

        try:
            while not self._stop_event.is_set():
                with self._lock:
                    wanted = set(self._wanted_owners)
                for owner in wanted - self._subscribed_owners:
                    subscriber.setsockopt_string(zmq.SUBSCRIBE, f"/{owner}/KV6posinfo")
                    _LOGGER.debug("Subscribed to KV6 topic for data owner %s", owner)
                self._subscribed_owners |= wanted

                try:
                    parts = subscriber.recv_multipart()
                except zmq.error.Again:
                    continue

                try:
                    payload = decompress_kv6_payload(b"".join(parts[1:]))
                except OSError as err:
                    _LOGGER.debug("Failed to decompress KV6 message: %s", err)
                    continue

                try:
                    for fix in parse_kv6_message(payload):
                        self._ingest(fix)
                except Exception:  # noqa: BLE001 - a single malformed message must not kill the subscriber
                    _LOGGER.debug("Failed to parse KV6 message", exc_info=True)
        finally:
            subscriber.close(0)
            context.term()

    def start(self) -> None:
        """Start the background subscriber thread."""
        self._thread = threading.Thread(
            target=self._run, name=f"ovapi-kv6-{self._entry_id}", daemon=True
        )
        self._thread.start()

    async def async_stop(self) -> None:
        """Signal the subscriber thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread is not None:
            await self._hass.async_add_executor_job(self._thread.join, 5)
