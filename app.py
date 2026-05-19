"""Kora — Gradio UI + state machine."""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import gradio as gr

import database as db
import gemma
import scheduler


CSS_PATH = Path(__file__).parent / "styles.css"
CSS = CSS_PATH.read_text() if CSS_PATH.exists() else ""


# ---------- markdown-ish to HTML ----------
import re as _re
import html as _html


def normalize_mermaid(s: str) -> str:
    """Mermaid needs real newlines between statements. Models often emit
    everything on a single line — restore the line breaks heuristically."""
    if not s:
        return s
    s = str(s).replace("\\n", "\n")  # literal \n → real newline
    # If model already used newlines, keep as-is
    if "\n" in s:
        return s
    # Add newline after diagram-type header
    s = _re.sub(
        r"^(\s*(?:flowchart\s+\w+|sequenceDiagram|mindmap|stateDiagram-v2|stateDiagram|graph\s+\w+|classDiagram|erDiagram))\s+",
        r"\1\n  ",
        s,
        count=1,
    )
    # Add newline before each new statement after any node-closer ] } )
    # followed by a node id and either an arrow or a bracket opener.
    s = _re.sub(
        r"([\]\}\)])\s+([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|\.\.>|->|\[|\{|\())",
        r"\1\n  \2",
        s,
    )
    return s


def strip_code_fences(s: str) -> str:
    """Strip ``` and ~~~ code fences (with optional language tag)."""
    if not s:
        return s
    s = _re.sub(r"^\s*```[a-zA-Z0-9_+-]*\s*\n?", "", s)
    s = _re.sub(r"\n?\s*```\s*$", "", s)
    s = _re.sub(r"^\s*~~~[a-zA-Z0-9_+-]*\s*\n?", "", s)
    s = _re.sub(r"\n?\s*~~~\s*$", "", s)
    # also strip inline fences if they happen on their own line in middle
    s = _re.sub(r"^\s*```[a-zA-Z0-9_+-]*\s*$", "", s, flags=_re.MULTILINE)
    s = _re.sub(r"^\s*```\s*$", "", s, flags=_re.MULTILINE)
    return s.strip("\n")


def clean_concept_name(name: str, max_len: int = 60) -> str:
    """Strip markdown formatting, trailing colon descriptions, and truncate."""
    if not name:
        return ""
    s = str(name)
    s = _re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = _re.sub(r"[*_`]", "", s)
    # If model crammed a description after the title (e.g. "Neurons: Understanding the..."),
    # take only the part before the colon.
    if ":" in s:
        first = s.split(":", 1)[0].strip()
        if 2 < len(first) <= max_len:
            s = first
    s = s.strip().rstrip(":").rstrip(".")
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def md_to_html(text: str) -> str:
    """Lightweight Markdown subset → HTML. Handles paragraphs, **bold**,
    *italic*, `code`, headings, lists, links."""
    if not text:
        return ""
    text = str(text).replace("\r\n", "\n").strip()

    # protect inline code first
    code_spans: list[str] = []
    def _stash_code(m):
        code_spans.append(m.group(1))
        return f"@@CODE{len(code_spans)-1}@@"
    text = _re.sub(r"`([^`]+)`", _stash_code, text)

    # escape HTML
    text = _html.escape(text)

    # restore code
    for i, c in enumerate(code_spans):
        text = text.replace(
            f"@@CODE{i}@@",
            f"<code>{_html.escape(c)}</code>",
        )

    # bold + italic
    text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = _re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = _re.sub(r"_([^_\n]+?)_", r"<em>\1</em>", text)

    # split into blocks
    blocks = _re.split(r"\n\s*\n", text)
    out_blocks: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")

        # heading?
        if lines[0].startswith("### "):
            out_blocks.append(f"<h4>{lines[0][4:].strip()}</h4>")
            rest = "\n".join(lines[1:]).strip()
            if rest:
                out_blocks.append(_render_block(rest))
            continue
        if lines[0].startswith("## "):
            out_blocks.append(f"<h3>{lines[0][3:].strip()}</h3>")
            rest = "\n".join(lines[1:]).strip()
            if rest:
                out_blocks.append(_render_block(rest))
            continue
        if lines[0].startswith("# "):
            out_blocks.append(f"<h2>{lines[0][2:].strip()}</h2>")
            rest = "\n".join(lines[1:]).strip()
            if rest:
                out_blocks.append(_render_block(rest))
            continue

        out_blocks.append(_render_block(block))

    return "\n".join(out_blocks)


def _render_block(block: str) -> str:
    lines = block.split("\n")
    # numbered list
    if all(_re.match(r"^\s*\d+\.\s+", ln) for ln in lines if ln.strip()):
        items = [_re.sub(r"^\s*\d+\.\s+", "", ln).strip() for ln in lines if ln.strip()]
        return "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"
    # bullet list
    if all(_re.match(r"^\s*[-*•]\s+", ln) for ln in lines if ln.strip()):
        items = [_re.sub(r"^\s*[-*•]\s+", "", ln).strip() for ln in lines if ln.strip()]
        return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"
    # paragraph
    return "<p>" + "<br>".join(lines) + "</p>"

SCREENS = [
    "home", "profile_q", "profile_reveal", "topic_setup", "loading",
    "module_hook", "module_teach", "module_activate", "module_bridge",
    "session_review", "review", "dashboard",
]


def empty_state() -> dict:
    return {
        "screen": "home",
        "topic": "",
        "session_id": None,
        "profile": None,
        "topic_map": None,
        "learning_path": None,
        "current_module_index": 0,
        "current_module_content": None,
        "current_module_id": None,
        "current_beat": "hook",
        "profile_questions": [],
        "profile_answers": [],
        "profile_q_index": 0,
        "current_question": None,
        "session_log": [],
        "session_start_time": 0.0,
        "depth": "solid",
        "self_reported_level": "none",
        "focus_note": "",
        "last_activation": None,
        "last_evaluation": None,
        "last_bridge": None,
        "review_queue": [],
        "review_current": None,
        "session_review_data": None,
    }


# ============================================================
# HTML render helpers
# ============================================================

KORA_MARK_SVG = """
<svg class='kora-mark' viewBox='0 0 32 32' aria-hidden='true'>
  <defs>
    <linearGradient id='kora-grad' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#f0bd64'/>
      <stop offset='100%' stop-color='#88cfc7'/>
    </linearGradient>
  </defs>
  <circle cx='16' cy='16' r='13' fill='none' stroke='url(#kora-grad)' stroke-width='1.5' opacity='0.4'/>
  <path d='M16 7 C16 7 11 12 11 16 C11 20 16 25 16 25' stroke='url(#kora-grad)' stroke-width='2.2' fill='none' stroke-linecap='round'/>
  <path d='M16 7 C16 7 21 12 21 16 C21 20 16 25 16 25' stroke='url(#kora-grad)' stroke-width='2.2' fill='none' stroke-linecap='round' opacity='0.6'/>
  <circle cx='16' cy='16' r='2' fill='#f0bd64'/>
</svg>
"""


def header_html(streak: int = 0) -> str:
    streak_block = ""
    if streak > 0:
        streak_block = f"""<div class='kora-streak'><span class='streak-icon'>◆</span><span>{streak}</span></div>"""
    return f"""
<div class='kora-header'>
  <div class='kora-logo'>
    {KORA_MARK_SVG}
    <span class='kora-wordmark'>Kora</span>
  </div>
  {streak_block}
</div>
"""


