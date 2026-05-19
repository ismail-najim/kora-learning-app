# Kora — Setup & Environment Guide

This guide gets you from zero to a running Kora instance on your machine in about 10 minutes. Everything runs locally — no API keys, no cloud calls.

---

## Prerequisites

| Requirement | Version | Why |
|-------------|---------|-----|
| **macOS / Linux / Windows** | any recent | Cross-platform |
| **Python** | 3.10+ (3.11 or 3.12 recommended) | Modern type-hint syntax used in the code |
| **pip** | bundled with Python | Dependency installer |
| **Ollama** | 0.1.30+ | Runs Gemma 4 locally |
| **Modern browser** | Chrome / Firefox / Safari / Edge | Renders the Gradio UI |
| **Disk space** | ~4 GB free | Gemma 3 4B Q4_K_M model is ~3.3 GB |
| **RAM** | 8 GB minimum, 16 GB recommended | Model inference is memory-bound |
| **Internet** | only for setup | Pull the model once; the app then runs fully offline |

---

## Step 1 — Install Ollama

Ollama is the local LLM runtime that hosts Gemma 4.

**macOS** — via Homebrew (recommended):
```bash
brew install ollama
brew services start ollama   # starts the Ollama daemon in the background
```

Or download the macOS app from [ollama.ai](https://ollama.ai) and launch it once.

**Linux**:
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**Windows**: download the installer from [ollama.ai](https://ollama.ai) and run it. Ollama runs as a background service after install.

Verify Ollama is running:
```bash
curl http://localhost:11434/api/tags
```
You should get back a JSON response (empty `models` array is fine at this point).

---

## Step 2 — Pull the Gemma 4 model

```bash
ollama pull gemma3:latest
```

This downloads about **3.3 GB**. Takes 2–5 minutes depending on your connection. You only need to do this once.

Verify the model is available:
```bash
ollama list
```
You should see `gemma3:latest` in the output with size ~3.3 GB.

> Note: the app's model name lives in [`gemma.py`](./gemma.py) at the top — `MODEL = "gemma3:latest"`. If you want to use a different Gemma variant (e.g. a fine-tuned one or a larger Q-level), edit that constant.

---

## Step 3 — Clone this repo

```bash
git clone https://github.com/ismail-najim/kora-learning-app.git
cd kora-learning-app
```

---

## Step 4 — Set up a Python virtual environment

This isolates Kora's dependencies from your system Python.

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

You should see `(.venv)` prefix in your terminal prompt.

---

## Step 5 — Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Dependencies installed:
| Package | What for |
|---------|---------|
| `gradio>=4.0.0` | The web UI framework (works with both Gradio 4.x and 6.x) |
| `requests>=2.31.0` | HTTP calls to the local Ollama server |
| `python-dateutil>=2.8.0` | Date helpers used by the spaced-repetition scheduler |

Everything else used (`sqlite3`, `json`, `re`, `dataclasses`) is in the Python standard library.

---

## Step 6 — Run the app

```bash
python app.py
```

You should see:
```
* Running on local URL:  http://0.0.0.0:7860
```

Open [http://localhost:7860](http://localhost:7860) in your browser.

---

## Verifying the install — your first topic

1. On the home page, type a topic like **"How vaccines work"** or **"Photosynthesis"**
2. Click **Start Learning →**
3. Answer the 5 profile-building questions (takes ~1 minute)
4. Pick a depth + level on the setup screen, then **Build My Learning Path →**
5. The first **Hook** beat should render in 10–30 seconds

The first call after a fresh start loads the model into memory — that's the slow one. Subsequent calls are much faster (typically 3–8 seconds each on a 2020+ machine).

If you don't see a hook screen after 60 seconds, see **Troubleshooting** below.

---

## How it works at runtime

```
┌──────────────────────┐         ┌────────────────┐
│   Browser (Gradio)   │ ◀────── │   app.py       │
│   localhost:7860     │ ───────▶│   state machine│
└──────────────────────┘         └────────┬───────┘
                                          │
                          ┌───────────────┼──────────────┐
                          ▼               ▼              ▼
                   ┌────────────┐ ┌──────────────┐ ┌──────────────┐
                   │ gemma.py   │ │ scheduler.py │ │ database.py  │
                   │ 11 prompt  │ │   SM-2       │ │   SQLite     │
                   │ functions  │ │ scheduler    │ │   kora.db    │
                   └─────┬──────┘ └──────────────┘ └──────────────┘
                         │
                         ▼
                   ┌──────────────┐
                   │   Ollama     │
                   │ localhost    │
                   │   :11434     │
                   │  (Gemma 4)   │
                   └──────────────┘
```

- `app.py` orchestrates the UI state machine and routes events
- `gemma.py` sends typed prompts to Ollama and parses JSON back
- `scheduler.py` handles spaced-repetition timing (SM-2)
- `database.py` persists everything to `kora.db` (SQLite, auto-created)
- The browser renders Mermaid SVGs client-side via [mermaid.js](https://mermaid.js.org/) loaded from a CDN

---

## File map

| File | Purpose |
|------|---------|
| [`app.py`](./app.py) | Gradio UI, state machine, all 12 screens |
| [`gemma.py`](./gemma.py) | `gemma_call()` + 11 prompt functions |
| [`database.py`](./database.py) | SQLite schema, dataclasses, CRUD operations |
| [`scheduler.py`](./scheduler.py) | SM-2 spaced repetition |
| [`styles.css`](./styles.css) | Custom brand theme (burnished gold + sage teal) |
| [`requirements.txt`](./requirements.txt) | Python dependencies |

---

## Troubleshooting

**Port 7860 already in use**
```bash
lsof -ti :7860 | xargs kill -9
python app.py
```

**Ollama not reachable / "Connection refused"**
- Check Ollama is running: `curl http://localhost:11434/api/tags`
- macOS Homebrew: `brew services restart ollama`
- Linux: `systemctl restart ollama`
- Or run in the foreground: `ollama serve`

**Model not found ("model gemma3:latest not found")**
```bash
ollama pull gemma3:latest
ollama list   # verify it shows
```

**First call takes >60 seconds**
- This is normal on first run after restart — the 3.3 GB model loads into RAM
- Subsequent calls should be 3–10 seconds each
- If consistently >30s after warm-up, you may be hitting swap; close other apps or use a smaller model

**Mermaid diagrams don't render**
- Open the browser console (Cmd+Option+I on Mac, F12 on Windows/Linux) — check for network errors loading `mermaid@10` from jsdelivr CDN
- If your network blocks CDNs, download `mermaid.min.js` locally and update the script URL in `app.py`

**"name 'X' is not defined" Python error**
- Make sure your virtualenv is active (`source .venv/bin/activate`)
- Reinstall deps: `pip install --upgrade -r requirements.txt`

**The UI is blank**
- Try the latest Chrome or Firefox
- Hard refresh: Cmd/Ctrl+Shift+R
- Check the terminal for stack traces from app.py

---

## Development workflow

If you want to modify Kora:

**Live reload:** Gradio auto-reloads on save when you run:
```bash
gradio app.py
```
(Use `python app.py` for the standard launch.)

**Reset your local data:**
```bash
rm kora.db
python app.py
```
The database is recreated on first run with a fresh schema.

**Edit a prompt:** the 11 prompt functions live in [`gemma.py`](./gemma.py). Each is a self-contained function that returns a typed dict — start there.

**Edit a screen:** screens live in `build_ui()` in [`app.py`](./app.py). Each `gr.Column(elem_id="screen-X")` is one screen; the `render()` function decides which one is visible based on `state["screen"]`.

---

## Going fully offline

After the initial setup (Ollama + `gemma3:latest` pulled + `pip install`), you can run Kora with no internet:

1. **One-time online prep:**
   - Download Mermaid locally: `curl -O https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js`
   - Update the script src in `app.py` from the CDN URL to a local path served by Gradio
2. **Run:** disconnect from the network, then `python app.py`. The app will work end-to-end.

---

## Tested environments

- **macOS 14 Sonoma**, Python 3.11, M-series chip — primary dev environment
- **macOS 14 Sonoma**, Python 3.14, Apple Silicon — works via venv
- **Ubuntu 22.04**, Python 3.10, x86_64 with CPU-only Ollama — works (slower inference)
- **Windows 11**, Python 3.11 — works via WSL2; native Windows should also work

If you hit issues on a different platform, [open an issue](https://github.com/ismail-najim/kora-learning-app/issues) — we'd love to know.
