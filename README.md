# AI Resume Parser (100% Free Stack)

A simple full-stack app that uploads a resume (PDF/DOCX/TXT), extracts the text,
sends it to a **free, local AI model via Ollama** to pull out structured fields
(name, contact info, skills, experience, education, summary), and stores the
result in **MongoDB**.

Everything here is free and runs on your own machine — no API keys, no
paid accounts, no cloud costs (unless you opt into a hosted MongoDB Atlas
cluster, which also has a free tier):

| Layer     | Tool                          | Cost |
|-----------|-------------------------------|------|
| Frontend  | Streamlit                     | Free |
| Backend   | FastAPI (Python)              | Free |
| Database  | MongoDB                       | Free |
| AI        | Ollama + Llama 3.2 1B (local) | Free |

```
resume-parser/
├── backend/
│   ├── main.py           # FastAPI app (routes + auth)
│   ├── parser.py         # text extraction + AI calls (resume parsing, JD extraction, match reasoning)
│   ├── scoring.py        # deterministic hiring-score math (skill match %, experience/education fit)
│   ├── db.py             # MongoDB storage (resumes + users + job descriptions)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app.py              # Streamlit app: landing page, login/signup, main product
    ├── api_client.py        # wrapper around backend REST calls
    ├── requirements.txt
    └── .streamlit/config.toml
```

## 1. Install Ollama (the free local AI)

