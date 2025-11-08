"""Market hours utilities."""

from datetime import datetime, time
import pytz
from typing import Optional

from app.config import settings


class MarketHours:
    """Utilities for checking US stock market hours."""

    # Market timezone
    NY_TZ = pytz.timezone('America/New_York')

    # Regular trading hours (Eastern Time)
    MARKET_OPEN = time(9, 30)  # 9:30 AM ET
    MARKET_CLOSE = time(16, 0)  # 4:00 PM ET

    # Pre-market hours
    PRE_MARKET_OPEN = time(4, 0)  # 4:00 AM ET
    PRE_MARKET_CLOSE = time(9, 30)  # 9:30 AM ET

    # After-hours
    AFTER_HOURS_OPEN = time(16, 0)  # 4:00 PM ET
    AFTER_HOURS_CLOSE = time(20, 0)  # 8:00 PM ET

    # Known US market holidays (2025)
    # Note: This should be updated yearly or fetched from an API
    MARKET_HOLIDAYS_2025 = [
        datetime(2025, 1, 1),   # New Year's Day
        datetime(2025, 1, 20),  # Martin Luther King Jr. Day
        datetime(2025, 2, 17),  # Presidents' Day
        datetime(2025, 4, 18),  # Good Friday
        datetime(2025, 5, 26),  # Memorial Day
        datetime(2025, 6, 19),  # Juneteenth
        datetime(2025, 7, 4),   # Independence Day
        datetime(2025, 9, 1),   # Labor Day
        datetime(2025, 11, 27), # Thanksgiving
        datetime(2025, 12, 25), # Christmas
    ]

    @classmethod
    def get_current_time_et(cls) -> datetime:
        """Get current time in Eastern Time."""
        return datetime.now(cls.NY_TZ)

    @classmethod
    def is_market_open(cls, dt: Optional[datetime] = None) -> bool:
        """
        Check if the US stock market is currently open for regular trading.

        Args:
            dt: Optional datetime to check. If None, uses current time.

        Returns:
            bool: True if market is open, False otherwise.
        """
        if dt is None:
            dt = cls.get_current_time_et()
        elif dt.tzinfo is None:
            # Assume UTC if no timezone
            dt = pytz.utc.localize(dt).astimezone(cls.NY_TZ)
        else:
            dt = dt.astimezone(cls.NY_TZ)

        # Check if weekend
        if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Check if holiday
        if cls.is_holiday(dt):
            return False

        # Check if within market hours
        current_time = dt.time()
        return cls.MARKET_OPEN <= current_time < cls.MARKET_CLOSE

    @classmethod
    def is_pre_market(cls, dt: Optional[datetime] = None) -> bool:
        """
        Check if currently in pre-market hours.

        Args:
            dt: Optional datetime to check. If None, uses current time.

        Returns:
            bool: True if in pre-market, False otherwise.
        """
        if dt is None:
            dt = cls.get_current_time_et()
        elif dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(cls.NY_TZ)
        else:
            dt = dt.astimezone(cls.NY_TZ)

        # Check if weekend
        if dt.weekday() >= 5:
            return False

        # Check if holiday
        if cls.is_holiday(dt):
            return False

        # Check if within pre-market hours
        current_time = dt.time()
        return cls.PRE_MARKET_OPEN <= current_time < cls.PRE_MARKET_CLOSE

    @classmethod
    def is_after_hours(cls, dt: Optional[datetime] = None) -> bool:
        """
        Check if currently in after-hours trading.

        Args:
            dt: Optional datetime to check. If None, uses current time.

        Returns:
            bool: True if in after-hours, False otherwise.
        """
        if dt is None:
            dt = cls.get_current_time_et()
        elif dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(cls.NY_TZ)
        else:
            dt = dt.astimezone(cls.NY_TZ)

        # Check if weekend
        if dt.weekday() >= 5:
            return False

        # Check if holiday
        if cls.is_holiday(dt):
            return False

        # Check if within after-hours
        current_time = dt.time()
        return cls.AFTER_HOURS_OPEN <= current_time < cls.AFTER_HOURS_CLOSE

    @classmethod
    def is_holiday(cls, dt: datetime) -> bool:
        """
        Check if the given date is a US market holiday.

        Args:
            dt: Datetime to check.

        Returns:
            bool: True if holiday, False otherwise.
        """
        # Convert to Eastern Time and get date only
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(cls.NY_TZ)
        else:
            dt = dt.astimezone(cls.NY_TZ)

        date_only = dt.date()

        # Check against known holidays
        for holiday in cls.MARKET_HOLIDAYS_2025:
            if holiday.date() == date_only:
                return True

        return False

    @classmethod
    def get_next_market_open(cls, dt: Optional[datetime] = None) -> datetime:
        """
        Get the next market open time.

        Args:
            dt: Optional datetime to check from. If None, uses current time.

        Returns:
            datetime: Next market open time.
        """
        if dt is None:
            dt = cls.get_current_time_et()
        elif dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(cls.NY_TZ)
        else:
            dt = dt.astimezone(cls.NY_TZ)

        # If market is currently open, return current open time
        if cls.is_market_open(dt):
            return dt.replace(
                hour=cls.MARKET_OPEN.hour,
                minute=cls.MARKET_OPEN.minute,
                second=0,
                microsecond=0
            )

        # Otherwise, find next trading day
        next_day = dt.replace(hour=cls.MARKET_OPEN.hour, minute=cls.MARKET_OPEN.minute, second=0, microsecond=0)

        # If past market close, start from next day
        if dt.time() >= cls.MARKET_CLOSE:
            next_day = next_day.replace(day=next_day.day + 1)

        # Skip weekends and holidays
        max_iterations = 10  # Prevent infinite loop
        for _ in range(max_iterations):
            if next_day.weekday() < 5 and not cls.is_holiday(next_day):
                return next_day
            next_day = next_day.replace(day=next_day.day + 1)

        return next_day

    @classmethod
    def get_next_market_close(cls, dt: Optional[datetime] = None) -> datetime:
        """
        Get the next market close time.

        Args:
            dt: Optional datetime to check from. If None, uses current time.

        Returns:
            datetime: Next market close time.
        """
        if dt is None:
            dt = cls.get_current_time_et()
        elif dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(cls.NY_TZ)
        else:
            dt = dt.astimezone(cls.NY_TZ)

        # If market is currently open, return today's close
        if cls.is_market_open(dt):
            return dt.replace(
                hour=cls.MARKET_CLOSE.hour,
                minute=cls.MARKET_CLOSE.minute,
                second=0,
                microsecond=0
            )

        # Otherwise, find next trading day's close
        next_close = dt.replace(hour=cls.MARKET_CLOSE.hour, minute=cls.MARKET_CLOSE.minute, second=0, microsecond=0)

        # If past market close, start from next day
        if dt.time() >= cls.MARKET_CLOSE:
            next_close = next_close.replace(day=next_close.day + 1)

        # Skip weekends and holidays
        max_iterations = 10
        for _ in range(max_iterations):
            if next_close.weekday() < 5 and not cls.is_holiday(next_close):
                return next_close
            next_close = next_close.replace(day=next_close.day + 1)

        return next_close

    @classmethod
    def is_extended_market_open(cls, dt: Optional[datetime] = None) -> bool:
        """
        Check if market is open for extended hours trading (pre-market + regular + after-hours).

        This checks if we're in any trading session: 4 AM - 8 PM ET.
        Only returns True if extended hours are enabled in config.

        Args:
            dt: Optional datetime to check. If None, uses current time.

        Returns:
            bool: True if extended market is open, False otherwise.
        """
        # Check if extended hours are enabled in config
        if not settings.enable_extended_hours:
            return cls.is_market_open(dt)

        # Extended hours enabled - check all sessions
        return (
            cls.is_market_open(dt) or
            cls.is_pre_market(dt) or
            cls.is_after_hours(dt)
        )

    @classmethod
    def get_market_status(cls, dt: Optional[datetime] = None) -> str:
        """
        Get a string describing the current market status.

        Args:
            dt: Optional datetime to check. If None, uses current time.

        Returns:
            str: Market status ("open", "pre-market", "after-hours", "closed")
        """
        if cls.is_market_open(dt):
            return "open"
        elif cls.is_pre_market(dt):
            return "pre-market"
        elif cls.is_after_hours(dt):
            return "after-hours"
        else:
            return "closed"


# Convenience functions
def is_market_open() -> bool:
    """Check if market is currently open."""
    return MarketHours.is_market_open()


def get_market_status() -> str:
    """Get current market status."""
    return MarketHours.get_market_status()


def get_current_time_et() -> datetime:
    """Get current time in Eastern Time."""
    return MarketHours.get_current_time_et()
