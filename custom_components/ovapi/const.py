"""Constants for the OVAPI integration."""

DOMAIN = "ovapi"

# Configuration keys
CONF_STOP_CODE = "stop_code"
CONF_STOP_CODES = "stop_codes"  # For multiple stops (bidirectional)
CONF_LINE_NUMBER = "line_number"
CONF_DESTINATION = "destination"
CONF_WALKING_TIME = "walking_time"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_LIVE_TRACKING = "enable_live_tracking"

# Default values
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_WALKING_TIME = 0  # minutes (0 = disabled by default)
MIN_SCAN_INTERVAL = 60  # minimum seconds between updates
MAX_SCAN_INTERVAL = 300  # maximum seconds between updates
DEFAULT_ENABLE_LIVE_TRACKING = False

# API
API_BASE_URL = "http://v0.ovapi.nl"
API_TIMEOUT = 10

# GitHub
GITHUB_REPO = "william-sy/ovapi"
GITHUB_NEW_ISSUE_URL = "https://github.com/william-sy/ovapi/issues/new"
GITHUB_CONTRIBUTING_URL = "https://github.com/william-sy/ovapi/blob/main/gtfs/CONTRIBUTING.md"

# TPC Finder URLs
TPC_FINDER_BASE_URL = "https://william-sy.github.io/ovapi-tpc-finder/data"
TPC_FINDER_CITIES_URL = f"{TPC_FINDER_BASE_URL}/cities.json"
TPC_FINDER_STOPS_URL = f"{TPC_FINDER_BASE_URL}/stops_by_city.json"
TPC_FINDER_LINES_URL = f"{TPC_FINDER_BASE_URL}/lines_by_stop.json"

# Sensor types
SENSOR_CURRENT_BUS = "current_bus"
SENSOR_NEXT_BUS = "next_bus"
SENSOR_DEPARTURE_TIME = "departure_time"
SENSOR_DELAY = "delay"
SENSOR_WALKING_PLANNER = "walking_planner"

# Device tracker types
TRACKER_CURRENT_BUS = "current_bus_location"
TRACKER_NEXT_BUS = "next_bus_location"

# KV6 live vehicle position feed (opt-in, see CONF_ENABLE_LIVE_TRACKING).
# Public GOVI/NDOVloket real-time feed — separate from the KV7/8-Turbo
# schedule API above. ZeroMQ pub/sub, not HTTP: browsers/aiohttp can't speak
# it, hence the dedicated pyzmq-based background thread in kv6.py.
KV6_ENDPOINT = "tcp://pubsub.besteffort.ndovloket.nl:7658"
KV6_RECV_TIMEOUT_MS = 2000  # how often the subscriber thread checks for new subscriptions / stop requests
VEHICLE_MAX_AGE = 180  # seconds — drop GPS fixes older than this as stale