def home_html(streak: int, active_sessions: list, due_reviews: list) -> str:
    reviews = ""
    if due_reviews:
        reviews = "<div class='section-title'>⏰ Today's Reviews</div><div class='review-list'>"
        for r in due_reviews[:6]:
            reviews += f"""
<div class='review-row'>
  <span class='review-name'>{_html.escape(r.concept_name)}</span>
  <span class='pill-amber'>due</span>
</div>
"""
        reviews += "</div>"

    return f"""
{header_html(streak)}
<div class='home-hero'>
  <div class='home-eyebrow'>On-device · Powered by Gemma 4</div>
  <h1 class='home-title'>Learn <span class='home-title-grad'>anything.</span><br>Adapted to you.</h1>
  <p class='home-sub'>Type a topic. Kora builds a path. You learn, recall, and adapt — all offline.</p>
</div>
{reviews}
"""


def profile_progress_html(idx: int) -> str:
    dots = ""
    for i in range(5):
        cls = "dot active" if i <= idx else "dot"
        dots += f"<span class='{cls}'></span>"
    return f"""
<div class='profile-top'>
  <div class='progress-dots'>{dots}</div>
  <p class='subtitle'>Let's understand how you learn best</p>
</div>
"""


def question_card_html(q: dict) -> str:
    if not q:
        return "<div class='card'>Loading question…</div>"
    return f"""
<div class='card card-amber'>
  <h2 class='q-title'>{q.get("question", "")}</h2>
</div>
"""


def profile_reveal_html(profile: dict) -> str:
    return f"""
<div class='reveal-wrap'>
  <div class='reveal-big'>{profile.get("level_label", "Your Learner Profile")}</div>
  <p class='reveal-desc'>{profile.get("style_description", "")}</p>
  <p class='reveal-sub'>Your profile is saved — I'll use this for every topic.</p>
</div>
"""


BRAIN_INSIGHTS = [
    ("The 80/20 of memory",
     "If you re-read a page, you'll remember almost nothing. If you try to recall it from memory, you'll remember 80% — even if you fail.",
     "Active recall beats re-reading by 3x."),
    ("Forgetting is a feature",
     "Your brain deliberately weakens unused connections. Reviewing things just before you'd forget them strengthens the connection more than studying fresh.",
     "This is the science behind spaced repetition."),
    ("Sleep writes memories",
     "Memories don't stick until you sleep. During slow-wave sleep, your hippocampus replays the day's events for your cortex to save.",
     "Cramming all-night is mathematically worse than half the studying + a full sleep."),
    ("Tests teach, not just measure",
     "Taking a test on material you've barely seen produces better long-term retention than re-reading the same material for the same amount of time.",
     "This is called the testing effect."),
    ("Interleaving > blocking",
     "If you mix topics — algebra, then geometry, then algebra — you learn each one better than studying algebra for an hour straight.",
     "Your brain forces itself to retrieve more deeply."),
    ("Concrete > abstract — at first",
     "A specific example before a general rule activates more brain regions than the rule alone. Then you can generalise.",
     "This is why Kora teaches with worked examples first."),
    ("Mistakes wire learning",
     "Getting a question wrong, then seeing the right answer, triggers stronger memory than getting it right the first time.",
     "Don't fear the dip — that's where the learning happens."),
    ("Meaning, not repetition",
     "Words you connect to meaning, story, or personal experience are remembered 7x more than words you simply repeat.",
     "Why analogies are so powerful."),
    ("Your prefrontal cortex is small",
     "You can only hold about 4 things in working memory at once. Good teaching presents ideas in chunks of 3-4.",
     "Why Kora paces concepts gradually."),
    ("Dopamine is for surprise",
     "Your brain releases dopamine when reality beats prediction. That's why a counterintuitive hook makes learning sticky.",
     "Surprise > novelty > reward."),
]


LOADING_PHRASES = [
    "Preparing your learning…",
    "Getting ready for you…",
    "Crafting your next step…",
    "Setting the scene…",
    "Drawing the threads together…",
    "Building your understanding…",
    "Designing this moment…",
    "Shaping your insight…",
    "Lining up the right ideas…",
    "Tuning to how you learn…",
]


def loading_html(msg: str | None = None, insight_idx: int | None = None) -> str:
    import random as _rnd
    if insight_idx is None:
        insight_idx = _rnd.randint(0, len(BRAIN_INSIGHTS) - 1)
    if msg is None:
        msg = _rnd.choice(LOADING_PHRASES)
    title, body, tag = BRAIN_INSIGHTS[insight_idx % len(BRAIN_INSIGHTS)]
    return f"""
<div class='loading-wrap'>
  <div class='loading-pulse'><span></span><span></span><span></span></div>
  <div class='loading-msg'>{_html.escape(msg)}</div>
  <div class='loading-insight'>
    <div class='loading-insight-tag'>While you wait — learning science</div>
    <div class='loading-insight-title'>{_html.escape(title)}</div>
    <div class='loading-insight-body'>{_html.escape(body)}</div>
    <div class='loading-insight-tagline'>{_html.escape(tag)}</div>
  </div>
</div>
"""


def module_top_html(state: dict, beat: str) -> str:
    path = state.get("learning_path") or []
    total = len(path)
    idx = state.get("current_module_index", 0)
    concept = ""
    if path and idx < total:
        concept = clean_concept_name(path[idx].get("concept_name", ""))
    pct = int(100 * (idx + (0.25 if beat == "hook" else 0.5 if beat == "teach"
                            else 0.75 if beat == "activate" else 1)) / max(1, total))
    beats = ["hook", "teach", "activate", "bridge"]
    strip = ""
    for b in beats:
        cls = "beat-active" if b == beat else ""
        strip += f"<span class='beat {cls}'>{b.title()}</span>"
        if b != "bridge":
            strip += "<span class='beat-sep'>→</span>"
    return f"""
<div class='module-top'>
  <div class='module-label'>Module {idx + 1} of {total} · <span class='module-concept'>{_html.escape(concept)}</span></div>
  <div class='progress-bar-track'><div class='progress-bar-fill' style='width:{pct}%'></div></div>
  <div class='beat-strip'>{strip}</div>
</div>
"""


def hook_html(state: dict, hook: dict) -> str:
    # Accept either rich-shaped dict or plain string (back-compat)
    if isinstance(hook, str):
        hook = {"hook_text": hook}
    headline = _html.escape(str(hook.get("headline") or ""))
    text = md_to_html(hook.get("hook_text") or "")
    stat = hook.get("stat") or {}
    stat_num = _html.escape(str(stat.get("number", ""))) if isinstance(stat, dict) else ""
    stat_lbl = _html.escape(str(stat.get("label", ""))) if isinstance(stat, dict) else ""
    paradox = hook.get("paradox")
    promise = hook.get("promise")

    headline_block = f"<h1 class='hook-headline'>{headline}</h1>" if headline else ""
    stat_block = ""
    if stat_num:
        stat_block = f"""
<div class='hook-stat-card'>
  <div class='hook-stat-num'>{stat_num}</div>
  <div class='hook-stat-label'>{stat_lbl}</div>
</div>
"""
    paradox_block = ""
    if paradox and paradox != "null":
        paradox_block = f"""
<div class='card card-paradox'>
  <div class='pill-paradox'>⚡ Counterintuitive</div>
  <p class='paradox-text'>{md_to_html(str(paradox)).replace('<p>','').replace('</p>','')}</p>
</div>
"""
    promise_block = ""
    if promise and promise != "null":
        promise_block = f"""
<div class='hook-promise'>
  <span class='promise-icon'>🎯</span>
  <span class='promise-text'>{md_to_html(str(promise)).replace('<p>','').replace('</p>','')}</span>
</div>
"""
    return f"""
{module_top_html(state, "hook")}
<div class='hook-wrap'>
  {headline_block}
  <div class='card card-teal hook-card'>
    <div class='hook-text prose'>{text}</div>
  </div>
  {stat_block}
  {paradox_block}
  {promise_block}
</div>
"""


_MERMAID_COUNTER = [0]


