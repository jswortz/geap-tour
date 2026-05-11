import uuid
from datetime import datetime

bookings: dict[str, dict] = {}


def create_booking(booking_type: str, item_id: str, details: dict) -> dict:
    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
    booking = {
        "booking_id": booking_id,
        "type": booking_type,
        "item_id": item_id,
        "status": "confirmed",
        "created_at": datetime.now().isoformat(),
        **details,
    }
    bookings[booking_id] = booking
    return booking


def cancel_booking(booking_id: str) -> dict | None:
    if booking_id not in bookings:
        return None
    bookings[booking_id]["status"] = "cancelled"
    bookings[booking_id]["cancelled_at"] = datetime.now().isoformat()
    return bookings[booking_id]


def get_booking(booking_id: str) -> dict | None:
    return bookings.get(booking_id)


def list_bookings() -> list[dict]:
    return list(bookings.values())
