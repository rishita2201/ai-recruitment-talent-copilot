"""
db.py — MongoDB storage layer for the resume parser.

Plain PyMongo, no ODM: one "resumes" collection whose documents mirror the
JSON shape the AI parser already produces (skills/education/experience are
native arrays, not JSON-encoded strings like they'd need to be in SQL).

A tiny "counters" collection hands out clean sequential integer ids (the
same trick SQLite's AUTOINCREMENT does), so the REST API and frontend keep
working with plain integer ids like /resumes/7 instead of Mongo ObjectIds.

Every public function here has the exact same name and signature as the
old SQLite version, so main.py didn't need to change at all.
"""
import os
from datetime import datetime, timezone

from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "resume_parser")

_client = MongoClient(MONGODB_URI)
_db = _client[MONGODB_DB]
resumes = _db["resumes"]
counters = _db["counters"]
users = _db["users"]
job_descriptions = _db["job_descriptions"]

# Fields returned for list/search views — everything except the heavy
# raw_text blob (mirrors the old SQLite SELECT column list).
_LIST_PROJECTION = {
    "_id": 0,
    "id": 1,
    "filename": 1,
    "name": 1,
    "email": 1,
    "phone": 1,
    "location": 1,
    "years_exp": 1,
    "created_at": 1,
}

# Fields sent to the AI model when scoring candidates against a job —
# deliberately excludes raw_text so we don't ship the whole document.
_MATCH_PROJECTION = {
    "_id": 0,
    "id": 1,
    "name": 1,
    "email": 1,
    "summary": 1,
    "skills": 1,
    "experience": 1,
    "education": 1,
    "years_exp": 1,
}


def init_db():
    """Create indexes. Safe to call on every startup — a no-op once they exist."""
    resumes.create_index([("id", ASCENDING)], unique=True)
    resumes.create_index([("created_at", DESCENDING)])
    resumes.create_index([("name", ASCENDING)])
    resumes.create_index([("owner", ASCENDING)])
    counters.update_one({"_id": "resumes"}, {"$setOnInsert": {"seq": 0}}, upsert=True)

    users.create_index([("username", ASCENDING)], unique=True)
    users.create_index([("email", ASCENDING)], unique=True)
    users.create_index([("session_token", ASCENDING)], sparse=True)

    job_descriptions.create_index([("id", ASCENDING)], unique=True)
    job_descriptions.create_index([("owner", ASCENDING)])
    job_descriptions.create_index([("created_at", DESCENDING)])
    counters.update_one({"_id": "job_descriptions"}, {"$setOnInsert": {"seq": 0}}, upsert=True)


# ---------------------------------------------------------------------------
# Users / auth
# ---------------------------------------------------------------------------

