"""Offer date formatting: DD/Full Month Name/YYYY, and no other format."""

from __future__ import annotations

import datetime
from typing import Optional


def format_offer_date(date: Optional[datetime.date] = None) -> str:
    d = date or datetime.date.today()
    return f"{d.day:02d}/{d.strftime('%B')}/{d.year:04d}"
