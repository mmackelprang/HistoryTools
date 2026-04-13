"""Entity CRUD operations and schema management."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .models import Person, Location, Event, Timeframe, Tag


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- Schema --

ENTITY_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS entities_people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    alternate_names TEXT,
    birth_date TEXT,
    birth_date_precision TEXT,
    death_date TEXT,
    death_date_precision TEXT,
    notes TEXT,
    source_connector TEXT,
    external_id TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entities_locations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    latitude REAL,
    longitude REAL,
    precision TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entities_events (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    event_type TEXT,
    start_date TEXT,
    start_date_precision TEXT,
    end_date TEXT,
    end_date_precision TEXT,
    location_id INTEGER REFERENCES entities_locations(id),
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entities_timeframes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT,
    start_date_precision TEXT,
    end_date TEXT,
    end_date_precision TEXT,
    person_id INTEGER REFERENCES entities_people(id),
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS entity_files (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL REFERENCES files(id),
    confidence TEXT,
    created_at TEXT,
    UNIQUE(entity_type, entity_id, file_id)
);

CREATE TABLE IF NOT EXISTS people_relationships (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES entities_people(id),
    related_person_id INTEGER NOT NULL REFERENCES entities_people(id),
    relationship_type TEXT NOT NULL,
    created_at TEXT,
    UNIQUE(person_id, related_person_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS connected_sources (
    id INTEGER PRIMARY KEY,
    connector_name TEXT NOT NULL,
    display_name TEXT,
    status TEXT DEFAULT 'active',
    last_sync_at TEXT,
    item_count INTEGER DEFAULT 0,
    created_at TEXT
);
"""


def init_entity_schema(conn: sqlite3.Connection) -> None:
    """Create entity tables if they don't exist."""
    conn.executescript(ENTITY_TABLES_SQL)
    conn.commit()


# -- Person CRUD --

