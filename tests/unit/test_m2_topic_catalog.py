from __future__ import annotations

import pytest
from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.topic_catalog_store import create_topic_catalog_version, get_topic_catalog_version, transition_topic_catalog_version


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _entry(key: str = "ranked_system") -> dict:
    return {
        "topic_key": key,
        "display_name": "Ranked System",
        "definition": "The game's ranked competition system.",
        "include": "Ratings, ranked queues, and competitive progression.",
        "exclude": "General multiplayer without ranked context.",
        "boundary": "Use for the ranked system as a game-specific object.",
        "aliases": ["ranked mode"],
    }


def test_game_topic_catalog_is_content_addressed_and_explicitly_published():
    first = create_topic_catalog_version(catalog_scope="game", app_id=10, catalog_version="game-topics-v1", entries=[_entry()])
    second = create_topic_catalog_version(catalog_scope="game", app_id=10, catalog_version="game-topics-v1", entries=[_entry()])
    assert first["catalog_version_id"] == second["catalog_version_id"]
    assert first["status"] == "DRAFT"
    published = transition_topic_catalog_version(first["catalog_version_id"], "PUBLISHED")
    assert published["status"] == "PUBLISHED"
    assert published["published_at"]
    with db.get_connection() as conn:
        with pytest.raises(Exception, match="topic_catalog_identity_immutable"):
            conn.execute(text("UPDATE topic_catalog_versions SET catalog_hash='tampered' WHERE catalog_version_id=:id"), {"id": first["catalog_version_id"]})
        with pytest.raises(Exception, match="topic_catalog_topic_immutable"):
            conn.execute(text("UPDATE topic_catalog_topics SET display_name='tampered' WHERE catalog_version_id=:id"), {"id": first["catalog_version_id"]})
    assert get_topic_catalog_version(first["catalog_version_id"])["topics"][0]["aliases"] == ["ranked mode"]


def test_catalog_scope_and_entries_are_validated():
    with pytest.raises(ValueError, match="topic_catalog_scope_invalid"):
        create_topic_catalog_version(catalog_scope="core", catalog_version="v1", entries=[_entry()])
    with pytest.raises(ValueError, match="game_topic_catalog_app_id_required"):
        create_topic_catalog_version(catalog_scope="game", catalog_version="v1", entries=[_entry()])
    with pytest.raises(ValueError, match="archetype_catalog_must_not_bind_app"):
        create_topic_catalog_version(catalog_scope="archetype", app_id=10, catalog_version="v1", entries=[_entry()])
    with pytest.raises(ValueError, match="topic_catalog_topic_key_invalid_or_duplicate"):
        create_topic_catalog_version(catalog_scope="archetype", catalog_version="v1", entries=[_entry(), _entry()])
