"""Run interactively on the computer whose browser will complete sign-in."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRIVATE = BASE / "private"
SCOPES = ["https://www.googleapis.com/auth/calendar.events.readonly",
          "https://www.googleapis.com/auth/gmail.readonly"]

def authorize():
    import argparse
    from app import load_config, profile_private
    from mirror_runtime import profile_config, profiles_for
    parser = argparse.ArgumentParser(description="Connect one mirror profile to Google")
    parser.add_argument("--profile", help="Profile id from config.json (defaults to first profile)")
    args = parser.parse_args()
    from google_auth_oauthlib.flow import InstalledAppFlow
    cfg = load_config()
    profile_id = args.profile or profiles_for(cfg)[0]["id"]
    cfg = profile_config(cfg, profile_id)
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    target_folder = profile_private(cfg)
    target_folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = target_folder / "credentials.json"
    if not source.exists():
        source = PRIVATE / "credentials.json"
    if not source.exists():
        raise SystemExit("Put your Google Desktop-app OAuth JSON in private/credentials.json first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(source), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    target = target_folder / "token.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(credentials.to_json())
    os.chmod(target, 0o600)
    print(f"Account connected for {profile_id}. Restart the mirror. Keep the token file secret.")

if __name__ == "__main__":
    authorize()
