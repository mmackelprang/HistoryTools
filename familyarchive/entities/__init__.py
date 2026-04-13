"""
Entity management for the Family Archive.

Provides people, locations, events, timeframes, and tags as first-class
archive metadata. Entities are stored in .archive.db alongside files
and transcripts.

Usage:
    from familyarchive.entities import create_person, link_entity_to_file
"""

from .db import (
    init_entity_schema,
    create_person, get_person, update_person, delete_person, list_people,
    create_location, get_location, list_locations,
    create_event, get_event, list_events,
    create_timeframe, get_timeframe,
    create_tag, get_tag, get_or_create_tag, list_tags,
    link_entity_to_file, get_file_entities, get_entity_files, unlink_entity_from_file,
    create_relationship, get_relationships,
)
from .models import Person, Location, Event, Timeframe, Tag

__all__ = [
    "init_entity_schema",
    "Person", "create_person", "get_person", "update_person", "delete_person", "list_people",
    "Location", "create_location", "get_location", "list_locations",
    "Event", "create_event", "get_event", "list_events",
    "Timeframe", "create_timeframe", "get_timeframe",
    "Tag", "create_tag", "get_tag", "get_or_create_tag", "list_tags",
    "link_entity_to_file", "get_file_entities", "get_entity_files", "unlink_entity_from_file",
    "create_relationship", "get_relationships",
]
