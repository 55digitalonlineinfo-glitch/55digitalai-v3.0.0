# Running audits on a schedule

The toolkit doesn't ship a scheduling wizard yet — but every script is a plain command your operating system's own scheduler can call, so you don't have to type anything by hand each time. Setup is a short, one-time, manual step; the recurring runs after that are fully automatic.

## Important: what "automatic" means here

A scheduled run defaults to the same safety rule as running a command yourself: **the check/analyze phase is fully safe to automate — it only ever produces a proposed list, never writes anything.** Automating the actual write (`--confirm`) is a separate, deliberate choice you make, not the default. This matches every other write path in the toolkit: proposing and applying are never the same step.

**Recommended pattern:** schedule the check phase to run automatically and drop its output somewhere you'll see it (a file in `clients/<slug>/reports/`, or pipe it to an email/Slack webhook of your choosing). Review it on your own cadence, then run the `apply`/`--confirm` step yourself when you're ready. This gets you "I don't have to remember to run this" without "the tool can silently do something I never saw."

If you want the full pipeline — including the write — to run unattended, that's possible (every script accepts `--confirm` like any other run), but it's your call to make deliberately, with the same caution you'd apply to any unattended process touching a live account: start with a client you know well, and check its `change_log.py show <slug>` output regularly.

## macOS — launchd

Create `~/Library/LaunchAgents/com.yourteam.ppc-audit.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.yourteam.ppc-audit</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/full/path/to/55digitalai/scripts/negative_keyword_audit.py</string>
    <string>fetch</string>
    <string>your-client-slug</string>
  </array>
  <key>StartInterval</key><integer>259200</integer> <!-- every 3 days, in seconds -->
  <key>StandardOutPath</key><string>/full/path/to/55digitalai/clients/your-client-slug/reports/scheduled_check.log</string>
</dict>
</plist>
```
Load it: `launchctl load ~/Library/LaunchAgents/com.yourteam.ppc-audit.plist`

## Linux — cron

`crontab -e`, then add a line (every 3 days at 9am):
```
0 9 */3 * * cd /full/path/to/55digitalai && /usr/bin/python3 scripts/negative_keyword_audit.py fetch your-client-slug >> clients/your-client-slug/reports/scheduled_check.log 2>&1
```

## Windows — Task Scheduler

1. Open **Task Scheduler** → **Create Basic Task**
2. Trigger: Daily, recur every 3 days
3. Action: **Start a program**
   - Program: `python`
   - Arguments: `scripts\negative_keyword_audit.py fetch your-client-slug`
   - Start in: the full path to your `55digitalai` folder

## Repeating for multiple clients

Duplicate the job per client slug — there's no multi-client batch mode built in yet, so each client gets its own scheduled entry pointing at its own slug.
