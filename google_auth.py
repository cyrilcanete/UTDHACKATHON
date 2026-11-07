"""Run interactively on the computer whose browser will complete sign-in."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRIVATE = BASE / "private"
SCOPES = ["https://www.googleapis.com/auth/calendar.events.readonly",
          "https://www.googleapis.com/auth/gmail.readonly"]

def authorize():
    from google_auth_oauthlib.flow import InstalledAppFlow
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    source = PRIVATE / "credentials.json"
    if not source.exists():
        raise SystemExit("Put your Google Desktop-app OAuth JSON in private/credentials.json first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(source), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    target = PRIVATE / "token.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(credentials.to_json())
    os.chmod(target, 0o600)
    print("Account connected. Restart the mirror. Keep private/token.json secret.")

if __name__ == "__main__":
    authorize()
