#!/usr/bin/env python3
"""Checks a buyer's license key against the license server (license-server/
check.php on 55digital.online). Called from setup_wizard.py.

Fails OPEN on network/server errors — a website hiccup shouldn't block a
paying buyer's setup, only a confirmed-invalid key should. This is a soft
deterrent against casual key-sharing, not hard DRM; see license-server/README.md
for the full reasoning."""
import json
import ssl
import urllib.error
import urllib.request

LICENSE_CHECK_URL = "https://55digital.online/license/check.php"

try:
    # Some Python installs (notably python.org's on macOS) don't wire up the
    # system CA trust store for urllib, causing CERTIFICATE_VERIFY_FAILED on
    # every HTTPS request. certifi ships transitively via requests/google-auth
    # (both toolkit dependencies), so it's reliably present — use its bundle
    # explicitly instead of assuming urllib's default context works.
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None


def check_license(key: str, url: str = LICENSE_CHECK_URL) -> tuple[bool, str]:
    """Returns (ok_to_proceed, message). ok_to_proceed is True both when the
    key is genuinely valid AND when the check itself couldn't be performed —
    only a confirmed "invalid" response blocks setup."""
    key = key.strip()
    if not key:
        return False, "no license key entered"

    data = json.dumps({"license_key": key}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return True, f"couldn't reach the license server ({e}) — proceeding anyway"

    if body.get("valid"):
        return True, "license valid"
    return False, body.get("message", "license invalid")