def create_user(username: str, email: str, password_hash: str) -> dict:
    """Insert a new user. Raises pymongo.errors.DuplicateKeyError if the
    username or email is already taken (caller should catch this)."""
    doc = {
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "session_token": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.insert_one(doc)
    return _clean(doc)


def get_user_by_username(username: str) -> dict | None:
    return _clean(users.find_one({"username": username}))


def get_user_by_email(email: str) -> dict | None:
    return _clean(users.find_one({"email": email}))


def set_session_token(username: str, token: str | None) -> None:
    users.update_one({"username": username}, {"$set": {"session_token": token}})


def get_user_by_token(token: str) -> dict | None:
    if not token:
        return None
    return _clean(users.find_one({"session_token": token}))


def _next_id(counter_name: str = "resumes") -> int:
    doc = counters.find_one_and_update(
        {"_id": counter_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


def _clean(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


def insert_resume(owner: str, filename: str, raw_text: str, parsed: dict) -> int:
    new_id = _next_id()
    resumes.insert_one(
        {
            "id": new_id,
            "owner": owner,
            "filename": filename,
            "name": parsed.get("name"),
            "email": parsed.get("email"),
            "phone": parsed.get("phone"),
            "location": parsed.get("location"),
            "summary": parsed.get("summary"),
            "skills": parsed.get("skills") or [],
            "education": parsed.get("education") or [],
            "experience": parsed.get("experience") or [],
            "years_exp": parsed.get("years_experience"),
            "raw_text": raw_text,
            "notes": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return new_id


def get_resume(owner: str, resume_id: int) -> dict | None:
    return _clean(resumes.find_one({"id": resume_id, "owner": owner}))


def list_resumes(owner: str) -> list:
    return list(resumes.find({"owner": owner}, _LIST_PROJECTION).sort("created_at", DESCENDING))


def update_notes(owner: str, resume_id: int, notes: str) -> bool:
    result = resumes.update_one({"id": resume_id, "owner": owner}, {"$set": {"notes": notes}})
    return result.matched_count > 0


def delete_resume(owner: str, resume_id: int) -> bool:
    result = resumes.delete_one({"id": resume_id, "owner": owner})
    return result.deleted_count > 0


def search_resumes(owner: str, query: str) -> list:
    """Simple, index-free keyword search across name, skills, and raw text,
    scoped to one user's candidate pool. Fine for a single-user/small-team
    tool; for large datasets swap this for a MongoDB Atlas Search index or
    a $text index instead."""
    import re

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    cursor = resumes.find(
        {
            "owner": owner,
            "$or": [{"name": pattern}, {"skills": pattern}, {"raw_text": pattern}],
        },
        _LIST_PROJECTION,
    ).sort("created_at", DESCENDING)
    return list(cursor)


def get_resumes_for_matching(owner: str) -> list:
    """Lightweight profile (no raw_text) for every resume owned by this user —
    used when scoring candidates against a job description so we don't ship
    the full document text to the model for every single candidate."""
    return list(resumes.find({"owner": owner}, _MATCH_PROJECTION))


def get_stats(owner: str) -> dict:
    """Aggregate numbers for the dashboard, scoped to one user: headcount,
    top skills, average experience, and a rough education-level breakdown."""
    total = resumes.count_documents({"owner": owner})

    avg_result = list(
        resumes.aggregate(
            [
                {"$match": {"owner": owner, "years_exp": {"$ne": None}}},
                {"$group": {"_id": None, "avg_y": {"$avg": "$years_exp"}}},
            ]
        )
    )
    avg_years = round(avg_result[0]["avg_y"], 1) if avg_result else None

    latest_doc = resumes.find_one({"owner": owner}, sort=[("created_at", DESCENDING)])
    latest_upload = latest_doc["created_at"] if latest_doc else None

    skill_counter: dict = {}
    for doc in resumes.find({"owner": owner}, {"_id": 0, "skills": 1}):
        for s in doc.get("skills") or []:
            key = (s or "").strip().lower()
            if not key:
                continue
            skill_counter[key] = skill_counter.get(key, 0) + 1
    top_skills = sorted(skill_counter.items(), key=lambda kv: kv[1], reverse=True)[:12]
    top_skills = [{"skill": k, "count": v} for k, v in top_skills]

    degree_counter: dict = {}
    for doc in resumes.find({"owner": owner}, {"_id": 0, "education": 1}):
        for ed in doc.get("education") or []:
            degree = (ed.get("degree") or "").strip()
            if not degree:
                continue
            degree_counter[degree] = degree_counter.get(degree, 0) + 1
    top_degrees = sorted(degree_counter.items(), key=lambda kv: kv[1], reverse=True)[:8]
    top_degrees = [{"degree": k, "count": v} for k, v in top_degrees]

    return {
        "total_candidates": total,
        "avg_years_experience": avg_years,
        "latest_upload": latest_upload,
        "top_skills": top_skills,
        "top_degrees": top_degrees,
    }


# ---------------------------------------------------------------------------
# Job descriptions (recruiter-created, used as the basis for matching)
# ---------------------------------------------------------------------------

_JOB_LIST_PROJECTION = {"_id": 0, "raw_text": 0}


def create_job(
    owner: str,
    title: str,
    raw_text: str,
    required_skills: list,
    min_years_experience: float | None,
    required_education: str | None,
) -> int:
    new_id = _next_id("job_descriptions")
    job_descriptions.insert_one(
        {
            "id": new_id,
            "owner": owner,
            "title": title,
            "raw_text": raw_text,
            "required_skills": required_skills,
            "min_years_experience": min_years_experience,
            "required_education": required_education,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return new_id


def list_jobs(owner: str) -> list:
    return list(
        job_descriptions.find({"owner": owner}, _JOB_LIST_PROJECTION).sort("created_at", DESCENDING)
    )


def get_job(owner: str, job_id: int) -> dict | None:
    return _clean(job_descriptions.find_one({"id": job_id, "owner": owner}))


def delete_job(owner: str, job_id: int) -> bool:
    result = job_descriptions.delete_one({"id": job_id, "owner": owner})
    return result.deleted_count > 0
