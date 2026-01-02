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
    min_price=50,
    max_price=200,
    room_types=["Entire home"],
    amenities=[4, 8],  # Wifi, Kitchen
    superhost_only=True,
    max_listings=100
)
```

### Geographic Bounds Search

```python
listings = await scraper.search_by_bounds(
    ne_lat=48.90, ne_lng=2.45,
    sw_lat=48.80, sw_lng=2.25,
    max_listings=500,
    price_bins=8
)
```

### Batch Enrichment

```python
listings = await scraper.search_listings(location="Rome", max_listings=20)
enriched = await scraper.enrich_listings(listings, max_concurrent=3)
```

## Amenity IDs

| ID | Name |
|----|------|
| 4 | Wifi |
| 5 | Air conditioning |
| 8 | Kitchen |
| 9 | Free parking |
| 280 | Pool |

## License

MIT
