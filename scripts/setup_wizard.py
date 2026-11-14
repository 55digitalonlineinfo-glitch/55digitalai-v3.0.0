#!/usr/bin/env python3
"""
55DigitalAI — Setup Wizard
=============================================================
Purpose  : One guided script that takes a new buyer from "just cloned the
           repo" to "first client configured and connection verified" —
           without hand-editing google-ads.yaml or clients.json directly.

           What it does, in order:
             1. Collect developer_token / client_id / client_secret / MCC id
                (skipped if google-ads.yaml already exists — see below)
             2. Run the OAuth browser flow to get a refresh_token, write google-ads.yaml
             3. Make a LIVE test call — lists the real accounts under your
                MCC, so you get proof it works, not just "no errors"
             4. Let you pick one of those accounts (or type your own), fill
                in the rest of its details, write it to clients.json, and
                scaffold clients/<slug>/ from clients/_template/ — then
                pull a real 7-day spend/campaign count for THAT account
                specifically, as final proof this exact client works.

           Re-run any time to add another client — if google-ads.yaml
           already exists, steps 1-2 are skipped and it goes straight to
           listing your existing accounts.

           Quality-of-life built in: customer IDs are accepted with or
           without dashes (auto-cleaned — the #1 copy-paste mistake),
           credential formats get a non-blocking sanity-check warning, and
           adding a customer ID that's already registered under another
           slug gets flagged before creating a duplicate.

Usage    : .venv/bin/python3 scripts/setup_wizard.py
           (or ./setup.sh / setup.bat, which also creates .venv and runs `pip install`
           into it first — every slash command in .claude/commands/ invokes
           .venv/bin/python3 directly, so scripts only work reliably from that venv)
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOOGLE_ADS_YAML = ROOT / "google-ads.yaml"
TEMPLATE_DIR = ROOT / "clients" / "_template"
BRAND_CONFIG = ROOT / "brand_config.json"

SCOPES = [
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/content",
]


def ask(prompt: str, default: str = None, required: bool = True) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{prompt}{suffix}: ").strip()
        if not val and default is not None:
            return default
        if not val and required:
            print("  (required — please enter a value)")
            continue
        return val


def ask_yesno(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    val = input(f"{prompt}{suffix}: ").strip().lower()
    if not val:
        return default
    return val.startswith("y")


def ask_digits(prompt: str, default: str = None) -> str:
    """Google Ads IDs are always shown with dashes in the UI (123-456-7890) but the
    API needs digits only — the single most common copy-paste mistake in this whole
    setup. Strip anything non-digit automatically instead of erroring on it later."""
    while True:
        raw = ask(prompt, default=default)
        digits = re.sub(r"\D", "", raw)
        if not digits:
            print("  (that didn't contain any digits — try again)")
            continue
        if digits != raw:
            print(f"  (stripped formatting -> using {digits})")
        return digits


def step(n: int, total: int, title: str) -> None:
    print(f"\n[Step {n}/{total}] {title}")
    print("-" * 40)


def _warn_if_unexpected(value: str, check, hint: str) -> None:
    if not check(value):
        print(f"  WARNING: {hint} — double check this is correct, but continuing anyway.")


# ─── step 1-3: credentials ────────────────────────────────────────────────────

def collect_credentials() -> dict:
    print("Need a developer token + OAuth client first? See google-ads.yaml.example")
    print("for links and instructions, or the fuller walkthrough in GETTING_STARTED.md.\n")

    developer_token = ask("Developer token")
    _warn_if_unexpected(developer_token, lambda v: len(v) >= 15 and " " not in v,
                        "developer tokens are usually ~22 characters with no spaces")

    client_id = ask("OAuth Client ID (ends in .apps.googleusercontent.com)")
    _warn_if_unexpected(client_id, lambda v: v.endswith(".apps.googleusercontent.com"),
                        "expected it to end in .apps.googleusercontent.com")

    client_secret = ask("OAuth Client Secret (starts with GOCSPX-)")
    _warn_if_unexpected(client_secret, lambda v: v.startswith("GOCSPX-"),
                        "expected it to start with GOCSPX-")

    login_customer_id = ask_digits("Your MCC / manager account ID (paste with or without dashes, e.g. 123-456-7890)")

    return {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "login_customer_id": login_customer_id,
    }


def run_oauth_flow(client_id: str, client_secret: str) -> str:
    from google_auth_oauthlib.flow import InstalledAppFlow

    print("\nOpening a browser to sign in with the Google account that has access")
    print("to your Google Ads MCC. If you see \"This app isn't verified\", click")
    print("Advanced -> Go to [app name] — expected for your own OAuth app.\n")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    for port in (8080, 8081, 8090, 0):  # 0 = let the OS pick any free port, last resort
        try:
            return flow.run_local_server(port=port, prompt="consent", access_type="offline").refresh_token
        except OSError as e:
            if port == 0:
                sys.exit(f"ERROR: couldn't open a local port for the OAuth callback ({e}). "
                          f"Close anything else listening on 8080/8081/8090 and try again.")
            print(f"  Port {port} is busy, trying another...")


def write_google_ads_yaml(creds: dict, refresh_token: str) -> None:
    import yaml
    data = {
        "developer_token": creds["developer_token"],
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": refresh_token,
        "login_customer_id": creds["login_customer_id"],
        "use_proto_plus": True,
    }
    GOOGLE_ADS_YAML.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    print(f"\nWrote {GOOGLE_ADS_YAML} (gitignored — never gets committed).")


# ─── step 4: live test call ───────────────────────────────────────────────────

def list_live_accounts() -> list:
    from google.ads.googleads.client import GoogleAdsClient

    print("\n=== Verifying the connection ===")
    client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = client.get_service("GoogleAdsService")
    login_customer_id = client.login_customer_id

    query = """
        SELECT customer_client.id, customer_client.descriptive_name, customer_client.status
        FROM customer_client
        WHERE customer_client.level = 1
    """
    accounts = []
    for row in ga_service.search(customer_id=login_customer_id, query=query):
        if row.customer_client.status.name != "ENABLED":
            continue
        accounts.append({
            "customer_id": str(row.customer_client.id),
            "name": row.customer_client.descriptive_name or f"(unnamed {row.customer_client.id})",
        })

    print(f"SUCCESS — found {len(accounts)} enabled account(s) under your MCC:\n")
    for i, a in enumerate(accounts, 1):
        print(f"  {i}. {a['name']}  ({a['customer_id']})")
    return accounts


# ─── step 5-6: client details + write ─────────────────────────────────────────

def find_shared_negative_list_by_name(customer_id: str, name: str) -> str:
    """Resolve a shared negative-keyword list's ID from its name, so the wizard can ask
    for the human-readable name shown in Google Ads > Tools > Shared Library instead of
    an ID nobody has memorized. Returns the ID, or raises if zero or 2+ lists match."""
    from google.ads.googleads.client import GoogleAdsClient

    client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT shared_set.id, shared_set.name
        FROM shared_set
        WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND shared_set.status = 'ENABLED'
    """
    matches = [
        str(row.shared_set.id)
        for row in ga_service.search(customer_id=customer_id, query=query)
        if row.shared_set.name.strip().lower() == name.strip().lower()
    ]
    if not matches:
        raise ValueError(f"no enabled shared negative-keyword list named '{name}' found on this account")
    if len(matches) > 1:
        raise ValueError(f"{len(matches)} shared negative-keyword lists are named '{name}' — rename one or set the ID by hand")
    return matches[0]


