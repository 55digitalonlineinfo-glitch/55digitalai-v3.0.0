---
description: Rebuild the local dashboard and push it live to the hosted copy workers use
---

Rebuild and redeploy the dashboard (same steps the hourly automation runs).

1. Run: `bash scripts/run_dashboard_build.sh`
   - This regenerates `dashboard/index.html` from current client briefs/reports/scripts, then uploads it to Hostinger via `scripts/deploy_dashboard.sh`.
   - If `scripts/.hostinger-credentials` is missing, the deploy step skips itself silently — tell the user if that happens, since it means only the local file updated, not the hosted copy.
2. Verify the live page updated by checking the hosted dashboard URL returns `200`.
   - If credentials aren't available or the check fails, say so plainly rather than assuming success.
3. Report back briefly: confirm it rebuilt (mention client/report counts from the build output) and that the hosted copy is current.
