"""
framework/waits.py
------------------
Simple timing helpers used across all page objects.
"""

import time


def sleep_seconds(seconds: float) -> None:
    """Sleep for *seconds*. Named function for easy mocking in tests."""
    time.sleep(seconds)
