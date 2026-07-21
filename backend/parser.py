"""
parser.py — turns a resume file into structured JSON.

Two stages:
  1. extract_text(): pull raw text out of PDF / DOCX / TXT
  2. parse_with_ai(): send that text to a local, free Ollama model and get
     back structured fields.

This uses Ollama (https://ollama.com) instead of a paid API — it runs the
model on your own machine for free. Install Ollama, pull a model, and make
sure `ollama serve` is running before starting this backend.
"""
import io
import json
import os

import ollama
from pypdf import PdfReader
from docx import Document

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

_client: ollama.Client | None = None


def get_client() -> ollama.Client:
    global _client
    if _client is None:
        # Long timeout on purpose: local models can be slow to load into
        # memory on the first call, especially without a GPU. But we still
        # want a hard cap so a genuinely stuck request fails with a clear
        # error instead of hanging forever.
        _client = ollama.Client(host=OLLAMA_HOST, timeout=180)
    return _client


def extract_text(filename: str, file_bytes: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if ext == "docx":
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)

    if ext in ("txt", "md"):
        return file_bytes.decode("utf-8", errors="ignore")

    raise ValueError(f"Unsupported file type: .{ext}. Use PDF, DOCX, or TXT.")


EXTRACTION_PROMPT = """You are a resume-parsing engine. Read the resume text below and \
extract structured information as JSON only — no preamble, no markdown fences, no commentary.

Return an object with exactly these keys:
{
  "name": string or null,
  "email": string or null,
  "phone": string or null,
  "location": string or null,
  "summary": string (2-3 sentence professional summary you write based on the resume),
  "years_experience": number or null (estimate total years of professional experience),
  "skills": array of strings (technical and soft skills, deduplicated),
  "education": array of objects: {"degree": string, "institution": string, "year": string or null},
  "experience": array of objects: {"title": string, "company": string, "start": string or null, "end": string or null, "highlights": array of strings}
}

If a field cannot be determined, use null (or an empty array for list fields). Do not invent facts \
that aren't supported by the text.

Resume text:
---
{resume_text}
---
"""


def _chat_json(prompt: str) -> dict:
    """Send a prompt to the local Ollama model and parse its JSON reply.
    Shared by resume parsing and job-match scoring."""
    client = get_client()

    try:
        response = client.chat(
            model=MODEL,
            format="json",  # ask Ollama to constrain output to valid JSON
            options={"temperature": 0.1},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        err_name = type(e).__name__
        if "timeout" in err_name.lower() or "Timeout" in str(e):
            raise RuntimeError(
                f"Ollama took longer than 180s to respond (model: '{MODEL}'). "
                f"This can happen on the very first request while the model loads into "
                f"memory — try again once. If it keeps timing out, your machine may be "
                f"struggling with this model's size; try an even smaller one, e.g. "
                f"`ollama pull qwen2.5:0.5b` then set OLLAMA_MODEL=qwen2.5:0.5b in .env."
            )
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_HOST}. Is `ollama serve` running, "
            f"and have you pulled the '{MODEL}' model? (ollama pull {MODEL})\n"
            f"Original error: {e}"
        )

    text_out = response["message"]["content"].strip()

    # Defensive cleanup in case the model wraps output in code fences anyway.
    if text_out.startswith("```"):
        text_out = text_out.strip("`")
        if text_out.lower().startswith("json"):
            text_out = text_out[4:]
        text_out = text_out.strip()

    try:
        return json.loads(text_out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI response was not valid JSON: {e}\nRaw output: {text_out[:500]}")


def parse_with_ai(resume_text: str) -> dict:
    # Guard against extremely long resumes blowing up the prompt.
    trimmed = resume_text[:15000]
    prompt = EXTRACTION_PROMPT.replace("{resume_text}", trimmed)
    return _chat_json(prompt)


MATCH_PROMPT = """You are a recruiting analyst. Compare this candidate's profile to the job \
description below and return JSON only — no preamble, no markdown fences, no commentary.

Return an object with exactly these keys:
{
  "score": integer from 0 to 100 (overall fit for this specific job),
  "matched_skills": array of strings (requirements from the job the candidate clearly has),
  "missing_skills": array of strings (important requirements the candidate seems to lack),
  "reasoning": string (1-2 sentences explaining the score, specific to this candidate)
}

Be honest and specific — do not default to a generic middle score. A candidate with little
overlap with the role should score low; a strong match should score high.

Candidate profile:
Name: {name}
Years of experience: {years_exp}
Summary: {summary}
Skills: {skills}
Experience: {experience}

Job description:
---
{job_description}
---
"""


def match_resume_to_job(profile: dict, job_description: str) -> dict:
    """Score one candidate profile (as returned by db.get_resumes_for_matching)
    against a job description using the local model."""
    prompt = (
        MATCH_PROMPT.replace("{name}", str(profile.get("name") or "Unknown"))
        .replace("{years_exp}", str(profile.get("years_exp") or "unknown"))
        .replace("{summary}", str(profile.get("summary") or "none provided"))
        .replace("{skills}", ", ".join(profile.get("skills") or []) or "none listed")
        .replace(
            "{experience}",
            "; ".join(
                f"{e.get('title', '')} at {e.get('company', '')}"
                for e in (profile.get("experience") or [])
            )
            or "none listed",
        )
        .replace("{job_description}", job_description[:6000])
    )
    return _chat_json(prompt)


JOB_REQUIREMENTS_PROMPT = """You are a recruiting analyst. Read the job description below and \
extract structured requirements as JSON only — no preamble, no markdown fences, no commentary.

Return an object with exactly these keys:
{
  "title": string or null (the job title),
  "required_skills": array of strings (the specific skills/technologies/tools a candidate needs
    for this role — be concrete, e.g. "Python", "AWS", "SQL", not vague like "programming"),
  "min_years_experience": number or null (minimum total years of professional experience implied
    or stated by the posting; null if not specified),
  "required_education": string or null (the minimum degree level implied or stated, e.g.
    "Bachelor's degree in Computer Science"; null if not specified)
}

Job description:
---
{job_text}
---
"""


def extract_job_requirements(job_text: str) -> dict:
    """Turn a pasted job description into structured requirements
    (title, required_skills, min_years_experience, required_education)
    so matching can compare candidates against concrete criteria instead
    of just free text."""
    trimmed = job_text[:8000]
    prompt = JOB_REQUIREMENTS_PROMPT.replace("{job_text}", trimmed)
    return _chat_json(prompt)
