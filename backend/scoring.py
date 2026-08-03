"""
scoring.py — deterministic candidate-vs-job scoring.

Everything here is plain Python (no AI calls) so it's fast, free, and
reproducible: the same candidate + job always yields the same numbers.
The AI model (see parser.match_resume_to_job) is used *only* for the
qualitative, free-text "reasoning" and to catch skill matches that aren't
exact string matches (e.g. "React.js" vs "React") — its 0-100 score is
blended into the deterministic hiring score as one weighted factor.

Weights (tune here if your hiring priorities differ):
"""
import re

SKILL_WEIGHT = 0.45         # skill match % of required skills
EXPERIENCE_WEIGHT = 0.20    # years of experience vs. requirement
EDUCATION_WEIGHT = 0.15     # highest degree vs. requirement
AI_WEIGHT = 0.20            # holistic AI reasoning score (0-100)

# Rough seniority ranking used to compare a candidate's highest degree
# against a job's stated minimum education requirement. Order matters:
# first match wins, so more specific terms should come first.
_DEGREE_RANK = [
    (r"\bph\.?d\b|doctorate", 5),
    (r"\bmaster|\bm\.?sc\b|\bm\.?tech\b|\bmba\b|\bm\.?a\b", 4),
    (r"\bbachelor|\bb\.?sc\b|\bb\.?tech\b|\bb\.?a\b|\bb\.?e\b", 3),
    (r"\bassociate", 2),
    (r"\bdiploma|\bcertificat", 1),
]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", (text or "").lower()).strip()


def _degree_rank(text: str) -> int:
    norm = _normalize(text)
    for pattern, rank in _DEGREE_RANK:
        if re.search(pattern, norm):
            return rank
    return 0


def compare_skills(candidate_skills: list, required_skills: list) -> dict:
    """Deterministic, case-insensitive comparison of a candidate's skill
    list against a job's required skill list.

    Returns matched / missing / additional skill lists (original casing
    preserved from their source), plus skill match % and skill gap %.
    """
    candidate_skills = candidate_skills or []
    required_skills = required_skills or []

    cand_norm = {_normalize(s): s for s in candidate_skills if s and s.strip()}
    req_norm = {_normalize(s): s for s in required_skills if s and s.strip()}

    matched = [req_norm[k] for k in req_norm if k in cand_norm]
    missing = [req_norm[k] for k in req_norm if k not in cand_norm]
    additional = [cand_norm[k] for k in cand_norm if k not in req_norm]

    total_required = len(req_norm)
    skill_match_pct = round(len(matched) / total_required * 100, 1) if total_required else None
    skill_gap_pct = round(100 - skill_match_pct, 1) if skill_match_pct is not None else None

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "additional_skills": additional,
        "skill_match_pct": skill_match_pct,
        "skill_gap_pct": skill_gap_pct,
    }


def experience_score(candidate_years, min_years_required) -> float | None:
    """0-100. None means the job didn't specify a requirement, so this
    factor is excluded from the hiring score rather than penalizing anyone."""
    if min_years_required is None or min_years_required <= 0:
        return None
    if candidate_years is None:
        return 0.0
    return round(min(100.0, (candidate_years / min_years_required) * 100), 1)


def education_score(candidate_education: list, required_education: str | None) -> float | None:
    """0-100 based on comparing the candidate's highest degree rank to the
    job's stated minimum. None means the job didn't specify a requirement."""
    if not required_education or not required_education.strip():
        return None

    required_rank = _degree_rank(required_education)
    if required_rank == 0:
        return None  # couldn't interpret the requirement — skip this factor

    candidate_rank = max(
        (_degree_rank(ed.get("degree", "")) for ed in (candidate_education or [])), default=0
    )
    if candidate_rank >= required_rank:
        return 100.0
    if candidate_rank == 0:
        return 0.0
    # Partial credit for being one tier below (e.g. Bachelor's when Master's requested)
    return round(max(0.0, (candidate_rank / required_rank) * 100), 1)


def recommendations_for_missing(missing_skills: list) -> list:
    """Plain-language upskilling suggestions for a recruiter or candidate
    to act on. Deliberately simple/templated — no AI call needed."""
    if not missing_skills:
        return ["No skill gaps identified — candidate covers every required skill."]
    recs = []
    for skill in missing_skills:
        recs.append(f"Consider upskilling in or certifying \"{skill}\" to close this gap.")
    return recs


def hiring_score(
    skill_match_pct: float | None,
    exp_score: float | None,
    edu_score: float | None,
    ai_score: float | None,
) -> float:
    """Weighted overall Hiring Score (0-100), re-normalizing weights across
    whichever factors are actually available (e.g. if the job has no stated
    experience/education requirement, that weight is redistributed)."""
    factors = [
        (skill_match_pct, SKILL_WEIGHT),
        (exp_score, EXPERIENCE_WEIGHT),
        (edu_score, EDUCATION_WEIGHT),
        (ai_score, AI_WEIGHT),
    ]
    available = [(val, weight) for val, weight in factors if val is not None]
    if not available:
        return 0.0
    total_weight = sum(weight for _, weight in available)
    score = sum(val * weight for val, weight in available) / total_weight
    return round(score, 1)


def summarize_interview(evaluations: list) -> dict:
    """Aggregate per-question evaluations (each with relevance_score,
    communication_score, confidence_score) into an overall interview
    performance report: average scores per dimension, one overall score,
    a plain-language verdict, and the pooled strengths/improvements."""
    if not evaluations:
        return {
            "overall_score": 0.0,
            "avg_relevance": None,
            "avg_communication": None,
            "avg_confidence": None,
            "verdict": "No answers were submitted.",
            "strengths": [],
            "improvements": [],
        }

    def _avg(key):
        vals = [e.get(key) for e in evaluations if e.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    avg_relevance = _avg("relevance_score")
    avg_communication = _avg("communication_score")
    avg_confidence = _avg("confidence_score")

    dims = [v for v in (avg_relevance, avg_communication, avg_confidence) if v is not None]
    overall = round(sum(dims) / len(dims), 1) if dims else 0.0

    if overall >= 80:
        verdict = "Strong performance — clear, relevant, and confident across most answers."
    elif overall >= 60:
        verdict = "Solid performance with some gaps — worth a follow-up round."
    elif overall >= 40:
        verdict = "Mixed performance — notable gaps in relevance or communication."
    else:
        verdict = "Weak performance — significant gaps across most answers."

    strengths, improvements = [], []
    for e in evaluations:
        strengths.extend(e.get("strengths") or [])
        improvements.extend(e.get("improvements") or [])

    def _dedupe(items, limit=6):
        seen, out = set(), []
        for item in items:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item)
            if len(out) >= limit:
                break
        return out

    return {
        "overall_score": overall,
        "avg_relevance": avg_relevance,
        "avg_communication": avg_communication,
        "avg_confidence": avg_confidence,
        "verdict": verdict,
        "strengths": _dedupe(strengths),
        "improvements": _dedupe(improvements),
    }
