"""
Airbnb Calendar Scraper - Availability and Pricing Data
========================================================

Scrapes calendar data for listings including:
- Daily availability (available/blocked/reserved)
- Price per night by date
- Min/max nights requirements
- Checkout-only days

This data is essential for:
- Dynamic pricing optimization
- Orphan night detection
- Demand/supply analysis
- Competitor availability tracking
"""

import json
import logging
import re
import asyncio
from datetime import datetime, timedelta, date
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CalendarDay:
    """Single day in a listing's calendar."""
    date: str  # YYYY-MM-DD
    available: bool
    price: float
    min_nights: int = 1
    max_nights: int = 365
    is_checkout_only: bool = False
    is_blocked_by_host: bool = False
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class ListingCalendar:
    """Complete calendar for a listing."""
    listing_id: str
    currency: str
    days: List[CalendarDay] = field(default_factory=list)
    scraped_at: str = ""
    
    # Computed stats
    total_days: int = 0
    available_days: int = 0
    blocked_days: int = 0
    avg_price: float = 0
    min_price: float = 0
    max_price: float = 0
    
    def __post_init__(self):
        self._compute_stats()
    
    def _compute_stats(self):
        if not self.days:
            return
        
        self.total_days = len(self.days)
        self.available_days = sum(1 for d in self.days if d.available)
        self.blocked_days = self.total_days - self.available_days
        
        available_prices = [d.price for d in self.days if d.available and d.price > 0]
        if available_prices:
            self.avg_price = sum(available_prices) / len(available_prices)
            self.min_price = min(available_prices)
            self.max_price = max(available_prices)
    
    @property
    def occupancy_rate(self) -> float:
        """Estimated occupancy rate (blocked/total)."""
        if self.total_days == 0:
            return 0
        return self.blocked_days / self.total_days * 100
    
    def get_days_range(self, start_date: str, end_date: str) -> List[CalendarDay]:
        """Get calendar days within a date range."""
        return [d for d in self.days if start_date <= d.date <= end_date]
    
    def get_available_days(self) -> List[CalendarDay]:
        """Get only available days."""
        return [d for d in self.days if d.available]
    
    def get_blocked_days(self) -> List[CalendarDay]:
        """Get only blocked days."""
        return [d for d in self.days if not d.available]
    
    def get_price_for_date(self, target_date: str) -> Optional[float]:
        """Get price for a specific date."""
        for day in self.days:
            if day.date == target_date:
                return day.price
        return None
    
    def to_dict(self) -> dict:
        return {
            "listing_id": self.listing_id,
            "currency": self.currency,
            "scraped_at": self.scraped_at,
            "stats": {
                "total_days": self.total_days,
                "available_days": self.available_days,
                "blocked_days": self.blocked_days,
                "occupancy_rate": round(self.occupancy_rate, 1),
                "avg_price": round(self.avg_price, 2),
                "min_price": self.min_price,
                "max_price": self.max_price,
            },
            "days": [d.to_dict() for d in self.days],
        }