def teach_html(state: dict, content: dict) -> str:
    # backward-compat: if old 'explanation' field exists, fall back to simple render
    if content.get("explanation") and not content.get("sections"):
        explanation = md_to_html(content.get("explanation", ""))
        return f"""
{module_top_html(state, "teach")}
<div class='card'>
  <h2 class='headline'>The Concept</h2>
  <div class='prose'>{explanation}</div>
</div>
"""

    core_insight = content.get("core_insight", "")
    sections = content.get("sections", []) or []
    mermaid_diagram = content.get("mermaid_diagram")
    diagram_caption = content.get("diagram_caption", "")
    worked = content.get("worked_example")
    key_terms = content.get("key_terms", []) or []
    confusion = content.get("common_confusion")

    blocks: list[str] = []

    if core_insight:
        blocks.append(f"""
<div class='card card-insight'>
  <div class='pill-amber'>Core Insight</div>
  <p class='insight-text'>{md_to_html(core_insight).replace('<p>', '').replace('</p>', '')}</p>
</div>
""")

    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            continue
        heading = _html.escape(str(sec.get("heading", "")))
        body = md_to_html(str(sec.get("body", "")))
        blocks.append(f"""
<div class='card section-card'>
  <div class='section-num'>{i+1}</div>
  <h3 class='section-heading'>{heading}</h3>
  <div class='prose'>{body}</div>
</div>
""")

    if mermaid_diagram and str(mermaid_diagram).strip() and mermaid_diagram != "null":
        _MERMAID_COUNTER[0] += 1
        diagram_id = f"mmd-{_MERMAID_COUNTER[0]}-{int(time.time()*1000) % 100000}"
        clean = strip_code_fences(str(mermaid_diagram))
        clean = _re.sub(r"^\s*mermaid\s*\n", "", clean, flags=_re.IGNORECASE)
        clean = normalize_mermaid(clean)

        # Aggressive label sanitization — wrap in double quotes if any special char,
        # strip chars that absolutely break parsing.
        def _sanitize_inside(text: str) -> str:
            text = text.strip()
            text = text.replace("&", "and")
            text = text.replace("|", "/")
            text = text.replace("<", "")
            text = text.replace(">", "")
            text = text.replace("`", "")
            # Subscript / superscript unicode → ascii numerals
            sub_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789" * 2)
            text = text.translate(sub_map)
            return text

        def _wrap_or_clean(open_ch: str, close_ch: str, inner: str) -> str:
            inner = _sanitize_inside(inner)
            # Strip the same kind of bracket from inside (e.g. parens inside parens)
            inner = inner.replace(open_ch, "").replace(close_ch, "")
            # Wrap label in double quotes if any special char remains, escape inner quotes
            needs_quotes = any(c in inner for c in ":;=+,#%@$")
            if '"' in inner:
                inner = inner.replace('"', "'")
                needs_quotes = True
            if needs_quotes:
                return f'{open_ch}"{inner}"{close_ch}'
            return f"{open_ch}{inner}{close_ch}"

        clean = _re.sub(
            r"(\[)([^\[\]\n]+)(\])",
            lambda m: _wrap_or_clean("[", "]", m.group(2)),
            clean,
        )
        clean = _re.sub(
            r"(\{)([^\{\}\n]+)(\})",
            lambda m: _wrap_or_clean("{", "}", m.group(2)),
            clean,
        )
        clean = _re.sub(
            r"(\()([^()\n]+)(\))",
            lambda m: _wrap_or_clean("(", ")", m.group(2)),
            clean,
        )
        # Strip trailing semicolons that some models emit
        clean = _re.sub(r";\s*\n", "\n", clean)
        clean = clean.rstrip(";").rstrip()
        caption_block = f"<p class='diagram-caption'>{_html.escape(str(diagram_caption))}</p>" if diagram_caption and diagram_caption != "null" else ""
        blocks.append(f"""
<div class='card diagram-card'>
  <div class='pill-teal'>Visual</div>
  <div class='mermaid' id='{diagram_id}'>{_html.escape(clean)}</div>
  {caption_block}
</div>
""")

    if worked and worked != "null" and worked is not None:
        worked_rendered = md_to_html(str(worked))
        blocks.append(f"""
<div class='card card-amber'>
  <div class='pill-amber'>Worked Example</div>
  <div class='prose'>{worked_rendered}</div>
</div>
""")

    if key_terms:
        term_items = ""
        for kt in key_terms:
            if not isinstance(kt, dict):
                continue
            term = _html.escape(str(kt.get("term", "")))
            defn = md_to_html(str(kt.get("definition", "")))
            defn = defn.replace("<p>", "").replace("</p>", "")
            term_items += f"""
<div class='key-term'>
  <div class='key-term-name'>{term}</div>
  <div class='key-term-def'>{defn}</div>
</div>
"""
        if term_items:
            blocks.append(f"""
<div class='card card-teal'>
  <div class='pill-teal'>Key Terms</div>
  <div class='key-terms-list'>{term_items}</div>
</div>
""")

    if confusion and confusion != "null":
        blocks.append(f"""
<div class='card card-confusion'>
  <div class='pill-confusion'>⚠ Common Confusion</div>
  <div class='prose'>{md_to_html(str(confusion))}</div>
</div>
""")

    return module_top_html(state, "teach") + "\n".join(blocks)


def bridge_html(state: dict, bridge_text: str, next_concept: str) -> str:
    rendered = md_to_html(bridge_text)
    short_next = clean_concept_name(next_concept)
    return f"""
{module_top_html(state, "bridge")}
<div class='card bridge-card'>
  <div class='bridge-text prose'>{rendered}</div>
  <p class='bridge-next'>Next up: <span class='pill-amber'>{_html.escape(short_next)}</span></p>
</div>
"""


def feedback_html(eval_result: dict) -> str:
    if not eval_result:
        return ""
    pct = int(eval_result.get("accuracy_score", 0) * 100)
    sharpen = eval_result.get("what_to_sharpen") or ""
    feedback_rendered = md_to_html(eval_result.get("feedback", ""))

    sharpen_block = ""
    if sharpen and str(sharpen).strip() and str(sharpen) != "null":
        sharpen_rendered = md_to_html(str(sharpen))
        sharpen_block = f"""
<div class='card sharpen-card'>
  <div class='sharpen-head'>
    <span class='sharpen-icon'>✨</span>
    <span class='sharpen-label'>What to add next time</span>
  </div>
  <div class='sharpen-body prose'>{sharpen_rendered}</div>
</div>
"""

    return f"""
<div class='card card-teal'>
  <div class='feedback-top'>
    <span class='pill-teal'>What you got</span>
    <span class='pill-amber'>{pct}% there</span>
  </div>
  <div class='prose'>{feedback_rendered}</div>
</div>
{sharpen_block}
"""


# ============================================================
# Helpers
# ============================================================

def visibility(active: str):
    """Return a dict of screen -> gr.update(visible=bool)."""
    return {s: gr.update(visible=(s == active)) for s in SCREENS}


def get_or_load_profile(state: dict) -> dict | None:
    if state.get("profile"):
        return state["profile"]
    p = db.get_profile()
    if p:
        return {
            "id": p.id,
            "engagement_style": p.engagement_style,
            "pace": p.pace,
            "visual_weight": p.visual_weight,
            "hook_preference": p.hook_preference,
            "confidence_bias": p.confidence_bias,
            "profile_summary": p.profile_summary,
            "level_label": p.level_label,
            "style_description": p.style_description,
            "adaptation_notes": p.adaptation_notes,
            "sessions_completed": p.sessions_completed,
        }
    return None


# ============================================================
# Event handlers
# ============================================================

