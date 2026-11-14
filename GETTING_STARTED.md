# Getting Started

This guide assumes you're starting from **just a computer** — nothing installed yet. Follow it top to bottom, in order. Every step is copy-paste; you don't need to know how to code.

## What this actually is, in one paragraph

This toolkit turns [Claude Code](https://claude.com/claude-code) — an AI assistant that runs inside your editor — into a Google Ads co-pilot for your account(s). You type plain-English requests (or short commands like `/55-daily-check`) in a chat panel, and it reads your real campaign data, applies judgment using rules you write about your business, and shows you exactly what it wants to change before it ever touches your live account. Nothing writes to your Google Ads account without you explicitly approving it first.

## What you'll need, all told

- A computer (Windows or Mac)
- On Windows only: **Git for Windows** (installed in Part 1.4 below) — Claude Code needs a Unix-style shell to run commands, which Windows doesn't have on its own
- A Google Ads account you have access to
- A Claude account with a paid plan (Pro, Team, or Enterprise) — required for Claude Code
- About 30–45 minutes for the one-time setup below (most of the wait is Google approving your API access, which happens in the background over the following days — it doesn't block you from starting)

---

## Part 1 — Install the tools

### 1.1 Install Visual Studio Code

Go to **[code.visualstudio.com](https://code.visualstudio.com)**, download the installer for your operating system, and run it. Accept the defaults.

### 1.2 Install the Claude Code extension

1. Open VS Code
2. Click the **Extensions** icon on the left sidebar (or press `Cmd+Shift+X` on Mac / `Ctrl+Shift+X` on Windows)
3. Search for **"Claude Code"**
4. Click **Install** on the one published by Anthropic
5. Sign in with your Claude account when prompted

You'll now see a Claude Code panel — this is the chat interface you'll use every day once setup is done.

### 1.3 Install Python

1. Go to **[python.org/downloads](https://python.org/downloads)** and download the latest version (3.10 or newer)
2. Run the installer
   - **Windows:** make sure you check the box **"Add python.exe to PATH"** on the first install screen — easy to miss, and things won't work without it
   - **Mac:** the standard installer is fine as-is

To check it worked, open a terminal (see 1.5 below) and type `python3 --version` — it should print a version number, not an error.

### 1.4 Windows only: install Git for Windows

Skip this on Mac. Go to **[git-scm.com/downloads/win](https://git-scm.com/downloads/win)**, download the installer, and run it — the defaults are fine for every screen. This gives you **Git Bash**, which is what makes Claude Code (and the toolkit's own scripts) actually work on Windows; without it, commands that run fine on Mac will fail here.

### 1.5 Opening a terminal inside VS Code

You'll need this a few times below. In VS Code: menu bar → **Terminal → New Terminal**. A command-line panel opens at the bottom of the window — that's where you'll type the commands in this guide.

**Windows only:** click the small dropdown arrow next to the **+** in that terminal panel and choose **Git Bash** as the shell, instead of the default PowerShell/Command Prompt. If you want it to default to Git Bash every time, open Settings (`Ctrl+,`), search for `terminal.integrated.defaultProfile.windows`, and set it to `Git Bash`.

---

## Part 2 — Get the toolkit onto your computer

You'll receive a GitHub invitation by email (or a link) — click **Accept invitation**.

Then, the simplest way to get the actual files, no extra tools needed:
1. On the repository page, click the green **Code** button → **Download ZIP**
2. Extract the ZIP file somewhere you'll remember — **on Mac, avoid Desktop, Documents, Downloads, or any iCloud/Dropbox/Google Drive synced folder.** Those are gated by a macOS privacy control that silently blocks the scheduled background automation (offered later in Part 4's wizard) from reading/writing files there. Your home folder works well, e.g. extract straight to `/Users/<you>/` so you end up with `/Users/<you>/55digitalai-main`.
3. In VS Code: **File → Open Folder**, and select the extracted folder

You should now see the project's files in VS Code's sidebar (`scripts/`, `clients/`, etc.). Nothing else to do here — dependencies get installed automatically as part of Part 4.

---

## Part 3 — Get your Google API access

This is the one part that involves leaving VS Code and clicking around Google's own sites. It's a one-time setup. Google's approval step can take a few days, but everything else here is instant — start this early, then come back to Part 4 once you have your developer token.

### 3.1 Apply for a Google Ads developer token
1. Sign into your Google Ads account at **[ads.google.com](https://ads.google.com)**
2. Go to **Tools & Settings → API Center** (if you don't see this, you may need a Manager/MCC account first — Google Ads will prompt you)
3. Apply for **Basic Access** (it's free)
4. Copy your **developer token** somewhere safe — you'll paste it into the setup wizard in Part 4

### 3.2 Create a Google Cloud project and enable the right APIs
1. Go to **[console.cloud.google.com](https://console.cloud.google.com)**
2. Create a new project (top-left, any name — e.g. "My Agency PPC Tools")
3. Go to **APIs & Services → Library** and enable each of these (search the name, click Enable):
   - **Google Ads API**
   - **Google Analytics Data API**
   - **Content API for Shopping** (only needed if any client sells physical products via Shopping/PMax)
   - **Search Console API**

   **If Google asks you to set up a billing account first:** this can happen even though everything this toolkit uses stays within Google's free usage tier — Google Cloud sometimes requires a billing account linked to the project before it'll let you enable APIs at all, as an identity/anti-abuse check, not because you'll be charged. Adding a card is normal and doesn't mean you'll see charges from this.

### 3.3 Set up the OAuth consent screen
1. Still in Google Cloud Console: **APIs & Services → OAuth consent screen**
2. User type: **External** (unless you have Google Workspace, then Internal is fine)
3. Fill in the app name (anything, e.g. "My 55DigitalAI") and your email as the support contact
4. On the **Scopes** page, click **Add or remove scopes** and add these four (search each by name or paste the URL):
   - `https://www.googleapis.com/auth/adwords`
   - `https://www.googleapis.com/auth/analytics.readonly`
   - `https://www.googleapis.com/auth/content`
   - `https://www.googleapis.com/auth/webmasters.readonly`
5. Add your own Google account as a **Test User**
6. Save through the remaining screens

### 3.4 Create your OAuth credentials
1. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
2. Application type: **Desktop app**
3. Copy the **Client ID** and **Client Secret** it gives you — you'll paste these into the setup wizard too

That's everything from Google's side. Now back to VS Code.

---

## Part 4 — Run the setup wizard

In your VS Code terminal (Part 1.5), one command installs everything needed and starts the wizard:

**Mac:**
```
bash setup.sh
```
**Windows:**
```
setup.bat
```
(`bash setup.sh` works even if the file's execute permission was lost — e.g. after downloading a ZIP from GitHub, which is why `./setup.sh` alone can fail with a "permission denied" error.)

**On Mac, you may see a security warning** the first time — something like *"setup.sh cannot be opened because it is from an unidentified developer"* or *"macOS cannot verify this file is free of malware."* This is macOS's standard Gatekeeper check on any script downloaded from the internet, not specific to this toolkit. To allow it: go to **System Settings → Privacy & Security**, scroll down, and click **Allow Anyway** next to the blocked-item message, then run `bash setup.sh` again.

It will:
1. Install the Python dependencies automatically
2. Ask for the developer token, Client ID, Client Secret, and your MCC/account ID from Part 3 — customer IDs can be pasted exactly as Google Ads shows them, dashes and all, it cleans them up automatically
3. Open your browser to sign in and approve access — sign in with the Google account that manages your Ads account
   - If you see **"This app isn't verified"**, that's expected for your own app — click **Advanced → Go to [your app name]**
4. **Prove the connection actually works** by listing the real accounts it can see — you should recognize your own client names in the terminal
5. Let you pick one of those accounts and answer a few short questions (currency, monthly budget, what kind of business it is)
6. **Pull a real number for that exact client** — recent spend and active campaign count — as final proof this specific account is connected and working, not just the connection in general

When it finishes, you have one client fully set up and verified.

---

## Part 5 — Tell it about this client

In VS Code's file sidebar, open `clients/<the-slug-you-chose>/client-brief.md`. This is the single most important file for getting good results — it's how you tell the AI what's normal for this specific business: what it sells, which searches are irrelevant, who its competitors are. Fill in each section; the file has examples already in it to follow.

**Faster starting point:** the setup wizard already offered to auto-draft this from the client's website — if you said yes, it's pre-filled from their homepage instead of blank. Either way, **read it before trusting it.** It's marked as a draft at the top until you remove that marker, and it should stay a draft in your head too until someone who actually knows the business has checked every section — this file directly controls what a live audit treats as irrelevant.

---

## Part 6 — Try it

Click into the **Claude Code panel** in VS Code (from Part 1.2) and type:
```
/55-daily-check <your-client-slug>
```

This is completely read-only — it cannot change anything in your account. Claude will run the check and show you a real report: budget pacing, conversion tracking, cost anomalies.

Other things you can try the same way: `/keyword-research`, `/55-keyword-audit`, `/55-pmax-brand-generic-audit`, `/seasonality`, `/merchant-review`, `/55-merchant-policy-check`, `/55-cro-audit`, `/55-seo-audit`, `/55-web-guidelines-audit` - each one's slash command file explains what it does and asks before writing anything.

**Prefer the terminal instead of the chat panel?** Every command also works as a direct script, e.g.:
```
.venv/bin/python3 scripts/daily_check.py <your-client-slug> --pdf
```
(Always run scripts via `.venv/bin/python3`, not a bare `python3` — that's the interpreter `setup.sh`/`setup.bat` installed dependencies into, and it's what every slash command uses under the hood.)
The `--pdf` flag produces a branded PDF report you could hand to a client, saved into `clients/<slug>/reports/`.

---

## Part 7 — See everything in one place

```
.venv/bin/python3 scripts/build_dashboard.py
```
Then find `dashboard/index.html` in your file explorer (Finder on Mac, File Explorer on Windows) and double-click it — it opens directly in your regular web browser. This is a private, local page — no server, no internet connection needed — showing every client, every report, and every change the toolkit has ever made to your accounts.

Each client opens into tabs: **Overview** (status today, budget pacing, month vs. month), **Daily Check**, **Reports**, **Negatives** (every negative the audits added, plus other logged changes) and **Scripts**. The moon button switches to dark mode.

Optional extras:
- **Client logos** instead of initials: `.venv/bin/python3 scripts/fetch_client_logos.py` downloads each client's site icon to `clients/<slug>/logo.png` (or `--file <slug> path/to/logo.png` for one you saved yourself). Rebuild the dashboard afterwards.
- **Archive a client** you no longer manage: add `"archived": true` to its entry in `clients.json`. It moves to an "Archived" list in the sidebar and drops out of the totals.
- **Client report link**: add `"report_url": "https://..."` to a client in `clients.json` to show a "Monthly report" link on its page.

---

## What's safe vs. what needs care

- **Always safe, changes nothing:** `/55-daily-check`, `/keyword-research`, `/ga4-data-analyst`, `/ga4-campaign-analyst`, `/merchant-review`, `/seasonality`, `/55-feed-title-optimizer`, `/55-merchant-policy-check`, `/55-cro-audit`, `/55-seo-audit`, `/55-web-guidelines-audit` — these only ever read data (the website ones fetch public pages; they never touch the site, Merchant Center or Google Ads).
- **Can write to your account, but only with your explicit OK:** `/55-keyword-audit`, `/keyword-expansion`, `/55-pmax-brand-generic-audit`, `/55-pmax-bucketing`. Every one of these shows you the *exact* list of what it wants to change and waits for you to approve it — and even the underlying scripts refuse to write anything unless you separately pass `--confirm`. If you never say yes, nothing changes.
- Every actual change ever made is recorded — see it any time with `.venv/bin/python3 scripts/change_log.py show <client_slug>`, or in the dashboard's **Negatives** tab ("Other logged changes").

## Adding another client later

Run the wizard again — `./setup.sh` (Mac) or `setup.bat` (Windows), or directly with `.venv/bin/python3 scripts/setup_wizard.py`. It recognizes you already have credentials and skips straight to "add a client," including the real-data proof pull for the new one. When it asks for your shared negative-keyword list, paste its **name** as shown in Google Ads > Tools & Settings > Shared Library — the wizard resolves the ID for you.

## If something goes wrong

- **"Developer token not approved yet"** — normal, can take a few days. You can still do Parts 1–2 and explore while you wait; account-connecting steps just won't work until it's approved.
- **"This app isn't verified" warning** — expected for your own app, click Advanced → Go to [app name].
- **`pip3` or `python3` not recognized** — Python likely isn't on your PATH. Reinstall it and make sure the "Add to PATH" box is checked (Windows), or try `pip`/`python` without the `3`.
- **Anything else** — see `README.md` for the full technical reference of every script and its options.
