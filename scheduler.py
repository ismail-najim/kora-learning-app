"""SM-2 inspired spaced repetition scheduler."""
from __future__ import annotations

from datetime import date, timedelta

import database as db

INTERVALS = [1, 3, 7, 14, 30, 60]


def schedule_next_review(module_id: int, concept_name: str,
                         topic_name: str, accuracy: float) -> None:
    record = db.get_review_record(module_id)
    if record is None:
        record = db.ReviewItem(
            module_id=module_id,
            concept_name=concept_name,
            topic_name=topic_name,
            easiness_factor=2.5,
            repetition_count=0,
        )

    if accuracy < 0.6:
        interval = 1
        ef = max(1.3, record.easiness_factor - 0.2)
        reps = 0
    else:
        reps = record.repetition_count + 1
        idx = min(reps - 1, len(INTERVALS) - 1)
        base = INTERVALS[idx]
        interval = int(base * record.easiness_factor) if reps > len(INTERVALS) else base
        q = accuracy * 5
        ef = max(1.3, record.easiness_factor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))

    record.next_review = (date.today() + timedelta(days=interval)).isoformat()
    record.easiness_factor = ef
    record.repetition_count = reps
    record.last_accuracy = accuracy
    db.save_review_item(record)


def get_due_reviews() -> list[db.ReviewItem]:
    return db.get_due_reviews()


def days_since_learned(module_id: int) -> int:
    record = db.get_review_record(module_id)
    if not record or not record.next_review:
        return 0
    try:
        nr = date.fromisoformat(record.next_review)
        return max(0, (date.today() - nr).days + 1)
    except Exception:
        return 0
