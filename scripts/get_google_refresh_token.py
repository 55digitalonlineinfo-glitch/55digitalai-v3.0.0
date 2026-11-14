import argparse
import os
import re
import requests
import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/content",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

def main():
    parser = argparse.ArgumentParser(description="Get a new Google OAuth refresh token for this toolkit.")
    parser.add_argument("--save", action="store_true",
                         help="Write the new refresh_token into google-ads.yaml, replacing the current one "
                              "for every client/script in the toolkit. Off by default — requires explicit opt-in.")
    args = parser.parse_args()

    # Read client_id and client_secret from google-ads.yaml
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "google-ads.yaml")
    with open(yaml_path) as f:
        raw_yaml = f.read()
        config = yaml.safe_load(raw_yaml)

    client_config = {
        "installed": {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=8080, prompt='consent', access_type='offline')

    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {credentials.token}"},
    ).json()

    print("\n" + "="*40)
    print("SUCCESS: REFRESH TOKEN OBTAINED")
    print("="*40)
    print(f"\nSigned in as: {userinfo.get('email', '(email not returned)')}")
    print(f"\nYour Refresh Token is:\n\n{credentials.refresh_token}\n")
    print("="*40)
    print("This token covers adwords + analytics.readonly + webmasters.readonly + content scopes.")

    if args.save:
        new_yaml, n = re.subn(
            r"^refresh_token:.*$",
            f"refresh_token: {credentials.refresh_token}",
            raw_yaml, count=1, flags=re.MULTILINE,
        )
        if n == 0:
            print("\nCould not find a `refresh_token:` line in google-ads.yaml — not saved. Paste it in by hand.")
        else:
            with open(yaml_path, "w") as f:
                f.write(new_yaml)
            print(f"\nSaved — google-ads.yaml now authenticates as {userinfo.get('email', '(unknown)')} for every client/script.")
    else:
        print("Nothing was saved automatically — this refresh token is NOT written to google-ads.yaml.")
        print("Re-run with --save if you actually want to swap the account this whole toolkit")
        print("authenticates as (it's shared across every client, not just this lookup).")

if __name__ == "__main__":
    main()