Download from [ollama.com](https://ollama.com) for Mac/Windows/Linux, then
pull the default model (one-time, ~1.3GB download — small and fast, runs
fine on CPU-only machines):

```bash
ollama pull llama3.2:1b
```

Make sure Ollama is running (it auto-starts on Mac/Windows after install;
on Linux run `ollama serve`). It listens on `http://localhost:11434` by
default — no account, no API key.

> Want more accurate extraction and have the RAM/GPU to spare?
> `ollama pull llama3.2` (3B, ~2GB) or `ollama pull llama3.1` (8B, ~4.7GB)
> both work well — just set `OLLAMA_MODEL` in `.env` to match.

## 2. Install MongoDB (the free local database)

Two options — pick whichever's easier for you:

**A. Run it locally (fully offline):**
Install [MongoDB Community Server](https://www.mongodb.com/try/download/community)
for your OS, then start it:

```bash
mongod --dbpath /path/to/some/data/folder
```

It listens on `mongodb://localhost:27017` by default — nothing further to
configure.

**B. Use a free MongoDB Atlas cluster (cloud, no local install):**
Create a free cluster at [mongodb.com/atlas](https://www.mongodb.com/atlas),
grab its connection string (starts with `mongodb+srv://...`), and paste it
into `MONGODB_URI` in `.env` in the next step.

## 3. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# defaults already point at llama3.2:1b on localhost:11434 and MongoDB on
# localhost:27017 — edit MONGODB_URI if you're using Atlas instead
```

Run the API:

```bash
uvicorn main:app --reload --port 8000
```

On first run, the app connects to MongoDB, creates the `resume_parser`
database and a `resumes` collection (with indexes) automatically — no
manual schema setup needed.

## Features

- **Landing page**: marketing splash page with a quick feature overview and
  "Get started" / "Log in" calls to action — shown to signed-out visitors.
- **Sign up / log in**: every account has its own private candidate pool.
  Passwords are hashed with bcrypt; the backend issues a bearer token on
  login/signup that the Streamlit app stores for the session and sends on
  every API call. All `/resumes`, `/jobs`, `/stats`, and `/match` endpoints
  require it.
- **Upload & parse**: drop in a PDF/DOCX/TXT resume and the local AI extracts
  name, contact info, skills, work history, education, and a summary.
- **Search**: filter your candidate list by name, skill, or any keyword.
- **Job Descriptions tab**: save job postings for reuse instead of re-pasting
  them every time. Give it a title, the raw text, and optionally the required
  skills / minimum years of experience / minimum education yourself — leave
  any of those blank and the AI fills them in from the posting text. Reuse a
  saved job from the Match Job tab with one click, or delete it when it's
  filled.
- **Hiring Score & skill-gap analysis**: the Match Job tab ranks every
  candidate against a job — saved or pasted ad-hoc — using a weighted
  **Hiring Score** (0–100) that blends:
  - **Skill Match %** — deterministic overlap between the candidate's skills
    and the job's required skills (also expressed as **Skill Gap %**)
  - **Experience fit** — candidate's years of experience vs. the job's
    stated minimum
  - **Education fit** — candidate's highest degree vs. the job's stated
    minimum education level
  - **AI holistic score** — the local model's qualitative read on overall
    fit, to catch nuance plain keyword-matching misses

  For every candidate you get a full breakdown: **Matched Skills**,
  **Missing Skills**, **Additional Skills** (skills the candidate has beyond
  what the job asked for), visual progress bars for each factor, plain-
  language **recommendations** for closing skill gaps, and a **downloadable
  skill-gap report** (Markdown) per candidate plus a combined **CSV export**
  of the whole ranked list. You can also score just the currently-open
  candidate from their detail view ("Score vs. selected job").
- **Dashboard tab**: headcount, average years of experience, most recent
  upload, a top-skills bar chart, and the most common degrees across your
  candidate pool.
- **Candidate notes**: jot down your own comments on any candidate from
  their dossier view (interview impressions, follow-ups, etc.) and save them
  alongside the parsed data in MongoDB.

### How the Hiring Score is calculated

`scoring.py` computes each factor independently and combines them with
these default weights (tune the constants at the top of that file if your
priorities differ):

| Factor              | Weight | Source                                              |
|---------------------|--------|------------------------------------------------------|
| Skill Match %        | 45%    | Deterministic: `matched required skills / total required skills`, case-insensitive |
| Experience fit        | 20%    | `min(100, candidate_years / job_min_years * 100)`    |
| Education fit         | 15%    | Candidate's highest degree rank vs. the job's stated minimum |
| AI holistic score      | 20%    | The local model's 0–100 qualitative judgment, from `parser.match_resume_to_job` |

If a job doesn't specify a minimum experience or education requirement,
that factor is dropped and the remaining weights are re-normalized —
candidates aren't penalized for a requirement that was never stated.

## API endpoints

| Method | Path                    | Description                          |
|--------|-------------------------|---------------------------------------|
| POST   | `/auth/signup`          | Create an account (body: `{"username", "email", "password"}`) → returns bearer token |
| POST   | `/auth/login`           | Log in (body: `{"username", "password"}`) → returns bearer token |
| POST   | `/auth/logout`          | Invalidate the current session token 🔒 |
| GET    | `/auth/me`              | Current user info 🔒                   |
| POST   | `/resumes/upload`       | Upload a file, parse it, store it 🔒   |
| GET    | `/resumes`              | List all resumes (add `?q=` to search) 🔒 |
| GET    | `/resumes/{id}`         | Full parsed record for one resume 🔒   |
| DELETE | `/resumes/{id}`         | Remove a record 🔒                     |
| GET    | `/stats`                | Dashboard aggregates 🔒                |
| PATCH  | `/resumes/{id}/notes`   | Save recruiter notes/comments for a candidate (body: `{"notes": "..."}`) 🔒 |
| POST   | `/jobs`                 | Save a Job Description (body: `{"raw_text", "title"?, "required_skills"?, "min_years_experience"?, "required_education"?}` — any omitted field is auto-extracted by AI from `raw_text`) 🔒 |
| GET    | `/jobs`                 | List saved Job Descriptions 🔒         |
| GET    | `/jobs/{id}`            | Full record for one Job Description 🔒 |
| DELETE | `/jobs/{id}`            | Remove a saved Job Description 🔒      |
| POST   | `/match`                | Score candidate(s) vs. a job (body: `{"job_id": optional, "job_description": optional, "resume_id": optional}` — provide `job_id` for a saved job or `job_description` for ad-hoc text; omit `resume_id` to score everyone). Returns `{"job_title", "required_skills", "min_years_experience", "required_education", "results": [{"id", "name", "hiring_score", "skill_match_pct", "skill_gap_pct", "matched_skills", "missing_skills", "additional_skills", "experience_score", "education_score", "ai_score", "reasoning", "recommendations"}], ...}`, ranked descending by `hiring_score` 🔒 |
| GET    | `/health`               | Health check                          |

🔒 = requires an `Authorization: Bearer <token>` header from `/auth/login` or `/auth/signup`.

## 4. Frontend setup

The frontend is a Streamlit app.

```bash
cd frontend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
# visit http://localhost:8501
```

It calls the API at `http://localhost:8000` by default. To point it at a
different backend, set the `API_BASE` environment variable before launching:

```bash
API_BASE=http://localhost:8000 streamlit run app.py
```

## 5. Using it

1. Make sure Ollama and MongoDB are both running in the background.
2. Start the backend (`uvicorn main:app --reload --port 8000`).
3. Start the frontend (`streamlit run app.py`).
4. You'll land on the marketing splash page — click **Get started** to
   create an account, or **Log in** if you already have one.
5. Once signed in, drop in a resume (PDF, DOCX, or TXT) on the Candidates
   tab. The local model extracts name, contact details, skills, work
   history, education, and a short summary, and it's saved to MongoDB under
   your account.
6. Click **View** on any candidate to see their parsed dossier on the
   right, add notes, delete them, or score them against a job description.
7. Use the **Job Descriptions** tab to save postings for reuse (AI fills in
   any requirements you don't specify), then the **Match Job** tab to pick a
   saved job or paste one ad-hoc and rank every candidate by Hiring Score,
   with a full skill-gap breakdown and downloadable reports. Use the
   **Dashboard** tab for pipeline-wide stats.

## Notes & next steps

- **Model**: set via `OLLAMA_MODEL` in `.env` (defaults to `llama3.2:1b` for
  speed on modest hardware). Any Ollama model works — larger models parse
  more accurately but run slower; try `llama3.2` (3B) or `llama3.1` (8B) if
  you want better extraction quality and have the hardware for it.
- **Speed**: local models are slower than a hosted API, especially on a
  laptop without a discrete GPU. First requests are also slower while the
  model loads into memory.
- **Database**: MongoDB, via PyMongo (no ODM). One `resumes` collection;
  ids are plain sequential integers (not ObjectIds) so the API stays simple
  — see the top of `db.py` for how that works. Point `MONGODB_URI` at a
  replica set or Atlas cluster if you outgrow a single local `mongod`.
- **Security**: accounts are gated by username/password (bcrypt-hashed) and
  a bearer token that the frontend attaches to every request. Every resume is
  tagged with an `owner` (the uploading user's username), and every read,
  search, update, delete, stats, and match call is filtered by it — so each
  account only ever sees its own candidate pool. Session tokens are single
  and non-expiring, stored in Mongo (not hashed); swap in JWTs with expiry
  and a hashed token store before using this for anything beyond a demo.
  If you switch to Atlas, also make sure your cluster's network access rules
  aren't wide open.
- **File size**: very long resumes are trimmed to ~15k characters before
  being sent to the model; adjust in `parser.py` if needed.
- **Troubleshooting**: if uploads fail with a connection error, first check
  which service is unreachable — confirm Ollama is running (`ollama list`
  should show your pulled model) and that `OLLAMA_HOST` in `.env` matches
  where it's listening; separately, confirm MongoDB is running (`mongosh
  "$MONGODB_URI"` should connect) and that `MONGODB_URI` in `.env` is correct.
- **Matching performance**: "Rank all candidates" scores every resume one at
  a time against the local model, so it scales with your candidate count —
  fine for dozens, slow for hundreds. Each score is computed fresh (not
  cached), so re-running against a different job description always
  reflects the new text.
