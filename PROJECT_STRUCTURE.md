# OVAPI Home Assistant Integration - Project Structure

```
ovapi/
├── .gitignore                          # Git ignore rules
├── README.md                           # User documentation
├── DEVELOPMENT.md                      # Developer notes
├── PLATINUM_COMPLIANCE.md              # Quality tier documentation
├── pyproject.toml                      # Python project configuration
├── requirements_test.txt               # Test dependencies
│
├── custom_components/ovapi/            # Integration code
│   ├── __init__.py                     # Integration setup & coordinator
│   ├── manifest.json                   # Integration metadata (Platinum tier)
│   ├── const.py                        # Constants and configuration
│   ├── config_flow.py                  # UI configuration flow
│   ├── api.py                          # OVAPI API client
│   ├── gtfs.py                         # GTFS data handler for stop search
│   ├── sensor.py                       # 7 sensor entities
│   ├── diagnostics.py                  # Diagnostics support
│   ├── py.typed                        # PEP 561 typing marker
│   ├── quality_scale.yaml              # Quality scale tracking
│   ├── strings.json                    # UI strings (primary)
│   └── translations/
│       └── en.json                     # English translations
│
└── tests/                              # Test suite (>95% coverage target)
    ├── __init__.py                     # Test package init
    ├── README.md                       # Test documentation
    ├── conftest.py                     # Shared test fixtures
    ├── test_config_flow.py             # Config flow tests
    ├── test_init.py                    # Integration lifecycle tests
    ├── test_sensor.py                  # Sensor tests
    └── test_diagnostics.py             # Diagnostics tests
```

## File Purposes

### Root Level

**README.md**
- User-facing documentation
- Installation instructions
- Configuration guide
- Example automations
- Troubleshooting

**PLATINUM_COMPLIANCE.md**
- Detailed quality tier compliance documentation
- Architecture highlights
- Test coverage information
- Performance optimizations

**DEVELOPMENT.md**
- Developer setup instructions
- API reference
- Customization guide
- Future enhancements

**pyproject.toml**
- pytest configuration
- coverage settings
- mypy strict type checking config

### Integration Files

**__init__.py** (149 lines)
- `async_setup_entry()` - Integration setup
- `async_unload_entry()` - Clean unload
- `OVAPIDataUpdateCoordinator` - Data update coordinator
- Uses `runtime_data` pattern

**manifest.json**
- Integration metadata
- Dependencies: aiohttp>=3.8.0
- Quality scale: platinum
- IoT class: cloud_polling

**const.py** (27 lines)
- DOMAIN = "ovapi"
- Configuration keys
- Default values (30s scan interval)
- API constants

**config_flow.py** (243 lines)
- Multi-step configuration flow:
  1. User choice (search/manual)
  2. Search or manual entry
  3. Stop selection (if search)
  4. Configuration options
- Reconfiguration support
- Validation with error handling

**api.py** (123 lines)
- `OVAPIClient` class
- `get_stop_info()` - Fetch stop data
- `filter_passes()` - Filter by line/destination
- `get_time_until_departure()` - Calculate arrival time
- Fully async with timeout handling

**gtfs.py** (176 lines)
- `GTFSDataHandler` class
- `GTFSStopCache` for 24-hour caching
- Downloads GTFS ZIP from ovapi.nl
- Parses stops.txt
- `search_stops()` - Search by name or code
- Smart filename detection (today/yesterday)

**sensor.py** (338 lines)
- 7 sensor entities:
  1. Current Bus (line → destination)
  2. Next Bus (disabled by default)
  3. Current Bus Delay (diagnostic)
  4. Next Bus Delay (diagnostic, disabled by default)
  5. Current Bus Departure (minutes)
  6. Next Bus Departure (disabled by default)
  7. Time to Leave (walking planner)
- All with proper device classes, categories, and translations
- Strict typing with `StateType` returns

**diagnostics.py** (38 lines)
- `async_get_config_entry_diagnostics()`
- Returns entry data, coordinator state, passes
- Redacts sensitive location data

**quality_scale.yaml**
- Tracks compliance with HA quality scale
- Documents exemptions (e.g., no authentication)
- Bronze, Silver, Gold, Platinum checkboxes

### Test Files

**conftest.py**
- `mock_ovapi_client` fixture
- `mock_gtfs_handler` fixture
- Common test setup

**test_config_flow.py**
- Manual entry flow
- Search flow  
- Error handling (cannot connect, no stops found)
- Reconfiguration

**test_init.py**
- Integration setup
- Entry unload
- Runtime data usage

**test_sensor.py**
- Sensor creation
- State values
- Unavailable handling

**test_diagnostics.py**
- Diagnostics data structure
- Data redaction

## Key Features

### 🏆 Platinum Tier
✅ Fully async codebase
✅ Strict type hints throughout
✅ Efficient data handling (caching, configurable polling)
✅ py.typed marker for type checkers

### 🥇 Gold Tier
✅ Diagnostics support
✅ Reconfiguration flow
✅ Entity translations
✅ Device classes and categories
✅ Device grouping
✅ GTFS discovery

### 🥈 Silver Tier
✅ Proper error handling
✅ Config entry unloading
✅ Integration owner
✅ Structured logging
✅ No reauthentication needed (public API)

### 🥉 Bronze Tier
✅ UI config flow
✅ Entity unique IDs
✅ has_entity_name pattern
✅ runtime_data usage
✅ Input validation

## Lines of Code

| File | Lines | Purpose |
|------|-------|---------|
| sensor.py | 338 | Sensor entities |
| config_flow.py | 243 | Configuration UI |
| gtfs.py | 176 | Stop search |
| __init__.py | 149 | Setup & coordinator |
| api.py | 123 | API client |
| diagnostics.py | 38 | Debug support |
| const.py | 27 | Constants |
| **Total** | **~1,094** | Core integration |

## Dependencies

**Runtime:**
- aiohttp>=3.8.0 (async HTTP client)

**Development:**
- pytest>=7.0.0
- pytest-homeassistant-custom-component>=0.13.0
- pytest-cov>=4.0.0
- pytest-asyncio>=0.21.0
- homeassistant>=2024.1.0
- mypy>=1.0.0 (type checking)

## Integration Capabilities

### Data Sources
- OVAPI.nl real-time transit API
- GTFS static transit data (stop search)

### User Inputs
- Stop code (manual or search)
- Line number filter (optional)
- Destination filter (optional)
- Walking time (1-60 minutes)
- Update interval (30-300 seconds)

### Sensors Created
- 7 sensors per stop (3 disabled by default)
- All grouped under bus stop device
- Proper units, device classes, categories

### Configuration
- UI-based setup (no YAML)
- Multi-step flow with search
- Reconfiguration support
- Validation before saving

## Performance

- **API Calls**: 1 per update cycle (30-300s configurable)
- **GTFS Download**: Once per 24 hours, ~5-10 MB
- **Memory**: Minimal, cached GTFS data only
- **CPU**: Lightweight, async operations only

## Maintainability

- **Type Safety**: 100% type-hinted code
- **Test Coverage**: >95% target
- **Documentation**: Comprehensive README and guides
- **Code Quality**: Follows HA best practices
- **Modularity**: Clear separation of concerns
