"""
Airbnb Scraper - High-performance scraping library
==================================================

A production-ready Airbnb scraper with:
- Parallel requests (5x faster)
- SQLite caching (1000x faster for cached data)
- Automatic retry with exponential backoff
- Rate limiting to avoid blocks
- 90+ data fields per listing

Quick Start:
-----------
```python
from pathlib import Path
from airbnb_scraper import AirbnbScraper, ScraperConfig

async def main():
    config = ScraperConfig(cache_dir=Path("/tmp/cache"))
    
    async with AirbnbScraper(currency="EUR", config=config) as scraper:
        listings = await scraper.search_listings(
            location="Paris, France",
            max_listings=50
        )
        print(scraper.get_metrics())
```
"""

from .scraper import (
    AirbnbScraper,
    ScraperConfig,
    ListingBasic,
    ListingDetails,
    ScraperMetrics,
    AMENITIES_MAP,
)

from .cache import CacheManager

__version__ = "1.0.0"
__author__ = "rabi3laser"

__all__ = [
    "AirbnbScraper",
    "ScraperConfig", 
    "ListingBasic",
    "ListingDetails",
    "ScraperMetrics",
    "CacheManager",
    "AMENITIES_MAP",
]
