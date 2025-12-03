# GTFS Data Directory

This directory contains GTFS (General Transit Feed Specification) data files bundled with the integration.

## Files

- **gtfs-kv7.zip** (6.4 MB): Bundled GTFS dataset containing stops with confirmed real-time data
- **custom_stops.json**: Community-contributed stops that work but aren't in official GTFS ([How to contribute](CONTRIBUTING.md))
- **CONTRIBUTING.md**: Guide for users to contribute missing stops
- **stops.txt** (6.3 MB): Full GTFS stops (kept for reference, not used by integration)
- **routes.txt** (206 KB): Route information (kept for reference)
- **stops.txt.sha256**: Legacy hash file (not used)

## Why gtfs-kv7?

The integration uses **gtfs-kv7.zip** from `https://gtfs.ovapi.nl/govi/` because:

1. **Real-time data confirmed**: Only includes stops with 8-digit codes that work with v0.ovapi.nl
2. **Reasonable size**: 6.4 MB vs 280 MB for the full dataset
3. **Prevents frustration**: Users won't find stops that don't have real-time data

## Community Custom Stops

**Some stops work with the API but aren't in the official GTFS dataset!**

These stops have been added to `custom_stops.json` by community contributors:
- ✅ **Rotterdam, Huslystraat** (line 36): Stop codes 31002742 & 31002797

Can't find your stop in search? You can:
1. Use **manual entry** with the stop code
2. **Contribute it** to help others - see [CONTRIBUTING.md](CONTRIBUTING.md)

## Updating gtfs-kv7.zip

To update the bundled GTFS file:

```bash
# Download the latest gtfs-kv7 dataset
wget https://gtfs.ovapi.nl/govi/gtfs-kv7.zip -O gtfs/gtfs-kv7.zip

# Or download today's specific file
TODAY=$(date +%Y%m%d)
wget https://gtfs.ovapi.nl/govi/gtfs-kv7-$TODAY.zip -O gtfs/gtfs-kv7.zip

# Commit the changes
git add gtfs/gtfs-kv7.zip
git commit -m "Update GTFS gtfs-kv7.zip to $TODAY"
```

## Data Sources

- **KV7 dataset**: http://gtfs.ovapi.nl/govi/ (~2.6 MB, stops with real-time data)
- **Full dataset**: http://gtfs.ovapi.nl/nl/ (~280 MB, all stops including those without real-time)

## Cache Behavior

The integration caches parsed GTFS data for 1 day to improve performance:
- Cache file: `.storage/ovapi_gtfs_cache.json` in Home Assistant config
- Cache version: 7 (auto-invalidates when code changes)
- Delete cache to force refresh after updating gtfs-kv7.zip
