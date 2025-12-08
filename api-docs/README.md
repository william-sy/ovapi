# v0.ovapi.nl API Documentation

Complete reference for the v0.ovapi.nl (OVapi) public transport API.

## Table of Contents

1. [Overview](#overview)
2. [Base URL](#base-url)
3. [Endpoints](#endpoints)
4. [Data Models](#data-models)
5. [Usage Examples](#usage-examples)
6. [Rate Limits](#rate-limits)
7. [Known Limitations](#known-limitations)

## Overview

The OVapi (Openbaar Vervoer API) provides real-time public transport information for the Netherlands. It aggregates data from multiple transport operators including trains (NS), buses, trams, and metros.

**Data Sources:**
- KV7 (transport schedule data)
- Real-time vehicle positions
- Service messages

**Coverage:**
- All public transport in the Netherlands
- Real-time departure information
- Service disruptions and messages

## Base URL

```
http://v0.ovapi.nl
```

⚠️ **Note:** API uses HTTP, not HTTPS.

## Endpoints

### 1. Timing Point Code (TPC) - Real-time Departures

Get real-time departure information for a specific stop.

**Endpoint:** `/tpc/{TimingPointCode}`

**Method:** GET

**Parameters:**
- `TimingPointCode` (required): 8-digit timing point code (e.g., `30001953`)

**Response Structure:**
```json
{
  "30001953": {
    "Stop": {
      "TimingPointCode": "30001953",
      "TimingPointName": "Arnhem, Meander",
      "TimingPointTown": "Arnhem",
      "StopAreaCode": "05065",
      "Latitude": 51.978394,
      "Longitude": 5.912638
    },
    "Passes": {
      "CONNEXXION_CXX_E102_1_1234567_20250101": {
        "LinePublicNumber": "102",
        "LinePlanningNumber": "E102",
        "LineDirection": 1,
        "DestinationName50": "Arnhem CS",
        "DataOwnerCode": "CONNEXXION",
        "TransportType": "BUS",
        "OperatorCode": "CXX",
        "ExpectedArrivalTime": "2025-12-07T14:30:00+01:00",
        "ExpectedDepartureTime": "2025-12-07T14:30:00+01:00",
        "TripStopStatus": "PLANNED",
        "TargetArrivalTime": "2025-12-07T14:30:00+01:00",
        "TargetDepartureTime": "2025-12-07T14:30:00+01:00"
      }
    },
    "GeneralMessages": {}
  }
}
```

**Key Fields:**
- `Passes`: Dictionary of upcoming departures keyed by unique trip ID
- `LinePublicNumber`: The line number shown to passengers
- `DestinationName50`: Destination name (max 50 chars)
- `TransportType`: BUS, TRAM, METRO, TRAIN, FERRY
- `ExpectedDepartureTime`: Real-time updated departure time (ISO 8601)
- `TargetDepartureTime`: Scheduled departure time
- `TripStopStatus`: PLANNED, DRIVING, PASSED, CANCELLED

**Example:**
```bash
curl "http://v0.ovapi.nl/tpc/30001953"
```

---

### 2. Stop Area Code - Metadata & Grouping

Get metadata and grouping information for stop areas.

**Endpoint:** `/stopareacode/{StopAreaCode}`

**Method:** GET

**Parameters:**
- `StopAreaCode` (required): 5-digit stop area code (e.g., `05095`)
- Or: `/stopareacode/` to get all stop area codes

**Response Structure:**
```json
{
  "05095": {
    "30005107": {
      "Stop": {
        "TimingPointCode": "30005107",
        "TimingPointName": "Centraal Station",
        "TimingPointTown": "Amsterdam",
        "StopAreaCode": "05095",
        "Latitude": 47.974766,
        "Longitude": 3.3135424
      },
      "Passes": {},
      "GeneralMessages": {}
    }
  }
}
```

**Use Case:**
- Get metadata about stop areas
- Find timing point codes within a stop area
- Does NOT aggregate all platforms at major stations

**Example:**
```bash
# Get specific stop area
curl "http://v0.ovapi.nl/stopareacode/05095"

# Get all stop areas (large response)
curl "http://v0.ovapi.nl/stopareacode/"
```

---

### 3. Line Information

Get information about transport lines.

**Endpoint:** `/line/{LinePlanningNumber}`

**Method:** GET

**Parameters:**
- `LinePlanningNumber` (required): Line planning number (e.g., `GVB_17`)
- Or: `/line/` to get all lines

**Response Structure:**
```json
{
  "GVB_17_1": {
    "LineWheelchairAccessible": "UNKNOWN",
    "TransportType": "TRAM",
    "DestinationName50": "Osdorp Dijkgraafplein",
    "DataOwnerCode": "GVB",
    "DestinationCode": "ODY",
    "LinePublicNumber": "17",
    "LinePlanningNumber": "17",
    "LineName": "Lijn 17",
    "LineDirection": 1
  }
}
```

**Key Fields:**
- `LinePublicNumber`: Public-facing line number
- `LinePlanningNumber`: Internal planning number
- `LineDirection`: 1 or 2 (different directions)
- `DestinationName50`: Final destination

**Limitations:**
- ⚠️ Does NOT return stop codes or timing points for the line
- Metadata only

**Example:**
```bash
# Get all lines (very large response ~250MB)
curl "http://v0.ovapi.nl/line/"
```

---

## Data Models

### Stop/Timing Point

```typescript
interface Stop {
  TimingPointCode: string;      // 8-digit code
  TimingPointName: string;       // Stop name
  TimingPointTown: string;       // City/town
  StopAreaCode: string;          // 5-digit area code
  Latitude: number;
  Longitude: number;
}
```

### Pass (Departure)

```typescript
interface Pass {
  LinePublicNumber: string;
  LinePlanningNumber: string;
  LineDirection: number;         // 1 or 2
  DestinationName50: string;
  DataOwnerCode: string;         // Transport operator
  TransportType: TransportType;
  OperatorCode: string;
  ExpectedArrivalTime: string;   // ISO 8601
  ExpectedDepartureTime: string; // ISO 8601
  TripStopStatus: TripStatus;
  TargetArrivalTime: string;     // Scheduled
  TargetDepartureTime: string;   // Scheduled
}

type TransportType = "BUS" | "TRAM" | "METRO" | "TRAIN" | "FERRY" | "BOAT";
type TripStatus = "PLANNED" | "DRIVING" | "PASSED" | "CANCELLED";
```

### Data Owner Codes

Common transport operators:

| Code | Operator |
|------|----------|
| `GVB` | GVB (Amsterdam) |
| `RET` | RET (Rotterdam) |
| `HTM` | HTM (Den Haag) |
| `NS` | Nederlandse Spoorwegen (Trains) |
| `CXX` | Connexxion |
| `ARR` | Arriva |
| `QBUZZ` | Qbuzz |
| `NL` | Various regional operators |

## Usage Examples

### Get Real-time Departures

```python
import requests

# Get departures for specific stop
response = requests.get("http://v0.ovapi.nl/tpc/30001953")
data = response.json()

stop_code = "30001953"
stop = data[stop_code]

print(f"Stop: {stop['Stop']['TimingPointName']}")
print(f"Town: {stop['Stop']['TimingPointTown']}")
print("\nUpcoming departures:")

for trip_id, departure in stop['Passes'].items():
    line = departure['LinePublicNumber']
    destination = departure['DestinationName50']
    time = departure['ExpectedDepartureTime']
    print(f"  Line {line} → {destination} at {time}")
```

### Search All Stops

```python
import requests

# Get all stop areas (warning: large response)
response = requests.get("http://v0.ovapi.nl/stopareacode/")
all_areas = response.json()

# Search for stops in a city
city = "Arnhem"
stops = [
    (code, info['TimingPointName'])
    for code, info in all_areas.items()
    if city in info.get('TimingPointTown', '')
]

for code, name in stops:
    print(f"{code}: {name}")
```

### Monitor Multiple Platforms

```python
# Amsterdam Centraal has multiple stop area codes for different modes
codes = ['05003', '05095', '09500', '09575', '05104']

for code in codes:
    response = requests.get(f"http://v0.ovapi.nl/stopareacode/{code}")
    data = response.json()
    
    for area_code, stops in data.items():
        for tpc, info in stops.items():
            print(f"TPC {tpc}: {info['Stop']['TimingPointName']}")
```

## Rate Limits

**Unknown / Not Documented**

⚠️ Best practices:
- Cache responses when possible
- Don't hammer the API with rapid requests
- Use reasonable refresh intervals (30-60 seconds for real-time data)
- Be respectful - this is a free public service

## Known Limitations

### 1. No Aggregation by Station

Major stations (e.g., Amsterdam Centraal with 19+ platforms) require querying **multiple timing point codes individually**. There is no endpoint that returns all platforms at once.

### 2. Incomplete Stop Area Grouping

`/stopareacode/` endpoint doesn't comprehensively list all platforms/stops at major stations. Some transport modes have separate stop area codes.

### 3. No Line-to-Stops Mapping

The `/line/` endpoint provides line metadata but **does not return which stops the line serves**. You must discover this through other means (GTFS data or observation).

### 4. No Search Endpoint

There is no text search endpoint. To find stops by name, you must:
1. Fetch all stop areas (`/stopareacode/`)
2. Parse and search locally
3. Or maintain your own search index

### 5. Data Quality Varies

- Some stops may have empty `Passes` (no upcoming departures)
- Coordinates may be approximate
- Stop names can be inconsistent between operators

### 6. HTTP Only

API is HTTP only, not HTTPS. Data is not encrypted in transit.

### 7. No Historical Data

API only provides:
- Current real-time data
- Near-future departures (typically next 2 hours)

No access to:
- Historical departure data
- Long-term schedules
- Archive of service disruptions

## Additional Resources

- **GTFS Data**: Available from transport operators for schedule data
- **Custom Stops**: Community-maintained lists for missing/inconsistent stops
- **Home Assistant Integration**: [`custom_components/ovapi`](../custom_components/ovapi/)

## Contributing

Found missing information or errors? Please open an issue or pull request on GitHub.

---

*Last Updated: 2025-12-07*