def on_start_learning(topic: str, state: dict):
    if not topic or not topic.strip():
        topic = "How the brain works"
    state = dict(state)
    state["topic"] = topic.strip()
    profile = get_or_load_profile(state)
    if profile:
        state["profile"] = profile
        state["screen"] = "topic_setup"
        return state, *render(state)
    # Need profile - start with first question
    state["profile_q_index"] = 0
    state["profile_answers"] = []
    q = gemma.build_profile_question(0, [])
    if not q or "question" not in q:
        q = {
            "question": "When something difficult finally clicked for you — what made it click?",
            "signal_type": "engagement",
            "options": [
                {"label": "📖 Someone told me a story", "value": "narrative"},
                {"label": "🔢 I saw it broken into clear steps", "value": "scaffolded"},
                {"label": "🔗 It connected to something I knew", "value": "analogical"},
                {"label": "⚡ I just tried it", "value": "abstract"},
            ],
        }
    state["current_question"] = q
    state["screen"] = "profile_q"
    return state, *render(state)


def on_profile_answer(choice: str, state: dict):
    state = dict(state)
    q = state.get("current_question") or {}
    answers = list(state.get("profile_answers", []))
    answers.append({
        "question": q.get("question", ""),
        "signal_type": q.get("signal_type", ""),
        "answer": choice,
    })
    state["profile_answers"] = answers
    idx = state.get("profile_q_index", 0) + 1
    if idx < 5:
        state["profile_q_index"] = idx
        nq = gemma.build_profile_question(idx, answers)
        if not nq or "question" not in nq:
            fallbacks = [
                {
                    "question": "When you start a new topic, what pace works best?",
                    "signal_type": "pace",
                    "options": [
                        {"label": "⏩ Fast overview, then loop back", "value": "fast"},
                        {"label": "🚶 Steady, one step at a time", "value": "steady"},
                        {"label": "🐢 Deep and slow, no shortcuts", "value": "thorough"},
                    ],
                },
                {
                    "question": "When learning, what helps you most?",
                    "signal_type": "visual",
                    "options": [
                        {"label": "📊 Diagrams and visuals", "value": "high_visual"},
                        {"label": "📝 Clear written explanations", "value": "low_visual"},
                        {"label": "⚖️ A mix of both", "value": "mid_visual"},
                    ],
                },
                {
                    "question": "How did you learn most of what you know?",
                    "signal_type": "experience",
                    "options": [
                        {"label": "🎓 Formal school / courses", "value": "formal"},
                        {"label": "🛠️ Self-taught / hands-on", "value": "self"},
                        {"label": "🧑‍🤝‍🧑 Other people / mentors", "value": "social"},
                    ],
                },
                {
                    "question": "When material gets hard, what do you do?",
                    "signal_type": "confidence",
                    "options": [
                        {"label": "💪 Push through, I'll get it", "value": "overconfident"},
                        {"label": "🧭 Slow down, ask questions", "value": "calibrated"},
                        {"label": "😬 Doubt myself, need reassurance", "value": "underconfident"},
                    ],
                },
            ]
            nq = fallbacks[idx - 1] if idx - 1 < len(fallbacks) else fallbacks[0]
        state["current_question"] = nq
        state["screen"] = "profile_q"
        return state, *render(state)

    # Done - infer profile
    profile = gemma.infer_learning_profile(answers)
    if not profile or "engagement_style" not in profile:
        profile = {
            "engagement_style": "scaffolded",
            "pace": "steady",
            "visual_weight": 0.5,
            "hook_preference": "story",
            "confidence_bias": "calibrated",
            "profile_summary": "A curious learner who likes clear structure and steady pacing.",
            "level_label": "The Explorer",
            "style_description": "I'll keep things structured and warm, with visuals when they help.",
            "adaptation_notes": "Start with moderate scaffolding.",
        }
    lp = db.LearningProfile(
        engagement_style=profile.get("engagement_style", "scaffolded"),
        pace=profile.get("pace", "steady"),
        visual_weight=float(profile.get("visual_weight", 0.5) or 0.5),
        hook_preference=profile.get("hook_preference", "story"),
        confidence_bias=profile.get("confidence_bias", "calibrated"),
        adaptation_notes=profile.get("adaptation_notes", ""),
        profile_summary=profile.get("profile_summary", ""),
        level_label=profile.get("level_label", "The Explorer"),
        style_description=profile.get("style_description", ""),
    )
    lp.id = db.save_profile(lp)
    profile["id"] = lp.id
    state["profile"] = profile
    state["screen"] = "profile_reveal"
    return state, *render(state)


def on_profile_reveal_continue(state: dict):
    state = dict(state)
    state["screen"] = "topic_setup"
    return state, *render(state)


def on_build_path(depth_choice: str, level_choice: str, focus_note: str, state: dict):
    yield from _yield_loading(state, "Mapping the territory…")
    state = dict(state)
    depth_map = {
        "🌱 Overview · 20m": "overview",
        "📚 Solid · 45m": "solid",
        "🔬 Deep · 90m": "deep",
    }
    level_map = {
        "🤷 Nothing yet": "none",
        "🙂 I know a little": "some",
        "🎓 I know quite a lot": "lots",
    }
    state["depth"] = depth_map.get(depth_choice, "solid")
    state["self_reported_level"] = level_map.get(level_choice, "none")
    state["focus_note"] = focus_note or ""
    state["screen"] = "loading"

    topic_map = gemma.generate_topic_map(state["topic"], state["depth"], state["focus_note"])
    if not topic_map or "core_concepts" not in topic_map:
        topic_map = {
            "topic": state["topic"],
            "one_line_description": state["topic"],
            "prerequisites": [],
            "core_concepts": ["Foundations", "Key Mechanisms", "Applications", "Edge Cases"],
            "estimated_modules": 4,
            "difficulty_ceiling": "intermediate",
        }
    state["topic_map"] = topic_map

    path_result = gemma.generate_learning_path(
        topic_map, state["profile"], state["depth"], state["self_reported_level"]
    )
    if not path_result or "path" not in path_result:
        path_result = {
            "path": [
                {
                    "module_number": i + 1,
                    "concept_name": c,
                    "hook_type": "story",
                    "teach_style": state["profile"].get("engagement_style", "scaffolded"),
                    "scaffold_level": "worked_example",
                    "visual_type": "diagram",
                    "estimated_minutes": 8,
                    "connects_to_next": "",
                }
                for i, c in enumerate(topic_map.get("core_concepts", []))
            ],
            "verified_level": "novice",
            "level_reasoning": "Default assessment.",
        }
    state["learning_path"] = path_result["path"]
    verified_level = path_result.get("verified_level", "novice")

    # save session
    session = db.TopicSession(
        topic_name=state["topic"],
        topic_map=topic_map,
        depth=state["depth"],
        self_reported_level=state["self_reported_level"],
        verified_level=verified_level,
        profile_id=state["profile"].get("id", 0),
        path=path_result["path"],
        current_module_index=0,
        status="active",
    )
    state["session_id"] = db.save_session(session)

    # create module rows
    for m in path_result["path"]:
        mod = db.Module(
            session_id=state["session_id"],
            module_number=m.get("module_number", 0),
            concept_name=m.get("concept_name", ""),
            content={"strategy": m},
            status="not_started",
            beat="hook",
        )
        db.save_module(mod)

    state["current_module_index"] = 0
    state["session_log"] = []
    state["session_start_time"] = time.time()
    yield from _enter_hook_gen(state, "Opening with a hook…")


def _current_module_strategy(state: dict) -> dict:
    path = state.get("learning_path") or []
    idx = state.get("current_module_index", 0)
    if idx >= len(path):
        return {}
    return path[idx]


def _module_db_row(state: dict) -> db.Module | None:
    sid = state.get("session_id")
    idx = state.get("current_module_index", 0)
    if not sid:
        return None
    mods = db.get_modules_for_session(sid)
    if idx >= len(mods):
        return None
    return mods[idx]


