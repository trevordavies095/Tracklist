"""
Test file to verify async test support is properly configured.
"""

import pytest
import asyncio
from httpx import AsyncClient


class TestAsyncSupport:
    """Test that async support is working correctly."""
    
    @pytest.mark.asyncio
    async def test_basic_async_function(self):
        """Test that basic async functions work."""
        async def sample_async_function():
            await asyncio.sleep(0.01)
            return "async works"
        
        result = await sample_async_function()
        assert result == "async works"
    
    @pytest.mark.asyncio
    async def test_async_http_client(self):
        """Test async HTTP client without fixture."""
        from httpx import AsyncClient
        from app.main import app
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_multiple_async_operations(self):
        """Test multiple concurrent async operations."""
        async def fetch_value(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2
        
        # Run multiple async operations concurrently
        results = await asyncio.gather(
            fetch_value(1),
            fetch_value(2),
            fetch_value(3)
        )
        
        assert results == [2, 4, 6]
    
    @pytest.mark.asyncio
    async def test_auto_async_mode(self):
        """Test that async tests work with asyncio configuration."""
        # With asyncio_mode=strict in pytest.ini, we need the decorator
        await asyncio.sleep(0.01)
        assert True