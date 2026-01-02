"""
Airbnb Scraper - Core scraping functionality
"""

import json
import logging
import re
import asyncio
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field

import httpx

from .cache import CacheManager

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

@dataclass
class ScraperConfig:
    """
    Scraper configuration.
    
    Attributes:
        min_request_interval: Seconds between sequential requests
        max_concurrent_requests: Maximum parallel requests
        max_retries: Number of retry attempts
        retry_backoff_base: Base for exponential backoff
        cache_dir: Directory for cache database
        cache_ttl_search: Cache TTL for search results (seconds)
        cache_ttl_details: Cache TTL for listing details (seconds)
        request_timeout: HTTP request timeout
    """
    min_request_interval: float = 0.5
    max_concurrent_requests: int = 5
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    cache_dir: Path = Path("/tmp/airbnb_scraper_cache")
    cache_ttl_search: int = 3600  # 1 hour
    cache_ttl_details: int = 86400  # 24 hours
    request_timeout: float = 30.0
    
    # API constants
    api_key: str = "d306zoyjsyarp7ifhu67rjxn52tv0t20"
    base_url: str = "https://www.airbnb.com"
    explore_hash: str = "13aa9971e70fbf5ab888f2a851c765ea098d8ae68c81e1f4ce06e2046d91b6ea"


# ============================================
# AMENITIES MAPPING
# ============================================

AMENITIES_MAP = {
    1: "TV", 4: "Wifi", 5: "Air conditioning", 7: "Pool", 8: "Kitchen",
    9: "Free parking", 10: "Paid parking", 11: "Elevator", 12: "Wheelchair accessible",
    15: "Gym", 16: "Hot tub", 21: "Breakfast", 23: "Doorman", 25: "Hot tub",
    27: "Indoor fireplace", 30: "Heating", 33: "Washer", 34: "Dryer", 
    35: "Smoke detector", 36: "Carbon monoxide detector", 37: "First aid kit", 
    39: "Fire extinguisher", 40: "Essentials", 41: "Shampoo", 44: "Hair dryer", 
    45: "Iron", 46: "Laptop workspace", 47: "Private entrance", 51: "Self check-in",
    54: "Lock on bedroom door", 57: "Hangers", 58: "Bed linens", 
    77: "Hot water", 85: "Microwave", 86: "Coffee maker", 89: "Dishwasher", 
    90: "Refrigerator", 91: "Dishes and silverware", 92: "Cooking basics", 
    93: "Oven", 94: "Stove", 95: "BBQ grill", 96: "Patio or balcony", 
    100: "Backyard", 104: "Luggage dropoff allowed", 137: "Long term stays allowed",
    145: "Pets allowed", 251: "Dedicated workspace", 280: "Pool", 286: "EV charger",
}


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class ListingBasic:
    """Basic listing data from search results."""
    airbnb_id: str
    name: str
    url: str
    price_per_night: float
    total_price: float
    rating: float
    reviews_count: int
    room_type: str
    bedrooms: int
    bathrooms: float
    beds: int
    max_guests: int
    latitude: float
    longitude: float
    city: str
    neighborhood: str
    image_url: str
    images: List[str] = field(default_factory=list)
    amenity_ids: List[int] = field(default_factory=list)
    amenities: List[str] = field(default_factory=list)
    host_id: str = ""
    is_superhost: bool = False
    instant_bookable: bool = False
    is_new: bool = False
    scraped_at: str = ""


@dataclass 
class ListingDetails:
    """Detailed listing data from HTML parsing."""
    airbnb_id: str
    name: str
    url: str
    description: str = ""
    property_type: str = ""
    room_type: str = ""
    bedrooms: int = 0
    beds: int = 0
    bathrooms: float = 0
    max_guests: int = 0
    price_per_night: float = 0
    cleaning_fee: float = 0
    service_fee: float = 0
    total_price: float = 0
    currency: str = "EUR"
    latitude: float = 0
    longitude: float = 0
    city: str = ""
    address: str = ""
    rating: float = 0
    reviews_count: int = 0
    host_id: str = ""
    host_name: str = ""
    host_is_superhost: bool = False
    images: List[str] = field(default_factory=list)
    amenities: List[str] = field(default_factory=list)
    scraped_at: str = ""


