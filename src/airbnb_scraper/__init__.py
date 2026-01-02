"""
Airbnb Scraper v3.1 - High-performance scraping library
=======================================================

Enhanced for algorithm-aligned grading with:
- All 6 sub-category ratings (Guest Favorites criteria)
- Host response metrics (rate, time)
- Guest Favorites badge detection
- Instant Book status
- Min/max nights
- **NEW: Calendar/availability scraping**
- **NEW: Orphan night detection**
- **NEW: Demand analysis**
- Parallel requests (5x faster)
- SQLite caching (1000x faster for cached data)
- Automatic retry with exponential backoff
- Rate limiting to avoid blocks
- 100+ data fields per listing

Quick Start:
-----------
```python
from airbnb_scraper import AirbnbScraper, CalendarScraper

async def main():
    # Search and get details
    async with AirbnbScraper(currency="EUR") as scraper:
        listings = await scraper.search_listings("Paris", max_listings=20)
        details = await scraper.get_listing_details(listings[0].airbnb_id)
    
    # Get calendar/availability data
    async with CalendarScraper(currency="EUR") as cal_scraper:
        calendar = await cal_scraper.get_calendar("12345678", months=3)
        
        print(f"Occupancy: {calendar.occupancy_rate}%")
        print(f"Avg price: €{calendar.avg_price}")
        
        # Find orphan nights
        from airbnb_scraper import find_orphan_nights
        orphans = find_orphan_nights(calendar)
        for o in orphans:
            print(f"Orphan: {o['dates']} at €{o['avg_price']}")
```
"""

__version__ = "3.1.0"
__author__ = "SpyBnB Team"

from .scraper import (
    AirbnbScraper,
    ScraperConfig,
    ListingBasic,
    ListingDetails,
    HostProfile,
    ScraperMetrics,
    AMENITIES_MAP,
)

from .calendar import (
    CalendarScraper,
    CalendarDay,
    ListingCalendar,
    find_orphan_nights,
    calculate_demand_score,
)

from .cache import CacheManager

__all__ = [
    # Main classes
    "AirbnbScraper",
    "ScraperConfig", 
    "CalendarScraper",  # NEW
    
    # Data classes
    "ListingBasic",
    "ListingDetails",
    "HostProfile",
    "ScraperMetrics",
    "CalendarDay",      # NEW
    "ListingCalendar",  # NEW
    
    # Utilities
    "CacheManager",
    "AMENITIES_MAP",
    "find_orphan_nights",     # NEW
    "calculate_demand_score", # NEW
]