def _build_hook_payload(state: dict):
    strat = _current_module_strategy(state)
    concept = strat.get("concept_name", "")
    hook_type = strat.get("hook_type", "story")
    hook = gemma.generate_module_hook(concept, hook_type, state["profile"], state["topic"])
    if not hook or ("hook_text" not in hook and "headline" not in hook):
        hook = {"hook_text": f"Let's dive into {concept}. There's something surprising here…",
                "hook_type": hook_type}
    state["current_module_content"] = {"hook": hook}
    state["current_beat"] = "hook"
    mod_row = _module_db_row(state)
    if mod_row:
        state["current_module_id"] = mod_row.id
        mod_row.status = "in_progress"
        mod_row.beat = "hook"
        db.save_module(mod_row)
    state["screen"] = "module_hook"
    return state


def _enter_hook(state: dict):
    """Sync version: builds hook and returns rendered tuple (for non-generator callers)."""
    state = _build_hook_payload(state)
    return state, *render(state)


def _enter_hook_gen(state: dict, msg: str = "Opening with a hook…"):
    """Generator version: yields loading first, then the hook result."""
    yield from _yield_loading(state, msg)
    state = _build_hook_payload(dict(state))
    yield state, *render(state)


def _yield_loading(state: dict, msg: str):
    state = dict(state)
    state["screen"] = "loading"
    state["_loading_msg"] = msg
    yield state, *render(state)


def on_hook_continue(state: dict):
    yield from _yield_loading(state, "Preparing your explanation…")
    state = dict(state)
    strat = _current_module_strategy(state)
    concept = strat.get("concept_name", "")
    teach = gemma.generate_module_teach(
        concept, state["profile"],
        strat.get("scaffold_level", "worked_example"),
        strat.get("visual_type", "diagram"),
        state["topic"],
    )
    if not teach or (not teach.get("sections") and not teach.get("explanation")):
        teach = {
            "core_insight": f"{concept} sits at the heart of {state['topic']}.",
            "sections": [{
                "heading": "Overview",
                "body": f"{concept} is a foundational idea in {state['topic']}. We'll build it up step by step.",
            }],
            "mermaid_diagram": None,
        }
    content = state.get("current_module_content") or {}
    content["teach"] = teach
    state["current_module_content"] = content
    state["current_beat"] = "teach"
    state["screen"] = "module_teach"
    state["_teach_start"] = time.time()
    yield state, *render(state)


def on_teach_continue(state: dict):
    yield from _yield_loading(state, "Designing your practice…")
    state = dict(state)
    strat = _current_module_strategy(state)
    concept = strat.get("concept_name", "")
    content = state.get("current_module_content") or {}
    explanation = (content.get("teach") or {}).get("explanation", "")
    act = gemma.generate_module_activate(
        concept,
        state["profile"].get("engagement_style", "scaffolded"),
        explanation,
        strat.get("scaffold_level", "worked_example"),
    )
    if not act or "activation_prompt" not in act:
        act = {
            "activation_prompt": f"In your own words, explain {concept} as if to a friend.",
            "activation_type": "retell",
            "cloze_text": None,
            "cloze_answers": None,
            "model_answer_guide": f"Key idea of {concept} and why it matters.",
        }
    content["activate"] = act
    state["current_module_content"] = content
    state["last_activation"] = act
    state["last_evaluation"] = None
    state["current_beat"] = "activate"
    state["screen"] = "module_activate"
    yield state, *render(state)


def on_submit_activation(answer: str, state: dict):
    yield from _yield_loading(state, "Reading your answer…")
    state = dict(state)
    act = state.get("last_activation") or {}
    strat = _current_module_strategy(state)
    concept = strat.get("concept_name", "")
    eval_result = gemma.evaluate_activation(
        act.get("activation_prompt", ""),
        act.get("model_answer_guide", ""),
        answer or "",
        concept,
    )
    if not eval_result or "accuracy_score" not in eval_result:
        eval_result = {
            "accuracy_score": 0.3,
            "feedback": "I couldn't quite read that — let's try the core idea in one or two sentences.",
            "what_to_sharpen": f"State the main idea of **{concept}** in your own words.",
            "is_sufficient": False,
        }
    state["last_evaluation"] = eval_result

    # log + schedule review
    log = list(state.get("session_log", []))
    log.append({
        "concept": concept,
        "accuracy": eval_result.get("accuracy_score", 0),
        "module_number": strat.get("module_number", 0),
    })
    state["session_log"] = log

    mod_row = _module_db_row(state)
    if mod_row:
        mod_row.mastery_score = float(eval_result.get("accuracy_score", 0))
        mod_row.status = "completed"
        mod_row.beat = "activate"
        db.save_module(mod_row)
        scheduler.schedule_next_review(
            mod_row.id, concept, state["topic"],
            float(eval_result.get("accuracy_score", 0)),
        )
    state["screen"] = "module_activate"
    yield state, *render(state)


def on_activation_retry(state: dict):
    """Clear feedback so user can resubmit."""
    state = dict(state)
    state["last_evaluation"] = None
    return state, *render(state)


def on_activation_continue(state: dict):
    path = state.get("learning_path") or []
    idx = state.get("current_module_index", 0)
    if idx + 1 < len(path):
        yield from _yield_loading(state, "Connecting to the next concept…")
        state = dict(state)
        cur_concept = path[idx].get("concept_name", "")
        nxt_concept = path[idx + 1].get("concept_name", "")
        acc = float((state.get("last_evaluation") or {}).get("accuracy_score", 0.7))
        bridge = gemma.generate_bridge(cur_concept, nxt_concept, acc)
        if not bridge or "bridge_text" not in bridge:
            bridge = {"bridge_text": f"Now that you've got {cur_concept}, we can build on it with {nxt_concept}."}
        state["last_bridge"] = bridge
        state["current_beat"] = "bridge"
        state["screen"] = "module_bridge"
        yield state, *render(state)
        return

    # Last module - go to session_review
    state = dict(state)
    db.bump_streak()
    state["screen"] = "session_review"
    yield state, *render(state)


def on_bridge_continue(state: dict):
    state = dict(state)
    state["current_module_index"] = state.get("current_module_index", 0) + 1
    if state.get("session_id"):
        s = db.get_session(state["session_id"])
        if s:
            s.current_module_index = state["current_module_index"]
            db.save_session(s)
    yield from _enter_hook_gen(state, "Setting up the next concept…")


def on_session_review_submit(fuzzy: str, pace: str, state: dict):
    state = dict(state)
    log = state.get("session_log", [])
    payload = {
        "modules": log,
        "fuzzy_concept": fuzzy,
        "pace_feedback": pace,
        "total_seconds": int(time.time() - state.get("session_start_time", time.time())),
    }
    result = gemma.analyse_session(payload, state.get("profile") or {})
    if not result or "updated_profile" not in result:
        result = {
            "updated_profile": state.get("profile") or {},
            "changed_fields": [],
            "adaptation_message": "Great session — your profile is staying steady for now.",
            "next_session_preview": "Next time we'll keep building on what we've covered.",
        }
    state["session_review_data"] = result

    # update profile
    if state.get("profile") and state["profile"].get("id"):
        up = result["updated_profile"]
        existing = db.get_profile()
        if existing:
            existing.engagement_style = up.get("engagement_style", existing.engagement_style)
            existing.pace = up.get("pace", existing.pace)
            existing.visual_weight = float(up.get("visual_weight", existing.visual_weight) or existing.visual_weight)
            existing.hook_preference = up.get("hook_preference", existing.hook_preference)
            existing.confidence_bias = up.get("confidence_bias", existing.confidence_bias)
            existing.adaptation_notes = up.get("adaptation_notes", existing.adaptation_notes)
            existing.sessions_completed = (existing.sessions_completed or 0) + 1
            db.save_profile(existing)
            state["profile"].update({
                "engagement_style": existing.engagement_style,
                "pace": existing.pace,
                "visual_weight": existing.visual_weight,
                "hook_preference": existing.hook_preference,
                "confidence_bias": existing.confidence_bias,
                "adaptation_notes": existing.adaptation_notes,
                "sessions_completed": existing.sessions_completed,
            })

    # mark session completed
    if state.get("session_id"):
        s = db.get_session(state["session_id"])
        if s:
            s.status = "completed"
            db.save_session(s)
    return state, *render(state)


