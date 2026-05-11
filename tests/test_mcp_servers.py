"""Tests for MCP server tools — validates mock data and tool logic."""

from src.mcp_servers.search.mock_db import FLIGHTS, HOTELS
from src.mcp_servers.booking.mock_db import create_booking, cancel_booking, get_booking, list_bookings, bookings
from src.mcp_servers.expense.mock_db import submit_expense, check_policy, get_expenses, expenses


class TestSearchMockDB:
    def test_flights_have_required_fields(self):
        for f in FLIGHTS:
            assert "id" in f
            assert "origin" in f
            assert "destination" in f
            assert "price" in f

    def test_hotels_have_required_fields(self):
        for h in HOTELS:
            assert "id" in h
            assert "city" in h
            assert "price_per_night" in h

    def test_flights_not_empty(self):
        assert len(FLIGHTS) > 0

    def test_hotels_not_empty(self):
        assert len(HOTELS) > 0


class TestBookingMockDB:
    def setup_method(self):
        bookings.clear()

    def test_create_booking(self):
        result = create_booking("flight", "FL001", {"passenger_name": "Test User"})
        assert result["booking_id"].startswith("BK-")
        assert result["status"] == "confirmed"
        assert result["type"] == "flight"

    def test_cancel_booking(self):
        result = create_booking("hotel", "HT001", {"guest_name": "Test"})
        cancelled = cancel_booking(result["booking_id"])
        assert cancelled["status"] == "cancelled"

    def test_cancel_nonexistent(self):
        assert cancel_booking("BK-NONEXISTENT") is None

    def test_get_booking(self):
        result = create_booking("flight", "FL001", {"passenger_name": "Test"})
        found = get_booking(result["booking_id"])
        assert found is not None
        assert found["booking_id"] == result["booking_id"]

    def test_list_bookings(self):
        create_booking("flight", "FL001", {"passenger_name": "A"})
        create_booking("hotel", "HT001", {"guest_name": "B"})
        assert len(list_bookings()) == 2


class TestExpenseMockDB:
    def setup_method(self):
        expenses.clear()

    def test_check_policy_within_limit(self):
        result = check_policy(50.0, "meals")
        assert result["within_policy"] is True

    def test_check_policy_over_limit(self):
        result = check_policy(100.0, "meals")
        assert result["within_policy"] is False
        assert result["reason"] is not None

    def test_check_policy_unknown_category(self):
        result = check_policy(10.0, "unknown")
        assert result["within_policy"] is False

    def test_submit_expense_within_policy(self):
        result = submit_expense(50.0, "meals", "lunch", "EMP001")
        assert result["status"] == "approved"

    def test_submit_expense_over_policy(self):
        result = submit_expense(500.0, "meals", "fancy dinner", "EMP001")
        assert result["status"] == "pending_review"

    def test_get_expenses_by_user(self):
        submit_expense(50.0, "meals", "lunch", "EMP001")
        submit_expense(30.0, "transport", "taxi", "EMP002")
        assert len(get_expenses("EMP001")) == 1
        assert len(get_expenses("EMP002")) == 1
