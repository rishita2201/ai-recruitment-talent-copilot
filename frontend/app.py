"""
app.py — Streamlit frontend for the AI Resume Parser.

Three views, controlled entirely by st.session_state["page"]:
  landing  -> marketing splash page, no auth required
  auth     -> combined sign in / sign up card
  app      -> the real product (Candidates / Match Job / Dashboard), auth required

Run with:
    streamlit run app.py
"""
import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(
    page_title="Resume Parser — AI-assisted hiring intake",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "page": "landing",       # landing | auth | app
    "auth_tab": "login",     # login | signup
    "token": None,
    "username": None,
    "selected_resume_id": None,
    "job_description": "",
    "match_job_id": None,
    "match_job_title": None,
    "match_results": None,          # {"job_title", "required_skills", ..., "results": [...]}
    "match_job_choice": None,       # "adhoc" or a saved job's id
    "interview_session": None,      # currently open interview session dict
    "pipeline_job_filter": None,    # job_id filter for Pipeline tab, or None = all
}
for key, default in _DEFAULTS.items():
    st.session_state.setdefault(key, default)


def goto(page: str):
    st.session_state["page"] = page


def is_authed() -> bool:
    return bool(st.session_state["token"])


# ---------------------------------------------------------------------------
# Shared styling
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
      :root {
        --ink: #16161F;          /* primary text — near-black, not gray */
        --ink-soft: #4A4A5C;     /* secondary text — still readable, not pale */
        --muted: #6B6B80;        /* tertiary/meta text — the lightest we go */
        --accent: #5B3FD9;       /* primary purple */
        --accent-soft: #F3F1FC;  /* accent tint background */
        --border: #E3E1F2;
        --card-bg: #FBFAFF;
        --good: #12805C;
        --warn: #B25E09;
        --bad: #C4302B;
      }

      #MainMenu, footer, header {visibility: hidden;}
      .block-container {padding-top: 2rem; max-width: 1150px;}

      html, body, [class*="css"] {
        color: var(--ink) !important;
        font-size: 16px;
      }

      h1, h2, h3, h4, h5 { color: var(--ink) !important; font-weight: 800 !important; }
      p, li, label, span { color: var(--ink) !important; }

      /* Streamlit's own caption/help text defaults to a very pale gray —
         override it everywhere so secondary text stays legible. */
      [data-testid="stCaptionContainer"], .stCaption, small {
        color: var(--ink-soft) !important;
        font-size: 0.92rem !important;
        font-weight: 500 !important;
      }

      /* Buttons: bolder weight + clearer primary/secondary contrast */
      .stButton > button {
        font-weight: 700 !important;
        border-radius: 8px !important;
        border: 1.5px solid var(--border) !important;
      }
      .stButton > button[kind="primary"] {
        background: var(--accent) !important;
        border-color: var(--accent) !important;
        color: #FFFFFF !important;
      }

      /* Inputs */
      .stTextInput input, .stTextArea textarea {
        color: var(--ink) !important;
        font-weight: 500 !important;
        border-radius: 8px !important;
      }
      .stTextInput input::placeholder, .stTextArea textarea::placeholder {
        color: var(--muted) !important;
        opacity: 1 !important;
      }

      /* Tabs */
      .stTabs [data-baseweb="tab"] {
        font-weight: 700 !important;
        font-size: 1rem !important;
        color: var(--ink-soft) !important;
      }
      .stTabs [aria-selected="true"] { color: var(--accent) !important; }

      /* Metrics */
      [data-testid="stMetricValue"] { color: var(--ink) !important; font-weight: 800 !important; }
      [data-testid="stMetricLabel"] { color: var(--ink-soft) !important; font-weight: 600 !important; }

      /* --- Landing page --- */
      .hero {text-align: center; padding: 3.5rem 1rem 1.5rem;}
      .hero .mark {font-size: 2.4rem; color: var(--accent);}
      .hero h1 {
        font-size: 3.1rem; font-weight: 800 !important; margin: 0.3rem 0 0.6rem;
        letter-spacing: -0.02em; color: var(--ink) !important;
      }
      .hero p.tagline {
        font-size: 1.2rem; font-weight: 500; color: var(--ink-soft) !important;
        max-width: 640px; margin: 0 auto 1.8rem; line-height: 1.55;
      }

      .feature-card {
        background: var(--card-bg); border: 1.5px solid var(--border); border-radius: 14px;
        padding: 1.5rem 1.3rem; height: 100%;
      }
      .feature-card .ic {font-size: 1.7rem; margin-bottom: 0.5rem; display:block;}
      .feature-card h4 {margin: 0 0 0.5rem; font-size: 1.1rem; font-weight: 800 !important; color: var(--ink) !important;}
      .feature-card p {margin: 0; color: var(--ink-soft) !important; font-size: 0.95rem; line-height: 1.5; font-weight: 500;}

      .auth-card-wrap {max-width: 420px; margin: 2rem auto 0;}

      /* --- Candidate UI --- */
      .skill-chip {
        display: inline-block; background: var(--accent-soft); color: var(--accent) !important;
        border: 1.5px solid #D9D2F7; border-radius: 999px; padding: 0.2rem 0.75rem;
        margin: 0.15rem; font-size: 0.86rem; font-weight: 700;
      }
      .score-badge {
        display: inline-block; font-size: 1.7rem; font-weight: 800; border-radius: 10px;
        padding: 0.25rem 1rem; margin-bottom: 0.4rem;
      }
      .cand-card {
        border: 1.5px solid var(--border); border-radius: 10px; padding: 0.7rem 0.9rem; margin-bottom: 0.5rem;
        background: var(--card-bg);
      }
      .cand-card .name {font-weight: 700; color: var(--ink) !important;}
      .cand-card .sub {color: var(--ink-soft) !important; font-size: 0.85rem; font-weight: 500;}

      .section-label {
        font-size: 0.95rem; font-weight: 800; color: var(--ink) !important;
        text-transform: uppercase; letter-spacing: 0.04em; margin: 1.1rem 0 0.4rem;
      }
      .meta-line { color: var(--ink-soft) !important; font-weight: 600; font-size: 0.95rem; }

      /* --- Skill-gap visuals --- */
      .gap-bar-track {
        background: var(--border); border-radius: 999px; height: 10px; width: 100%;
        overflow: hidden; margin: 0.3rem 0 0.15rem;
      }
      .gap-bar-fill { height: 100%; border-radius: 999px; }
      .gap-bar-label {
        display: flex; justify-content: space-between; font-size: 0.85rem;
        font-weight: 700; color: var(--ink-soft) !important;
      }
      .job-chip {
        display: inline-block; background: var(--card-bg); border: 1.5px solid var(--border);
        border-radius: 8px; padding: 0.15rem 0.6rem; margin: 0.15rem 0.15rem 0.15rem 0;
        font-size: 0.85rem; font-weight: 700; color: var(--ink-soft) !important;
      }
      .rec-box {
        background: var(--accent-soft); border: 1.5px solid #D9D2F7; border-radius: 10px;
        padding: 0.7rem 0.9rem; font-size: 0.92rem; font-weight: 600; color: var(--ink) !important;
      }

      /* --- Interview & pipeline visuals --- */
      .diff-badge {
        display: inline-block; border-radius: 6px; padding: 0.05rem 0.55rem;
        font-size: 0.75rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.03em;
        margin-left: 0.5rem;
      }
      .diff-Beginner { background: #E6F4EC; color: var(--good) !important; }
      .diff-Intermediate { background: #FDF1DF; color: var(--warn) !important; }
      .diff-Advanced { background: #FBE6E5; color: var(--bad) !important; }

      .stage-col-header {
        font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.03em;
        color: var(--ink-soft) !important; text-align: center; padding: 0.4rem 0; border-radius: 8px 8px 0 0;
        background: var(--card-bg); border: 1.5px solid var(--border); border-bottom: none;
      }
      .stage-col-body {
        border: 1.5px solid var(--border); border-radius: 0 0 8px 8px; min-height: 60px;
        padding: 0.5rem; background: #FFFFFF;
      }
      .pipeline-card {
        border: 1.5px solid var(--border); border-radius: 8px; padding: 0.5rem 0.6rem;
        margin-bottom: 0.4rem; background: var(--card-bg); font-size: 0.85rem; font-weight: 700;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Shared helpers: scoring visuals + downloadable reports
# ---------------------------------------------------------------------------

def _score_color(value) -> str:
    if value is None:
        return "#6B6B80"
    if value >= 70:
        return "#12805C"
    if value >= 40:
        return "#B25E09"
    return "#C4302B"


def score_badge_html(label: str, value, size: str = "1.7rem") -> str:
    color = _score_color(value)
    shown = f"{value}" if value is not None else "—"
    return (
        f'<div>'
        f'<span class="score-badge" style="background:{color}22; color:{color}; font-size:{size};">{shown}</span>'
        f'<div class="meta-line" style="margin-top:-0.3rem;">{label}</div>'
        f'</div>'
    )


def gap_bar_html(label: str, pct, color: str | None = None) -> str:
    pct_val = 0 if pct is None else max(0, min(100, pct))
    color = color or _score_color(pct)
    shown = f"{pct}%" if pct is not None else "n/a"
    return (
        f'<div class="gap-bar-label"><span>{label}</span><span>{shown}</span></div>'
        f'<div class="gap-bar-track"><div class="gap-bar-fill" '
        f'style="width:{pct_val}%; background:{color};"></div></div>'
    )


def chip_row_html(items: list, css_class: str = "skill-chip") -> str:
    if not items:
        return '<span class="meta-line">None</span>'
    return "".join(f'<span class="{css_class}">{s}</span>' for s in items)


def build_candidate_report_md(job_title: str, result: dict) -> str:
    """Markdown skill-gap report for a single candidate — used for the
    per-candidate download button."""
    lines = [
        f"# Skill-Gap Report — {result['name']}",
        f"**Job:** {job_title}",
        "",
        f"- **Hiring Score:** {result.get('hiring_score')}/100",
        f"- **Skill Match:** {result.get('skill_match_pct')}%",
        f"- **Skill Gap:** {result.get('skill_gap_pct')}%",
        f"- **Experience fit:** {result.get('experience_score')}",
        f"- **Education fit:** {result.get('education_score')}",
        f"- **AI holistic score:** {result.get('ai_score')}",
        "",
        "## Matched skills",
        ", ".join(result.get("matched_skills") or []) or "None",
        "",
        "## Missing skills",
        ", ".join(result.get("missing_skills") or []) or "None",
        "",
        "## Additional skills (beyond the job's requirements)",
        ", ".join(result.get("additional_skills") or []) or "None",
        "",
        "## Recommendations",
    ]
    lines += [f"- {r}" for r in (result.get("recommendations") or [])]
    lines += ["", "## AI reasoning", result.get("reasoning") or "—"]
    return "\n".join(lines)


def build_results_csv(results: list) -> str:
    """CSV export of a full ranked candidate list — one row per candidate."""
    rows = []
    for r in results:
        rows.append(
            {
                "rank": None,  # filled in after sort below
                "name": r["name"],
                "hiring_score": r.get("hiring_score"),
                "skill_match_pct": r.get("skill_match_pct"),
                "skill_gap_pct": r.get("skill_gap_pct"),
                "experience_score": r.get("experience_score"),
                "education_score": r.get("education_score"),
                "ai_score": r.get("ai_score"),
                "matched_skills": "; ".join(r.get("matched_skills") or []),
                "missing_skills": "; ".join(r.get("missing_skills") or []),
                "additional_skills": "; ".join(r.get("additional_skills") or []),
            }
        )
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return pd.DataFrame(rows).to_csv(index=False)


def difficulty_badge_html(difficulty: str) -> str:
    diff = difficulty if difficulty in ("Beginner", "Intermediate", "Advanced") else "Intermediate"
    return f'<span class="diff-badge diff-{diff}">{diff}</span>'


def build_interview_report_md(session: dict) -> str:
    """Markdown interview performance report — downloadable after completing
    a simulated interview session."""
    report = session.get("report") or {}
    lines = [
        f"# Interview Performance Report — {session.get('resume_name')}",
        f"**Job:** {session.get('job_title')}",
        "",
        f"- **Overall Score:** {report.get('overall_score')}/100",
        f"- **Relevance (avg):** {report.get('avg_relevance')}",
        f"- **Communication (avg):** {report.get('avg_communication')}",
        f"- **Confidence (avg):** {report.get('avg_confidence')}",
        "",
        f"**Verdict:** {report.get('verdict')}",
        "",
        "## Strengths",
    ]
    lines += [f"- {s}" for s in (report.get("strengths") or [])] or ["- None noted"]
    lines += ["", "## Areas to improve"]
    lines += [f"- {s}" for s in (report.get("improvements") or [])] or ["- None noted"]
    lines += ["", "## Question-by-question detail"]
    evaluations = session.get("evaluations") or {}
    answers = session.get("answers") or {}
    for q in session.get("questions") or []:
        qid = q["id"]
        ev = evaluations.get(qid)
        lines.append(f"\n### [{q['category'].title()} · {q['difficulty']}] {q['question']}")
        lines.append(f"**Answer:** {answers.get(qid, '(not answered)')}")
        if ev:
            lines.append(
                f"**Scores:** relevance {ev.get('relevance_score')}, "
                f"communication {ev.get('communication_score')}, confidence {ev.get('confidence_score')}"
            )
            lines.append(f"**Feedback:** {ev.get('feedback', '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

def render_landing():
    st.markdown(
        """
        <div class="hero">
          <span class="mark">◆</span>
          <h1>Resume Parser</h1>
          <p class="tagline">Upload resumes, let AI turn them into structured candidate
          profiles, rank them against a job description, and track your pipeline —
          all in one place.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("Get started — it's free", type="primary", use_container_width=True):
            st.session_state["auth_tab"] = "signup"
            goto("auth")
            st.rerun()
    with c2:
        if st.button("Log in", use_container_width=True):
            st.session_state["auth_tab"] = "login"
            goto("auth")
            st.rerun()
    with c3:
        st.write("")

    st.write("")
    st.write("")

    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown(
            """<div class="feature-card"><span class="ic">📄</span>
            <h4>AI resume parsing</h4>
            <p>Drop in a PDF, DOCX, or TXT resume and get back a clean structured
            profile — contact info, skills, education, and work history.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with f2:
        st.markdown(
            """<div class="feature-card"><span class="ic">🎯</span>
            <h4>Job matching & hiring score</h4>
            <p>Save job descriptions once, then rank every candidate by a weighted
            Hiring Score — skill match %, experience, education, and AI judgment
            combined, with a full matched/missing/additional skills breakdown.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with f3:
        st.markdown(
            """<div class="feature-card"><span class="ic">📊</span>
            <h4>Pipeline dashboard</h4>
            <p>See headcount, average experience, top skills, and degree
            breakdowns across your whole candidate pool at a glance.</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    st.write("")
    st.caption("No credit card. No setup beyond signing up — your account keeps your candidate pool private.")


# ---------------------------------------------------------------------------
# Auth page (sign in / sign up)
# ---------------------------------------------------------------------------

def render_auth():
    left, mid, right = st.columns([1, 2, 1])
    with mid:
        st.markdown('<div class="auth-card-wrap">', unsafe_allow_html=True)
        st.markdown("### ◆ Resume Parser")

        tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)
            if submitted:
                if not username or not password:
                    st.error("Enter both your username and password.")
                else:
                    with st.spinner("Logging in…"):
                        ok, data = api.login(username, password)
                    if ok:
                        st.session_state["token"] = data["token"]
                        st.session_state["username"] = data["username"]
                        goto("app")
                        st.rerun()
                    else:
                        st.error(data)

        with tab_signup:
            with st.form("signup_form"):
                s_username = st.text_input("Choose a username", key="signup_username")
                s_email = st.text_input("Email", key="signup_email")
                s_password = st.text_input("Password", type="password", key="signup_password")
                s_password2 = st.text_input("Confirm password", type="password", key="signup_password2")
                st.caption("At least 8 characters. Username: letters, numbers, '.', '_', '-'.")
                submitted2 = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if submitted2:
                if not all([s_username, s_email, s_password, s_password2]):
                    st.error("Please fill in every field.")
                elif s_password != s_password2:
                    st.error("Passwords don't match.")
                else:
                    with st.spinner("Creating your account…"):
                        ok, data = api.signup(s_username, s_email, s_password)
                    if ok:
                        st.session_state["token"] = data["token"]
                        st.session_state["username"] = data["username"]
                        goto("app")
                        st.rerun()
                    else:
                        st.error(data)

        st.write("")
        if st.button("← Back to homepage"):
            goto("landing")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main app (post-login)
# ---------------------------------------------------------------------------

def render_topbar():
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            f'<h4 style="margin-bottom:0;">◆ Resume Parser</h4>'
            f'<div class="meta-line">signed in as <b>{st.session_state["username"]}</b></div>',
            unsafe_allow_html=True,
        )
    with c2:
        if st.button("Log out", use_container_width=True):
            api.logout(st.session_state["token"])
            st.session_state["token"] = None
            st.session_state["username"] = None
            st.session_state["selected_resume_id"] = None
            goto("landing")
            st.rerun()


def render_candidates_tab():
    token = st.session_state["token"]
    left, right = st.columns([1, 1.4])

    with left:
        st.markdown('<div class="section-label">Upload a resume</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "PDF, DOCX, or TXT", type=["pdf", "docx", "txt", "md"], label_visibility="collapsed"
        )
        if uploaded is not None:
            cache_key = f"uploaded::{uploaded.name}::{uploaded.size}"
            if st.session_state.get("_last_upload") != cache_key:
                with st.spinner("Extracting text and parsing with AI…"):
                    ok, data = api.upload_resume(token, uploaded.name, uploaded.getvalue())
                if ok:
                    st.session_state["_last_upload"] = cache_key
                    st.session_state["selected_resume_id"] = data["id"]
                    st.success(f"Parsed **{data.get('name') or uploaded.name}** successfully.")
                    st.rerun()
                else:
                    st.error(data)

        st.markdown('<div class="section-label">Candidates</div>', unsafe_allow_html=True)
        query = st.text_input("Search name, skill, keyword…", label_visibility="collapsed", placeholder="Search name, skill, keyword…")
        ok, resumes = api.list_resumes(token, query or None)
        if not ok:
            st.error(resumes)
            resumes = []

        if not resumes:
            st.info("No resumes yet. Upload one above to get started.")
        for r in resumes:
            with st.container(border=True):
                cc1, cc2 = st.columns([4, 1])
                with cc1:
                    st.markdown(f"**{r.get('name') or 'Unnamed candidate'}**")
                    sub_bits = [b for b in [r.get("email"), r.get("location")] if b]
                    if sub_bits:
                        st.caption(" · ".join(sub_bits))
                with cc2:
                    if st.button("View", key=f"view_{r['id']}", use_container_width=True):
                        st.session_state["selected_resume_id"] = r["id"]
                        st.rerun()

    with right:
        render_candidate_detail(token)


def render_candidate_detail(token: str):
    rid = st.session_state["selected_resume_id"]
    if not rid:
        st.info("Select a candidate on the left to view their parsed dossier.")
        return

    ok, r = api.get_resume(token, rid)
    if not ok:
        st.error(r)
        return

    st.markdown(f"### {r.get('name') or 'Unnamed candidate'}")
    contact_bits = [b for b in [r.get("email"), r.get("phone"), r.get("location")] if b]
    if contact_bits:
        st.caption(" · ".join(contact_bits))

    meta_bits = []
    if r.get("years_exp") is not None:
        meta_bits.append(f"{r['years_exp']} yrs experience")
    if r.get("filename"):
        meta_bits.append(r["filename"])
    if meta_bits:
        st.caption(" · ".join(meta_bits))

    b1, b2 = st.columns(2)
    with b1:
        if st.button("◎ Score vs. selected job", use_container_width=True):
            has_saved_job = bool(st.session_state.get("match_job_id"))
            has_adhoc_text = bool(st.session_state["job_description"].strip())
            if not has_saved_job and not has_adhoc_text:
                st.warning("Choose or paste a job on the **Match Job** tab first.")
            else:
                with st.spinner("Scoring candidate…"):
                    ok2, data = api.match_candidates(
                        token,
                        job_id=st.session_state.get("match_job_id"),
                        job_description=None if has_saved_job else st.session_state["job_description"],
                        resume_id=rid,
                    )
                if ok2 and data.get("results"):
                    st.session_state[f"score_{rid}"] = {"job_title": data.get("job_title"), **data["results"][0]}
                else:
                    st.error(data if not ok2 else "No score returned.")
    with b2:
        if st.button("✕ Delete candidate", use_container_width=True):
            ok3, data = api.delete_resume(token, rid)
            if ok3:
                st.session_state["selected_resume_id"] = None
                st.success("Deleted.")
                st.rerun()
            else:
                st.error(data)

    score = st.session_state.get(f"score_{rid}")
    if score:
        st.markdown(f'<div class="meta-line">vs. <b>{score.get("job_title","this job")}</b></div>', unsafe_allow_html=True)
        st.markdown(score_badge_html("Hiring Score", score.get("hiring_score")), unsafe_allow_html=True)
        st.write(score.get("reasoning", ""))

        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            st.markdown(gap_bar_html("Skill match", score.get("skill_match_pct")), unsafe_allow_html=True)
        with bc2:
            st.markdown(gap_bar_html("Experience fit", score.get("experience_score")), unsafe_allow_html=True)
        with bc3:
            st.markdown(gap_bar_html("Education fit", score.get("education_score")), unsafe_allow_html=True)

        with st.expander("Skill-gap breakdown, recommendations & report"):
            st.markdown("**Matched skills**")
            st.markdown(chip_row_html(score.get("matched_skills"), "skill-chip"), unsafe_allow_html=True)
            st.markdown("**Missing skills**")
            st.markdown(chip_row_html(score.get("missing_skills"), "job-chip"), unsafe_allow_html=True)
            st.markdown("**Additional skills** (beyond what the job asked for)")
            st.markdown(chip_row_html(score.get("additional_skills"), "job-chip"), unsafe_allow_html=True)
            if score.get("recommendations"):
                st.markdown("**Recommendations**")
                st.markdown(
                    '<div class="rec-box">' + "<br>".join(f"• {r}" for r in score["recommendations"]) + "</div>",
                    unsafe_allow_html=True,
                )
            st.download_button(
                "⬇ Download skill-gap report (Markdown)",
                data=build_candidate_report_md(score.get("job_title", "this job"), score),
                file_name=f"skill_gap_report_{(score.get('name') or 'candidate').replace(' ', '_')}.md",
                mime="text/markdown",
                key=f"detail_report_{rid}",
            )

    st.markdown('<div class="section-label">Summary</div>', unsafe_allow_html=True)
    st.write(r.get("summary") or "—")

    st.markdown('<div class="section-label">Skills</div>', unsafe_allow_html=True)
    skills = r.get("skills") or []
    if skills:
        st.markdown("".join(f'<span class="skill-chip">{s}</span>' for s in skills), unsafe_allow_html=True)
    else:
        st.write("—")

    st.markdown('<div class="section-label">Experience</div>', unsafe_allow_html=True)
    experience = r.get("experience") or []
    if experience:
        for e in experience:
            span = " – ".join([b for b in [e.get("start"), e.get("end")] if b])
            st.markdown(
                f'<div style="font-weight:700;">{e.get("title","")} — {e.get("company","")}</div>'
                f'<div class="meta-line">{span}</div>',
                unsafe_allow_html=True,
            )
            for h in e.get("highlights") or []:
                st.markdown(f"- {h}")
    else:
        st.write("—")

    st.markdown('<div class="section-label">Education</div>', unsafe_allow_html=True)
    education = r.get("education") or []
    if education:
        for ed in education:
            year = f" ({ed['year']})" if ed.get("year") else ""
            st.markdown(f"**{ed.get('degree', '')}** — {ed.get('institution', '')}{year}")
    else:
        st.write("—")

    st.markdown('<div class="section-label">Notes</div>', unsafe_allow_html=True)
    notes = st.text_area(
        "Notes", value=r.get("notes") or "", height=120, label_visibility="collapsed",
        placeholder="Interview impressions, follow-ups, red flags…", key=f"notes_{rid}",
    )
    if st.button("Save notes", key=f"save_notes_{rid}"):
        ok4, data = api.update_notes(token, rid, notes)
        if ok4:
            st.success("Notes saved.")
        else:
            st.error(data)


def render_jobs_tab():
    token = st.session_state["token"]
    left, right = st.columns([1, 1.2])

    with left:
        st.markdown('<div class="section-label">Save a job description</div>', unsafe_allow_html=True)
        st.caption(
            "Paste the job text. Leave title, required skills, minimum experience, or "
            "education blank and the AI will fill them in from the text."
        )
        with st.form("create_job_form"):
            title = st.text_input("Job title (optional)", placeholder="e.g. Senior Backend Engineer")
            raw_text = st.text_area("Job description text", height=200, placeholder="Paste the full job posting here…")
            skills_csv = st.text_input(
                "Required skills — comma separated (optional)", placeholder="Python, AWS, PostgreSQL"
            )
            c1, c2 = st.columns(2)
            with c1:
                min_years = st.number_input(
                    "Minimum years experience (optional)", min_value=0.0, max_value=40.0, value=0.0, step=0.5
                )
            with c2:
                required_education = st.text_input(
                    "Minimum education (optional)", placeholder="e.g. Bachelor's degree"
                )
            submitted = st.form_submit_button("Save job description", type="primary", use_container_width=True)

        if submitted:
            if not raw_text.strip():
                st.error("Paste the job description text first.")
            else:
                required_skills = [s.strip() for s in skills_csv.split(",") if s.strip()] or None
                with st.spinner("Saving job (AI fills in any missing requirements)…"):
                    ok, data = api.create_job(
                        token,
                        raw_text,
                        title=title or None,
                        required_skills=required_skills,
                        min_years_experience=min_years or None,
                        required_education=required_education or None,
                    )
                if ok:
                    st.success(f"Saved **{data['title']}**.")
                    st.rerun()
                else:
                    st.error(data)

    with right:
        st.markdown('<div class="section-label">Saved job descriptions</div>', unsafe_allow_html=True)
        ok, jobs = api.list_jobs(token)
        if not ok:
            st.error(jobs)
            jobs = []
        if not jobs:
            st.info("No saved job descriptions yet — create one on the left.")
        for j in jobs:
            with st.container(border=True):
                st.markdown(f"**{j['title']}**")
                meta_bits = []
                if j.get("min_years_experience") is not None:
                    meta_bits.append(f"{j['min_years_experience']}+ yrs")
                if j.get("required_education"):
                    meta_bits.append(j["required_education"])
                if meta_bits:
                    st.markdown(f'<div class="meta-line">{" · ".join(meta_bits)}</div>', unsafe_allow_html=True)
                if j.get("required_skills"):
                    st.markdown(chip_row_html(j["required_skills"], "job-chip"), unsafe_allow_html=True)
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("Use in Match Job", key=f"use_job_{j['id']}", use_container_width=True):
                        st.session_state["match_job_id"] = j["id"]
                        st.session_state["match_job_title"] = j["title"]
                        st.success(f'"{j["title"]}" selected — open the **Match Job** tab to rank candidates.')
                with cc2:
                    if st.button("Delete", key=f"del_job_{j['id']}", use_container_width=True):
                        ok2, data = api.delete_job(token, j["id"])
                        if ok2:
                            if st.session_state.get("match_job_id") == j["id"]:
                                st.session_state["match_job_id"] = None
                                st.session_state["match_job_title"] = None
                            st.rerun()
                        else:
                            st.error(data)



def render_match_tab():
    token = st.session_state["token"]

    ok, jobs = api.list_jobs(token)
    if not ok:
        jobs = []
    job_options = ["✎ Paste a one-off job description"] + [f"{j['title']} (#{j['id']})" for j in jobs]
    id_by_label = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs}

    default_index = 0
    if st.session_state.get("match_job_id"):
        wanted = f"{st.session_state['match_job_title']} (#{st.session_state['match_job_id']})"
        if wanted in job_options:
            default_index = job_options.index(wanted)

    st.markdown('<div class="section-label">Choose a job</div>', unsafe_allow_html=True)
    choice = st.selectbox(
        "Job",
        job_options,
        index=default_index,
        label_visibility="collapsed",
        key="match_job_choice",
    )

    using_saved_job = choice in id_by_label
    if using_saved_job:
        st.session_state["match_job_id"] = id_by_label[choice]
        st.session_state["match_job_title"] = choice.rsplit(" (#", 1)[0]
        st.caption("Using a saved Job Description — manage these on the **Job Descriptions** tab.")
    else:
        st.session_state["match_job_id"] = None
        st.session_state["job_description"] = st.text_area(
            "Job description", value=st.session_state["job_description"], height=200,
            label_visibility="collapsed", placeholder="Paste the job description here…",
        )

    if st.button("⟶ Rank all candidates", type="primary"):
        if not using_saved_job and not st.session_state["job_description"].strip():
            st.warning("Paste a job description first, or save/select one on the Job Descriptions tab.")
        else:
            with st.spinner("Scoring every candidate — skill match, experience, education, and AI judgment…"):
                ok2, data = api.match_candidates(
                    token,
                    job_id=st.session_state["match_job_id"],
                    job_description=None if using_saved_job else st.session_state["job_description"],
                )
            if ok2:
                st.session_state["match_results"] = data
            else:
                st.error(data)

    data = st.session_state.get("match_results")
    st.markdown('<div class="section-label">Rankings</div>', unsafe_allow_html=True)
    if not data or not data.get("results"):
        st.info('No rankings yet — choose a job above and click "Rank all candidates".')
        return

    results = data["results"]  # already sorted descending by hiring_score from the backend

    req_bits = []
    if data.get("required_skills"):
        req_bits.append(f"{len(data['required_skills'])} required skills")
    if data.get("min_years_experience"):
        req_bits.append(f"{data['min_years_experience']}+ yrs experience")
    if data.get("required_education"):
        req_bits.append(data["required_education"])
    st.markdown(
        f'<div class="meta-line">Ranked for <b>{data.get("job_title","this job")}</b>'
        + (f' · {" · ".join(req_bits)}' if req_bits else "")
        + "</div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "⬇ Download full rankings (CSV)",
        data=build_results_csv(results),
        file_name="candidate_rankings.csv",
        mime="text/csv",
    )
    st.write("")

    for rank, res in enumerate(results, start=1):
        with st.container(border=True):
            c1, c2 = st.columns([1, 5])
            with c1:
                st.markdown(f"**#{rank}**")
                st.markdown(score_badge_html("Hiring Score", res.get("hiring_score")), unsafe_allow_html=True)
            with c2:
                st.markdown(f"**{res['name']}**")
                st.write(res.get("reasoning", ""))

                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    st.markdown(gap_bar_html("Skill match", res.get("skill_match_pct")), unsafe_allow_html=True)
                with bc2:
                    st.markdown(gap_bar_html("Experience fit", res.get("experience_score")), unsafe_allow_html=True)
                with bc3:
                    st.markdown(gap_bar_html("Education fit", res.get("education_score")), unsafe_allow_html=True)

                with st.expander("Skill-gap breakdown, recommendations & report"):
                    st.markdown("**Matched skills**")
                    st.markdown(chip_row_html(res.get("matched_skills"), "skill-chip"), unsafe_allow_html=True)
                    st.markdown("**Missing skills**")
                    st.markdown(chip_row_html(res.get("missing_skills"), "job-chip"), unsafe_allow_html=True)
                    st.markdown("**Additional skills** (beyond what the job asked for)")
                    st.markdown(chip_row_html(res.get("additional_skills"), "job-chip"), unsafe_allow_html=True)

                    if res.get("recommendations"):
                        st.markdown("**Recommendations**")
                        st.markdown(
                            '<div class="rec-box">' + "<br>".join(f"• {r}" for r in res["recommendations"]) + "</div>",
                            unsafe_allow_html=True,
                        )

                    st.download_button(
                        "⬇ Download this candidate's skill-gap report (Markdown)",
                        data=build_candidate_report_md(data.get("job_title", "this job"), res),
                        file_name=f"skill_gap_report_{res['name'].replace(' ', '_')}.md",
                        mime="text/markdown",
                        key=f"report_{res['id']}",
                    )


def render_interview_tab():
    token = st.session_state["token"]

    st.markdown('<div class="section-label">Start a new interview prep</div>', unsafe_allow_html=True)

    ok, candidates = api.list_resumes(token)
    if not ok:
        candidates = []
    ok2, jobs = api.list_jobs(token)
    if not ok2:
        jobs = []

    if not candidates:
        st.info("Upload at least one candidate on the Candidates tab first.")
        return

    c1, c2 = st.columns(2)
    with c1:
        cand_labels = [f"{c.get('name') or 'Unnamed'} (#{c['id']})" for c in candidates]
        cand_choice = st.selectbox("Candidate", cand_labels, key="interview_candidate_choice")
        resume_id = candidates[cand_labels.index(cand_choice)]["id"]
    with c2:
        job_options = ["✎ Paste a one-off job description"] + [f"{j['title']} (#{j['id']})" for j in jobs]
        id_by_label = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs}
        job_choice = st.selectbox("Job", job_options, key="interview_job_choice")

    using_saved_job = job_choice in id_by_label
    adhoc_text = ""
    if not using_saved_job:
        adhoc_text = st.text_area("Job description", height=140, placeholder="Paste the job description here…")

    if st.button("✦ Generate interview questions", type="primary"):
        if not using_saved_job and not adhoc_text.strip():
            st.warning("Paste a job description, or pick a saved one.")
        else:
            with st.spinner("Analyzing the role and candidate profile to build interview questions…"):
                ok3, data = api.generate_interview(
                    token,
                    resume_id,
                    job_id=id_by_label.get(job_choice) if using_saved_job else None,
                    job_description=None if using_saved_job else adhoc_text,
                )
            if ok3:
                st.session_state["interview_session"] = data
                st.rerun()
            else:
                st.error(data)

    st.markdown('<div class="section-label">Simulated interview</div>', unsafe_allow_html=True)
    session = st.session_state.get("interview_session")
    if not session:
        st.info("Generate a question set above to start a simulated interview.")
    else:
        render_interview_session(token, session)

    st.markdown('<div class="section-label">Past interview sessions</div>', unsafe_allow_html=True)
    ok4, sessions = api.list_interview_sessions(token)
    if not ok4:
        st.error(sessions)
        sessions = []
    if not sessions:
        st.caption("No interview sessions yet.")
    for s in sessions:
        with st.container(border=True):
            sc1, sc2, sc3 = st.columns([3, 1, 1])
            with sc1:
                st.markdown(f"**{s['resume_name']}** vs **{s['job_title']}**")
                status_txt = "Completed" if s["status"] == "completed" else "In progress"
                overall = (s.get("report") or {}).get("overall_score")
                st.caption(f"{status_txt}" + (f" · Overall score {overall}/100" if overall is not None else ""))
            with sc2:
                if st.button("Open", key=f"open_session_{s['id']}", use_container_width=True):
                    ok5, full = api.get_interview_session(token, s["id"])
                    if ok5:
                        st.session_state["interview_session"] = full
                        st.rerun()
                    else:
                        st.error(full)
            with sc3:
                if st.button("Delete", key=f"del_session_{s['id']}", use_container_width=True):
                    ok6, data = api.delete_interview_session(token, s["id"])
                    if ok6:
                        if st.session_state.get("interview_session", {}).get("id") == s["id"]:
                            st.session_state["interview_session"] = None
                        st.rerun()
                    else:
                        st.error(data)


def render_interview_session(token: str, session: dict):
    st.markdown(
        f'<div class="meta-line">Interviewing <b>{session["resume_name"]}</b> for '
        f'<b>{session["job_title"]}</b></div>',
        unsafe_allow_html=True,
    )

    categories = [("technical", "Technical questions"), ("behavioral", "Behavioral questions"), ("follow_up", "Follow-up questions")]
    for cat_key, cat_label in categories:
        qs = [q for q in session["questions"] if q["category"] == cat_key]
        if not qs:
            continue
        st.markdown(f"**{cat_label}**")
        for q in qs:
            qid = q["id"]
            with st.container(border=True):
                st.markdown(
                    f'{q["question"]} {difficulty_badge_html(q["difficulty"])}', unsafe_allow_html=True
                )
                existing_answer = (session.get("answers") or {}).get(qid, "")

                mode = st.radio(
                    "Response mode", ["⌨ Type answer", "🎙 Record voice answer"],
                    key=f"mode_{session['id']}_{qid}", horizontal=True, label_visibility="collapsed",
                )

                if mode == "⌨ Type answer":
                    answer = st.text_area(
                        "Candidate's answer", value=existing_answer, key=f"answer_{session['id']}_{qid}",
                        label_visibility="collapsed", placeholder="Type the candidate's answer here…", height=90,
                    )
                    if st.button("Submit answer", key=f"submit_{session['id']}_{qid}"):
                        if not answer.strip():
                            st.warning("Enter an answer first.")
                        else:
                            with st.spinner("Evaluating answer…"):
                                ok, ev = api.answer_interview_question(token, session["id"], qid, answer)
                            if ok:
                                session.setdefault("answers", {})[qid] = answer
                                session.setdefault("evaluations", {})[qid] = ev
                                st.session_state["interview_session"] = session
                                st.rerun()
                            else:
                                st.error(ev)
                else:
                    audio_bytes = None
                    if hasattr(st, "audio_input"):
                        audio = st.audio_input("Record the candidate's answer", key=f"audio_{session['id']}_{qid}")
                        if audio is not None:
                            audio_bytes = audio.getvalue()
                        st.caption("Transcribed locally with Whisper — no audio leaves your machine's Ollama/Whisper setup.")
                    else:
                        audio_file = st.file_uploader(
                            "Upload the candidate's answer recording",
                            type=["wav", "mp3", "m4a", "ogg"],
                            key=f"audio_{session['id']}_{qid}",
                        )
                        if audio_file is not None:
                            audio_bytes = audio_file.getvalue()
                        st.caption("Upload a voice recording to transcribe locally with Whisper.")

                    if audio_bytes is not None and st.button("Submit voice answer", key=f"submit_audio_{session['id']}_{qid}"):
                        with st.spinner("Transcribing and evaluating the recording…"):
                            ok, result = api.answer_interview_question_audio(
                                token, session["id"], qid, "answer.wav", audio_bytes
                            )
                        if ok:
                            transcript = result.pop("transcript", "")
                            st.success(f'Transcript: "{transcript}"')
                            session.setdefault("answers", {})[qid] = transcript
                            session.setdefault("evaluations", {})[qid] = result
                            st.session_state["interview_session"] = session
                            st.rerun()
                        else:
                            st.error(result)
                    elif existing_answer:
                        st.caption(f'Last submitted answer: "{existing_answer}"')

                ev = (session.get("evaluations") or {}).get(qid)
                if ev:
                    bc1, bc2, bc3 = st.columns(3)
                    with bc1:
                        st.markdown(gap_bar_html("Relevance", ev.get("relevance_score")), unsafe_allow_html=True)
                    with bc2:
                        st.markdown(gap_bar_html("Communication", ev.get("communication_score")), unsafe_allow_html=True)
                    with bc3:
                        st.markdown(gap_bar_html("Confidence", ev.get("confidence_score")), unsafe_allow_html=True)
                    st.write(ev.get("feedback", ""))

    answered = len(session.get("evaluations") or {})
    total = len(session.get("questions") or [])
    st.caption(f"{answered} of {total} questions answered.")

    if session.get("status") == "completed" and session.get("report"):
        render_interview_report(session)
    elif st.button("✔ Complete interview & generate report", type="primary"):
        if answered == 0:
            st.warning("Submit at least one answer before completing the interview.")
        else:
            with st.spinner("Aggregating performance report…"):
                ok, report = api.complete_interview(token, session["id"])
            if ok:
                session["status"] = "completed"
                session["report"] = report
                st.session_state["interview_session"] = session
                st.rerun()
            else:
                st.error(report)


def render_interview_report(session: dict):
    report = session.get("report") or {}
    st.markdown('<div class="section-label">Interview performance report</div>', unsafe_allow_html=True)
    st.markdown(score_badge_html("Overall Score", report.get("overall_score")), unsafe_allow_html=True)
    st.write(report.get("verdict", ""))

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        st.markdown(gap_bar_html("Relevance (avg)", report.get("avg_relevance")), unsafe_allow_html=True)
    with bc2:
        st.markdown(gap_bar_html("Communication (avg)", report.get("avg_communication")), unsafe_allow_html=True)
    with bc3:
        st.markdown(gap_bar_html("Confidence (avg)", report.get("avg_confidence")), unsafe_allow_html=True)

    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown("**Strengths**")
        st.markdown(chip_row_html(report.get("strengths"), "skill-chip"), unsafe_allow_html=True)
    with rc2:
        st.markdown("**Areas to improve**")
        st.markdown(chip_row_html(report.get("improvements"), "job-chip"), unsafe_allow_html=True)

    st.download_button(
        "⬇ Download interview report (Markdown)",
        data=build_interview_report_md(session),
        file_name=f"interview_report_{session['resume_name'].replace(' ', '_')}.md",
        mime="text/markdown",
        key=f"interview_report_{session['id']}",
    )


def render_pipeline_tab():
    token = st.session_state["token"]

    ok, jobs = api.list_jobs(token)
    if not ok:
        jobs = []
    if not jobs:
        st.info("Save a Job Description first (Job Descriptions tab) to start tracking a pipeline.")
        return
    job_labels = ["All jobs"] + [f"{j['title']} (#{j['id']})" for j in jobs]
    job_id_by_label = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs}

    st.markdown('<div class="section-label">Candidate pipeline</div>', unsafe_allow_html=True)
    job_filter_label = st.selectbox("Filter by job", job_labels, key="pipeline_job_filter")
    job_filter_id = job_id_by_label.get(job_filter_label)

    ok2, entries = api.list_pipeline(token, job_id=job_filter_id)
    if not ok2:
        st.error(entries)
        entries = []

    # Kanban-style stage overview
    stage_cols = st.columns(len(db_stages := ["Applied", "Screening", "Interview", "Selected", "Rejected"]))
    by_stage = {s: [] for s in db_stages}
    for e in entries:
        by_stage.setdefault(e["status"], []).append(e)
    for col, stage in zip(stage_cols, db_stages):
        with col:
            st.markdown(f'<div class="stage-col-header">{stage} ({len(by_stage[stage])})</div>', unsafe_allow_html=True)
            body = "".join(
                f'<div class="pipeline-card">{e["resume_name"]}<br>'
                f'<span class="meta-line">{e["job_title"]}</span></div>'
                for e in by_stage[stage]
            ) or '<div class="meta-line">—</div>'
            st.markdown(f'<div class="stage-col-body">{body}</div>', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="section-label">Add or update a candidate in the pipeline</div>', unsafe_allow_html=True)
    ok3, candidates = api.list_resumes(token)
    if not ok3:
        candidates = []
    if candidates:
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            cand_labels = [f"{c.get('name') or 'Unnamed'} (#{c['id']})" for c in candidates]
            cand_choice = st.selectbox("Candidate", cand_labels, key="pipeline_cand_choice")
            picked_resume_id = candidates[cand_labels.index(cand_choice)]["id"]
        with cc2:
            job_choice_2 = st.selectbox(
                "Job", [f"{j['title']} (#{j['id']})" for j in jobs], key="pipeline_job_choice"
            )
            picked_job_id = job_id_by_label[job_choice_2]
        with cc3:
            status_choice = st.selectbox("Stage", db_stages, key="pipeline_status_choice")

        interview_dt = st.text_input(
            "Interview date/time (optional, free text)", placeholder="e.g. 2026-08-04 3:00 PM", key="pipeline_dt"
        )
        feedback = st.text_area("Recruiter feedback (optional)", key="pipeline_feedback", height=80)

        if st.button("Save to pipeline", type="primary"):
            ok4, data = api.upsert_pipeline(
                token, picked_resume_id, picked_job_id, status_choice, interview_dt or None, feedback or None
            )
            if ok4:
                st.success(f'{data["resume_name"]} set to "{data["status"]}" for {data["job_title"]}.')
                st.rerun()
            else:
                st.error(data)

    st.write("")
    st.markdown('<div class="section-label">All pipeline entries</div>', unsafe_allow_html=True)
    fc1, fc2 = st.columns([1, 2])
    with fc1:
        status_filter = st.selectbox("Filter by stage", ["All stages"] + db_stages, key="pipeline_status_filter")
    with fc2:
        name_query = st.text_input(
            "Search candidate name", placeholder="Search candidate name…", key="pipeline_name_search",
            label_visibility="collapsed",
        )

    filtered_entries = entries
    if status_filter != "All stages":
        filtered_entries = [e for e in filtered_entries if e["status"] == status_filter]
    if name_query.strip():
        q = name_query.strip().lower()
        filtered_entries = [e for e in filtered_entries if q in e["resume_name"].lower()]

    if not filtered_entries:
        st.caption("No pipeline entries match this filter.")
    for e in filtered_entries:
        with st.container(border=True):
            ec1, ec2 = st.columns([3, 2])
            with ec1:
                st.markdown(f"**{e['resume_name']}** — {e['job_title']}")
                if e.get("interview_datetime"):
                    st.caption(f"Interview: {e['interview_datetime']}")
                if e.get("recruiter_feedback"):
                    st.write(e["recruiter_feedback"])
            with ec2:
                new_status = st.selectbox(
                    "Stage", db_stages, index=db_stages.index(e["status"]), key=f"stage_{e['id']}",
                    label_visibility="collapsed",
                )
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("Update stage", key=f"update_stage_{e['id']}", use_container_width=True):
                        ok5, data = api.update_pipeline(token, e["id"], status=new_status)
                        if ok5:
                            st.rerun()
                        else:
                            st.error(data)
                with bc2:
                    if st.button("Remove", key=f"remove_pipeline_{e['id']}", use_container_width=True):
                        ok6, data = api.delete_pipeline(token, e["id"])
                        if ok6:
                            st.rerun()
                        else:
                            st.error(data)


def render_dashboard_tab():
    token = st.session_state["token"]
    ok, stats = api.get_stats(token)
    if not ok:
        st.error(stats)
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Total candidates", stats.get("total_candidates", 0))
    c2.metric("Avg. years experience", stats.get("avg_years_experience") or "—")
    latest = stats.get("latest_upload")
    c3.metric("Most recent upload", latest[:10] if latest else "—")

    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-label">Top skills</div>', unsafe_allow_html=True)
        top_skills = stats.get("top_skills") or []
        if top_skills:
            df = pd.DataFrame(top_skills).set_index("skill")
            st.bar_chart(df, use_container_width=True)
        else:
            st.info("No skills data yet.")
    with col2:
        st.markdown('<div class="section-label">Common degrees</div>', unsafe_allow_html=True)
        top_degrees = stats.get("top_degrees") or []
        if top_degrees:
            for d in top_degrees:
                st.write(f"**{d['degree']}** — {d['count']}")
        else:
            st.info("No education data yet.")

    st.write("")
    col3, col4 = st.columns(2)
    with col3:
        st.markdown('<div class="section-label">Candidate pipeline</div>', unsafe_allow_html=True)
        okp, entries = api.list_pipeline(token)
        if not okp:
            st.error(entries)
            entries = []
        stages = ["Applied", "Screening", "Interview", "Selected", "Rejected"]
        counts = {s: 0 for s in stages}
        for e in entries:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
        if entries:
            df = pd.DataFrame({"stage": stages, "count": [counts[s] for s in stages]}).set_index("stage")
            st.bar_chart(df, use_container_width=True)
        else:
            st.info("No candidates in the pipeline yet — add some on the Pipeline tab.")

    with col4:
        st.markdown('<div class="section-label">Interview activity</div>', unsafe_allow_html=True)
        oki, sessions = api.list_interview_sessions(token)
        if not oki:
            st.error(sessions)
            sessions = []
        completed = [s for s in sessions if s.get("status") == "completed"]
        if sessions:
            scores = [s["report"]["overall_score"] for s in completed if s.get("report")]
            avg_score = round(sum(scores) / len(scores), 1) if scores else None
            ic1, ic2 = st.columns(2)
            ic1.metric("Interviews run", len(sessions))
            ic2.metric("Avg. performance score", avg_score if avg_score is not None else "—")
            st.caption("Most recent sessions:")
            for s in sessions[:5]:
                score_txt = f' · {s["report"]["overall_score"]}/100' if s.get("report") else " · in progress"
                st.markdown(f'<div class="meta-line">{s["resume_name"]} vs {s["job_title"]}{score_txt}</div>', unsafe_allow_html=True)
        else:
            st.info("No interview sessions yet — generate one on the Interview Prep tab.")


def render_app():
    render_topbar()
    st.write("")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["Candidates", "Job Descriptions", "Match Job", "Interview Prep", "Pipeline", "Dashboard"]
    )
    with tab1:
        render_candidates_tab()
    with tab2:
        render_jobs_tab()
    with tab3:
        render_match_tab()
    with tab4:
        render_interview_tab()
    with tab5:
        render_pipeline_tab()
    with tab6:
        render_dashboard_tab()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if st.session_state["page"] == "app" and not is_authed():
    st.session_state["page"] = "landing"

if st.session_state["page"] == "landing":
    render_landing()
elif st.session_state["page"] == "auth":
    render_auth()
else:
    render_app()