class CalendarScraper:
    """
    Scrapes Airbnb calendar data.
    
    Uses the public calendar API endpoint.
    
    Example:
        scraper = CalendarScraper(currency="EUR")
        calendar = await scraper.get_calendar("12345678", months=3)
        
        print(f"Occupancy: {calendar.occupancy_rate}%")
        print(f"Avg price: €{calendar.avg_price}")
        
        for day in calendar.get_available_days()[:5]:
            print(f"{day.date}: €{day.price}")
    """
    
    def __init__(
        self,
        currency: str = "EUR",
        locale: str = "en",
        api_key: str = "d306zoyjsyarp7ifhu67rjxn52tv0t20",
    ):
        self.currency = currency
        self.locale = locale
        self.api_key = api_key
        self.base_url = "https://www.airbnb.com"
        
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "x-airbnb-api-key": api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
    
    async def close(self):
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def get_calendar(
        self,
        listing_id: str,
        months: int = 3,
        start_date: Optional[str] = None,
    ) -> ListingCalendar:
        """
        Get calendar data for a listing.
        
        Args:
            listing_id: Airbnb listing ID
            months: Number of months to fetch (1-12)
            start_date: Start date (YYYY-MM-DD), defaults to today
            
        Returns:
            ListingCalendar with daily availability and pricing
        """
        months = min(max(months, 1), 12)  # Clamp to 1-12
        
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        
        # Fetch calendar data
        all_days = []
        
        # Method 1: Try the calendar months endpoint
        days_from_months = await self._fetch_calendar_months(
            listing_id, start_dt.month, start_dt.year, months
        )
        
        if days_from_months:
            all_days = days_from_months
        else:
            # Method 2: Fallback to PDP page parsing
            days_from_pdp = await self._fetch_calendar_from_pdp(listing_id, months)
            if days_from_pdp:
                all_days = days_from_pdp
        
        # Create calendar object
        calendar = ListingCalendar(
            listing_id=listing_id,
            currency=self.currency,
            days=all_days,
            scraped_at=datetime.utcnow().isoformat(),
        )
        calendar._compute_stats()
        
        return calendar
    
    async def _fetch_calendar_months(
        self,
        listing_id: str,
        start_month: int,
        start_year: int,
        count: int,
    ) -> List[CalendarDay]:
        """Fetch calendar using the calendar_months endpoint."""
        url = f"{self.base_url}/api/v3/PdpAvailabilityCalendar"
        
        variables = {
            "request": {
                "count": count,
                "listingId": listing_id,
                "month": start_month,
                "year": start_year,
            }
        }
        
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "8f08e03c7bd16fcad3c92a3592c19a8b559a0d0571c37bcddc7c2ca8b81eb7a4"
            }
        }
        
        params = {
            "operationName": "PdpAvailabilityCalendar",
            "locale": self.locale,
            "currency": self.currency,
            "variables": json.dumps(variables, separators=(',', ':')),
            "extensions": json.dumps(extensions, separators=(',', ':')),
        }
        
        try:
            response = await self.client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(f"Calendar API returned {response.status_code}")
                return []
            
            data = response.json()
            return self._parse_calendar_response(data)
            
        except Exception as e:
            logger.error(f"Error fetching calendar: {e}")
            return []
    
    def _parse_calendar_response(self, data: dict) -> List[CalendarDay]:
        """Parse the calendar API response."""
        days = []
        
        try:
            calendar_data = (
                data.get("data", {})
                .get("merlin", {})
                .get("pdpAvailabilityCalendar", {})
            )
            
            months = calendar_data.get("calendarMonths", [])
            
            for month in months:
                for day_data in month.get("days", []):
                    cal_date = day_data.get("calendarDate")
                    if not cal_date:
                        continue
                    
                    # Parse availability
                    available = day_data.get("available", False)
                    
                    # Parse price
                    price_data = day_data.get("price", {})
                    price = 0
                    if price_data:
                        # Try different price formats
                        if isinstance(price_data, dict):
                            price = float(price_data.get("amount", 0) or 0)
                        elif isinstance(price_data, (int, float)):
                            price = float(price_data)
                    
                    # Parse min/max nights
                    min_nights = int(day_data.get("minNights", 1) or 1)
                    max_nights = int(day_data.get("maxNights", 365) or 365)
                    
                    # Check if checkout only
                    is_checkout_only = day_data.get("availableForCheckin", True) == False
                    
                    # Check if blocked by host
                    is_blocked = day_data.get("bookable", True) == False
                    
                    days.append(CalendarDay(
                        date=cal_date,
                        available=available,
                        price=price,
                        min_nights=min_nights,
                        max_nights=max_nights,
                        is_checkout_only=is_checkout_only,
                        is_blocked_by_host=is_blocked and not available,
                    ))
                    
        except Exception as e:
            logger.error(f"Error parsing calendar: {e}")
        
        return days
    
    async def _fetch_calendar_from_pdp(
        self,
        listing_id: str,
        months: int,
    ) -> List[CalendarDay]:
        """Fallback: Extract calendar from listing page."""
        url = f"{self.base_url}/rooms/{listing_id}"
        
        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return []
            
            html = response.text
            return self._parse_calendar_from_html(html, months)
            
        except Exception as e:
            logger.error(f"Error fetching PDP: {e}")
            return []
    
    def _parse_calendar_from_html(self, html: str, months: int) -> List[CalendarDay]:
        """Extract calendar data from HTML."""
        days = []
        
        try:
            # Look for calendar data in script tags
            pattern = r'"calendarMonths":\s*(\[[^\]]+\])'
            match = re.search(pattern, html)
            
            if match:
                calendar_json = match.group(1)
                months_data = json.loads(calendar_json)
                
                for month in months_data[:months]:
                    for day_data in month.get("days", []):
                        if day_data.get("calendarDate"):
                            days.append(CalendarDay(
                                date=day_data["calendarDate"],
                                available=day_data.get("available", False),
                                price=float(day_data.get("price", {}).get("amount", 0) or 0),
                                min_nights=int(day_data.get("minNights", 1) or 1),
                            ))
            
            # Alternative: Look for availability data
            if not days:
                avail_pattern = r'"availabilityCalendar":\s*(\{[^}]+\})'
                avail_match = re.search(avail_pattern, html)
                if avail_match:
                    # Parse alternative format
                    pass
                    
        except Exception as e:
            logger.error(f"Error parsing HTML calendar: {e}")
        
        return days
    
    async def get_calendars_batch(
        self,
        listing_ids: List[str],
        months: int = 3,
        max_concurrent: int = 5,
    ) -> Dict[str, ListingCalendar]:
        """
        Get calendars for multiple listings in parallel.
        
        Args:
            listing_ids: List of listing IDs
            months: Number of months per calendar
            max_concurrent: Max parallel requests
            
        Returns:
            Dict mapping listing_id to ListingCalendar
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_one(lid: str) -> tuple:
            async with semaphore:
                await asyncio.sleep(0.5)  # Rate limiting
                calendar = await self.get_calendar(lid, months)
                return lid, calendar
        
        tasks = [fetch_one(lid) for lid in listing_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        calendars = {}
        for result in results:
            if isinstance(result, tuple):
                lid, calendar = result
                calendars[lid] = calendar
        
        return calendars


# Utility functions

def find_orphan_nights(
    calendar: ListingCalendar,
    max_gap: int = 2,
) -> List[Dict]:
    """
    Find orphan nights (isolated available days between blocked periods).
    
    Args:
        calendar: ListingCalendar to analyze
        max_gap: Maximum gap size to consider orphan (1-2 nights)
        
    Returns:
        List of orphan periods with dates and prices
    """
    orphans = []
    days = sorted(calendar.days, key=lambda d: d.date)
    
    i = 0
    while i < len(days):
        if days[i].available:
            # Found an available day, check if it's orphaned
            gap_start = i
            gap_length = 0
            
            # Count consecutive available days
            while i < len(days) and days[i].available:
                gap_length += 1
                i += 1
            
            # Check if it's truly orphaned (blocked before AND after)
            blocked_before = gap_start == 0 or not days[gap_start - 1].available
            blocked_after = i >= len(days) or not days[i].available
            
            if gap_length <= max_gap and blocked_before and blocked_after:
                orphan_days = days[gap_start:gap_start + gap_length]
                orphans.append({
                    "dates": [d.date for d in orphan_days],
                    "length": gap_length,
                    "prices": [d.price for d in orphan_days],
                    "avg_price": sum(d.price for d in orphan_days) / gap_length if orphan_days else 0,
                })
        else:
            i += 1
    
    return orphans


def calculate_demand_score(calendars: List[ListingCalendar], target_date: str) -> Dict:
    """
    Calculate demand score based on competitor availability.
    
    Args:
        calendars: List of competitor calendars
        target_date: Date to analyze (YYYY-MM-DD)
        
    Returns:
        Dict with demand metrics
    """
    total = len(calendars)
    if total == 0:
        return {"demand_score": 50, "available_count": 0, "blocked_count": 0}
    
    available_count = 0
    blocked_count = 0
    prices = []
    
    for cal in calendars:
        day = next((d for d in cal.days if d.date == target_date), None)
        if day:
            if day.available:
                available_count += 1
                if day.price > 0:
                    prices.append(day.price)
            else:
                blocked_count += 1
    
    # Demand score: 100 = all blocked (high demand), 0 = all available (low demand)
    if total > 0:
        demand_score = (blocked_count / total) * 100
    else:
        demand_score = 50
    
    return {
        "date": target_date,
        "demand_score": round(demand_score, 1),
        "available_count": available_count,
        "blocked_count": blocked_count,
        "total_competitors": total,
        "availability_rate": round(available_count / total * 100, 1) if total > 0 else 0,
        "avg_competitor_price": round(sum(prices) / len(prices), 2) if prices else 0,
        "min_competitor_price": min(prices) if prices else 0,
        "max_competitor_price": max(prices) if prices else 0,
    }
