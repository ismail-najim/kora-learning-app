"""Gemma 4 integration via Ollama — gemma_call() + 11 prompt functions."""
from __future__ import annotations

import json
import re
from typing import Any

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:latest"


def gemma_call(prompt: str) -> dict:
    """Single function for all Gemma 4 calls via Ollama. Returns parsed JSON or {}."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt + "\n\nReturn only valid JSON.",
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 2048},
            },
            timeout=180,
        )
        raw = response.json().get("response", "")
    except Exception:
        return {}

    if not raw:
        return {}

    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


# ---------- 1. topic map ----------

def generate_topic_map(topic: str, depth: str, focus_note: str = "") -> dict:
    prompt = f"""
You are a curriculum designer. A student wants to learn: {topic}
Desired depth: {depth} (overview=3-4 concepts, solid=5-7, deep=8-10)
Special focus: {focus_note or "none"}

Generate a structured topic map:
{{
  "topic": "clean topic name",
  "one_line_description": "plain language description",
  "prerequisites": ["helpful prior knowledge"],
  "core_concepts": ["ordered list of concepts to cover"],
  "estimated_modules": <int>,
  "difficulty_ceiling": "beginner|intermediate|advanced"
}}
"""
    return gemma_call(prompt)


# ---------- 2. profile question ----------

def build_profile_question(question_number: int, previous_answers: list) -> dict:
    prev = json.dumps(previous_answers) if previous_answers else "none yet"
    prompt = f"""
You are building a learning profile for a new student.
Question number: {question_number + 1} of 5
Previous answers so far: {prev}

Generate the next profiling question as a conversation
(not a form). Each question probes one of these signals:
- Q1: engagement style (story / steps / analogy / doing)
- Q2: pace preference (fast overview / steady / deep dive)
- Q3: visual vs text preference
- Q4: prior learning experience (formal / self-taught)
- Q5: confidence with difficult material

Return:
{{
  "question": "warm conversational question text",
  "signal_type": "engagement|pace|visual|experience|confidence",
  "options": [
    {{"label": "option text with emoji", "value": "code_value"}},
    {{"label": "option text with emoji", "value": "code_value"}},
    {{"label": "option text with emoji", "value": "code_value"}},
    {{"label": "option text with emoji", "value": "code_value"}}
  ]
}}
"""
    return gemma_call(prompt)


# ---------- 3. infer profile ----------

def infer_learning_profile(conversation_log: list) -> dict:
    prompt = f"""
A student answered 5 profiling questions.
Conversation log: {json.dumps(conversation_log)}

Infer their LearningProfile:
{{
  "engagement_style": "narrative|scaffolded|analogical|abstract",
  "pace": "fast|steady|thorough",
  "visual_weight": <float 0.0-1.0, 1.0=highly visual>,
  "hook_preference": "story|paradox|goal|challenge",
  "confidence_bias": "overconfident|calibrated|underconfident",
  "profile_summary": "2 sentences describing how to teach this person",
  "level_label": "friendly name e.g. 'The Explorer' or 'The Builder'",
  "style_description": "one sentence: how I'll adapt learning for you",
  "adaptation_notes": "initial teaching strategy note"
}}

Be specific. Do not return generic profiles.
"""
    return gemma_call(prompt)


# ---------- 4. learning path ----------

def generate_learning_path(topic_map: dict, profile: dict, depth: str,
                           self_reported_level: str) -> dict:
    prompt = f"""
Build a learning path for this student.

Topic map: {json.dumps(topic_map)}
Student profile: {json.dumps(profile)}
Depth: {depth}
Self-reported level: {self_reported_level}

Generate an ordered list of modules with strategy per module:

IMPORTANT: concept_name must be 2-5 words. A label, NOT a description. NO colons, NO markdown, NO "Understanding..." prefix. Examples of good names: "Neurons and Synapses", "Light Reactions", "Supply and Demand", "Linear Equations".