def create_person(
    conn: sqlite3.Connection,
    name: str,
    alternate_names: list[str] | None = None,
    birth_date: str | None = None,
    birth_date_precision: str | None = None,
    death_date: str | None = None,
    death_date_precision: str | None = None,
    notes: str | None = None,
    source_connector: str | None = None,
    external_id: str | None = None,
) -> int:
    now = _now()
    alt_json = json.dumps(alternate_names) if alternate_names else None
    cur = conn.execute(
        "INSERT INTO entities_people "
        "(name, alternate_names, birth_date, birth_date_precision, "
        "death_date, death_date_precision, notes, "
        "source_connector, external_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, alt_json, birth_date, birth_date_precision,
         death_date, death_date_precision, notes,
         source_connector, external_id, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_person(conn: sqlite3.Connection, person_id: int) -> Person | None:
    row = conn.execute(
        "SELECT * FROM entities_people WHERE id = ?", (person_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_person(row)


def update_person(conn: sqlite3.Connection, person_id: int, **kwargs) -> None:
    allowed = {"name", "alternate_names", "birth_date", "birth_date_precision",
               "death_date", "death_date_precision", "notes", "source_connector", "external_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if "alternate_names" in updates and isinstance(updates["alternate_names"], list):
        updates["alternate_names"] = json.dumps(updates["alternate_names"])
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [person_id]
    conn.execute(f"UPDATE entities_people SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_person(conn: sqlite3.Connection, person_id: int) -> None:
    conn.execute("DELETE FROM entity_files WHERE entity_type = 'person' AND entity_id = ?", (person_id,))
    conn.execute("DELETE FROM people_relationships WHERE person_id = ? OR related_person_id = ?", (person_id, person_id))
    conn.execute("DELETE FROM entities_people WHERE id = ?", (person_id,))
    conn.commit()


def list_people(conn: sqlite3.Connection, search: str | None = None) -> list[Person]:
    if search:
        rows = conn.execute(
            "SELECT * FROM entities_people WHERE name LIKE ? ORDER BY name",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entities_people ORDER BY name").fetchall()
    return [_row_to_person(r) for r in rows]


def _row_to_person(row) -> Person:
    alt = json.loads(row[2]) if row[2] else None
    return Person(
        id=row[0], name=row[1], alternate_names=alt,
        birth_date=row[3], birth_date_precision=row[4],
        death_date=row[5], death_date_precision=row[6],
        notes=row[7], source_connector=row[8], external_id=row[9],
        created_at=row[10], updated_at=row[11],
    )


# -- Location CRUD --

def create_location(
    conn: sqlite3.Connection,
    name: str,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    precision: str | None = None,
    notes: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO entities_locations "
        "(name, address, city, state, country, latitude, longitude, precision, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, address, city, state, country, latitude, longitude, precision, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_location(conn: sqlite3.Connection, location_id: int) -> Location | None:
    row = conn.execute(
        "SELECT * FROM entities_locations WHERE id = ?", (location_id,)
    ).fetchone()
    if not row:
        return None
    return Location(
        id=row[0], name=row[1], address=row[2], city=row[3],
        state=row[4], country=row[5], latitude=row[6], longitude=row[7],
        precision=row[8], notes=row[9], created_at=row[10], updated_at=row[11],
    )


def list_locations(conn: sqlite3.Connection, search: str | None = None) -> list[Location]:
    if search:
        rows = conn.execute(
            "SELECT * FROM entities_locations WHERE name LIKE ? ORDER BY name",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entities_locations ORDER BY name").fetchall()
    return [
        Location(id=r[0], name=r[1], address=r[2], city=r[3], state=r[4],
                 country=r[5], latitude=r[6], longitude=r[7], precision=r[8],
                 notes=r[9], created_at=r[10], updated_at=r[11])
        for r in rows
    ]


# -- Event CRUD --

def create_event(
    conn: sqlite3.Connection,
    name: str,
    event_type: str | None = None,
    start_date: str | None = None,
    start_date_precision: str | None = None,
    end_date: str | None = None,
    end_date_precision: str | None = None,
    location_id: int | None = None,
    notes: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO entities_events "
        "(name, event_type, start_date, start_date_precision, "
        "end_date, end_date_precision, location_id, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, event_type, start_date, start_date_precision,
         end_date, end_date_precision, location_id, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_event(conn: sqlite3.Connection, event_id: int) -> Event | None:
    row = conn.execute(
        "SELECT * FROM entities_events WHERE id = ?", (event_id,)
    ).fetchone()
    if not row:
        return None
    return Event(
        id=row[0], name=row[1], event_type=row[2], start_date=row[3],
        start_date_precision=row[4], end_date=row[5], end_date_precision=row[6],
        location_id=row[7], notes=row[8],
        created_at=row[9], updated_at=row[10],
    )


def list_events(conn: sqlite3.Connection, search: str | None = None) -> list[Event]:
    if search:
        rows = conn.execute(
            "SELECT * FROM entities_events WHERE name LIKE ? ORDER BY start_date",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entities_events ORDER BY start_date").fetchall()
    return [
        Event(id=r[0], name=r[1], event_type=r[2], start_date=r[3],
              start_date_precision=r[4], end_date=r[5], end_date_precision=r[6],
              location_id=r[7], notes=r[8],
              created_at=r[9], updated_at=r[10])
        for r in rows
    ]


# -- Timeframe CRUD --

def create_timeframe(
    conn: sqlite3.Connection,
    name: str,
    start_date: str | None = None,
    start_date_precision: str | None = None,
    end_date: str | None = None,
    end_date_precision: str | None = None,
    person_id: int | None = None,
    notes: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO entities_timeframes "
        "(name, start_date, start_date_precision, end_date, end_date_precision, "
        "person_id, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, start_date, start_date_precision, end_date, end_date_precision,
         person_id, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_timeframe(conn: sqlite3.Connection, timeframe_id: int) -> Timeframe | None:
    row = conn.execute(
        "SELECT * FROM entities_timeframes WHERE id = ?", (timeframe_id,)
    ).fetchone()
    if not row:
        return None
    return Timeframe(
        id=row[0], name=row[1], start_date=row[2], start_date_precision=row[3],
        end_date=row[4], end_date_precision=row[5],
        person_id=row[6], notes=row[7], created_at=row[8], updated_at=row[9],
    )


# -- Tag CRUD --

def create_tag(
    conn: sqlite3.Connection,
    name: str,
    color: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO tags (name, color, created_at) VALUES (?, ?, ?)",
        (name, color, now),
    )
    conn.commit()
    return cur.lastrowid


def get_tag(conn: sqlite3.Connection, tag_id: int) -> Tag | None:
    row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not row:
        return None
    return Tag(id=row[0], name=row[1], color=row[2], created_at=row[3])


def get_or_create_tag(conn: sqlite3.Connection, name: str, color: str | None = None) -> int:
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    return create_tag(conn, name=name, color=color)


def list_tags(conn: sqlite3.Connection) -> list[Tag]:
    rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
    return [Tag(id=r[0], name=r[1], color=r[2], created_at=r[3]) for r in rows]


# -- Entity <-> File Linking --

def link_entity_to_file(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    file_id: int,
    confidence: str = "manual",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO entity_files "
        "(entity_type, entity_id, file_id, confidence, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity_type, entity_id, file_id, confidence, _now()),
    )
    conn.commit()


def unlink_entity_from_file(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    file_id: int,
) -> None:
    conn.execute(
        "DELETE FROM entity_files "
        "WHERE entity_type = ? AND entity_id = ? AND file_id = ?",
        (entity_type, entity_id, file_id),
    )
    conn.commit()


def get_file_entities(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT entity_type, entity_id, confidence, created_at "
        "FROM entity_files WHERE file_id = ?",
        (file_id,),
    ).fetchall()
    return [
        {"entity_type": r[0], "entity_id": r[1], "confidence": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_entity_files(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT file_id, confidence, created_at "
        "FROM entity_files WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchall()
    return [
        {"file_id": r[0], "confidence": r[1], "created_at": r[2]}
        for r in rows
    ]


# -- Relationships --

def create_relationship(
    conn: sqlite3.Connection,
    person_id: int,
    related_person_id: int,
    relationship_type: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO people_relationships "
        "(person_id, related_person_id, relationship_type, created_at) "
        "VALUES (?, ?, ?, ?)",
        (person_id, related_person_id, relationship_type, _now()),
    )
    conn.commit()


def get_relationships(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT related_person_id, relationship_type, created_at "
        "FROM people_relationships WHERE person_id = ?",
        (person_id,),
    ).fetchall()
    return [
        {"related_person_id": r[0], "relationship_type": r[1], "created_at": r[2]}
        for r in rows
    ]