def prompt_client_details(accounts: list, existing_clients: dict) -> dict:
    chosen = None
    if accounts:
        choice = ask("Pick a number from the list above, or press enter to type one in manually",
                      default="", required=False)
        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            chosen = accounts[int(choice) - 1]

    name = ask("Client name", default=chosen["name"] if chosen else None)
    customer_id = ask_digits("Google Ads customer ID (paste with or without dashes)",
                              default=chosen["customer_id"] if chosen else None)

    dupe_slug = next((s for s, e in existing_clients.items() if e.get("customer_id") == customer_id), None)
    if dupe_slug and dupe_slug != "acme":
        print(f"  NOTE: customer ID {customer_id} is already registered as '{dupe_slug}' in clients.json.")
        if not ask_yesno("Add it again under a different slug anyway?", default=False):
            sys.exit("Cancelled — no changes made.")

    slug = ask("Short slug for this client (used in folder names, e.g. 'acme')",
               default=name.lower().replace(" ", "-")[:20])
    domain = ask("Website domain (e.g. acme.example)")
    country = ask("Country code (e.g. US, PL, UA)")
    timezone = ask("Timezone (e.g. America/New_York, Europe/Warsaw)")
    business_type = ask("Business type — 'lead_gen' or 'ecommerce'", default="lead_gen")
    currency = ask("Currency code (e.g. USD, PLN, UAH)", default="USD")
    monthly_budget_raw = ask("Monthly budget (numbers only, or press enter to skip)",
                              default="", required=False)
    monthly_budget = float(monthly_budget_raw) if monthly_budget_raw else None

    ga4_property_id = ask("GA4 property ID (press enter to skip, set later)", default="", required=False) or None

    negative_list_id = None
    negative_list_name = ask(
        "Shared negative-keyword list name — as shown in Google Ads > Tools & Settings > "
        "Shared Library (press enter to skip, set later)",
        default="", required=False,
    )
    if negative_list_name:
        try:
            negative_list_id = find_shared_negative_list_by_name(customer_id, negative_list_name)
            print(f"  Found it — ID {negative_list_id}.")
        except Exception as e:
            print(f"  WARNING: couldn't resolve '{negative_list_name}' to a list ID ({e}).")
            print(f"  Set negative_list_id by hand in clients.json once you've confirmed the right one.")

    merchant_center_id = None
    if business_type == "ecommerce":
        merchant_center_id = ask("Merchant Center ID (press enter to skip)", default="", required=False) or None

    return {
        "slug": slug,
        "entry": {
            "name": name, "domain": domain, "customer_id": customer_id,
            "country": country, "timezone": timezone,
            "monthly_budget": monthly_budget, "currency": currency,
            "business_type": business_type,
            "ga4_property_id": ga4_property_id,
            "negative_list_id": negative_list_id,
            "merchant_center_id": merchant_center_id,
            "pmax_branded_generic_list_id": None,
            "links": {},
        },
    }