{{
  "path": [
    {{
      "module_number": 1,
      "concept_name": "short 2-5 word concept name (NO description after colon)",
      "hook_type": "story|paradox|goal|challenge",
      "teach_style": "narrative|scaffolded|analogical|abstract",
      "scaffold_level": "worked_example|completion|independent|challenge",
      "visual_type": "diagram|comparison_table|process_flow|none",
      "estimated_minutes": <int>,
      "connects_to_next": "one sentence preview bridge"
    }}
  ],
  "verified_level": "novice|developing|competent|advanced",
  "level_reasoning": "one sentence explaining level assessment"
}}

scaffold_level rules:
- novice -> worked_example (full worked example before any attempt)
- developing -> completion (partial example, student fills last steps)
- competent -> independent (problem first, light support)
- advanced -> challenge (hardest version, no hints)
"""
    return gemma_call(prompt)


# ---------- 5. hook ----------

def generate_module_hook(concept: str, hook_type: str, profile: dict, topic: str) -> dict:
    profile_summary = profile.get("profile_summary", "")
    prompt = f"""
Write a RICH opening hook for a learning module about: {concept}
Topic: {topic}
Hook flavour: {hook_type}
Student profile: {profile_summary}

Return JSON in this EXACT shape:

{{
  "headline": "5-9 word punchy headline that creates intrigue",
  "hook_text": "3-4 sentence vivid opener. SPECIFIC. Use a scene, a number, or a question. NO 'In this module' fluff.",
  "stat": {{
    "number": "the eye-catching number, e.g. '86 billion' or '20 nanometres' or '50 ms'",
    "label": "what the number means in 5-10 words"
  }},
  "paradox": "one counterintuitive fact about this concept in one sentence, or null",
  "promise": "one sentence: 'By the end of this module you'll be able to...'",
  "hook_type": "{hook_type}"
}}

Hook flavour rules:
- story: open with a real scene (a person, a moment, a place)
- paradox: open with a surprise that breaks intuition
- goal: open with capability the student will gain
- challenge: open with a hard question

EXAMPLE for "Light Reactions":
{{
  "headline": "How a Plant Eats Sunlight",
  "hook_text": "Inside every leaf, a green molecule called chlorophyll catches a single photon of sunlight. That single photon kicks off a chain of events that splits a water molecule, releases oxygen into the air you're breathing right now, and stores energy in a bond that powers life. Plants are running a nuclear-grade trick — at room temperature.",
  "stat": {{"number": "10^17", "label": "photons hitting Earth every second to power photosynthesis"}},
  "paradox": "The oxygen you breathe is, technically, a waste product.",
  "promise": "By the end of this module you'll be able to explain how plants turn light into chemical energy step-by-step.",
  "hook_type": "paradox"
}}

Now produce one for: {concept}
"""
    return gemma_call(prompt)


# ---------- 6. teach ----------

def _normalise_teach(teach: dict, concept: str, topic: str) -> dict:
    """Coerce model output into the rich teach schema; build sections from
    a plain 'explanation' if that's all the model returned."""
    if not isinstance(teach, dict):
        teach = {}

    # If we got rich shape, keep it
    has_sections = isinstance(teach.get("sections"), list) and len(teach["sections"]) > 0
    if has_sections:
        return teach

    # Convert old-style "explanation" into sections by splitting paragraphs
    expl = teach.get("explanation") or ""
    if expl:
        paras = [p.strip() for p in re.split(r"\n\s*\n", expl) if p.strip()]
        sections = []
        for i, p in enumerate(paras[:5]):
            sections.append({
                "heading": f"Part {i+1}",
                "body": p,
            })
        if not sections:
            sections = [{"heading": "Overview", "body": expl}]
        teach["sections"] = sections
        teach.setdefault("core_insight", paras[0] if paras else f"Understanding {concept}.")
        teach.setdefault("worked_example", teach.get("worked_example"))
    return teach


