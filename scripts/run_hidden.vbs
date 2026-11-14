' 55DigitalAI — hidden-window launcher for Windows Scheduled Tasks
' =============================================================
' Purpose: Task Scheduler's own "Hidden" task property only hides the task
'          from the Task Scheduler UI list — it does NOT suppress the console
'          window of whatever the task launches. bash.exe is a console app, so
'          every 30-min poll (even the ones that immediately no-op on the
'          wrong day) flashes a visible window on the desktop otherwise. This
'          script runs the given command with WScript.Shell.Run's window
'          style 0 (hidden), which does suppress it, and waits for completion
'          so the exit code still propagates back to Task Scheduler's own
'          "Last Result" — behavior is otherwise identical to calling the
'          command directly.
'
' Usage:   wscript.exe //B run_hidden.vbs "<path to exe>" "<path to script arg>"
'          (exactly two arguments — the exe to run and the one argument to
'          pass it — matching how setup_task_scheduler.py always invokes
'          bash.exe with exactly one script path)

Set objShell = CreateObject("WScript.Shell")
Set objArgs = WScript.Arguments

exePath = objArgs(0)
scriptPath = objArgs(1)
command = """" & exePath & """ """ & scriptPath & """"

exitCode = objShell.Run(command, 0, True)
WScript.Quit(exitCode)
