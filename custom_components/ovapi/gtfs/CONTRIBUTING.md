# Contributing Custom Stops

Some stops work with the v0.ovapi.nl API but aren't included in the official GTFS dataset. You can contribute these stops to help other users!

## When to Add a Custom Stop

Add a stop to `custom_stops.json` when:
- ✅ The stop has real-time data (verify at `http://v0.ovapi.nl/tpc/{stop_code}`)
- ✅ The stop is NOT found in the integration's search
- ✅ You've tested it works with manual entry 

## Example Entry

```json
{
    "stop_id": "custom_huslystraat_1",
    "stop_name": "Rotterdam, Huslystraat",
    "stop_code": "31002742",
    "stop_lat": "51.936783",
    "stop_lon": "4.5409513",
    "line_name": "Station Alexander - Kralingse Zoom",
    "line_num": "36"
}
```

## Fields Explanation

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `stop_id` | ✅ | Unique identifier (use `custom_{name}_{direction}`) | `custom_huslystraat_1` |
| `stop_name` | ✅ | Display name (use "City, Street" format) | `Rotterdam, Huslystraat` |
| `stop_code` | ✅ | 8-digit timing point code from v0 API | `31002742` |
| `stop_lat` | ✅ | Latitude coordinate | `51.936783` |
| `stop_lon` | ✅ | Longitude coordinate | `4.5409513` |
| `line_name` | ⚠️ | Full line name for reference | `Station Alexander - Kralingse Zoom` |
| `line_num` | ⚠️ | Line number users see | `36` |

## How to Find Stop Information

### 1. Get the Stop Code

The stop code is usually printed on physical signage at the stop, or you can:
1. Use a transit app (9292.nl, Google Maps)
2. Check `http://v0.ovapi.nl/line/` and search for your line
3. Browse stops on that line

### 2. Verify the Stop Works

Test the stop code:
```bash
curl http://v0.ovapi.nl/tpc/31002742
```
(Or open it in your browser)
Should return JSON with `"Passes"` data. If you get `[]`, the stop code doesn't work.

### 3. Get Coordinates

From the v0 API response:
```json
{
    "31002742": {
        "Stop": {
            "Latitude": 51.936783,
            "Longitude": 4.5409513,
            ...
        }
    }
}
```

### 4. Get Line Information

From the same API response under `"Passes"`:
```json
{
    "LinePublicNumber": "36",
    "LineName": "Station Alexander - Kralingse Zoom",
    ...
}
```

## Adding Both Directions

Most stops have two directions. Add separate entries:

```json
[
    {
        "stop_id": "custom_huslystraat_1",
        "stop_name": "Rotterdam, Huslystraat",
        "stop_code": "31002742",
        "stop_lat": "51.936783",
        "stop_lon": "4.5409513",
        "line_name": "Station Alexander - Kralingse Zoom",
        "line_num": "36"
    },
    {
        "stop_id": "custom_huslystraat_2",
        "stop_name": "Rotterdam, Huslystraat",
        "stop_code": "31002797",
        "stop_lat": "51.937405",
        "stop_lon": "4.539805",
        "line_name": "Station Alexander - Kralingse Zoom",
        "line_num": "36"
    }
]
```

The integration will automatically group them by name for bidirectional support.

## Submitting Your Contribution

1. Fork the repository
2. Edit `gtfs/custom_stops.json`
3. Add your stop(s) to the array
4. Ensure valid JSON format (check with a JSON validator)
5. Test locally if possible
6. Submit a Pull Request with:
   - Title: "Add custom stop: [City, Stop Name]"
   - Description: Line number(s) and why it's needed

## JSON Format Rules

- Each entry must be a valid JSON object
- Use double quotes for strings
- No trailing commas
- Validate before submitting: https://jsonlint.com/

## Testing Locally

After adding to `custom_stops.json`:
1. Delete cache: `config/.storage/ovapi_gtfs_cache.json`
2. Restart Home Assistant
3. Search for your stop - it should appear!
4. Test manual entry with the stop code
5. Verify real-time data shows up

## Questions?

Open an issue on GitHub if you need help finding stop information or have questions about contributing.
