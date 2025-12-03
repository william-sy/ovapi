"""Tests for GTFS data handling."""
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import json
import pytest

from custom_components.ovapi.gtfs import GTFSDataHandler


@pytest.fixture
def mock_session():
    """Mock aiohttp session."""
    return AsyncMock()


@pytest.fixture
def mock_cache_dir(tmp_path):
    """Mock cache directory."""
    return tmp_path


@pytest.fixture
def sample_custom_stops():
    """Sample custom stops data."""
    return [
        {
            "stop_id": "custom_test_1",
            "stop_name": "Test City, Test Street",
            "stop_code": "12345678",
            "stop_lat": "52.123456",
            "stop_lon": "4.123456",
            "line_name": "Test Line",
            "line_num": "42"
        },
        {
            "stop_id": "custom_test_2",
            "stop_name": "Test City, Test Street",
            "stop_code": "87654321",
            "stop_lat": "52.234567",
            "stop_lon": "4.234567",
            "line_name": "Test Line",
            "line_num": "42"
        }
    ]


@pytest.mark.asyncio
async def test_custom_stops_loaded(mock_session, mock_cache_dir, sample_custom_stops, tmp_path):
    """Test that custom stops are loaded and merged with GTFS data."""
    # Create mock GTFS zip file with minimal stops.txt
    gtfs_file = tmp_path / "gtfs-kv7.zip"
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        stops_content = "stop_id,stop_name,stop_code,stop_lat,stop_lon\n"
        stops_content += "gtfs_stop_1,GTFS Stop,11111111,52.0,4.0\n"
        zip_file.writestr("stops.txt", stops_content)
    
    gtfs_file.write_bytes(zip_buffer.getvalue())
    
    # Create custom stops file
    custom_file = tmp_path / "custom_stops.json"
    custom_file.write_text(json.dumps(sample_custom_stops))
    
    # Patch the file paths
    with patch("custom_components.ovapi.gtfs.BUNDLED_GTFS_FILE", gtfs_file), \
         patch("custom_components.ovapi.gtfs.CUSTOM_STOPS_FILE", custom_file):
        
        handler = GTFSDataHandler(mock_session, mock_cache_dir)
        stops = await handler.download_and_parse_stops()
        
        # Verify GTFS stop is present
        assert "gtfs_stop_1" in stops
        assert stops["gtfs_stop_1"]["stop_code"] == "11111111"
        
        # Verify custom stops are added
        assert "custom_test_1" in stops
        assert stops["custom_test_1"]["stop_code"] == "12345678"
        assert stops["custom_test_1"]["stop_name"] == "Test City, Test Street"
        assert stops["custom_test_1"]["routes"] == ["42"]
        
        assert "custom_test_2" in stops
        assert stops["custom_test_2"]["stop_code"] == "87654321"
        
        # Total should be 3 (1 GTFS + 2 custom)
        assert len(stops) == 3


@pytest.mark.asyncio
async def test_custom_stops_dont_override_gtfs(mock_session, mock_cache_dir, tmp_path):
    """Test that custom stops don't override existing GTFS stops."""
    # Create mock GTFS zip with a stop
    gtfs_file = tmp_path / "gtfs-kv7.zip"
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        stops_content = "stop_id,stop_name,stop_code,stop_lat,stop_lon\n"
        stops_content += "same_stop_id,Original GTFS Stop,11111111,52.0,4.0\n"
        zip_file.writestr("stops.txt", stops_content)
    
    gtfs_file.write_bytes(zip_buffer.getvalue())
    
    # Create custom stops file with same stop_id
    custom_stops = [
        {
            "stop_id": "same_stop_id",
            "stop_name": "Custom Stop Name",
            "stop_code": "99999999",
            "stop_lat": "53.0",
            "stop_lon": "5.0",
            "line_num": "42"
        }
    ]
    custom_file = tmp_path / "custom_stops.json"
    custom_file.write_text(json.dumps(custom_stops))
    
    with patch("custom_components.ovapi.gtfs.BUNDLED_GTFS_FILE", gtfs_file), \
         patch("custom_components.ovapi.gtfs.CUSTOM_STOPS_FILE", custom_file):
        
        handler = GTFSDataHandler(mock_session, mock_cache_dir)
        stops = await handler.download_and_parse_stops()
        
        # GTFS data should be preserved (not overridden by custom)
        assert stops["same_stop_id"]["stop_name"] == "Original GTFS Stop"
        assert stops["same_stop_id"]["stop_code"] == "11111111"
        assert len(stops) == 1


