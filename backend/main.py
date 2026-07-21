"""
main.py — FastAPI app tying together file upload, AI parsing, and MongoDB storage.

Run with:
    uvicorn main:app --reload --port 8000
"""
from dotenv import load_dotenv

load_dotenv()  # must run before parser.py reads ANTHROPIC_API_KEY

import re
import secrets

import bcrypt
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, field_validator
from pymongo.errors import DuplicateKeyError

import db
import parser
import scoring

app = FastAPI(title="AI Resume Parser")

# Allow the frontend (Streamlit, or any dev server) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


class MatchRequest(BaseModel):
    job_id: int | None = None            # score against a saved Job Description
    job_description: str | None = None   # or score against ad-hoc pasted text
    resume_id: int | None = None         # if omitted, score every candidate


class JobDescriptionCreate(BaseModel):
    title: str | None = None
    raw_text: str
    required_skills: list[str] | None = None       # auto-extracted via AI if omitted
    min_years_experience: float | None = None       # auto-extracted via AI if omitted
    required_education: str | None = None           # auto-extracted via AI if omitted

    @field_validator("raw_text")
    @classmethod
    def non_empty_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Job description text cannot be empty.")
        return v


class NotesRequest(BaseModel):
    notes: str


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def valid_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-32 characters: letters, numbers, '.', '_', or '-' only."
            )
        return v

    @field_validator("password")
    @classmethod
    def valid_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 characters or fewer.")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Dependency that resolves the bearer token in the Authorization header
    into a user document, or raises 401 if it's missing/invalid."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired session. Please log in again.")
    return user


@app.post("/auth/signup")
def signup(req: SignupRequest):
    password_hash = hash_password(req.password)
    try:
        db.create_user(req.username, req.email, password_hash)
    except DuplicateKeyError:
        raise HTTPException(409, "That username or email is already registered.")

    token = secrets.token_hex(32)
    db.set_session_token(req.username, token)
    return {"token": token, "username": req.username, "email": req.email}


@app.post("/auth/login")
def login(req: LoginRequest):
    user = db.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect username or password.")

    token = secrets.token_hex(32)
    db.set_session_token(req.username, token)
    return {"token": token, "username": user["username"], "email": user["email"]}


@app.post("/auth/logout")
def logout(user: dict = Depends(get_current_user)):
    db.set_session_token(user["username"], None)
    return {"logged_out": True}


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "email": user["email"]}


