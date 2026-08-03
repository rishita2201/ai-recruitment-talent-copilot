"""
api_client.py — thin wrapper around the FastAPI backend for the Streamlit app.

Every function returns (ok: bool, data_or_error). On success `data_or_error`
is the parsed JSON body; on failure it's a human-readable error string. This
keeps app.py free of try/except and status-code plumbing.
"""
import os

import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
TIMEOUT = 30          # quick calls: auth, list, stats, delete, notes
AI_TIMEOUT = 240      # calls that trigger a local Ollama inference: upload, match


def _headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _friendly_error(resp: requests.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except Exception:
        detail = None
    if isinstance(detail, list):  # pydantic validation errors
        detail = "; ".join(d.get("msg", str(d)) for d in detail)
    return detail or f"Request failed ({resp.status_code})."


def _call(method: str, path: str, token: str | None = None, timeout: int = TIMEOUT, **kwargs):
    try:
        resp = requests.request(
            method, f"{API_BASE}{path}", headers=_headers(token), timeout=timeout, **kwargs
        )
    except requests.exceptions.ConnectionError:
        return False, f"Can't reach the API at {API_BASE}. Is the backend running?"
    except requests.exceptions.Timeout:
        return False, (
            "The AI model is taking longer than expected (this can happen on the very "
            "first request while Ollama loads the model into memory). Please try again — "
            "it should be much faster the second time."
        )

    if resp.ok:
        try:
            return True, resp.json()
        except ValueError:
            return True, {}
    return False, _friendly_error(resp)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def signup(username: str, email: str, password: str):
    return _call(
        "POST", "/auth/signup", json={"username": username, "email": email, "password": password}
    )


def login(username: str, password: str):
    return _call("POST", "/auth/login", json={"username": username, "password": password})


def logout(token: str):
    return _call("POST", "/auth/logout", token=token)


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------

def upload_resume(token: str, filename: str, file_bytes: bytes):
    files = {"file": (filename, file_bytes)}
    return _call("POST", "/resumes/upload", token=token, files=files, timeout=AI_TIMEOUT)


def list_resumes(token: str, query: str | None = None):
    params = {"q": query} if query else None
    return _call("GET", "/resumes", token=token, params=params)


def get_resume(token: str, resume_id: int):
    return _call("GET", f"/resumes/{resume_id}", token=token)


def update_notes(token: str, resume_id: int, notes: str):
    return _call("PATCH", f"/resumes/{resume_id}/notes", token=token, json={"notes": notes})


def delete_resume(token: str, resume_id: int):
    return _call("DELETE", f"/resumes/{resume_id}", token=token)


def get_stats(token: str):
    return _call("GET", "/stats", token=token)


def match_candidates(
    token: str,
    job_id: int | None = None,
    job_description: str | None = None,
    resume_id: int | None = None,
):
    payload = {"job_id": job_id, "job_description": job_description, "resume_id": resume_id}
    return _call("POST", "/match", token=token, json=payload, timeout=AI_TIMEOUT)


# ---------------------------------------------------------------------------
# Job descriptions
# ---------------------------------------------------------------------------

def create_job(
    token: str,
    raw_text: str,
    title: str | None = None,
    required_skills: list | None = None,
    min_years_experience: float | None = None,
    required_education: str | None = None,
):
    payload = {
        "title": title,
        "raw_text": raw_text,
        "required_skills": required_skills,
        "min_years_experience": min_years_experience,
        "required_education": required_education,
    }
    return _call("POST", "/jobs", token=token, json=payload, timeout=AI_TIMEOUT)


def list_jobs(token: str):
    return _call("GET", "/jobs", token=token)


def get_job(token: str, job_id: int):
    return _call("GET", f"/jobs/{job_id}", token=token)


def delete_job(token: str, job_id: int):
    return _call("DELETE", f"/jobs/{job_id}", token=token)


# ---------------------------------------------------------------------------
# Interview generation & simulation
# ---------------------------------------------------------------------------

def generate_interview(token: str, resume_id: int, job_id: int | None = None, job_description: str | None = None):
    payload = {"resume_id": resume_id, "job_id": job_id, "job_description": job_description}
    return _call("POST", "/interview/generate", token=token, json=payload, timeout=AI_TIMEOUT)


def list_interview_sessions(token: str):
    return _call("GET", "/interview/sessions", token=token)


def get_interview_session(token: str, session_id: int):
    return _call("GET", f"/interview/sessions/{session_id}", token=token)


def answer_interview_question(token: str, session_id: int, question_id: str, answer: str):
    payload = {"question_id": question_id, "answer": answer}
    return _call("POST", f"/interview/sessions/{session_id}/answer", token=token, json=payload, timeout=AI_TIMEOUT)


def answer_interview_question_audio(token: str, session_id: int, question_id: str, filename: str, audio_bytes: bytes):
    files = {"file": (filename, audio_bytes)}
    data = {"question_id": question_id}
    return _call(
        "POST", f"/interview/sessions/{session_id}/answer-audio", token=token,
        files=files, data=data, timeout=AI_TIMEOUT,
    )


def complete_interview(token: str, session_id: int):
    return _call("POST", f"/interview/sessions/{session_id}/complete", token=token, timeout=AI_TIMEOUT)


def delete_interview_session(token: str, session_id: int):
    return _call("DELETE", f"/interview/sessions/{session_id}", token=token)


# ---------------------------------------------------------------------------
# ATS pipeline
# ---------------------------------------------------------------------------

def upsert_pipeline(
    token: str,
    resume_id: int,
    job_id: int,
    status: str | None = None,
    interview_datetime: str | None = None,
    recruiter_feedback: str | None = None,
):
    payload = {
        "resume_id": resume_id,
        "job_id": job_id,
        "status": status,
        "interview_datetime": interview_datetime,
        "recruiter_feedback": recruiter_feedback,
    }
    return _call("POST", "/pipeline", token=token, json=payload)


def list_pipeline(token: str, job_id: int | None = None, status: str | None = None):
    params = {}
    if job_id is not None:
        params["job_id"] = job_id
    if status:
        params["status"] = status
    return _call("GET", "/pipeline", token=token, params=params or None)


def update_pipeline(
    token: str,
    entry_id: int,
    status: str | None = None,
    interview_datetime: str | None = None,
    recruiter_feedback: str | None = None,
):
    payload = {"status": status, "interview_datetime": interview_datetime, "recruiter_feedback": recruiter_feedback}
    return _call("PATCH", f"/pipeline/{entry_id}", token=token, json=payload)


def delete_pipeline(token: str, entry_id: int):
    return _call("DELETE", f"/pipeline/{entry_id}", token=token)


def pipeline_stages(token: str):
    return _call("GET", "/pipeline/stages", token=token)