def load_clients() -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    from client_registry import CONFIG_PATH
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}


def save_client(slug: str, entry: dict, data: dict) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from client_registry import save_clients
    if "acme" in data and slug != "acme":
        print("\nRemoving the 'acme' placeholder entry now that you have a real client.")
        del data["acme"]
    data[slug] = entry
    save_clients(data)
    print(f"Wrote '{slug}' to clients.json.")


def smoke_test_client(customer_id: str, currency: str) -> None:
    """Real proof the specific client just added actually works — not just that the
    MCC connection works in general. Pulls a real 7-day spend/campaign count."""
    from google.ads.googleads.client import GoogleAdsClient
    from datetime import date, timedelta

    client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = client.get_service("GoogleAdsService")
    date_to = date.today()
    date_from = date_to - timedelta(days=7)

    query = f"""
        SELECT campaign.id, metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    campaign_ids, cost_micros = set(), 0
    for row in ga_service.search(customer_id=customer_id, query=query):
        campaign_ids.add(row.campaign.id)
        cost_micros += row.metrics.cost_micros

    cost = cost_micros / 1_000_000
    print(f"  Pulled real data for this account: {len(campaign_ids)} campaign(s) with activity, "
          f"{cost:,.2f} {currency} spent in the last 7 days.")


def scaffold_client_folder(slug: str, name: str) -> None:
    client_dir = ROOT / "clients" / slug
    if client_dir.exists():
        print(f"clients/{slug}/ already exists — leaving it as-is.")
        return
    client_dir.mkdir(parents=True)
    template_brief = TEMPLATE_DIR / "client-brief.md"
    if template_brief.exists():
        text = template_brief.read_text(encoding="utf-8")
        text = text.replace("# Client: <Name> (<domain>)", f"# Client: {name}")
        (client_dir / "client-brief.md").write_text(text, encoding="utf-8")
    print(f"Created clients/{slug}/client-brief.md from the template — fill it in before running any audit.")


def offer_generate_brief(slug: str, name: str, domain: str, url: str) -> None:
    """Fetches url, drafts a client-brief.md with Claude, and overwrites the template
    scaffold_client_folder() just created. Reuses generate_brief.py's own functions
    rather than duplicating the fetch/prompt/Claude-call logic here."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import generate_brief

    print(f"\nFetching {url}...")
    page_texts = generate_brief.gather_page_texts([url])
    if not page_texts:
        print("  Could not fetch that URL — skipping auto-draft. Write the brief by hand instead.")
        return
    print("  Drafting with Claude (can take a minute)...")

    claude_binary = generate_brief.find_claude_binary()
    prompt = generate_brief.build_prompt(name, domain, page_texts)
    draft = generate_brief.call_claude(prompt, claude_binary)

    from datetime import datetime
    header = (
        f"<!-- DRAFT — auto-generated from {', '.join(page_texts.keys())} on {datetime.now().date()}. "
        f"Nobody who actually knows this business has reviewed this yet. Read every "
        f"section and correct it before running any audit that relies on this file. -->\n\n"
    )
    brief_path = ROOT / "clients" / slug / "client-brief.md"
    brief_path.write_text(header + draft.strip() + "\n", encoding="utf-8")
    print(f"Draft written to clients/{slug}/client-brief.md — this is a STARTING POINT, "
          f"review every section before relying on it for any real audit.")