@dataclass
class ScraperMetrics:
    """Performance metrics for monitoring."""
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    requests_cached: int = 0
    avg_response_time: float = 0
    total_listings_scraped: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def success_rate(self) -> float:
        if self.requests_total == 0:
            return 0
        return self.requests_success / self.requests_total * 100
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    def to_dict(self) -> dict:
        return {
            "requests_total": self.requests_total,
            "requests_success": self.requests_success,
            "requests_failed": self.requests_failed,
            "requests_cached": self.requests_cached,
            "success_rate": round(self.success_rate, 2),
            "avg_response_time_ms": round(self.avg_response_time * 1000, 2),
            "total_listings_scraped": self.total_listings_scraped,
            "elapsed_time_sec": round(self.elapsed_time, 2),
        }


# ============================================
# MAIN SCRAPER CLASS
# ============================================

class AirbnbScraper:
    """
    High-performance Airbnb scraper.
    
    Features:
    - Parallel requests (configurable concurrency)
    - SQLite caching with TTL
    - Automatic retry with exponential backoff
    - Rate limiting to avoid blocks
    - Comprehensive metrics
    """
    
    def __init__(
        self, 
        currency: str = "EUR", 
        locale: str = "en",
        config: Optional[ScraperConfig] = None
    ):
        self.config = config or ScraperConfig()
        self.currency = currency
        self.locale = locale
        
        self.metrics = ScraperMetrics()
        
        cache_db = self.config.cache_dir / "scraper_cache.db"
        self.cache = CacheManager(cache_db)
        
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)
        self._last_request_time = 0
        
        self.client = httpx.AsyncClient(
            timeout=self.config.request_timeout,
            headers={
                "x-airbnb-api-key": self.config.api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            http2=True,
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self.config.min_request_interval:
            await asyncio.sleep(self.config.min_request_interval - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()
    
    async def _request_with_retry(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        """Execute HTTP request with retry logic."""
        async with self._semaphore:
            await self._rate_limit()
            
            for attempt in range(self.config.max_retries):
                try:
                    start_time = time.time()
                    
                    if method.upper() == "GET":
                        response = await self.client.get(url, **kwargs)
                    else:
                        response = await self.client.post(url, **kwargs)
                    
                    elapsed = time.time() - start_time
                    self.metrics.requests_total += 1
                    self.metrics.avg_response_time = (
                        (self.metrics.avg_response_time * (self.metrics.requests_total - 1) + elapsed) 
                        / self.metrics.requests_total
                    )
                    
                    if response.status_code == 200:
                        self.metrics.requests_success += 1
                        return response
                    elif response.status_code == 429:
                        wait_time = self.config.retry_backoff_base ** (attempt + 2)
                        logger.warning(f"Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    elif response.status_code >= 500:
                        wait_time = self.config.retry_backoff_base ** attempt
                        logger.warning(f"Server error {response.status_code}, retry {attempt+1}")
                        await asyncio.sleep(wait_time)
                    else:
                        self.metrics.requests_failed += 1
                        return None
                        
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    wait_time = self.config.retry_backoff_base ** attempt
                    logger.warning(f"Network error: {e}, retry {attempt+1}")
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
                    self.metrics.requests_failed += 1
                    return None
            
            self.metrics.requests_failed += 1
            return None
    
    def _cache_key(self, prefix: str, *args) -> str:
        data = f"{prefix}:{':'.join(str(a) for a in args)}"
        return hashlib.md5(data.encode()).hexdigest()
    
    async def search_listings(
        self,
        location: str,
        checkin: Optional[str] = None,
        checkout: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        guests: int = 2,
        room_types: Optional[List[str]] = None,
        amenities: Optional[List[int]] = None,
        superhost_only: bool = False,
        instant_book: bool = False,
        min_bedrooms: int = 0,
        min_bathrooms: int = 0,
        max_listings: int = 50,
        use_cache: bool = True,
    ) -> List[ListingBasic]:
        """Search for Airbnb listings."""
        logger.info(f"[SEARCH] {location} (max: {max_listings})")
        
        if not checkin or not checkout:
            checkin = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            checkout = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        
        cache_key = self._cache_key(
            "search", location, checkin, checkout, min_price, max_price,
            guests, str(room_types), str(amenities), superhost_only, max_listings
        )
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"[CACHE HIT] {len(cached)} listings")
                self.metrics.requests_cached += 1
                return [ListingBasic(**l) for l in cached]
        
        all_listings = []
        seen_ids: Set[str] = set()
        max_pages = min(10, (max_listings // 20) + 2)
        
        first_page = await self._fetch_search_page(
            location, checkin, checkout, min_price, max_price,
            guests, room_types, amenities, superhost_only, 0
        )
        
        for l in first_page:
            if l.airbnb_id not in seen_ids:
                seen_ids.add(l.airbnb_id)
                all_listings.append(l)
        
        if len(all_listings) < max_listings:
            remaining_pages = min(max_pages - 1, (max_listings - len(all_listings)) // 20 + 1)
            
            if remaining_pages > 0:
                tasks = [
                    self._fetch_search_page(
                        location, checkin, checkout, min_price, max_price,
                        guests, room_types, amenities, superhost_only, 
                        (page + 1) * 20
                    )
                    for page in range(remaining_pages)
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, list):
                        for l in result:
                            if l.airbnb_id not in seen_ids and len(all_listings) < max_listings:
                                seen_ids.add(l.airbnb_id)
                                all_listings.append(l)
        
        self.metrics.total_listings_scraped += len(all_listings)
        
        if use_cache and all_listings:
            self.cache.set(cache_key, [asdict(l) for l in all_listings], self.config.cache_ttl_search)
        
        logger.info(f"[SEARCH] Found {len(all_listings)} unique listings")
        return all_listings[:max_listings]
    
    async def _fetch_search_page(
        self, location: str, checkin: str, checkout: str,
        min_price: Optional[int], max_price: Optional[int],
        guests: int, room_types: Optional[List[str]],
        amenities: Optional[List[int]], superhost_only: bool,
        items_offset: int
    ) -> List[ListingBasic]:
        url = self._build_search_url(
            location, checkin, checkout, min_price, max_price,
            guests, room_types, amenities, superhost_only, items_offset
        )
        response = await self._request_with_retry("GET", url)
        if response:
            return self._parse_search_results(response.json())
        return []
    
    async def search_by_bounds(
        self,
        ne_lat: float, ne_lng: float,
        sw_lat: float, sw_lng: float,
        checkin: Optional[str] = None,
        checkout: Optional[str] = None,
        guests: int = 2,
        max_listings: int = 300,
        price_bins: int = 5,
        use_cache: bool = True,
    ) -> List[ListingBasic]:
        """Search by geographic bounding box with price binning."""
        logger.info(f"[BOUNDS] Searching with {price_bins} price bins")
        
        if not checkin or not checkout:
            checkin = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            checkout = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        
        cache_key = self._cache_key(
            "bounds", ne_lat, ne_lng, sw_lat, sw_lng, checkin, checkout, guests, max_listings, price_bins
        )
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                self.metrics.requests_cached += 1
                return [ListingBasic(**l) for l in cached]
        
        price_ranges = [
            (0, 50), (50, 100), (100, 150), (150, 200), (200, 300),
            (300, 500), (500, 1000), (1000, 5000)
        ][:price_bins]
        
        tasks = [
            self._fetch_bounds_search(ne_lat, ne_lng, sw_lat, sw_lng, checkin, checkout, guests, min_p, max_p)
            for min_p, max_p in price_ranges
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_listings = []
        seen_ids: Set[str] = set()
        
        for result in results:
            if isinstance(result, list):
                for l in result:
                    if l.airbnb_id not in seen_ids:
                        seen_ids.add(l.airbnb_id)
                        all_listings.append(l)
        
        all_listings = all_listings[:max_listings]
        self.metrics.total_listings_scraped += len(all_listings)
        
        if use_cache and all_listings:
            self.cache.set(cache_key, [asdict(l) for l in all_listings], self.config.cache_ttl_search)
        
        logger.info(f"[BOUNDS] Found {len(all_listings)} unique listings")
        return all_listings
    
    async def _fetch_bounds_search(
        self, ne_lat: float, ne_lng: float, sw_lat: float, sw_lng: float,
        checkin: str, checkout: str, guests: int, min_price: int, max_price: int
    ) -> List[ListingBasic]:
        request_params = {
            "metadataOnly": False, "version": "1.8.3", "itemsPerGrid": 50,
            "tabId": "home_tab", "refinementPaths": ["/homes"],
            "checkin": checkin, "checkout": checkout, "adults": guests,
            "priceMin": min_price, "priceMax": max_price,
            "neLat": ne_lat, "neLng": ne_lng, "swLat": sw_lat, "swLng": sw_lng,
            "searchByMap": True, "zoomLevel": 14,
        }
        
        variables = {"request": request_params}
        extensions = {"persistedQuery": {"version": 1, "sha256Hash": self.config.explore_hash}}
        
        url = f"{self.config.base_url}/api/v3/ExploreSearch"
        url += f"?operationName=ExploreSearch&locale={self.locale}&currency={self.currency}"
        url += f"&variables={json.dumps(variables, separators=(',', ':'))}"
        url += f"&extensions={json.dumps(extensions, separators=(',', ':'))}"
        
        response = await self._request_with_retry("GET", url)
        if response:
            return self._parse_search_results(response.json())
        return []
    
    def _build_search_url(
        self, location: str, checkin: str, checkout: str,
        min_price: Optional[int], max_price: Optional[int],
        guests: int, room_types: Optional[List[str]], 
        amenities: Optional[List[int]], superhost_only: bool, items_offset: int = 0
    ) -> str:
        request_params = {
            "metadataOnly": False, "version": "1.8.3", "itemsPerGrid": 20,
            "tabId": "home_tab", "refinementPaths": ["/homes"],
            "source": "structured_search_input_header", "query": location,
            "itemsOffset": items_offset, "checkin": checkin, "checkout": checkout, "adults": guests,
        }
        
        if min_price: request_params["priceMin"] = min_price
        if max_price: request_params["priceMax"] = max_price
        if superhost_only: request_params["superhostFilter"] = True
        if room_types:
            type_map = {"Entire home": "Entire home/apt", "Private room": "Private room", "Shared room": "Shared room"}
            request_params["roomTypes"] = [type_map.get(t, t) for t in room_types]
        if amenities: request_params["amenities"] = amenities
        
        variables = {"request": request_params}
        extensions = {"persistedQuery": {"version": 1, "sha256Hash": self.config.explore_hash}}
        
        url = f"{self.config.base_url}/api/v3/ExploreSearch"
        url += f"?operationName=ExploreSearch&locale={self.locale}&currency={self.currency}"
        url += f"&variables={json.dumps(variables, separators=(',', ':'))}"
        url += f"&extensions={json.dumps(extensions, separators=(',', ':'))}"
        
        return url
    
    def _parse_search_results(self, data: dict) -> List[ListingBasic]:
        listings = []
        try:
            explore = data.get("data", {}).get("dora", {}).get("exploreV3", {})
            sections = explore.get("sections", [])
            
            for section in sections:
                if section.get("__typename") != "DoraExploreV3ListingsSection":
                    continue
                
                for item in section.get("items", []):
                    listing_data = item.get("listing")
                    if not listing_data:
                        continue
                    
                    pricing = item.get("pricingQuote", {}) or {}
                    price = float((pricing.get("rate", {}) or {}).get("amount", 0) or 0)
                    
                    images = [pic.get("picture") for pic in listing_data.get("contextualPictures", [])[:10] if pic.get("picture")]
                    amenity_ids = listing_data.get("amenityIds", [])
                    amenity_names = [AMENITIES_MAP.get(aid, f"Amenity_{aid}") for aid in amenity_ids]
                    
                    listing = ListingBasic(
                        airbnb_id=str(listing_data.get("id", "")),
                        name=listing_data.get("name", ""),
                        url=f"https://www.airbnb.com/rooms/{listing_data.get('id', '')}",
                        price_per_night=price, total_price=price,
                        rating=float(listing_data.get("avgRating", 0) or 0),
                        reviews_count=int(listing_data.get("reviewsCount", 0) or 0),
                        room_type=listing_data.get("roomTypeCategory", ""),
                        bedrooms=int(listing_data.get("bedrooms", 0) or 0),
                        bathrooms=float(listing_data.get("bathrooms", 0) or 0),
                        beds=int(listing_data.get("beds", 0) or 0),
                        max_guests=int(listing_data.get("personCapacity", 0) or 0),
                        latitude=float(listing_data.get("lat", 0) or 0),
                        longitude=float(listing_data.get("lng", 0) or 0),
                        city=listing_data.get("city", ""),
                        neighborhood=listing_data.get("neighborhood", "") or "",
                        image_url=images[0] if images else "",
                        images=images, amenity_ids=amenity_ids, amenities=amenity_names,
                        host_id=str(listing_data.get("user", {}).get("id", "")) if listing_data.get("user") else "",
                        is_superhost=listing_data.get("isSuperhost", False) or False,
                        instant_bookable=pricing.get("canInstantBook", False) or False,
                        is_new=listing_data.get("isNew", False) or False,
                        scraped_at=datetime.utcnow().isoformat(),
                    )
                    listings.append(listing)
        except Exception as e:
            logger.error(f"[PARSE] Error: {str(e)}")
        return listings
    
    async def get_listing_details(
        self, listing_id: str,
        checkin: Optional[str] = None, checkout: Optional[str] = None,
        guests: int = 2, use_cache: bool = True
    ) -> Optional[ListingDetails]:
        """Get detailed listing information."""
        cache_key = self._cache_key("details", listing_id, checkin, checkout)
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                self.metrics.requests_cached += 1
                return ListingDetails(**cached)
        
        if not checkin or not checkout:
            checkin = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            checkout = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        
        url = f"{self.config.base_url}/rooms/{listing_id}"
        params = {"check_in": checkin, "check_out": checkout, "adults": guests}
        
        response = await self._request_with_retry("GET", url, params=params)
        if not response:
            return None
        
        details = self._parse_html_details(response.text, listing_id)
        if details and use_cache:
            self.cache.set(cache_key, asdict(details), self.config.cache_ttl_details)
        return details
    
    async def enrich_listings(
        self, listings: List[ListingBasic],
        checkin: Optional[str] = None, checkout: Optional[str] = None,
        max_concurrent: int = 3
    ) -> List[ListingDetails]:
        """Enrich multiple listings with detailed information."""
        logger.info(f"[ENRICH] Enriching {len(listings)} listings")
        
        if not checkin or not checkout:
            checkin = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            checkout = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        
        enrich_semaphore = asyncio.Semaphore(max_concurrent)
        
        async def enrich_one(listing: ListingBasic) -> Optional[ListingDetails]:
            async with enrich_semaphore:
                return await self.get_listing_details(listing.airbnb_id, checkin, checkout)
        
        tasks = [enrich_one(l) for l in listings]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        enriched = [r for r in results if isinstance(r, ListingDetails)]
        logger.info(f"[ENRICH] Successfully enriched {len(enriched)}/{len(listings)}")
        return enriched
    
    def _parse_html_details(self, html: str, listing_id: str) -> Optional[ListingDetails]:
        details = ListingDetails(
            airbnb_id=listing_id, name="",
            url=f"https://www.airbnb.com/rooms/{listing_id}",
            scraped_at=datetime.utcnow().isoformat()
        )
        
        try:
            schema_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>([^<]+)</script>'
            schemas = re.findall(schema_pattern, html)
            
            for s in schemas:
                try:
                    data = json.loads(s)
                    if data.get('@type') == 'VacationRental':
                        details.name = data.get('name', '')
                        details.description = data.get('description', '')
                        details.latitude = float(data.get('latitude', 0) or 0)
                        details.longitude = float(data.get('longitude', 0) or 0)
                        details.images = data.get('image', [])[:20]
                        details.city = data.get('address', {}).get('addressLocality', '')
                        agg = data.get('aggregateRating', {})
                        details.rating = float(agg.get('ratingValue', 0) or 0)
                        details.reviews_count = int(agg.get('ratingCount', 0) or 0)
                        occ = data.get('containsPlace', {}).get('occupancy', {})
                        if occ:
                            details.max_guests = int(occ.get('value', 0) or 0)
                except json.JSONDecodeError:
                    pass
            
            amenity_pattern = r'"amenities":\s*\[([^\]]+)\]'
            amenity_matches = re.findall(amenity_pattern, html)
            if amenity_matches:
                try:
                    amenities_list = json.loads("[" + amenity_matches[0] + "]")
                    for a in amenities_list:
                        if isinstance(a, dict) and a.get('available') and a.get('title'):
                            details.amenities.append(a['title'])
                except:
                    pass
            
            if '"isSuperhost":true' in html or '"is_superhost":true' in html:
                details.host_is_superhost = True
        except Exception as e:
            logger.error(f"[PARSE_HTML] Error: {str(e)}")
        
        return details
    
    def get_metrics(self) -> dict:
        """Get performance metrics."""
        return self.metrics.to_dict()
    
    def reset_metrics(self):
        """Reset performance metrics."""
        self.metrics = ScraperMetrics()
    
    def clear_cache(self):
        """Clear all cached data."""
        self.cache.clear_all()
        logger.info("[CACHE] Cache cleared")
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache.stats()
    
    @staticmethod
    def listing_to_dict(listing: ListingBasic) -> dict:
        return asdict(listing)
    
    @staticmethod
    def details_to_dict(details: ListingDetails) -> dict:
        return asdict(details)
