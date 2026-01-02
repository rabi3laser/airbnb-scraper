"""
Tests for Airbnb Scraper
"""

import pytest
import asyncio
from pathlib import Path
from airbnb_scraper import AirbnbScraper, ScraperConfig, ListingBasic, CacheManager


class TestCacheManager:
    """Tests for cache functionality"""
    
    def test_cache_set_get(self, tmp_path):
        cache = CacheManager(tmp_path / "test.db")
        
        cache.set("key1", {"data": "value"}, ttl=3600)
        result = cache.get("key1")
        
        assert result == {"data": "value"}
    
    def test_cache_expired(self, tmp_path):
        cache = CacheManager(tmp_path / "test.db")
        
        cache.set("key1", {"data": "value"}, ttl=0)  # Instant expiry
        result = cache.get("key1")
        
        assert result is None
    
    def test_cache_stats(self, tmp_path):
        cache = CacheManager(tmp_path / "test.db")
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        stats = cache.stats()
        assert stats["total_entries"] == 2


class TestScraperConfig:
    """Tests for configuration"""
    
    def test_default_config(self):
        config = ScraperConfig()
        
        assert config.max_concurrent_requests == 5
        assert config.max_retries == 3
        assert config.cache_ttl_search == 3600
    
    def test_custom_config(self):
        config = ScraperConfig(
            max_concurrent_requests=10,
            cache_ttl_search=7200
        )
        
        assert config.max_concurrent_requests == 10
        assert config.cache_ttl_search == 7200


class TestAirbnbScraper:
    """Integration tests for scraper"""
    
    @pytest.fixture
    def scraper(self, tmp_path):
        config = ScraperConfig(cache_dir=tmp_path)
        return AirbnbScraper(currency="EUR", config=config)
    
    @pytest.mark.asyncio
    async def test_search_listings(self, scraper):
        """Test basic search functionality"""
        listings = await scraper.search_listings(
            location="Paris, France",
            max_listings=5,
            use_cache=False
        )
        
        assert len(listings) > 0
        assert all(isinstance(l, ListingBasic) for l in listings)
        assert all(l.airbnb_id for l in listings)
        
        await scraper.close()
    
    @pytest.mark.asyncio
    async def test_search_with_cache(self, scraper):
        """Test caching behavior"""
        # First call
        listings1 = await scraper.search_listings(
            location="London, UK",
            max_listings=5,
            use_cache=True
        )
        
        # Second call should hit cache
        scraper.reset_metrics()
        listings2 = await scraper.search_listings(
            location="London, UK",
            max_listings=5,
            use_cache=True
        )
        
        assert scraper.get_metrics()["requests_cached"] == 1
        assert len(listings1) == len(listings2)
        
        await scraper.close()
    
    @pytest.mark.asyncio
    async def test_metrics(self, scraper):
        """Test metrics tracking"""
        await scraper.search_listings(
            location="Rome, Italy",
            max_listings=5,
            use_cache=False
        )
        
        metrics = scraper.get_metrics()
        
        assert metrics["requests_total"] > 0
        assert metrics["success_rate"] > 0
        
        await scraper.close()
    
    @pytest.mark.asyncio
    async def test_context_manager(self, tmp_path):
        """Test async context manager"""
        config = ScraperConfig(cache_dir=tmp_path)
        
        async with AirbnbScraper(config=config) as scraper:
            listings = await scraper.search_listings(
                location="Berlin, Germany",
                max_listings=3
            )
            assert len(listings) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])