def offer_bypass_permissions() -> None:
    """Optionally set Claude Code to skip ALL permission prompts (bash, read, edit,
    write — everything) for THIS PROJECT ONLY. Written to .claude/settings.local.json,
    not .claude/settings.json (that's committed, so it'd force this on every teammate
    who pulls the repo) and not ~/.claude/settings.json (that's machine-wide, affecting
    every other project on this computer too). settings.local.json is gitignored and
    per-person, so each person who runs this wizard opts in for their own checkout only.

    This removes every safety confirmation Claude Code normally asks before running a
    shell command or touching a file, for this project. Only enable it if you understand
    and accept that."""
    settings_path = ROOT / ".claude" / "settings.local.json"
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if existing.get("permissions", {}).get("defaultMode") == "bypassPermissions":
            print(f"\n{settings_path} already has permission prompts bypassed for this project.")
            return
    else:
        existing = {}

    print("\nOptional: let Claude Code work in this folder without asking \"is this OK?\"")
    print("every time (for example, before running a script or saving a file). This")
    print("only applies here, in this project folder — nowhere else on your computer.")
    print()
    print("Why you might want it: less clicking \"yes\" over and over while working.")
    print("If you say no: nothing bad happens — Claude Code will just keep double-")
    print("checking with you before each step in this folder, like it normally does.")
    print("(This has no effect on the Tuesday/Friday automatic checks — that's a")
    print("separate setting, up next.)")
    if not ask_yesno("Turn this on?", default=False):
        return

    existing.setdefault("permissions", {})["defaultMode"] = "bypassPermissions"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {settings_path} — permission prompts are now bypassed for this project only.")

    gitignore_path = ROOT / ".gitignore"
    if gitignore_path.exists():
        gitignore_text = gitignore_path.read_text(encoding="utf-8")
        if ".claude/settings.local.json" not in gitignore_text:
            with gitignore_path.open("a", encoding="utf-8") as f:
                f.write("\n# Personal Claude Code overrides — not shared with the team\n.claude/settings.local.json\n")
            print(f"Added .claude/settings.local.json to {gitignore_path} (personal, never committed).")


