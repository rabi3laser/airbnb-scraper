# 🕷️ Airbnb Scraper

High-performance Airbnb scraping library for Python.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- ⚡ **Fast**: Parallel requests (5x faster than sequential)
- 💾 **Cached**: SQLite caching (1000x faster for repeated queries)
- 🔄 **Reliable**: Automatic retry with exponential backoff
- 🛡️ **Safe**: Rate limiting to avoid blocks
- 📊 **Observable**: Built-in metrics and logging
- 🗺️ **Bounds Search**: Bypass 300 result limit with price binning

## Installation

```bash
pip install git+https://github.com/rabi3laser/airbnb-scraper.git
```

## Quick Start

```python
import asyncio
from pathlib import Path
from airbnb_scraper import AirbnbScraper, ScraperConfig

async def main():
    config = ScraperConfig(cache_dir=Path("/tmp/airbnb_cache"))
    
    async with AirbnbScraper(currency="EUR", config=config) as scraper:
        listings = await scraper.search_listings(
            location="Paris, France",
            max_listings=50
        )
        
        print(f"Found {len(listings)} listings")
        for listing in listings[:5]:
            print(f"- {listing.name}: €{listing.price_per_night}/night")

asyncio.run(main())
```

## Advanced Usage

### Search with Filters

```python
listings = await scraper.search_listings(
    location="Barcelona, Spain",
    checkin="2025-03-01",
    checkout="2025-03-05",
    min_price=50,
    max_price=200,
    guests=2,
    room_types=["Entire home"],
    amenities=[4, 8],  # Wifi, Kitchen
    superhost_only=True,
    min_bedrooms=2,
    max_listings=100
)
```

### Geographic Bounds Search

Bypass Airbnb's 300 result limit using price binning:

```python
listings = await scraper.search_by_bounds(
    ne_lat=48.90, ne_lng=2.45,
    sw_lat=48.80, sw_lng=2.25,
    max_listings=500,
    price_bins=8  # More bins = more results
)
```

### Get Listing Details

```python
details = await scraper.get_listing_details("12345678")

print(details.description)
print(details.amenities)  # Full list with names
print(details.images)     # Up to 20 images
```

### Batch Enrichment

```python
# Get basic listings
listings = await scraper.search_listings(location="Rome", max_listings=20)

# Enrich with detailed info (parallel)
enriched = await scraper.enrich_listings(listings, max_concurrent=3)
```

### Performance Metrics

```python
metrics = scraper.get_metrics()
print(f"Success rate: {metrics['success_rate']}%")
print(f"Avg response: {metrics['avg_response_time_ms']}ms")
print(f"Cache hits: {metrics['requests_cached']}")
```

## Configuration

```python
from pathlib import Path
from airbnb_scraper import AirbnbScraper, ScraperConfig

config = ScraperConfig(
    max_concurrent_requests=10,    # Parallel requests (default: 5)
    min_request_interval=0.5,      # Seconds between requests
    max_retries=3,                 # Retry attempts
    cache_dir=Path("/app/cache"), # Cache location
    cache_ttl_search=7200,         # Search cache: 2 hours
    cache_ttl_details=86400,       # Details cache: 24 hours
    request_timeout=60.0,          # HTTP timeout
)

scraper = AirbnbScraper(currency="USD", locale="en", config=config)
```

## Data Fields

### ListingBasic (from search)

| Field | Type | Description |
|-------|------|-------------|
| airbnb_id | str | Unique listing ID |
| name | str | Listing title |
| url | str | Full URL |
| price_per_night | float | Nightly price |
| rating | float | Average rating (0-5) |
| reviews_count | int | Number of reviews |
| room_type | str | entire_home, private_room, shared_room |
| bedrooms | int | Number of bedrooms |
| beds | int | Number of beds |
| bathrooms | float | Number of bathrooms |
| max_guests | int | Maximum capacity |
| latitude | float | GPS latitude |
| longitude | float | GPS longitude |
| city | str | City name |
| images | List[str] | Image URLs (up to 10) |
| amenities | List[str] | Amenity names |
| amenity_ids | List[int] | Amenity IDs |
| host_id | str | Host ID |
| is_superhost | bool | Superhost status |
| instant_bookable | bool | Instant booking available |

### ListingDetails (from enrichment)

All fields from ListingBasic plus:

| Field | Type | Description |
|-------|------|-------------|
| description | str | Full description |
| images | List[str] | All images (up to 20) |
| host_name | str | Host name |
| host_is_superhost | bool | Superhost status |
| cleaning_fee | float | Cleaning fee |
| service_fee | float | Service fee |

## Amenity IDs

Common amenities for filtering:

| ID | Name |
|----|------|
| 4 | Wifi |
| 5 | Air conditioning |
| 8 | Kitchen |
| 9 | Free parking |
| 30 | Heating |
| 33 | Washer |
| 34 | Dryer |
| 145 | Pets allowed |
| 251 | Dedicated workspace |
| 280 | Pool |

Full list available via `AMENITIES_MAP`.

## Performance

| Operation | Speed | Notes |
|-----------|-------|-------|
| Search 50 listings | ~2s | ~25 listings/sec |
| Search (cached) | <1ms | 1000x+ speedup |
| Bounds 100 listings | ~1s | ~100 listings/sec |
| Enrich 1 listing | ~0.5s | HTML parsing |

## License

MIT