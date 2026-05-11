from fastmcp import FastMCP

try:
    from .mock_db import FLIGHTS, HOTELS
except ImportError:
    from mock_db import FLIGHTS, HOTELS

mcp = FastMCP("search-mcp", instructions="Search for flights and hotels.")


@mcp.tool()
def search_flights(origin: str, destination: str, date: str | None = None) -> list[dict]:
    """Search available flights by origin and destination airport codes.

    Args:
        origin: Origin airport code (e.g., SFO, JFK, LAX)
        destination: Destination airport code
        date: Optional date filter (YYYY-MM-DD)
    """
    results = [
        f for f in FLIGHTS
        if f["origin"].upper() == origin.upper()
        and f["destination"].upper() == destination.upper()
    ]
    if date:
        results = [f for f in results if f["date"] == date]
    return results


@mcp.tool()
def search_hotels(city: str, max_price: float | None = None) -> list[dict]:
    """Search available hotels by city name.

    Args:
        city: City name (e.g., New York, Chicago, London)
        max_price: Optional maximum price per night filter
    """
    results = [h for h in HOTELS if h["city"].lower() == city.lower()]
    if max_price is not None:
        results = [h for h in results if h["price_per_night"] <= max_price]
    return results


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