def _add_to_user_path_windows(directory: Path) -> bool:
    """Persist `directory` on the current user's PATH via the registry and broadcast
    WM_SETTINGCHANGE, so a newly opened terminal picks it up without a full logoff.
    setx isn't used here — it silently truncates PATH at 1024 chars. Returns False
    (non-fatal — caller falls back to telling the user to add it by hand) on any
    failure, e.g. no registry access."""
    try:
        import winreg
        import ctypes

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            try:
                current, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current = ""
            parts = [p for p in current.split(";") if p]
            if str(directory) in parts:
                return True
            parts.append(str(directory))
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
        finally:
            winreg.CloseKey(key)

        HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x1A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0, 5000, None
        )
        return True
    except Exception:
        return False


def ensure_claude_cli() -> None:
    """Install the Claude CLI automatically if it's missing — no prompt. This is
    just getting the binary onto the machine (harmless, doesn't change any
    permission/trust behavior), needed by an unattended scheduled audit
    (clients/<slug>/scripts/run_audit.sh on macOS via launchd, or the
    Windows Task Scheduler equivalent) to run headless.

    Covers macOS (native curl|bash installer feeding launchd) and Windows
    (native irm|iex installer feeding Task Scheduler). Linux is left alone —
    no scheduled-automation path targets it yet, so there's nothing for the
    binary to feed."""
    import shutil
    import subprocess

    if sys.platform == "darwin":
        claude_bin = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
        if shutil.which("claude") or Path(claude_bin).exists():
            return
        print("\nInstalling the Claude CLI (curl -fsSL https://claude.ai/install.sh | bash)...")
        result = subprocess.run("curl -fsSL https://claude.ai/install.sh | bash", shell=True)
        if result.returncode != 0:
            print("  WARNING: installer failed — install it yourself later: https://claude.ai/install.sh")
        else:
            print("  Claude CLI installed.")
        return

    if sys.platform == "win32":
        if shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe"):
            return

        local_bin = Path.home() / ".local" / "bin"
        already_installed = (local_bin / "claude.exe").exists()

        if not already_installed:
            print("\nInstalling the Claude CLI (irm https://claude.ai/install.ps1 | iex)...")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "irm https://claude.ai/install.ps1 | iex"],
            )
            if result.returncode != 0:
                print("  WARNING: installer failed — install it yourself later: https://claude.ai/install.ps1")
                return
            print("  Claude CLI installed.")

        # The native installer drops the binary in ~/.local/bin but doesn't reliably
        # get it onto PATH in the same session — fix that here instead of sending the
        # user to System Properties by hand.
        if (local_bin / "claude.exe").exists():
            if _add_to_user_path_windows(local_bin):
                print(f"  Added {local_bin} to your PATH — open a NEW terminal window for it to take effect.")
            else:
                print(f"  WARNING: couldn't update PATH automatically. Add it by hand: System Properties -> "
                      f"Environment Variables -> Edit User PATH -> New -> {local_bin}")

        print("  Run `claude login` once yourself (interactive OAuth) before any scheduled task tries to use it headlessly.")
        return


