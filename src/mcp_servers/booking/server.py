"""Booking MCP server — exposes flight and hotel booking tools over StreamableHTTP."""

from fastmcp import FastMCP

try:
    from .mock_db import create_booking, cancel_booking as _cancel, get_booking, list_bookings
except ImportError:
    from mock_db import create_booking, cancel_booking as _cancel, get_booking, list_bookings

mcp = FastMCP("booking-mcp", instructions="Book and manage flight and hotel reservations.")


@mcp.tool()
def book_flight(flight_id: str, passenger_name: str) -> dict:
    """Book a flight for a passenger.

    Args:
        flight_id: The flight ID from search results (e.g., FL001)
        passenger_name: Full name of the passenger
    """
    return create_booking("flight", flight_id, {"passenger_name": passenger_name})


@mcp.tool()
def book_hotel(hotel_id: str, guest_name: str, checkin: str, checkout: str) -> dict:
    """Book a hotel for a guest.

    Args:
        hotel_id: The hotel ID from search results (e.g., HT001)
        guest_name: Full name of the guest
        checkin: Check-in date (YYYY-MM-DD)
        checkout: Check-out date (YYYY-MM-DD)
    """
    return create_booking("hotel", hotel_id, {
        "guest_name": guest_name,
        "checkin": checkin,
        "checkout": checkout,
    })


@mcp.tool()
def cancel_booking(booking_id: str) -> dict:
    """Cancel an existing booking.

    Args:
        booking_id: The booking ID to cancel (e.g., BK-A1B2C3D4)
    """
    result = _cancel(booking_id)
    if result is None:
        return {"error": f"Booking {booking_id} not found"}
    return result


@mcp.tool()
def get_booking_details(booking_id: str) -> dict:
    """Get details of an existing booking.

    Args:
        booking_id: The booking ID to look up
    """
    result = get_booking(booking_id)
    if result is None:
        return {"error": f"Booking {booking_id} not found"}
    return result


@mcp.tool()
def list_all_bookings() -> list[dict]:
    """List all bookings in the system."""
    return list_bookings()


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)