def generate_module_teach(concept: str, profile: dict, scaffold_level: str,
                          visual_type: str, topic: str) -> dict:
    engagement_style = profile.get("engagement_style", "scaffolded")
    prompt = f"""
Design a RICH, VISUAL learning module for one concept.

Topic: {topic}
Concept: {concept}
Student engagement style: {engagement_style}
Scaffold level: {scaffold_level}
Suggested diagram type: {visual_type}

Engagement style rules:
- narrative: frame as story or real-world situation. Open with scene.
- scaffolded: numbered steps. One idea per step. Short sentences.
- analogical: open with "X is like Y because..." Build via comparison.
- abstract: state principle first. Then example. Then edges.

Scaffold rules:
- worked_example: show complete example BEFORE asking student to do anything
- completion: show partial example, mark [STUDENT FILLS HERE]
- independent: give problem, no example
- challenge: hardest version, ask student to generalise

CRITICAL: respond with VALID JSON in this exact shape:

{{
  "core_insight": "1-2 sentence punchy takeaway — the SINGLE most important idea",
  "sections": [
    {{
      "heading": "short section title (5 words max)",
      "body": "1-2 short paragraphs. Use **bold** for key terms. Use bullet lists (- item) or numbered lists (1. item) where helpful. Plain markdown, NO ``` fences, NO headings inside."
    }}
  ],
  "mermaid_diagram": "valid Mermaid.js syntax that visualises the concept. Use ONE of: flowchart TD, flowchart LR, sequenceDiagram, mindmap, stateDiagram-v2. Use simple node names (no special characters in node IDs). NO ``` fences. Example: 'flowchart LR\\n  A[Sunlight] --> B[Chlorophyll]\\n  B --> C[Glucose]'",
  "diagram_caption": "one sentence describing what the diagram shows",
  "worked_example": "concrete example with **bold** key bits, or null",
  "key_terms": [
    {{"term": "term name", "definition": "one-line definition"}}
  ],
  "common_confusion": "one common misconception people have about this concept, and the correction (2-3 sentences), or null"
}}

Rules:
- 4-5 sections REQUIRED. Each section body is 2-3 paragraphs (NOT one sentence). Pack in real substance — facts, mechanisms, numbers, names, examples.
- mermaid_diagram is REQUIRED. Pick the diagram type that best fits the concept. NO triple-backticks.
- Mermaid node IDs must be simple letters or short alphanumeric (A, B1, Node1). Put readable text in [brackets] (rectangles) or {{curly}} (diamonds) or (parens) (circles).
- Inside mermaid labels: NO ampersand (&), NO angle brackets, NO double quotes. Replace "&" with "and". Keep labels short (2-5 words).
- Each statement on its OWN LINE separated by literal \n. Example: "flowchart LR\\n  A[Start] --> B[Middle]\\n  B --> C[End]".
- 3-4 key_terms with specific definitions (not "the thing that does X" — actual definitions).
- worked_example is REQUIRED for novice/developing levels. A real concrete instance with names/numbers.
- common_confusion is REQUIRED — pick the misconception even smart students have.
- Tone: warm, specific, vivid. NO generic phrases like "let's dive in" or "in this module".
- The student should finish this and FEEL they learned something concrete. A paragraph of fluff is a failure.

EXAMPLE of the EXACT shape (a different concept) — return JSON that looks structurally like this:

{{
  "core_insight": "A neuron doesn't 'send' a signal — it triggers a chemical handoff at a tiny gap called the synapse.",
  "sections": [
    {{"heading": "The Three Parts", "body": "Every neuron has three working parts: **dendrites** (the antennae that collect signals), the **soma** (the cell body that decides whether to fire), and the **axon** (the long cable that carries the output).\\n\\nThink of it as: input → decision → output. The soma is the integrator. If enough excitement arrives at the dendrites, the soma fires."}},
    {{"heading": "The Synapse", "body": "Where one neuron's axon meets the next neuron's dendrite, they don't touch. There's a 20-nanometre gap called the **synaptic cleft**.\\n\\nSignals cross this gap as chemicals — **neurotransmitters** — released from vesicles. The receiving side has receptors waiting for them."}},
    {{"heading": "Firing Rules", "body": "A neuron is binary: it either fires or it doesn't. This is the **all-or-none principle**.\\n\\nWhat varies is the *rate* of firing. A loud noise = neurons fire faster. A whisper = slower firing."}},
    {{"heading": "Why It Matters", "body": "Everything you experience — vision, memory, emotion — is patterns of firing across **86 billion** neurons connected by **trillions** of synapses.\\n\\nLearning literally reshapes which synapses are strong. This is called **synaptic plasticity**."}}
  ],
  "mermaid_diagram": "flowchart LR\\n  D[Dendrites] --> S[Soma]\\n  S --> A[Axon]\\n  A --> C[Synapse]\\n  C --> N[Next Neuron]",
  "diagram_caption": "The flow of a signal through one neuron and into the next.",
  "worked_example": "When you touch a hot stove, **sensory neurons** in your skin fire. Their axons connect to neurons in your spinal cord, which in turn fire motor neurons that contract your arm muscles — all before your brain consciously registers pain. Total time: ~50 milliseconds.",
  "key_terms": [
    {{"term": "Synapse", "definition": "The tiny chemical junction between two neurons."}},
    {{"term": "Neurotransmitter", "definition": "A chemical messenger that carries the signal across the synapse (e.g. dopamine, glutamate)."}},
    {{"term": "All-or-none", "definition": "A neuron either fires fully or not at all — no half-firings."}}
  ],
  "common_confusion": "People think neurons 'send electricity' to each other. They don't — the electrical signal travels WITHIN one neuron, but BETWEEN neurons the signal is purely chemical."
}}

Now produce the same shape for: {concept}
"""
    result = gemma_call(prompt)
    return _normalise_teach(result, concept, topic)


