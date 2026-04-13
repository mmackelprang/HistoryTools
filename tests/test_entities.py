"""Tests for entity schema and CRUD operations."""

import sqlite3
import pytest
from pathlib import Path

from familyarchive.core.db import get_db, close_db
from familyarchive.entities.models import Person, Location, Event, Timeframe, Tag
from familyarchive.entities.db import (
    init_entity_schema,
    create_person,
    get_person,
    update_person,
    delete_person,
    list_people,
    create_location,
    get_location,
    list_locations,
    create_event,
    get_event,
    list_events,
    create_timeframe,
    get_timeframe,
    create_tag,
    get_tag,
    get_or_create_tag,
    list_tags,
    link_entity_to_file,
    get_file_entities,
    get_entity_files,
    unlink_entity_from_file,
    create_relationship,
    get_relationships,
)


@pytest.fixture()
def db(tmp_path):
    """Create a test database with entity schema."""
    dest = tmp_path / "archive"
    dest.mkdir()
    conn = get_db(str(dest))
    init_entity_schema(conn)
    yield conn
    close_db(conn)


# -- Person CRUD --

def test_create_and_get_person(db):
    pid = create_person(db, name="Rose Smith", birth_date="1920-03-15", birth_date_precision="exact")
    person = get_person(db, pid)
    assert person.name == "Rose Smith"
    assert person.birth_date == "1920-03-15"
    assert person.birth_date_precision == "exact"
    assert person.id == pid


def test_person_approximate_dates(db):
    """People can have approximate birth/death dates."""
    pid = create_person(
        db, name="Great Grandpa",
        birth_date="1880-01-01", birth_date_precision="year",
        death_date="1960-01-01", death_date_precision="decade",
    )
    person = get_person(db, pid)
    assert person.birth_date_precision == "year"
    assert person.death_date_precision == "decade"


def test_update_person(db):
    pid = create_person(db, name="Rose Smith")
    update_person(db, pid, death_date="2005-11-20", notes="Grandmother")
    person = get_person(db, pid)
    assert person.death_date == "2005-11-20"
    assert person.notes == "Grandmother"
    assert person.name == "Rose Smith"


def test_delete_person(db):
    pid = create_person(db, name="Temporary")
    delete_person(db, pid)
    assert get_person(db, pid) is None


def test_list_people(db):
    create_person(db, name="Alice")
    create_person(db, name="Bob")
    create_person(db, name="Charlie")
    people = list_people(db)
    assert len(people) == 3
    names = [p.name for p in people]
    assert "Alice" in names


def test_list_people_search(db):
    create_person(db, name="Alice Smith")
    create_person(db, name="Bob Jones")
    results = list_people(db, search="smith")
    assert len(results) == 1
    assert results[0].name == "Alice Smith"


# -- Location CRUD --

def test_create_and_get_location(db):
    lid = create_location(db, name="Springfield, IL", state="Illinois", precision="city")
    loc = get_location(db, lid)
    assert loc.name == "Springfield, IL"
    assert loc.state == "Illinois"
    assert loc.precision == "city"


def test_location_approximate(db):
    """Locations can have approximate precision."""
    lid = create_location(db, name="Somewhere in Utah", state="Utah", precision="state")
    loc = get_location(db, lid)
    assert loc.precision == "state"
    assert loc.city is None


def test_list_locations(db):
    create_location(db, name="Springfield")
    create_location(db, name="Shelbyville")
    locs = list_locations(db)
    assert len(locs) == 2


# -- Event CRUD --

def test_create_and_get_event(db):
    lid = create_location(db, name="Grandma's house")
    eid = create_event(
        db, name="1996 Family Reunion",
        event_type="reunion",
        start_date="1996-07-04",
        end_date="1996-07-06",
        location_id=lid,
    )
    event = get_event(db, eid)
    assert event.name == "1996 Family Reunion"
    assert event.event_type == "reunion"
    assert event.location_id == lid


def test_list_events(db):
    create_event(db, name="Wedding")
    create_event(db, name="Funeral")
    events = list_events(db)
    assert len(events) == 2


# -- Timeframe CRUD --

def test_create_and_get_timeframe(db):
    pid = create_person(db, name="Mark")
    tid = create_timeframe(
        db, name="7th Grade",
        start_date="1989-09-01",
        end_date="1990-06-15",
        person_id=pid,
    )
    tf = get_timeframe(db, tid)
    assert tf.name == "7th Grade"
    assert tf.person_id == pid


# -- Tag CRUD --

def test_create_and_get_tag(db):
    tid = create_tag(db, name="Scout Camp", color="#2ecc71")
    tag = get_tag(db, tid)
    assert tag.name == "Scout Camp"
    assert tag.color == "#2ecc71"


def test_get_or_create_tag(db):
    tid1 = get_or_create_tag(db, name="Family Reunion")
    tid2 = get_or_create_tag(db, name="Family Reunion")
    assert tid1 == tid2


def test_list_tags(db):
    create_tag(db, name="Tag A")
    create_tag(db, name="Tag B")
    tags = list_tags(db)
    assert len(tags) == 2


# -- Entity <-> File Linking --

def test_link_entity_to_file(db):
    pid = create_person(db, name="Rose")
    # Insert a fake file record
    db.execute(
        "INSERT INTO files (path, filename, folder, file_type, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Letters/letter.pdf", "letter.pdf", "Letters", "document", 1024),
    )
    file_id = db.execute("SELECT id FROM files WHERE path = ?", ("Letters/letter.pdf",)).fetchone()[0]

    link_entity_to_file(db, "person", pid, file_id, confidence="manual")

    # Check from file side
    entities = get_file_entities(db, file_id)
    assert len(entities) == 1
    assert entities[0]["entity_type"] == "person"
    assert entities[0]["entity_id"] == pid

    # Check from entity side
    files = get_entity_files(db, "person", pid)
    assert len(files) == 1
    assert files[0]["file_id"] == file_id


def test_unlink_entity_from_file(db):
    pid = create_person(db, name="Rose")
    db.execute(
        "INSERT INTO files (path, filename, folder, file_type, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Letters/letter.pdf", "letter.pdf", "Letters", "document", 1024),
    )
    file_id = db.execute("SELECT id FROM files WHERE path = ?", ("Letters/letter.pdf",)).fetchone()[0]

    link_entity_to_file(db, "person", pid, file_id)
    unlink_entity_from_file(db, "person", pid, file_id)
    assert len(get_file_entities(db, file_id)) == 0


# -- Relationships --

def test_create_relationship(db):
    pid1 = create_person(db, name="Rose Smith")
    pid2 = create_person(db, name="Mark Smith")
    create_relationship(db, pid1, pid2, "parent")

    rels = get_relationships(db, pid1)
    assert len(rels) == 1
    assert rels[0]["related_person_id"] == pid2
    assert rels[0]["relationship_type"] == "parent"