def on_session_done_home(state: dict):
    state = dict(state)
    new_state = empty_state()
    return new_state, *render(new_state)


def on_back_home(state: dict):
    state = dict(state)
    state["screen"] = "home"
    return state, *render(state)


def on_resume_session(slot_idx: int, state: dict):
    """Resume the session at the given index of the active list."""
    state = dict(state)
    active = db.get_active_sessions()
    if slot_idx < 0 or slot_idx >= len(active):
        yield state, *render(state)
        return
    target = active[slot_idx]

    state["session_id"] = target.id
    state["topic"] = target.topic_name
    state["topic_map"] = target.topic_map
    state["learning_path"] = target.path
    state["current_module_index"] = target.current_module_index
    state["depth"] = target.depth
    state["self_reported_level"] = target.self_reported_level
    state["session_log"] = []
    state["session_start_time"] = time.time()
    state["profile"] = get_or_load_profile(state)
    if state["current_module_index"] >= len(target.path):
        state["screen"] = "session_review"
        yield state, *render(state)
        return
    yield from _enter_hook_gen(state, "Picking up where you left off…")


def on_start_review(state: dict):
    state = dict(state)
    due = scheduler.get_due_reviews()
    if not due:
        state["screen"] = "home"
        return state, *render(state)
    state["review_queue"] = [r.id for r in due]
    return _enter_next_review(state)


def _enter_next_review(state: dict):
    queue = state.get("review_queue", [])
    if not queue:
        state["screen"] = "home"
        return state, *render(state)
    rid = queue[0]
    # find item by id
    all_due = db.get_due_reviews()
    item = next((i for i in all_due if i.id == rid), None)
    if not item:
        state["review_queue"] = queue[1:]
        return _enter_next_review(state)
    days = scheduler.days_since_learned(item.module_id)
    q = gemma.generate_review_question(item.concept_name, item.topic_name, days, item.last_accuracy)
    if not q or "question" not in q:
        q = {
            "question": f"What's a key thing to remember about {item.concept_name}?",
            "question_type": "application",
            "hint": None,
            "model_answer": f"Core idea of {item.concept_name}.",
            "difficulty": "medium",
        }
    state["review_current"] = {"item_id": item.id, "module_id": item.module_id,
                               "concept": item.concept_name, "topic": item.topic_name,
                               "question": q, "days": days, "answer": None, "feedback": None}
    state["screen"] = "review"
    return state, *render(state)


def on_review_submit(answer: str, state: dict):
    state = dict(state)
    rc = state.get("review_current") or {}
    q = rc.get("question", {})
    eval_result = gemma.evaluate_activation(
        q.get("question", ""),
        q.get("model_answer", ""),
        answer or "",
        rc.get("concept", ""),
    )
    if not eval_result:
        eval_result = {"accuracy_score": 0.7, "feedback": "Solid attempt."}
    rc["answer"] = answer
    rc["feedback"] = eval_result
    state["review_current"] = rc
    scheduler.schedule_next_review(
        rc.get("module_id"), rc.get("concept"), rc.get("topic"),
        float(eval_result.get("accuracy_score", 0.7)),
    )
    return state, *render(state)


def on_review_next(state: dict):
    state = dict(state)
    state["review_queue"] = (state.get("review_queue") or [])[1:]
    return _enter_next_review(state)


# ============================================================
# RENDER — produce HTML strings + visibility updates
# ============================================================

def render(state: dict):
    """Return tuple matching `outputs` list in build_ui()."""
    screen = state.get("screen", "home")

    # home
    streak = db.get_streak()
    active = db.get_active_sessions()
    due = scheduler.get_due_reviews()
    home_h = home_html(streak, active, due)

    # profile_q
    pq_progress = profile_progress_html(state.get("profile_q_index", 0))
    pq_card = question_card_html(state.get("current_question"))
    q = state.get("current_question") or {}
    options = q.get("options", []) or []
    choices = [o.get("label", "") for o in options]

    # profile_reveal
    profile_reveal_h = profile_reveal_html(state.get("profile") or {})

    # topic_setup
    topic_pill = f"""
<div class='setup-eyebrow'>
  <span class='setup-eyebrow-tag'>YOUR TOPIC</span>
  <span class='setup-eyebrow-topic'>{_html.escape(state.get('topic', ''))}</span>
</div>
"""

    # loading
    loading_h = loading_html(state.get("_loading_msg"))

    # module hook
    hook_content = (state.get("current_module_content") or {}).get("hook", {})
    hook_h = hook_html(state, hook_content)

    # module teach
    teach_content = (state.get("current_module_content") or {}).get("teach", {})
    teach_h = teach_html(state, teach_content)

    # module activate
    act = state.get("last_activation") or {}
    act_type = act.get("activation_type", "retell")
    act_prompt = act.get("activation_prompt", "")
    activate_top = f"{module_top_html(state, 'activate')}"
    activate_card = f"""
<div class='card card-amber'>
  <div class='pill-amber'>Your turn</div>
  <p class='body-lg'>{act_prompt}</p>
</div>
"""
    cloze_text = act.get("cloze_text") if act_type == "cloze" else None
    cloze_visible = bool(cloze_text and cloze_text != "null")
    cloze_block = f"<div class='card'><pre class='diagram'>{cloze_text}</pre></div>" if cloze_visible else ""
    fb_h = feedback_html(state.get("last_evaluation"))

    # bridge
    path = state.get("learning_path") or []
    idx = state.get("current_module_index", 0)
    next_concept = path[idx + 1].get("concept_name", "") if idx + 1 < len(path) else ""
    bridge_h = bridge_html(state, (state.get("last_bridge") or {}).get("bridge_text", ""), next_concept)

    # session review
    session_review_top = f"""
<div class='hero-small'>
  <h1 class='hero-title'>Session complete 🎉</h1>
  <p class='subtitle'>{len(state.get('session_log', []))} modules · ~{max(1, int((time.time() - state.get('session_start_time', time.time())) / 60))} minutes</p>
</div>
"""
    fuzzy_choices = [m.get("concept", "") for m in state.get("session_log", []) if m.get("concept")] + ["All felt clear"]
    sr_data = state.get("session_review_data") or {}
    adaptation_block = ""
    if sr_data:
        adaptation_block = f"""
<div class='card card-amber'>
  <div class='pill-amber'>What I noticed</div>
  <p class='body-lg'>{sr_data.get("adaptation_message", "")}</p>
  <p class='subtitle'>Your learning profile updated.</p>
</div>
<div class='card next-card'>
  <div class='pill-teal'>Next up</div>
  <p class='body-lg'>{sr_data.get("next_session_preview", "")}</p>
</div>
"""

    # review
    rc = state.get("review_current") or {}
    rq = rc.get("question", {})
    hint = rq.get("hint")
    hint_block = f"<p class='subtitle'>Hint: {hint}</p>" if hint and hint != "null" else ""
    review_h = f"""
<div class='hero-small'>
  <h1 class='hero-title'>{rc.get("concept", "")}</h1>
  <p class='subtitle'>{rc.get("days", 0)} days since you learned this</p>
</div>
<div class='card card-teal'>
  <p class='body-lg'>{rq.get("question", "")}</p>
  {hint_block}
</div>
"""
    review_fb_data = rc.get("feedback")
    review_fb_h = feedback_html(review_fb_data) if review_fb_data else ""
    review_model_answer = f"<div class='card'><div class='pill-teal'>Model answer</div><p class='body-lg'>{rq.get('model_answer', '')}</p></div>" if review_fb_data else ""

    vis = visibility(screen)

    # Resume slot population — up to 3 active sessions
    def _slot_update(idx: int):
        if idx < len(active):
            s = active[idx]
            total = len(s.path) if s.path else 1
            short = clean_concept_name(s.topic_name, max_len=40)
            label = f"▸  {short}   ·   {s.current_module_index}/{total}"
            return gr.update(value=label, visible=True)
        return gr.update(visible=False)
    resume_row_update = gr.update(visible=bool(active))
    slot1_update = _slot_update(0)
    slot2_update = _slot_update(1)
    slot3_update = _slot_update(2)

    return (
        # home
        home_h, vis["home"], resume_row_update, slot1_update, slot2_update, slot3_update,
        # profile_q
        pq_progress, pq_card, gr.update(choices=choices, value=None), vis["profile_q"],
        # profile_reveal
        profile_reveal_h, vis["profile_reveal"],
        # topic_setup
        topic_pill, vis["topic_setup"],
        # loading
        loading_h, vis["loading"],
        # module_hook
        hook_h, vis["module_hook"],
        # module_teach
        teach_h, vis["module_teach"],
        # module_activate
        activate_top, activate_card, gr.update(visible=cloze_visible, value=cloze_block),
        gr.update(visible=not cloze_visible), gr.update(visible=cloze_visible),
        fb_h,
        gr.update(visible=not bool(state.get("last_evaluation"))),  # activate_submit_row
        gr.update(visible=bool(state.get("last_evaluation"))),       # activate_after_row
        vis["module_activate"],
        # module_bridge
        bridge_h, vis["module_bridge"],
        # session_review
        session_review_top,
        gr.update(choices=fuzzy_choices, value=None),
        adaptation_block, gr.update(visible=bool(sr_data)),
        vis["session_review"],
        # review
        review_h, review_fb_h, review_model_answer, gr.update(visible=bool(review_fb_data)),
        vis["review"],
        # dashboard
        gr.update(visible=False),
    )


