"""Kora SQLite database — schema, CRUD, dataclasses."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent / "kora.db"


# ---------- dataclasses ----------

@dataclass
class LearningProfile:
    id: Optional[int] = None
    engagement_style: str = "scaffolded"
    pace: str = "steady"
    visual_weight: float = 0.5
    hook_preference: str = "story"
    confidence_bias: str = "calibrated"
    adaptation_notes: str = ""
    sessions_completed: int = 0
    last_updated: str = ""
    profile_summary: str = ""
    level_label: str = ""
    style_description: str = ""


@dataclass
class TopicSession:
    id: Optional[int] = None
    topic_name: str = ""
    topic_map: dict = field(default_factory=dict)
    depth: str = "solid"
    self_reported_level: str = "none"
    verified_level: str = "novice"
    profile_id: int = 0
    path: list = field(default_factory=list)
    current_module_index: int = 0
    status: str = "active"
    created_at: str = ""


@dataclass
class Module:
    id: Optional[int] = None
    session_id: int = 0
    module_number: int = 0
    concept_name: str = ""
    content: dict = field(default_factory=dict)
    status: str = "not_started"
    mastery_score: float = 0.0
    beat: str = "hook"


@dataclass
class ReviewItem:
    id: Optional[int] = None
    module_id: int = 0
    concept_name: str = ""
    topic_name: str = ""
    next_review: str = ""
    easiness_factor: float = 2.5
    repetition_count: int = 0
    last_accuracy: float = 0.0


# ---------- connection ----------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS learning_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_style TEXT NOT NULL,
            pace TEXT NOT NULL,
            visual_weight REAL NOT NULL,
            hook_preference TEXT NOT NULL,
            confidence_bias TEXT NOT NULL,
            adaptation_notes TEXT,
            sessions_completed INTEGER DEFAULT 0,
            last_updated TEXT,
            profile_summary TEXT,
            level_label TEXT,
            style_description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS topic_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_name TEXT NOT NULL,
            topic_map TEXT,
            depth TEXT,
            self_reported_level TEXT,
            verified_level TEXT,
            profile_id INTEGER,
            path TEXT,
            current_module_index INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT,
            FOREIGN KEY(profile_id) REFERENCES learning_profile(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS module (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            module_number INTEGER,
            concept_name TEXT,
            content TEXT,
            status TEXT DEFAULT 'not_started',
            mastery_score REAL DEFAULT 0.0,
            beat TEXT DEFAULT 'hook',
            FOREIGN KEY(session_id) REFERENCES topic_session(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS review_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER,
            concept_name TEXT,
            topic_name TEXT,
            next_review TEXT,
            easiness_factor REAL DEFAULT 2.5,
            repetition_count INTEGER DEFAULT 0,
            last_accuracy REAL DEFAULT 0.0,
            FOREIGN KEY(module_id) REFERENCES module(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS streak (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_streak INTEGER DEFAULT 0,
            last_activity_date TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO streak (id, current_streak, last_activity_date) VALUES (1, 0, NULL)")

    conn.commit()
    conn.close()


# ---------- profile CRUD ----------

def save_profile(profile: LearningProfile) -> int:
    conn = get_conn()
    c = conn.cursor()
    profile.last_updated = date.today().isoformat()
    if profile.id is None:
        c.execute("""
            INSERT INTO learning_profile
            (engagement_style, pace, visual_weight, hook_preference,
             confidence_bias, adaptation_notes, sessions_completed, last_updated,
             profile_summary, level_label, style_description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile.engagement_style, profile.pace, profile.visual_weight,
              profile.hook_preference, profile.confidence_bias,
              profile.adaptation_notes, profile.sessions_completed,
              profile.last_updated, profile.profile_summary,
              profile.level_label, profile.style_description))
        profile.id = c.lastrowid
    else:
        c.execute("""
            UPDATE learning_profile SET
            engagement_style=?, pace=?, visual_weight=?, hook_preference=?,
            confidence_bias=?, adaptation_notes=?, sessions_completed=?, last_updated=?,
            profile_summary=?, level_label=?, style_description=?
            WHERE id=?
        """, (profile.engagement_style, profile.pace, profile.visual_weight,
              profile.hook_preference, profile.confidence_bias,
              profile.adaptation_notes, profile.sessions_completed,
              profile.last_updated, profile.profile_summary,
              profile.level_label, profile.style_description, profile.id))
    conn.commit()
    conn.close()
    return profile.id


def get_profile() -> Optional[LearningProfile]:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM learning_profile ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return None
    return LearningProfile(**dict(row))


# ---------- session CRUD ----------

