# Clemailer

A local web app for triaging large Gmail emails — review, download attachments, strip them from emails, or delete messages one by one. Includes a batch mode to process everything automatically.

---

## What you need

- **Python 3.10+**
- **A `credentials.json` file** from Google — see below.

---

## Getting your credentials.json

You need to create a Google Cloud project and enable the Gmail API.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in.
2. Click the project dropdown at the top → **New Project** → give it any name → **Create**.
3. In the left menu go to **APIs & Services → Library**.
4. Search for **Gmail API**, click it, then click **Enable**.
5. Go to **APIs & Services → OAuth consent screen**.
   - Choose **External** → **Create**.
   - Fill in an app name (anything, e.g. "Clemailer") and your email for the support and developer fields.
   - Click **Save and Continue** through the rest of the screens (you don't need to add scopes manually here).
   - On the **Test users** screen, add your Gmail address, then finish.
6. Go to **APIs & Services → Credentials**.
   - Click **+ Create Credentials → OAuth client ID**.
   - Application type: **Desktop app** → name it anything → **Create**.
   - Click **Download JSON** on the confirmation dialog (or the download icon next to your new client in the list).
7. Rename the downloaded file to `credentials.json` and place it in the same folder as this README.

> Your credentials.json stays on your machine and is never uploaded anywhere

---

## Running the app

Double-click **`run.bat`**.

- The first run installs dependencies into a local `.venv` folder.
- Your browser will open automatically at `http://localhost:5000`.
- Sign in with your Google account when prompted. Google will warn that the app is unverified — click **Advanced → Go to [app name]** to proceed.

After signing in, a `token_*.json` file is saved locally so you stay logged in between sessions.

---

## What each file does

| File | Purpose |
|---|---|
| `credentials.json` | Your Google OAuth client credentials — **you provide this** |
| `token_*.json` | Your login token, created automatically on first sign-in |
| `progress_*.json` | Your email queue and decisions, saved between sessions |
| `downloads/` | Where attachments are saved (configurable in Settings) |
| `.secret_key` | Flask session key, generated automatically |

---

## Features

- **Triage view** — review emails one at a time with attachment previews
- **Actions** — download attachments, strip them from the email, trash the message or whole thread
- **Batch mode** — process all remaining emails automatically (download, strip, trash)
- **Next undecided** — jump straight to the first email that hasn't been actioned
- **Label filter** — scan a specific Gmail label/folder instead of all mail
- **Settings** — size threshold, download folder, folder structure, dry run mode

---

## Troubleshooting

**"Access blocked: App has not completed verification"** — go back to the OAuth consent screen in Google Cloud Console, make sure your Gmail is listed under Test Users, and try again.

**The app stops working after a while** — your token may have expired. Delete `token_*.json` and sign in again via the app.
