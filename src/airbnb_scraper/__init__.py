"""
Airbnb Scraper v3 - High-performance scraping library
=====================================================

Enhanced for algorithm-aligned grading with:
- All 6 sub-category ratings (Guest Favorites criteria)
- Host response metrics (rate, time)
- Guest Favorites badge detection
- Instant Book status
- Min/max nights
- Parallel requests (5x faster)
- SQLite caching (1000x faster for cached data)
- Automatic retry with exponential backoff
- Rate limiting to avoid blocks
- 100+ data fields per listing

Quick Start:
-----------
```python
from pathlib import Path
from airbnb_scraper import AirbnbScraper, ScraperConfig

async def main():
    config = ScraperConfig(cache_dir=Path("/tmp/cache"))
    
    async with AirbnbScraper(currency="EUR", config=config) as scraper:
        # Search listings
        listings = await scraper.search_listings(
            location="Paris, France",
            max_listings=50
        )
        
        # Get detailed info with sub-ratings
        details = await scraper.get_listing_details(listings[0].airbnb_id)
        print(f"Rating: {details.rating}")
        print(f"Cleanliness: {details.rating_cleanliness}")
        print(f"Guest Favorite: {details.is_guest_favorite}")
        
        # Get host profile
        host = await scraper.get_host_profile(details.host_id)
        print(f"Response rate: {host.response_rate}%")
```

For more examples, see the documentation.
"""

__version__ = "3.0.0"
__author__ = "SpyBnB Team"

from .scraper import (
    AirbnbScraper,
    ScraperConfig,
    ListingBasic,
    ListingDetails,
    HostProfile,  # NEW
    ScraperMetrics,
    AMENITIES_MAP,
)

from .cache import CacheManager

__all__ = [
    # Main classes
    "AirbnbScraper",
    "ScraperConfig", 
    
    # Data classes
    "ListingBasic",
    "ListingDetails",
    "HostProfile",  # NEW
    "ScraperMetrics",
    
    # Utilities
    "CacheManager",
    "AMENITIES_MAP",
]
