---
title: ProPresenter Lyrics
emoji: 🎵
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Turn lyrics text into ProPresenter 7 (.pro) files
---

# ProPresenter Lyrics — web interface

A browser front end for [propresenter-lyrics](https://github.com/LilySnow/propresenter-lyrics):
paste lyrics, optionally let Claude fix reverence pronouns and add translations,
review, and download a `.pro` file. No installation for users.

Building slides is free and unlimited. Only the Claude step uses your API key, and it
is protected by a password and a daily limit.

## Settings (secrets)

| Name | Required | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | for the Claude step | Your Claude API key |
| `APP_PASSWORD` | strongly recommended | Password users need for the Claude step |
| `DAILY_LIMIT` | no (default 50) | Max Claude runs per day, shared by all users |
| `MAX_CHARS` | no (default 8000) | Max lyrics length sent to Claude |

The daily counter lives in memory, so it also resets when the app restarts.
As a hard backstop, set a monthly spend limit in the
[Claude Console](https://console.anthropic.com/settings/limits).

## Deploy on Hugging Face Spaces (free)

1. Sign in at huggingface.co → **New Space**. Pick a name, choose **Docker** →
   **Blank**, hardware **CPU basic (free)**, visibility **Public**.
2. In the new Space, open **Files → Add file → Upload files** and upload the three
   files from this folder: `README.md`, `Dockerfile`, `app.py`.
3. **Settings → Variables and secrets → New secret**: add `ANTHROPIC_API_KEY` and
   `APP_PASSWORD` (and optionally `DAILY_LIMIT`).
4. Wait for the build (a few minutes) and share the Space's URL.

Free Spaces go to sleep after ~48 hours without visitors; the first visit then
takes about a minute to wake up.

To pick up a new version of propresenter-lyrics after you push to GitHub:
**Settings → Factory rebuild**.

## Deploy on Google Cloud Run (alternative)

```bash
cd webapp
gcloud run deploy propresenter-lyrics --source . --region europe-west4 \
  --allow-unauthenticated \
  --set-env-vars APP_PASSWORD=choose-one,DAILY_LIMIT=50 \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest
```

(Create the `anthropic-key` secret in Secret Manager first.) Cloud Run may run
several copies of the app at once, each with its own daily counter; add
`--max-instances 1` to keep the limit exact.

## Run locally

```bash
pip install -e . streamlit        # from the repository root
streamlit run webapp/app.py
```