# ---------- 7. activate ----------

def generate_module_activate(concept: str, engagement_style: str,
                             explanation: str, scaffold_level: str) -> dict:
    summary = explanation[:400] if explanation else ""
    prompt = f"""
Generate an activation prompt for a student who just read an explanation.

Concept: {concept}
Student engagement style: {engagement_style}
Scaffold level: {scaffold_level}
Explanation they read: {summary}

Activation type by engagement style:
- narrative: ask student to retell in own words or apply to a new story scenario
- scaffolded: fill in a text diagram or complete a cloze paragraph (2 blanks)
- analogical: ask student to generate their own analogy for the concept
- abstract: give a novel problem applying the principle

Return:
{{
  "activation_prompt": "what you ask the student to do",
  "activation_type": "retell|cloze|analogy|apply",
  "cloze_text": "sentence with ___ blanks if cloze, else null",
  "cloze_answers": ["answer1", "answer2"],
  "model_answer_guide": "what a good response includes"
}}
"""
    return gemma_call(prompt)


# ---------- 8. evaluate ----------

_NON_ANSWERS = {
    "", "?", "??", "???", ".", "..", "idk", "i dont know", "i don't know",
    "no idea", "no clue", "dunno", "not sure", "nothing", "blank", "skip",
    "pass", "n/a", "na", "...", "—", "-",
}


def evaluate_activation(activation_prompt: str, model_answer_guide: str,
                        student_answer: str, concept: str) -> dict:
    # Short-circuit obvious non-answers before calling the model
    norm = (student_answer or "").strip().lower().rstrip(".!?")
    if norm in _NON_ANSWERS or len(norm) < 3:
        return {
            "accuracy_score": 0.0,
            "feedback": "You didn't take a swing yet — and that's fine. The whole point of this beat is to try.",
            "what_to_sharpen": f"Write one sentence about **{concept}** using the explanation above. Even a partial attempt teaches your brain more than reading it again.",
            "is_sufficient": False,
        }

    prompt = f"""
Evaluate a student's answer HONESTLY but warmly.

Concept: {concept}
They were asked: {activation_prompt}
A good answer includes: {model_answer_guide}
Their answer: "{student_answer}"

SCORING RUBRIC — be strict and realistic. Generosity ≠ honesty:
- 0.0: Empty, "I don't know", off-topic, or just keywords with no understanding shown.
- 0.1–0.3: Mentions related words but doesn't show grasp. Missing the core idea.
- 0.4–0.6: Partial understanding. Got SOME of the key idea but missed major pieces.
- 0.7–0.85: Essentially right. Has the core idea. Missing nuance or precision.
- 0.86–0.95: Solid, complete, accurate. Maybe small wording polish.
- 0.96–1.0: Perfect or beyond — clear, complete, well-stated.

DO NOT default to 0.6–0.7 as a "polite" score. If the student wrote one vague sentence, that's 0.3 — be honest. They will trust you more when you're real with them.

Return:
{{
  "accuracy_score": <float 0.0-1.0 per rubric above>,
  "feedback": "1-2 sentences. Honest but warm. If they got something right, say what. If they didn't, name what's missing WITHOUT being harsh. Examples of honest framing: 'You're circling the idea but the core piece is still missing.' / 'You named X correctly — but the WHY isn't there yet.' / 'That captures the surface, not the mechanism.'",
  "what_to_sharpen": "ONE clear, memorable, actionable improvement. Start with the SPECIFIC concept they missed (use **bold** on the key term). Under 25 words. Example: 'Add **water** to the inputs — it's split during the light reactions to release oxygen.' Set to null ONLY if the answer is fully complete.",
  "is_sufficient": true
}}

Rules:
- Never say "correct" / "incorrect" — describe what they showed.
- A vague answer is not 60% — it's 30%. Be honest.
- A "good try" with the wrong mechanism is 20-40%, not 70%.
- Honesty earns trust. Fake encouragement teaches nothing.
"""
    result = gemma_call(prompt)
    if not result or "accuracy_score" not in result:
        # Honest fallback when the model fails
        return {
            "accuracy_score": 0.3,
            "feedback": "I couldn't quite parse what you wrote — that's on me. Want to try once more with the key idea?",
            "what_to_sharpen": f"State the core mechanism of **{concept}** in your own words — one or two sentences is enough.",
            "is_sufficient": False,
        }
    # Clamp + sanity check
    try:
        s = float(result.get("accuracy_score", 0.5))
        result["accuracy_score"] = max(0.0, min(1.0, s))
    except Exception:
        result["accuracy_score"] = 0.3
    return result


