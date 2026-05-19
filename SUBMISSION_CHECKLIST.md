# Kaggle Submission Checklist — Kora

**Deadline:** 2026-05-18 11:59 PM UTC

---

## 1. GitHub Repo (do first — everything else links here)

```bash
cd "/Users/ismailn/Downloads/Claude Workspace/kora"
git init
git add database.py gemma.py scheduler.py app.py styles.css requirements.txt README.md KAGGLE_WRITEUP.md VIDEO_SCRIPT.md
echo "kora.db" > .gitignore
echo "__pycache__/" >> .gitignore
echo ".DS_Store" >> .gitignore
git add .gitignore
git commit -m "Initial commit: Kora — adaptive learning on Gemma 4"

# Create the public GitHub repo (or do via web UI)
gh repo create kora --public --source=. --remote=origin --push
```

If `gh` isn't installed: create the repo at github.com/new (name it `kora`, public), then:
```bash
git remote add origin https://github.com/YOUR_USERNAME/kora.git
git branch -M main
git push -u origin main
```

**Verify the repo shows README on the landing page and that the code is browsable without login.**

---

## 2. Live Demo

Three options ranked by effort:

### Option A — Hugging Face Spaces (recommended, free, public)
```bash
pip install huggingface_hub
huggingface-cli login
huggingface-cli repo create kora --type space --space_sdk gradio
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/kora
git push hf main
```
**Caveat:** Spaces doesn't run Ollama. You'll need to either:
- Add a `gemma_call()` fallback that uses the Hugging Face Inference API (free tier) when Ollama isn't reachable, OR
- Record a video and link to it as the "live demo" since the judges need an offline-capable demo anyway.

### Option B — Loom or YouTube screen recording (simplest)
If a real live demo isn't reachable, attach a **second YouTube video** showing a full live session. Mark it clearly: *"Live walkthrough — Kora running locally on a MacBook Air, airplane mode on."* Link this as the "Live Demo" attachment.

### Option C — Cloudflare Tunnel (your local Mac, exposed)
```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:7860
```
Get a `*.trycloudflare.com` URL. Keep your laptop running during judging. Risky but works.

**Recommended:** Option B. Judges expect a usable demo; a clean recorded walkthrough is more reliable than a tunnel.

---

## 3. The Video (most important deliverable)

Follow `VIDEO_SCRIPT.md`. Concrete steps:

1. **Record screen** — Cmd+Shift+5 → "Record Selected Portion" → frame the Kora window at 1080p. Record one continuous run-through of the full user journey (4–5 min raw).
2. **Record voiceover** — separately, in a quiet room, reading the script. Phone Voice Memos with EarPods is fine.
3. **Edit** — DaVinci Resolve (free) or CapCut. Cut the screen recording to match script timing, layer voiceover, drop in subtle music at -18dB.
4. **Export** — 1080p, H.264, MP4.
5. **Upload to YouTube** — set to **Unlisted** (publicly viewable with the link, but not searchable) OR **Public** if you want max exposure. Title: *"Kora — Adaptive Learning on Gemma 4 (Gemma 4 Good Hackathon)"*. Add the GitHub link in the description.

---

## 4. Cover Image / Media Gallery

You need at least one cover image. Easy version:

1. Open the app at full screen on the home page
2. Cmd+Shift+4 → spacebar → click the window → saves a clean screenshot
3. Crop to 16:9 (1920x1080) — keep the hero headline visible and centred
4. Save as `kora-cover.png`

**Bonus screenshots** (drop these into the Media Gallery for context):
- Home screen
- A teach screen with the Mermaid diagram rendered
- The activation feedback screen showing honest grading
- The session review with Gemma's adaptation message

---

## 5. Kaggle Writeup

1. Go to the competition page → **"New Writeup"**
2. Title: **Kora — Learn Anything. Adapted to You. Fully Offline.**
3. Subtitle: **An on-device adaptive learning app powered entirely by Gemma 4. One model. Eleven roles. Zero cloud.**
4. **Tracks**: tick Main + Future of Education + Digital Equity
5. **Body**: copy/paste from `KAGGLE_WRITEUP.md` (Markdown supported)
6. **Attachments → Project Links**:
   - GitHub: your repo URL
   - Live Demo: YouTube unlisted link (or HF Space URL)
7. **Media Gallery**:
   - Upload `kora-cover.png` (set as cover)
   - Upload the 3-min YouTube video URL
   - Upload additional screenshots
8. **Save** → review → click **Submit** in the top right

---

## Day-Of Sanity Check (60 minutes before deadline)

- [ ] GitHub repo is public — open in incognito to confirm
- [ ] README renders on the GitHub landing page
- [ ] `requirements.txt` works: fresh `pip install -r requirements.txt` succeeds
- [ ] Run `python app.py` from a clean checkout and walk through one topic
- [ ] YouTube video is publicly accessible (open incognito)
- [ ] Writeup body is under 1,500 words (`wc -w KAGGLE_WRITEUP.md` reports 1328)
- [ ] All three tracks ticked
- [ ] Cover image is set
- [ ] Click **Submit** (not just Save)

---

## After Submission

You can edit and re-submit unlimited times before the deadline. Don't be afraid to fix typos in the writeup or replace the cover image after submitting.
