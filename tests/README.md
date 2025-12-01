# OVAPI Integration Test Suite

## Running Tests

### Install Test Dependencies
```bash
pip install -r requirements_test.txt
```

### Run All Tests
```bash
pytest tests/
```

### Run with Coverage
```bash
pytest --cov=custom_components/ovapi --cov-report=html tests/
```

Coverage report will be available in `htmlcov/index.html`

### Run Specific Test File
```bash
pytest tests/test_config_flow.py -v
```

### Run Type Checking
```bash
mypy custom_components/ovapi
```

## Test Structure

```
tests/
├── __init__.py                 # Test package init
├── conftest.py                 # Shared fixtures
├── test_config_flow.py         # Config flow tests
├── test_init.py                # Integration setup tests
├── test_sensor.py              # Sensor tests
└── test_diagnostics.py         # Diagnostics tests
```

## Fixtures Available

- `mock_ovapi_client` - Mocked OVAPI API client
- `mock_gtfs_handler` - Mocked GTFS data handler
- `mock_setup_entry` - Mocked integration setup

## Coverage Goals

Target: **95%+ code coverage**

Areas covered:
- Config flow (all paths)
- Integration lifecycle
- Sensor creation and updates
- API client functionality
- GTFS search
- Diagnostics generation
- Error handling

## Continuous Integration

For GitHub Actions, add `.github/workflows/test.yml`:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements_test.txt
      - name: Run tests
        run: |
          pytest --cov=custom_components/ovapi --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```