def ensure_daily_check_automation() -> None:
    """Install/refresh the hourly all-clients daily-check job automatically — no
    prompt. Unlike the negative-keyword automation, this is safe to default on:
    daily_check.py is pure read-only Python (no Claude, no live writes), so there's
    no per-client consent decision to make, just a convenience to turn on. Re-running
    this (e.g. after adding a new client) refreshes the job so it covers everyone
    currently in clients.json.

    macOS (launchd) and Windows (Task Scheduler) only. On Linux, see
    SCHEDULING.md's cron section for the manual equivalent."""
    if sys.platform == "darwin":
        script, args = "setup_launchd.py", ["--only", "daily-checks"]
    elif sys.platform == "win32":
        script, args = "setup_task_scheduler.py", ["--only", "daily-checks"]
    else:
        return

    import subprocess

    print("\nSetting up the hourly all-clients daily-check (read-only, no approval needed)...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print(f"  WARNING: could not install the daily-check job — run manually later:")
        print(f"  python3 scripts/{script} --only daily-checks")


def offer_scheduled_automation_setup() -> None:
    """Optionally mark this workspace as trusted in ~/.claude.json — the remaining
    prerequisite (beyond google-ads.yaml/.venv, already handled above, and the Claude
    CLI binary itself, installed automatically by ensure_claude_cli()) that an
    unattended scheduled audit (launchd on macOS, Task Scheduler on Windows) needs
    to run headless with `claude -p ... --dangerously-skip-permissions`. Without
    this flag, a headless run silently ignores .claude/settings.json's permissions
    instead of erroring loudly. Kept opt-in (unlike the CLI install) because it's
    what actually lets an unattended session skip permission checks on this
    workspace.

    macOS and Windows only — those are the two platforms with a scheduled-audit
    path (see ensure_claude_cli()). Skip if you only plan to use interactive slash
    commands, or don't use scheduled audits yet."""
    if sys.platform not in ("darwin", "win32"):
        return

    print("\nOptional: prepare this computer so the automatic negative-keyword checks")
    print("can run properly on their own schedule (e.g. every Tuesday and Friday),")
    print("with nobody at the keyboard. Only relevant if you're using that automatic")
    print("scheduling feature — skip if you're only running checks yourself, by hand.")
    print()
    print("Why you might want it: without this, the automatic runs still happen, but")
    print("they may log an extra warning message each time instead of running cleanly.")
    print("If you say no: nothing breaks today — you can turn this on later by running")
    print("this setup again whenever you actually start using the automatic schedule.")
    if not ask_yesno("Turn this on?", default=False):
        return

    import subprocess

    print("  Checking Claude CLI auth...")
    if sys.platform == "darwin":
        auth_check = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials"],
            capture_output=True,
        )
        authenticated = auth_check.returncode == 0
    else:
        authenticated = (Path.home() / ".claude" / ".credentials.json").exists()
    if not authenticated:
        print("  Not authenticated yet — run `claude login` yourself once (interactive")
        print("  browser sign-in) before any scheduled job will work.")
    else:
        print("  Already authenticated.")

    claude_json_path = Path.home() / ".claude.json"
    if claude_json_path.exists():
        try:
            data = json.loads(claude_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    projects = data.setdefault("projects", {})
    # Claude Code normalizes project keys to forward slashes even on Windows —
    # str(ROOT) there is backslash-separated and silently fails to match.
    root_str = str(ROOT).replace("\\", "/") if sys.platform == "win32" else str(ROOT)
    if projects.get(root_str, {}).get("hasTrustDialogAccepted"):
        print(f"  {root_str} already marked trusted.")
    else:
        projects.setdefault(root_str, {})["hasTrustDialogAccepted"] = True
        claude_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"  Marked {root_str} as trusted in {claude_json_path}.")


def configure_brand() -> None:
    """One-time agency branding for client-facing PDFs/GA4 dashboards. Repo-wide
    (not per-client), so skip silently on re-runs once brand_config.json exists —
    see scripts/brand.py for how it's consumed."""
    if BRAND_CONFIG.exists():
        return

    print("\n[Optional] Agency branding")
    print("-" * 40)
    print("Sets the agency name/colors shown on every client-facing PDF and GA4 dashboard —")
    print("a one-time, repo-wide setting. Edit brand_config.json by hand later to change it.")
    if not ask_yesno("Configure it now?", default=True):
        return

    agency_name = ask("Agency name (shown on every report)", default="Your Agency Name")
    primary = ask("Primary color (hex)", default="#07153F")
    _warn_if_unexpected(primary, lambda v: re.fullmatch(r"#[0-9A-Fa-f]{6}", v) is not None,
                         "expected a 6-digit hex color like #07153F")
    accent = ask("Accent color (hex)", default="#3E5CE7")
    _warn_if_unexpected(accent, lambda v: re.fullmatch(r"#[0-9A-Fa-f]{6}", v) is not None,
                         "expected a 6-digit hex color like #3E5CE7")
    logo_path = ask("Logo file path (optional, leave blank to skip)", default="", required=False)

    config = {
        "agency_name": agency_name,
        "logo_path": logo_path or None,
        "colors": {
            "primary": primary, "accent": accent, "accent_alt": accent,
            "secondary": "#444751", "text": "#6F7176", "bg_light": "#F4F7FC", "white": "#FFFFFF",
            "pass": "#1E8E3E", "pass_bg": "#E6F4EA", "fail": "#D93025", "fail_bg": "#FCE8E6",
            "warn": "#F9AB00", "warn_bg": "#FEF7E0", "na": "#9AA0A6", "na_bg": "#F1F3F4",
        },
    }
    BRAND_CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"  Saved -> {BRAND_CONFIG}")


