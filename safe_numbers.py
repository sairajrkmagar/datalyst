"""
Numbers from real files can be NaN (not a number) or infinite. Python's int() crashes on both.
Every "is this a whole number?" check in the app goes through here.
"""

import math


def is_whole(number):
    """True for 3.0 and 7, False for 3.5, nan and inf (never raises)."""
    try:
        return bool(math.isfinite(number) and number == int(number))
    except (TypeError, ValueError, OverflowError):
        return False


def is_finite(number):
    try:
        return bool(math.isfinite(number))
    except (TypeError, ValueError):
        return False
