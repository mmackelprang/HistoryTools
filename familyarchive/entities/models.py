"""Entity dataclasses for the Family Archive."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Person:
    id: int
    name: str
    alternate_names: Optional[list[str]] = None
    birth_date: Optional[str] = None
    birth_date_precision: Optional[str] = None   # "exact", "month", "year", "decade", "approximate"
    death_date: Optional[str] = None
    death_date_precision: Optional[str] = None
    notes: Optional[str] = None
    source_connector: Optional[str] = None
    external_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Location:
    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: Optional[str] = None  # "exact", "city", "state", "country", "approximate"
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Event:
    id: int
    name: str
    event_type: Optional[str] = None
    start_date: Optional[str] = None
    start_date_precision: Optional[str] = None  # "exact", "month", "year", "decade", "approximate"
    end_date: Optional[str] = None
    end_date_precision: Optional[str] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Timeframe:
    id: int
    name: str
    start_date: Optional[str] = None
    start_date_precision: Optional[str] = None  # "exact", "month", "year", "decade", "approximate"
    end_date: Optional[str] = None
    end_date_precision: Optional[str] = None
    person_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Tag:
    id: int
    name: str
    color: Optional[str] = None
    created_at: Optional[str] = None