@pytest.mark.asyncio
async def test_missing_custom_stops_file_handled(mock_session, mock_cache_dir, tmp_path):
    """Test that missing custom_stops.json doesn't cause errors."""
    # Create mock GTFS zip file
    gtfs_file = tmp_path / "gtfs-kv7.zip"
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        stops_content = "stop_id,stop_name,stop_code,stop_lat,stop_lon\n"
        stops_content += "gtfs_stop_1,GTFS Stop,11111111,52.0,4.0\n"
        zip_file.writestr("stops.txt", stops_content)
    
    gtfs_file.write_bytes(zip_buffer.getvalue())
    
    # Don't create custom_stops.json
    custom_file = tmp_path / "custom_stops.json"
    
    with patch("custom_components.ovapi.gtfs.BUNDLED_GTFS_FILE", gtfs_file), \
         patch("custom_components.ovapi.gtfs.CUSTOM_STOPS_FILE", custom_file):
        
        handler = GTFSDataHandler(mock_session, mock_cache_dir)
        stops = await handler.download_and_parse_stops()
        
        # Should only have GTFS stop
        assert len(stops) == 1
        assert "gtfs_stop_1" in stops


@pytest.mark.asyncio
async def test_malformed_custom_stops_handled(mock_session, mock_cache_dir, tmp_path):
    """Test that malformed custom_stops.json is handled gracefully."""
    # Create mock GTFS zip file
    gtfs_file = tmp_path / "gtfs-kv7.zip"
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        stops_content = "stop_id,stop_name,stop_code,stop_lat,stop_lon\n"
        stops_content += "gtfs_stop_1,GTFS Stop,11111111,52.0,4.0\n"
        zip_file.writestr("stops.txt", stops_content)
    
    gtfs_file.write_bytes(zip_buffer.getvalue())
    
    # Create malformed JSON file
    custom_file = tmp_path / "custom_stops.json"
    custom_file.write_text("{ invalid json }")
    
    with patch("custom_components.ovapi.gtfs.BUNDLED_GTFS_FILE", gtfs_file), \
         patch("custom_components.ovapi.gtfs.CUSTOM_STOPS_FILE", custom_file):
        
        handler = GTFSDataHandler(mock_session, mock_cache_dir)
        stops = await handler.download_and_parse_stops()
        
        # Should still load GTFS stops despite malformed custom file
        assert len(stops) == 1
        assert "gtfs_stop_1" in stops


@pytest.mark.asyncio
async def test_custom_stops_without_line_num(mock_session, mock_cache_dir, tmp_path):
    """Test that custom stops work without line_num field."""
    # Create mock GTFS zip file
    gtfs_file = tmp_path / "gtfs-kv7.zip"
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        stops_content = "stop_id,stop_name,stop_code,stop_lat,stop_lon\n"
        zip_file.writestr("stops.txt", stops_content)
    
    gtfs_file.write_bytes(zip_buffer.getvalue())
    
    # Create custom stops without line_num
    custom_stops = [
        {
            "stop_id": "custom_no_line",
            "stop_name": "Test Stop",
            "stop_code": "12345678",
            "stop_lat": "52.0",
            "stop_lon": "4.0"
        }
    ]
    custom_file = tmp_path / "custom_stops.json"
    custom_file.write_text(json.dumps(custom_stops))
    
    with patch("custom_components.ovapi.gtfs.BUNDLED_GTFS_FILE", gtfs_file), \
         patch("custom_components.ovapi.gtfs.CUSTOM_STOPS_FILE", custom_file):
        
        handler = GTFSDataHandler(mock_session, mock_cache_dir)
        stops = await handler.download_and_parse_stops()
        
        # Custom stop should be added with empty routes
        assert "custom_no_line" in stops
        assert stops["custom_no_line"]["routes"] == []
