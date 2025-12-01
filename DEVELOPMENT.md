# OVAPI Home Assistant Integration - Development Notes

## Installation in Home Assistant

To install this integration in your Home Assistant instance:

1. Copy the entire `custom_components/ovapi` folder to your Home Assistant's `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via UI: Configuration → Integrations → Add Integration → Search "OVAPI"

## Directory Structure

```
ovapi/
├── custom_components/
│   └── ovapi/
│       ├── __init__.py          # Integration setup and coordinator
│       ├── manifest.json        # Integration metadata
│       ├── const.py             # Constants
│       ├── config_flow.py       # UI configuration flow
│       ├── api.py               # OVAPI API client
│       ├── sensor.py            # Sensor platform
│       ├── strings.json         # UI strings (primary)
│       └── translations/
│           └── en.json          # English translations
├── README.md                    # User documentation
└── .gitignore
```

## Testing

To test this integration:

1. Install in Home Assistant (see above)
2. Find a valid OVAPI stop code (e.g., search on bus stops in the Netherlands)
3. Add the integration and configure with:
   - Stop code
   - Optional: specific line number
   - Optional: destination filter
   - Walking time in minutes

## API Reference

The integration uses OVAPI.nl endpoints:
- Base URL: `http://v0.ovapi.nl`
- Stop endpoint: `/stopareacode/{stop_code}`

Example: `http://v0.ovapi.nl/stopareacode/31000495`

## Sensor Features

1. **Current Bus** - Next bus arriving (line + destination)
2. **Next Bus** - Bus after current one
3. **Current Bus Delay** - Delay in minutes
4. **Next Bus Delay** - Delay in minutes
5. **Current Bus Departure** - Minutes until arrival
6. **Next Bus Departure** - Minutes until arrival  
7. **Time to Leave** - When to start walking (considers walking time)

All sensors update every 60 seconds.

## Customization

You can modify the update interval in `const.py`:
```python
DEFAULT_SCAN_INTERVAL = 60  # seconds
```

## Future Enhancements

Potential improvements:
- [ ] Multiple stops per integration instance
- [ ] Configurable update intervals
- [ ] Historical delay tracking
- [ ] Binary sensor for "should leave now"
- [ ] Support for tram/train in addition to buses
- [ ] Route planning with multiple connections