@app.post("/resumes/upload")
async def upload_resume(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty.")

    try:
        raw_text = parser.extract_text(file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not raw_text.strip():
        raise HTTPException(422, "Could not extract any text from this file.")

    try:
        parsed = parser.parse_with_ai(raw_text)
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    resume_id = db.insert_resume(user["username"], file.filename, raw_text, parsed)
    saved = db.get_resume(user["username"], resume_id)
    return saved


@app.get("/resumes")
def list_resumes(q: str | None = Query(default=None, description="Optional search keyword"), user: dict = Depends(get_current_user)):
    if q:
        return db.search_resumes(user["username"], q)
    return db.list_resumes(user["username"])


@app.get("/resumes/{resume_id}")
def get_resume(resume_id: int, user: dict = Depends(get_current_user)):
    resume = db.get_resume(user["username"], resume_id)
    if not resume:
        raise HTTPException(404, "Resume not found.")
    return resume


@app.patch("/resumes/{resume_id}/notes")
def update_notes(resume_id: int, req: NotesRequest, user: dict = Depends(get_current_user)):
    """Save recruiter notes/comments for a candidate."""
    if not db.update_notes(user["username"], resume_id, req.notes):
        raise HTTPException(404, "Resume not found.")
    return {"id": resume_id, "notes": req.notes}


@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, user: dict = Depends(get_current_user)):
    if not db.delete_resume(user["username"], resume_id):
        raise HTTPException(404, "Resume not found.")
    return {"deleted": resume_id}


@app.get("/stats")
def get_stats(user: dict = Depends(get_current_user)):
    """Dashboard numbers: headcount, top skills, average experience, degrees."""
    return db.get_stats(user["username"])


# ---------------------------------------------------------------------------
# Job descriptions
# ---------------------------------------------------------------------------

@app.post("/jobs")
def create_job(req: JobDescriptionCreate, user: dict = Depends(get_current_user)):
    """Save a Job Description for reuse. If required_skills / min_years_experience /
    required_education aren't provided explicitly, the AI extracts them from the
    pasted text so matching always has concrete criteria to compare against."""
    required_skills = req.required_skills
    min_years_experience = req.min_years_experience
    required_education = req.required_education
    title = req.title

    needs_extraction = required_skills is None or min_years_experience is None or required_education is None or not title
    if needs_extraction:
        try:
            extracted = parser.extract_job_requirements(req.raw_text)
        except RuntimeError as e:
            raise HTTPException(502, str(e))
        title = title or extracted.get("title") or "Untitled role"
        if required_skills is None:
            required_skills = extracted.get("required_skills") or []
        if min_years_experience is None:
            min_years_experience = extracted.get("min_years_experience")
        if required_education is None:
            required_education = extracted.get("required_education")

    job_id = db.create_job(
        user["username"], title, req.raw_text, required_skills, min_years_experience, required_education
    )
    return db.get_job(user["username"], job_id)


@app.get("/jobs")
def list_jobs(user: dict = Depends(get_current_user)):
    return db.list_jobs(user["username"])


@app.get("/jobs/{job_id}")
def get_job(job_id: int, user: dict = Depends(get_current_user)):
    job = db.get_job(user["username"], job_id)
    if not job:
        raise HTTPException(404, "Job description not found.")
    return job


@app.delete("/jobs/{job_id}")
def delete_job(job_id: int, user: dict = Depends(get_current_user)):
    if not db.delete_job(user["username"], job_id):
        raise HTTPException(404, "Job description not found.")
    return {"deleted": job_id}


@app.post("/match")
def match_candidates(req: MatchRequest, user: dict = Depends(get_current_user)):
    """Score one candidate (resume_id set) or every candidate (resume_id omitted)
    against a job — either a saved Job Description (job_id) or ad-hoc pasted
    text (job_description). Returns a full skill-gap breakdown and a weighted
    Hiring Score per candidate, ranked descending."""
    if not req.job_id and not (req.job_description and req.job_description.strip()):
        raise HTTPException(400, "Provide either job_id or job_description.")

    # Resolve the job's concrete requirements — either from a saved Job
    # Description, or by extracting them on the fly from pasted text so we
    # always have required_skills / min_years / required_education to score against.
    if req.job_id:
        job = db.get_job(user["username"], req.job_id)
        if not job:
            raise HTTPException(404, "Job description not found.")
        job_title = job["title"]
        job_text = job["raw_text"]
        required_skills = job.get("required_skills") or []
        min_years_experience = job.get("min_years_experience")
        required_education = job.get("required_education")
    else:
        job_text = req.job_description
        job_title = "Ad-hoc job description"
        try:
            extracted = parser.extract_job_requirements(job_text)
        except RuntimeError as e:
            raise HTTPException(502, str(e))
        job_title = extracted.get("title") or job_title
        required_skills = extracted.get("required_skills") or []
        min_years_experience = extracted.get("min_years_experience")
        required_education = extracted.get("required_education")

    if req.resume_id is not None:
        profiles = db.get_resumes_for_matching(user["username"])
        profile = next((p for p in profiles if p["id"] == req.resume_id), None)
        if not profile:
            raise HTTPException(404, "Resume not found.")
        profiles_to_score = [profile]
    else:
        profiles_to_score = db.get_resumes_for_matching(user["username"])
        if not profiles_to_score:
            return {"job_title": job_title, "required_skills": required_skills, "results": []}

    results = []
    for profile in profiles_to_score:
        # Deterministic skill-gap comparison (matched / missing / additional, % match, % gap).
        skill_cmp = scoring.compare_skills(profile.get("skills") or [], required_skills)

        exp_score = scoring.experience_score(profile.get("years_exp"), min_years_experience)
        edu_score = scoring.education_score(profile.get("education") or [], required_education)

        # Holistic AI read on fit — catches nuance plain string-matching can't
        # (synonyms, adjacent tech, seniority signals in the free text).
        try:
            ai_match = parser.match_resume_to_job(profile, job_text)
        except RuntimeError as e:
            raise HTTPException(502, str(e))
        ai_score = ai_match.get("score")

        overall = scoring.hiring_score(skill_cmp["skill_match_pct"], exp_score, edu_score, ai_score)
        recommendations = scoring.recommendations_for_missing(skill_cmp["missing_skills"])

        results.append(
            {
                "id": profile["id"],
                "name": profile.get("name") or "Unnamed candidate",
                "hiring_score": overall,
                "skill_match_pct": skill_cmp["skill_match_pct"],
                "skill_gap_pct": skill_cmp["skill_gap_pct"],
                "matched_skills": skill_cmp["matched_skills"],
                "missing_skills": skill_cmp["missing_skills"],
                "additional_skills": skill_cmp["additional_skills"],
                "experience_score": exp_score,
                "education_score": edu_score,
                "ai_score": ai_score,
                "reasoning": ai_match.get("reasoning", ""),
                "recommendations": recommendations,
            }
        )

    results.sort(key=lambda r: (-(r["hiring_score"] or 0)))
    return {
        "job_title": job_title,
        "required_skills": required_skills,
        "min_years_experience": min_years_experience,
        "required_education": required_education,
        "results": results,
    }