# ============================================================
# UI
# ============================================================

def build_ui():
    head_html = ""

    # JS body (no <script> wrapper) — Gradio runs this on page load via demo.load(js=...)
    mermaid_bootstrap_js = """
() => {
  if (window.__koraMermaidBootstrapped) return;
  window.__koraMermaidBootstrapped = true;

  function setupMermaid() {
    if (!window.mermaid) { return setTimeout(setupMermaid, 100); }
    window.mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
      themeVariables: {
        primaryColor: '#d9a44e',
        primaryTextColor: '#14141f',
        primaryBorderColor: '#d9a44e',
        lineColor: '#6cb8b0',
        secondaryColor: '#6cb8b0',
        tertiaryColor: '#1f1f2e',
        background: '#181823',
        mainBkg: '#1f1f2e',
        secondBkg: '#181823',
        textColor: '#ece9f5',
        fontFamily: 'Plus Jakarta Sans, sans-serif'
      }
    });
    function renderAll() {
      var els = document.querySelectorAll('.mermaid:not([data-processed="true"]):not([data-kora-failed])');
      if (!els.length) return;
      els.forEach(el => { if (!el.dataset.koraSource) el.dataset.koraSource = el.textContent.trim(); });
      try {
        window.mermaid.run({ nodes: Array.from(els) }).catch(() => {
          els.forEach(el => {
            if (el.querySelector('svg')) return;
            el.dataset.koraFailed = '1';
            el.innerHTML = '<div class="mermaid-fallback">' +
              '<div class="mf-icon">◇</div>' +
              '<div class="mf-text">A visual was prepared but did not render cleanly.<br>The concept is fully explained in the sections above.</div>' +
              '</div>';
          });
        });
      } catch (e) { /* swallow */ }
    }
    var obs = new MutationObserver(() => setTimeout(renderAll, 80));
    obs.observe(document.body, { childList: true, subtree: true });
    setInterval(renderAll, 800);
    setTimeout(renderAll, 300);
  }

  if (!document.querySelector('script[data-kora-mermaid]')) {
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
    s.dataset.koraMermaid = '1';
    s.onload = setupMermaid;
    document.head.appendChild(s);
  } else {
    setupMermaid();
  }
}
"""
    demo = gr.Blocks(title="Kora — Adaptive Learning")
    demo._kora_head = head_html
    with demo:
        gr.HTML("<div id='kora-mermaid-slot' style='display:none'></div>")
        state = gr.State(empty_state())

        # ----- HOME -----
        with gr.Column(visible=True, elem_id="screen-home") as scr_home:
            home_hdr = gr.HTML()
            with gr.Column(elem_id="home-search"):
                topic_box = gr.Textbox(
                    placeholder="Type any topic… (e.g. how vaccines work)",
                    label="",
                    show_label=False,
                    elem_id="topic-input",
                )
                start_btn = gr.Button(
                    "Start Learning →", variant="primary", elem_id="start-btn"
                , elem_classes=["kora-primary"])
            gr.HTML("<div class='chips-label'>Or try one of these</div>")
            with gr.Row(elem_id="chips-row"):
                chip1 = gr.Button("🧠  How the brain works", size="sm", elem_classes=["kora-chip"])
                chip2 = gr.Button("📐  Basic algebra", size="sm", elem_classes=["kora-chip"])
                chip3 = gr.Button("🌍  Climate change", size="sm", elem_classes=["kora-chip"])
            resume_row = gr.Column(visible=False, elem_id="resume-row")
            with resume_row:
                gr.HTML("<div class='resume-label'>Continue where you left off</div>")
                with gr.Column(elem_id="resume-list"):
                    resume_slot_1 = gr.Button("", visible=False, elem_classes=["resume-slot"])
                    resume_slot_2 = gr.Button("", visible=False, elem_classes=["resume-slot"])
                    resume_slot_3 = gr.Button("", visible=False, elem_classes=["resume-slot"])
            review_btn = gr.Button("Review due concepts →", variant="secondary", elem_classes=["kora-secondary"])

        # ----- PROFILE Q -----
        with gr.Column(visible=True, elem_id="screen-profile-q") as scr_profile_q:
            pq_progress_html = gr.HTML()
            pq_question_html = gr.HTML()
            pq_radio = gr.Radio(choices=[], label="", elem_id="pq-radio")
            pq_next = gr.Button("Next →", variant="primary", elem_classes=["kora-primary"])
            gr.HTML("<p class='subtitle center'>5 quick questions · Takes 2 minutes</p>")

        # ----- PROFILE REVEAL -----
        with gr.Column(visible=True, elem_id="screen-profile-reveal") as scr_profile_reveal:
            reveal_html_box = gr.HTML()
            reveal_continue = gr.Button("Let's set up your topic →", variant="primary", elem_classes=["kora-primary"])

        # ----- TOPIC SETUP -----
        with gr.Column(visible=True, elem_id="screen-topic-setup") as scr_topic_setup:
            topic_pill_box = gr.HTML()
            gr.HTML("<h1 class='setup-title'>Let's set up your path</h1>")
            gr.HTML("<div class='setup-q-label'>How deep do you want to go?</div>")
            depth_radio = gr.Radio(
                choices=["🌱 Overview · 20m", "📚 Solid · 45m", "🔬 Deep · 90m"],
                label="",
                show_label=False,
                value="📚 Solid · 45m",
                elem_id="depth-radio",
                elem_classes=["card-radio"],
            )
            gr.HTML("<div class='setup-q-label'>How much do you already know about this?</div>")
            level_radio = gr.Radio(
                choices=["🤷 Nothing yet", "🙂 I know a little", "🎓 I know quite a lot"],
                label="",
                show_label=False,
                value="🤷 Nothing yet",
                elem_id="level-radio",
                elem_classes=["card-radio"],
            )
            gr.HTML("<div class='setup-q-label'>Anything specific to focus on? <span class='setup-q-optional'>Optional</span></div>")
            focus_input = gr.Textbox(
                placeholder="e.g. I need this for an exam next week",
                label="",
                show_label=False,
                lines=1,
                elem_id="focus-input",
            )
            build_btn = gr.Button("Build My Learning Path →", variant="primary", elem_id="build-btn", elem_classes=["kora-primary"])
            gr.HTML("<p class='subtitle center setup-foot'>⚡ Generated on your device by Gemma 4</p>")

        # ----- LOADING -----
        with gr.Column(visible=True, elem_id="screen-loading") as scr_loading:
            loading_box = gr.HTML()

        # ----- MODULE HOOK -----
        with gr.Column(visible=True, elem_id="screen-module-hook") as scr_module_hook:
            hook_box = gr.HTML()
            hook_continue = gr.Button("I'm curious → Show me", variant="primary", elem_classes=["kora-primary"])

        # ----- MODULE TEACH -----
        with gr.Column(visible=True, elem_id="screen-module-teach") as scr_module_teach:
            teach_box = gr.HTML()
            teach_continue = gr.Button("I've got this → Activate me", variant="primary", elem_classes=["kora-primary"])
            teach_back = gr.Button("Read again", variant="secondary", size="sm", elem_classes=["kora-secondary"])

        # ----- MODULE ACTIVATE -----
        with gr.Column(visible=True, elem_id="screen-module-activate") as scr_module_activate:
            activate_top_box = gr.HTML()
            activate_card_box = gr.HTML()
            cloze_box = gr.HTML(visible=False)
            cloze_input1 = gr.Textbox(label="Blank 1", visible=False)
            cloze_input2 = gr.Textbox(label="Blank 2", visible=False)
            activate_textarea = gr.Textbox(
                label="Your answer",
                lines=4,
                placeholder="Just write naturally — no wrong answers here",
                visible=True,
            )
            with gr.Row(visible=True) as activate_submit_row:
                activate_submit = gr.Button("Submit →", variant="primary", elem_classes=["kora-primary"])
            feedback_box = gr.HTML()
            with gr.Row(visible=False) as activate_after_row:
                activate_retry = gr.Button("Try again", variant="secondary", elem_classes=["kora-secondary"])
                activate_continue = gr.Button("Continue →", variant="primary", elem_classes=["kora-primary"])

        # ----- MODULE BRIDGE -----
        with gr.Column(visible=True, elem_id="screen-module-bridge") as scr_module_bridge:
            bridge_box = gr.HTML()
            bridge_continue = gr.Button("Let's go →", variant="primary", elem_classes=["kora-primary"])

        # ----- SESSION REVIEW -----
        with gr.Column(visible=True, elem_id="screen-session-review") as scr_session_review:
            session_review_top_box = gr.HTML()
            fuzzy_radio = gr.Radio(choices=[], label="Which concept felt fuzziest?")
            pace_radio = gr.Radio(
                choices=["⏩ Too fast", "✅ Just right", "🐢 Too slow"],
                label="How did the pace feel?",
                value="✅ Just right",
            )
            session_submit = gr.Button("Submit →", variant="primary", elem_classes=["kora-primary"])
            adaptation_box = gr.HTML()
            session_done_row = gr.Row(visible=False)
            with session_done_row:
                go_home = gr.Button("See you next time →", variant="primary", elem_classes=["kora-primary"])
                keep_going = gr.Button("Keep going now", variant="secondary", elem_classes=["kora-secondary"])

        # ----- REVIEW -----
        with gr.Column(visible=True, elem_id="screen-review") as scr_review:
            review_box = gr.HTML()
            review_input = gr.Textbox(label="Your answer", lines=3)
            review_submit = gr.Button("Submit →", variant="primary", elem_classes=["kora-primary"])
            review_feedback_box = gr.HTML()
            review_model_box = gr.HTML()
            review_next_row = gr.Row(visible=False)
            with review_next_row:
                review_next_btn = gr.Button("Next Review →", variant="primary", elem_classes=["kora-primary"])
                review_home_btn = gr.Button("Back to Home →", variant="secondary", elem_classes=["kora-secondary"])

        # ----- DASHBOARD -----
        with gr.Column(visible=True, elem_id="screen-dashboard") as scr_dashboard:
            dash_html = gr.HTML()

        # Outputs list (must match render() return order)
        outputs = [
            home_hdr, scr_home, resume_row, resume_slot_1, resume_slot_2, resume_slot_3,
            pq_progress_html, pq_question_html, pq_radio, scr_profile_q,
            reveal_html_box, scr_profile_reveal,
            topic_pill_box, scr_topic_setup,
            loading_box, scr_loading,
            hook_box, scr_module_hook,
            teach_box, scr_module_teach,
            activate_top_box, activate_card_box, cloze_box,
            activate_textarea, cloze_input1,
            feedback_box, activate_submit_row, activate_after_row, scr_module_activate,
            bridge_box, scr_module_bridge,
            session_review_top_box, fuzzy_radio, adaptation_box, session_done_row,
            scr_session_review,
            review_box, review_feedback_box, review_model_box, review_next_row,
            scr_review,
            scr_dashboard,
        ]

        # initial render on load
        def initial_load():
            s = empty_state()
            return (s, *render(s))

        demo.load(initial_load, inputs=None, outputs=[state, *outputs], js=mermaid_bootstrap_js)

        # wire events
        start_btn.click(on_start_learning, [topic_box, state], [state, *outputs])
        chip1.click(lambda s: on_start_learning("How the brain works", s), [state], [state, *outputs])
        chip2.click(lambda s: on_start_learning("Basic algebra", s), [state], [state, *outputs])
        chip3.click(lambda s: on_start_learning("Climate change", s), [state], [state, *outputs])
        review_btn.click(on_start_review, [state], [state, *outputs])
        resume_slot_1.click(lambda s: (yield from on_resume_session(0, s)), [state], [state, *outputs])
        resume_slot_2.click(lambda s: (yield from on_resume_session(1, s)), [state], [state, *outputs])
        resume_slot_3.click(lambda s: (yield from on_resume_session(2, s)), [state], [state, *outputs])

        pq_next.click(on_profile_answer, [pq_radio, state], [state, *outputs])
        reveal_continue.click(on_profile_reveal_continue, [state], [state, *outputs])
        build_btn.click(on_build_path, [depth_radio, level_radio, focus_input, state], [state, *outputs])

        hook_continue.click(on_hook_continue, [state], [state, *outputs])
        teach_continue.click(on_teach_continue, [state], [state, *outputs])
        teach_back.click(lambda s: (s, *render(s)), [state], [state, *outputs])
        activate_submit.click(on_submit_activation, [activate_textarea, state], [state, *outputs])
        activate_continue.click(on_activation_continue, [state], [state, *outputs])
        activate_retry.click(on_activation_retry, [state], [state, *outputs])
        bridge_continue.click(on_bridge_continue, [state], [state, *outputs])

        session_submit.click(on_session_review_submit, [fuzzy_radio, pace_radio, state], [state, *outputs])
        go_home.click(on_session_done_home, [state], [state, *outputs])
        keep_going.click(on_session_done_home, [state], [state, *outputs])

        review_submit.click(on_review_submit, [review_input, state], [state, *outputs])
        review_next_btn.click(on_review_next, [state], [state, *outputs])
        review_home_btn.click(on_back_home, [state], [state, *outputs])

    return demo


if __name__ == "__main__":
    db.init_db()
    demo = build_ui()
    launch_kwargs = dict(server_name="0.0.0.0", server_port=7860, show_error=True, css=CSS)
    try:
        demo.launch(**launch_kwargs)
    except TypeError:
        launch_kwargs.pop("css", None)
        demo.launch(**launch_kwargs)
