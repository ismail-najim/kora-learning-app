# Kora — Learn Anything. Adapted to You. Fully Offline.

**Subtitle:** An on-device adaptive learning app powered entirely by Gemma 4. 

**Track:** Main Track · Future of Education Impact Track · Digital Equity Impact Track

---

## Why I Built Kora

Learning is the most powerful tool humanity has. It's the engine of hope. It makes people smart and innovative, lifts people out of poverty, and gives us a shot at the biggest problems we face — disease, climate, conflict.

And yet learning is still broken.

It's **passive**: you read a page, you watch a video, your brain forgets 90% by tomorrow. It's **gated**: a personalised tutor costs $200/hr. Bloom's "2-sigma problem" — that a one-to-one tutor lifts a student two standard deviations above the classroom — has been a known result since 1984. For 42 years it's been impossible to deploy at scale. And it's **online-only** — a student with patchy 3G or no connection gets the worst version of every AI tool.

This is what Kora fixes. Every adult on Earth is about to carry a 4B-parameter model in their pocket. The 2-sigma tutor is finally deployable. It just needed to be built right.

## What Kora Does

You type any topic — "photosynthesis", "the French Revolution", "how vaccines work". Kora then:

1. **Builds your learner profile** through a 5-question conversation — engagement style, pace, visual preference, prior experience, confidence with hard material.
2. **Generates a personalised path** of modules scaled to the depth you want.
3. **Teaches each concept in four active beats**: **Hook → Teach → Activate → Bridge**.
4. **Grades your answers honestly** with a 0–100 rubric and tells you the one specific thing to add next time.
5. **Schedules spaced reviews** (SM-2) so concepts resurface just before you'd forget them.
6. **Adapts after every session** — Gemma 4 reads your session log and rewrites your teaching profile based on what you actually did, not just what you said.

All on-device. After the model pull, **zero network calls**.

## The Learning Experience

Three things make Kora different from every "AI tutor" demo I've seen.

### 1. It Adapts From What You *Do*, Not Just What You *Say*

Most adaptive systems ask a checkbox question — "do you prefer visual or text?" — and stop there. Kora does the cold-start questions (5 of them, conversational, asked one at a time so the answer to Q2 informs Q3). But the real adaptation happens in the loop: every session, Gemma 4 reads the **full session log** — your accuracy per module, time spent on text vs. visuals, pace feedback — and rewrites your profile. If you sped through the prose and slowed on the diagrams, visual weight goes up. If your accuracy dropped in the last module, pace slows down. You don't have to tell Kora how you learn. It watches.

### 2. It Cracks the "Boring" Problem Through Story + Stat + Shock

Every Hook beat has four ingredients: a punchy headline, a vivid 3–4 sentence opener, **an eye-catching stat card** (big amber number, e.g. "86 billion neurons"), and **a counterintuitive fact** (the oxygen you breathe is, technically, a waste product). Every Teach beat is broken into 4–5 numbered sections with bold key terms, plus a **rendered Mermaid SVG diagram**, a worked example, a key-terms grid, and a **common-confusion callout** that names the misconception even smart students hold. This is not decoration. This is the dual-coding principle, the predict-first principle, and the misconception-correction principle from learning science — packed into every screen.

### 3. The Improvement Loop Is the Product

Every concept moves through a tight loop: **Concept → Learning → Test → Feedback → Next.** The Test is real retrieval, not multiple choice. You type a sentence. You get an **honest** score (a vague answer is 30%, not the polite 70% that other apps give). And critically, the feedback has two parts: what you got right, and **what to add next time** — bolded, memorable, under 25 words. Honesty earns trust. Fake encouragement teaches nothing.

### 4. Latency Becomes a Feature

On-device inference takes 5–10 seconds per call. Most apps would show a spinner. Kora shows **a rotating learning-science insight** — *"Active recall beats re-reading by 3x"* / *"Forgetting is a feature"* / *"Sleep writes memories"* / *"Mistakes wire learning"* — every transition. Ten curated insights. The waiting time itself becomes a meta-learning moment. You're not just learning the topic; you're learning *how to learn*.

## Eleven Roles for One Model

Kora's edge is treating Gemma 4 not as a chatbot but as a **structured curriculum designer** with 11 distinct roles, each via a typed JSON contract:

