# Kora

**Learn anything. Adapted to you. Fully offline.**

An on-device adaptive learning app powered entirely by **Gemma 4** running locally via Ollama. Type any topic → Kora builds a personalised path → you learn through Hook → Teach → Activate → Bridge beats → spaced repetition surfaces concepts before you'd forget them.

Built for the [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon).

---

## What It Does

1. **Type any topic** — "Photosynthesis", "The French Revolution", "Linear algebra"
2. **Build your learner profile** — a 5-question conversation infers engagement style, pace, visual preference, prior experience, confidence bias
3. **Set depth + level** — Overview · 20m / Solid · 45m / Deep · 90m
4. **Learn actively** — each module = **Hook → Teach → Activate → Bridge**
5. **Get honest feedback** — your answers are graded on a strict 0–100 rubric, with the specific gap called out
6. **Spaced repetition** — SM-2 surfaces concepts when you're about to forget them
7. **Adapt** — Gemma 4 reads your session log and updates your profile after every session

All on-device. Zero cloud calls after `ollama pull`.

---

## Setup

```bash
# 1. Install Ollama  →  https://ollama.ai  (or: brew install ollama)
# 2. Pull Gemma 4 (4.3B Q4_K_M, ~3.3 GB)
ollama pull gemma3:latest

# 3. Clone + install
git clone https://github.com/ismail-najim/kora-learning-app.git
cd kora-learning-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. Run
python app.py

# 5. Open
open http://localhost:7860
```

**For a detailed setup, dependency list, troubleshooting, and architecture diagram, see [SETUP.md](./SETUP.md).**

Tested on macOS 14+ with Python 3.11+. Gradio 4.x and 6.x both supported.

---

## The Science

Six evidence-based teaching techniques, baked into the prompts:

- **Retrieval practice** — you produce an answer before moving on
- **Spaced repetition** — SM-2 scheduler picks the next-review date
- **Dual coding** — every module has text + a Mermaid SVG diagram
- **Cognitive load scaffolding** — novice gets worked examples, advanced gets challenges
- **Predict-first** — the hook fires before the explanation
- **Session adaptation** — Gemma 4 rewrites your teaching strategy after each session

---

## Gemma 4 Roles (11 prompt functions)

Kora treats Gemma 4 not as a chatbot but as a **structured curriculum designer**, with 11 typed roles:

| # | Function | Purpose |
|---|----------|---------|
| 1 | `generate_topic_map` | Ordered concept list scaled to depth |
| 2 | `build_profile_question` | One conversational profiling question |
| 3 | `infer_learning_profile` | Typed profile from 5 answers |
| 4 | `generate_learning_path` | Per-module strategy |
| 5 | `generate_module_hook` | Headline + opener + stat + paradox |
| 6 | `generate_module_teach` | Sections + Mermaid + worked example + key terms + common confusion |
| 7 | `generate_module_activate` | Retrieval task tuned to engagement style |
| 8 | `evaluate_activation` | Honest 0–1 score + actionable next-step |
| 9 | `generate_bridge` | One-sentence transition between modules |
| 10 | `analyse_session` | Updated profile from session log |
| 11 | `generate_review_question` | Fresh-angle spaced-repetition question |

Each role uses Ollama's `format: "json"` mode with an explicit JSON schema example in the prompt.

---

## File Structure

```
kora/
├── app.py          # Gradio Blocks UI + state machine (12 screens)
├── gemma.py        # gemma_call() + all 11 prompt functions
├── database.py     # SQLite schema, dataclasses, CRUD
├── scheduler.py    # SM-2 spaced repetition (intervals 1, 3, 7, 14, 30, 60)
├── styles.css      # Custom brand theme (burnished gold + sage teal)
├── requirements.txt
└── README.md
```

---

## Data Model

All in SQLite (`kora.db`, auto-created on first run):

- `learning_profile` — engagement style, pace, visual weight, hook preference, confidence bias
- `topic_session` — topic, depth, level, ordered path, current module index
- `module` — generated content (JSON), mastery score, beat
- `review_item` — SM-2 fields per module (next_review, easiness factor, repetition count)
- `streak` — daily activity tracker

---

## Why On-Device Matters

- **Privacy** — your learning data, mistakes, and confidence gaps never leave your device
- **Equity** — works for students with patchy or no connectivity
- **Cost** — zero per-token cost, learn unlimited topics
- **Latency** — no network round-trips between beats

---

## Roadmap

- **LiteRT Android port** — the prompt library is portable; reimplement `gemma_call()` against LiteRT and rebuild screens in Compose
- **Multimodal recall** — photograph a confusing textbook page and have Kora explain it back
- **Cohort mode** — share a topic with a study group, each learner gets their own adapted path

---

## Tech

Python 3.11 · Gradio · SQLite (stdlib) · Mermaid.js · Ollama · Gemma 3 4B (4.3B Q4_K_M)

Built with care for the Gemma 4 Good Hackathon. 