def main():
    from check_safe_location import check as check_safe_location

    if not check_safe_location():
        sys.exit(1)

    print("=" * 60)
    print("  55DigitalAI — Setup Wizard")
    print("=" * 60)

    from check_license import check_license

    print("\nEnter your license key (from your purchase confirmation).")
    while True:
        key = ask("License key")
        ok, message = check_license(key)
        if ok:
            if message != "license valid":
                print(f"  {message}")
            break
        print(f"  {message} — check the key and try again, or contact the seller if this seems wrong.")

    ensure_claude_cli()

    total_steps = 4
    need_credentials = True

    if GOOGLE_ADS_YAML.exists():
        print(f"\n{GOOGLE_ADS_YAML} already exists.")
        need_credentials = not ask_yesno("Keep existing credentials and just add a client?", default=True)

    if need_credentials:
        step(1, total_steps, "Google Ads API credentials")
        creds = collect_credentials()
        step(2, total_steps, "Sign in with Google")
        refresh_token = run_oauth_flow(creds["client_id"], creds["client_secret"])
        write_google_ads_yaml(creds, refresh_token)
    else:
        print("\n[Steps 1-2/4] Skipped — using existing credentials.")

    step(3, total_steps, "Verifying the connection")
    try:
        accounts = list_live_accounts()
    except Exception as e:
        print(f"\nWARNING: couldn't list accounts ({e})")
        print("You can still add a client manually — just double check your credentials after.")
        accounts = []

    step(4, total_steps, "Add a client")
    existing_clients = load_clients()
    details = prompt_client_details(accounts, existing_clients)
    save_client(details["slug"], details["entry"], existing_clients)
    scaffold_client_folder(details["slug"], details["entry"]["name"])

    domain = details["entry"]["domain"]
    if domain:
        try:
            offer_generate_brief(details["slug"], details["entry"]["name"], details["entry"]["domain"], f"https://{domain}")
            ask(
                "Press enter once you've read the draft above and corrected anything "
                "wrong — every real audit depends on this brief being accurate",
                default="", required=False,
            )
        except Exception as e:
            print(f"  WARNING: couldn't auto-draft the brief ({e}) — fill in clients/{details['slug']}/client-brief.md by hand instead.")
    else:
        print(f"\nNo domain on file for this client — fill in clients/{details['slug']}/client-brief.md by hand.")

    print("\nDouble-checking that specific client's data pulls correctly...")
    try:
        smoke_test_client(details["entry"]["customer_id"], details["entry"]["currency"])
    except Exception as e:
        print(f"  WARNING: couldn't pull live data for this client yet ({e})")
        print("  This can happen if the account has no recent activity, or if the signed-in")
        print("  Google account doesn't have access to it yet — check Access and Security")
        print("  in the Google Ads UI for this specific account.")

    configure_brand()
    offer_bypass_permissions()
    offer_scheduled_automation_setup()
    ensure_daily_check_automation()

    print("\n" + "=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print(f"Next steps:")
    print(f"  1. Edit clients/{details['slug']}/client-brief.md")
    print(f"  2. Try it: .venv/bin/python3 scripts/daily_check.py {details['slug']}")
    print(f"  3. Run this wizard again any time to add another client.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled — nothing was changed beyond what was already confirmed above.")
        sys.exit(1)