# ---------- 9. bridge ----------

def generate_bridge(current_concept: str, next_concept: str,
                    student_answer_quality: float) -> dict:
    prompt = f"""
Write a bridge sentence connecting two learning modules.

Current concept just learned: {current_concept}
Next concept coming up: {next_concept}
Student answered well: {student_answer_quality:.2f}

Return:
{{
  "bridge_text": "2-3 sentences. Connect the dots between what they just learned and what comes next. Build anticipation. If student struggled, add a reassuring note first."
}}
"""
    return gemma_call(prompt)


# ---------- 10. analyse session ----------

def analyse_session(session_log: list, current_profile: dict) -> dict:
    prompt = f"""
Analyse a completed learning session and update the student's learning profile.

Current profile: {json.dumps(current_profile)}
Session log (modules completed, accuracy scores, time per beat, pace feedback, fuzzy concept):
{json.dumps(session_log)}

Detect changes in:
- Did they rush through text but slow on visuals? -> increase visual_weight
- Did accuracy drop in later modules? -> recommend slower pace
- Did they consistently score high? -> consider increasing scaffold_level
- Did they report pace was too fast/slow? -> adjust pace field

Return:
{{
  "updated_profile": {{
    "engagement_style": "narrative|scaffolded|analogical|abstract",
    "pace": "fast|steady|thorough",
    "visual_weight": <float 0.0-1.0>,
    "hook_preference": "story|paradox|goal|challenge",
    "confidence_bias": "overconfident|calibrated|underconfident",
    "adaptation_notes": "updated note"
  }},
  "changed_fields": ["list of field names that changed"],
  "adaptation_message": "1-2 sentences shown to student: what you noticed and how you'll adjust. Specific, not generic.",
  "next_session_preview": "one sentence about what's next and how you'll open it"
}}
"""
    return gemma_call(prompt)


# ---------- 11. review question ----------

def generate_review_question(concept: str, topic: str,
                             days_since: int, accuracy: float) -> dict:
    prompt = f"""
Generate a spaced review question.

Concept: {concept} (part of topic: {topic})
Days since learned: {days_since}
Previous accuracy: {accuracy:.2f}

Generate a FRESH question - not a repeat of original.
Test the same concept from a different angle.

Type rules:
- accuracy < 0.6: easy application question + include hint
- accuracy 0.6-0.85: medium transfer question
- accuracy > 0.85: hard consequence/generalisation question

Return:
{{
  "question": "fresh question from new angle",
  "question_type": "application|transfer|consequence",
  "hint": "gentle hint or null",
  "model_answer": "what a complete answer includes",
  "difficulty": "easy|medium|hard"
}}
"""
    return gemma_call(prompt)