def save_session(session: TopicSession) -> int:
    conn = get_conn()
    c = conn.cursor()
    if session.created_at == "":
        session.created_at = date.today().isoformat()
    if session.id is None:
        c.execute("""
            INSERT INTO topic_session
            (topic_name, topic_map, depth, self_reported_level, verified_level,
             profile_id, path, current_module_index, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session.topic_name, json.dumps(session.topic_map), session.depth,
              session.self_reported_level, session.verified_level,
              session.profile_id, json.dumps(session.path),
              session.current_module_index, session.status, session.created_at))
        session.id = c.lastrowid
    else:
        c.execute("""
            UPDATE topic_session SET
            topic_name=?, topic_map=?, depth=?, self_reported_level=?,
            verified_level=?, profile_id=?, path=?, current_module_index=?,
            status=?, created_at=?
            WHERE id=?
        """, (session.topic_name, json.dumps(session.topic_map), session.depth,
              session.self_reported_level, session.verified_level,
              session.profile_id, json.dumps(session.path),
              session.current_module_index, session.status,
              session.created_at, session.id))
    conn.commit()
    conn.close()
    return session.id


def get_session(session_id: int) -> Optional[TopicSession]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM topic_session WHERE id=?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["topic_map"] = json.loads(d["topic_map"] or "{}")
    d["path"] = json.loads(d["path"] or "[]")
    return TopicSession(**d)


def get_active_sessions() -> list[TopicSession]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM topic_session WHERE status='active' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        d = dict(row)
        d["topic_map"] = json.loads(d["topic_map"] or "{}")
        d["path"] = json.loads(d["path"] or "[]")
        out.append(TopicSession(**d))
    return out


# ---------- module CRUD ----------

def save_module(module: Module) -> int:
    conn = get_conn()
    c = conn.cursor()
    if module.id is None:
        c.execute("""
            INSERT INTO module
            (session_id, module_number, concept_name, content, status, mastery_score, beat)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (module.session_id, module.module_number, module.concept_name,
              json.dumps(module.content), module.status,
              module.mastery_score, module.beat))
        module.id = c.lastrowid
    else:
        c.execute("""
            UPDATE module SET
            session_id=?, module_number=?, concept_name=?, content=?,
            status=?, mastery_score=?, beat=?
            WHERE id=?
        """, (module.session_id, module.module_number, module.concept_name,
              json.dumps(module.content), module.status,
              module.mastery_score, module.beat, module.id))
    conn.commit()
    conn.close()
    return module.id


def get_module(module_id: int) -> Optional[Module]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM module WHERE id=?", (module_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["content"] = json.loads(d["content"] or "{}")
    return Module(**d)


def get_modules_for_session(session_id: int) -> list[Module]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM module WHERE session_id=? ORDER BY module_number",
        (session_id,)
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        d = dict(row)
        d["content"] = json.loads(d["content"] or "{}")
        out.append(Module(**d))
    return out


# ---------- review CRUD ----------

def save_review_item(item: ReviewItem) -> int:
    conn = get_conn()
    c = conn.cursor()
    if item.id is None:
        c.execute("""
            INSERT INTO review_item
            (module_id, concept_name, topic_name, next_review,
             easiness_factor, repetition_count, last_accuracy)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (item.module_id, item.concept_name, item.topic_name,
              item.next_review, item.easiness_factor,
              item.repetition_count, item.last_accuracy))
        item.id = c.lastrowid
    else:
        c.execute("""
            UPDATE review_item SET
            next_review=?, easiness_factor=?, repetition_count=?, last_accuracy=?
            WHERE id=?
        """, (item.next_review, item.easiness_factor,
              item.repetition_count, item.last_accuracy, item.id))
    conn.commit()
    conn.close()
    return item.id


def get_review_record(module_id: int) -> Optional[ReviewItem]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM review_item WHERE module_id=?", (module_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return ReviewItem(**dict(row))


def get_due_reviews() -> list[ReviewItem]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM review_item WHERE next_review <= ? ORDER BY next_review",
        (date.today().isoformat(),)
    ).fetchall()
    conn.close()
    return [ReviewItem(**dict(r)) for r in rows]


# ---------- streak ----------

def get_streak() -> int:
    conn = get_conn()
    row = conn.execute("SELECT * FROM streak WHERE id=1").fetchone()
    conn.close()
    if not row:
        return 0
    return row["current_streak"] or 0


def bump_streak() -> int:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM streak WHERE id=1").fetchone()
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last = row["last_activity_date"] if row else None
    current = row["current_streak"] if row else 0
    if last == today:
        new = current
    elif last == yesterday:
        new = current + 1
    else:
        new = 1
    c.execute("UPDATE streak SET current_streak=?, last_activity_date=? WHERE id=1",
              (new, today))
    conn.commit()
    conn.close()
    return new


init_db()
