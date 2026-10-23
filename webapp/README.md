# ProPresenter Lyrics — web interface

A browser front end for [propresenter-lyrics](https://github.com/LilySnow/propresenter-lyrics).
Users paste lyrics, optionally let Claude fix reverence pronouns and add
translations, review the result, and download a `.pro` file. They don't need to
install anything.

Building slides is free and unlimited. Only the Claude step uses your API key, and
it is protected by a password and a daily limit.

## Files

| File | Used by |
|---|---|
| `app.py` | the app itself (all hosts) |
| `requirements.txt` | Streamlit Community Cloud |
| `Dockerfile` | Hugging Face Spaces, Google Cloud Run |

`requirements.txt` and `Dockerfile` install this package from GitHub. The part
after `@` picks the branch or tag (for example `@main`, or `@web-interface` while
testing a branch).

## Settings (secrets)

| Name | Required | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | for the Claude step | Your Claude API key |
| `APP_PASSWORD` | strongly recommended | Password users need for the Claude step |
| `DAILY_LIMIT` | no (default 50) | Max Claude runs per day, shared by all users |
| `MAX_CHARS` | no (default 8000) | Max lyrics length sent to Claude |

The daily counter lives in memory, so it also resets when the app restarts. As a
hard backstop, set a monthly spend limit in the
[Claude Console](https://console.anthropic.com/settings/limits).

## Deploy on Streamlit Community Cloud (free, recommended)

1. Make sure `webapp/requirements.txt` points at the branch you deploy (see above).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and
   click **Create app**:
   - Repository: `LilySnow/propresenter-lyrics`
   - Branch: `main` (or a branch you want to test)
   - Main file path: `webapp/app.py`
3. Open **Advanced settings**, choose Python **3.11**, and paste into **Secrets**:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   APP_PASSWORD = "choose-a-password"
   # DAILY_LIMIT = "50"
   ```
4. Click **Deploy**. After a few minutes you get a `….streamlit.app` link to share.

Notes:
- The app sleeps after about 12 hours without visitors. The next visitor clicks
  a "wake up" button and waits about a minute.
- Changes pushed to the deployed branch update the app automatically. If a change
  to the package itself doesn't show up, use **Reboot app** in the app's menu.
- To change secrets later: app menu → **Settings → Secrets**.

## Deploy on Hugging Face Spaces (needs a PRO subscription)

Since July 2026, Docker Spaces on Hugging Face need a PRO subscription. Free
accounts can only host Static Spaces, and a static page can't keep your API key
secret.

1. Create a **New Space** with the **Docker → Blank** SDK.
2. Upload `Dockerfile` and `app.py`, plus a `README.md` that starts with this
   header (Hugging Face reads its settings from it):
   ```yaml
   ---
   title: ProPresenter Lyrics
   emoji: 🎵
   colorFrom: indigo
   colorTo: blue
   sdk: docker
   app_port: 7860
   license: apache-2.0
   ---
   ```
3. **Settings → Variables and secrets**: add `ANTHROPIC_API_KEY` and `APP_PASSWORD`
   as secrets.
4. To pick up a new version of the package after you push to GitHub:
   **Settings → Factory rebuild**.

## Deploy on Google Cloud Run (alternative)

The free allowance easily covers a church team, but signing up needs a credit card.

```bash
cd webapp
gcloud run deploy propresenter-lyrics --source . --region europe-west4 \
  --allow-unauthenticated --max-instances 1 \
  --set-env-vars APP_PASSWORD=choose-one,DAILY_LIMIT=50 \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest
```

Create the `anthropic-key` secret in Secret Manager first. `--max-instances 1`
keeps the daily limit exact, because each running copy of the app has its own
counter.

## Run locally

```bash
pip install -e . streamlit        # from the repository root
streamlit run webapp/app.py
```

Set `ANTHROPIC_API_KEY` (and optionally `APP_PASSWORD`) in your environment first
if you want to use the Claude step.