| # | Role | What It Outputs |
|---|------|------------------|
| 1 | `generate_topic_map` | Ordered concept list scaled to depth |
| 2 | `build_profile_question` | One profiling question + 3–4 options |
| 3 | `infer_learning_profile` | Typed profile from 5 answers |
| 4 | `generate_learning_path` | Per-module strategy: hook type, teach style, scaffold level, visual type |
| 5 | `generate_module_hook` | Headline + opener + stat + paradox + capability promise |
| 6 | `generate_module_teach` | Core insight + 4 sections + Mermaid diagram + worked example + key terms + common confusion |
| 7 | `generate_module_activate` | Retrieval task tuned to engagement style |
| 8 | `evaluate_activation` | Honest 0–1 score with rubric + warm feedback + actionable next-step |
| 9 | `generate_bridge` | Transition that connects modules |
| 10 | `analyse_session` | Updated profile based on accuracy, timing, pace |
| 11 | `generate_review_question` | Fresh-angle review question at matched difficulty |

Each role uses Ollama's `format: "json"` mode with explicit JSON schema examples in the prompt. Eleven typed contracts is what makes a 4B model production-trustworthy.

## Architecture

Stack: **Python 3.11 + Gradio + SQLite (stdlib) + Ollama + Gemma 4** (`gemma3:latest`, 4.3B Q4_K_M, 3.3 GB).

The UI is a single-page state machine with 12 screens. Slow Gemma transitions are Python generators that **yield a loading state first** — the insight card appears immediately, then the real result streams in.

Diagrams render as real SVGs via **Mermaid.js**, with a server-side normalizer that handles the model's frequent missing-newline bug, sanitizes characters that break Mermaid's parser (`&`, `<`, `>`, unicode subscripts), and wraps labels with `:`, `=`, `+` in proper Mermaid quotes.

SQLite holds five tables: `learning_profile`, `topic_session`, `module` (content as JSON), `review_item` (SM-2 state), `streak`. Every interaction persists — resuming a half-finished topic just works.

## Challenges I Hit

**Mermaid's hidden contract.** Gemma reliably emits valid syntax — on a single line. Mermaid requires newlines between statements. I wrote a regex normalizer that detects diagram-type headers and inserts newlines after node closers (`]`, `}`, `)`). Then a second pass wraps labels with reserved characters in double quotes per Mermaid's escape rules. Result: every Teach beat ships with a real rendered SVG.

**Honest grading.** The default for any AI evaluator is to be polite. I had Gemma giving 70% for vague one-sentence answers. I rewrote the prompt with a strict 0–100 rubric (vague = 30%, partial = 40–60%, solid = 80%+) and added in-code short-circuits for "I don't know", "?", "idk" → 0%. Honesty earns trust.

**Schema reliability.** The first version of `generate_module_teach` returned plain `{ "explanation": "..." }` half the time. I added an explicit example output in the prompt and a `_normalise_teach()` post-processor that converts any old-shape response into proper sections. Eleven contracts × at least one fallback each = a system that doesn't break in front of a learner.

## Why On-Device, Why Gemma, Why Now

**Privacy.** Your mistakes, gaps, and confidence levels are some of the most sensitive data you generate. They should never leave the device.

**Equity.** Internet access is the largest single barrier to personalised education. An app that works in airplane mode works everywhere.

**Cost.** Zero per-token cost means a learner can explore unlimited topics. Cloud LLM pricing puts a paywall around curiosity itself.

**Gemma 4** is the only open-weight, instruction-tuned model that runs at acceptable speed on a 2020 laptop and is small enough to be deployable to a $50 Android phone via LiteRT. It's the right model for the right moment.

## What's Next

**LiteRT Android port.** The prompt library is portable string templates with JSON contracts. The work is reimplementing `gemma_call()` against LiteRT's inference API and rebuilding the screens in Compose. The economics: Gemma 3 1B INT4 fits in ~600 MB on a $50 phone.

**Multimodal recall.** Gemma can read images. I want students to photograph a confusing page from a real textbook and have Kora explain it back in their voice, using their learner profile.

**Cohort mode.** Share a topic with a study group. Each learner's adapted profile shapes their personal path while the group sees shared progress.


