"""Generate a local-only synthetic login credential; never reuse the Linux API key."""
import hashlib
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
target = root / ".dev.vars"
credential = root / ".local-credential"
if target.exists() or credential.exists():
    raise SystemExit("Local authentication files already exist; preserved.")
value = secrets.token_urlsafe(32)
for path, text in (
    (credential, value),
    (target, 'PUBLIC_ORIGIN="http://127.0.0.1:18787"\nOWNER_ID="synthetic-owner"\n'
     f'OWNER_CREDENTIAL_SHA256="{hashlib.sha256(value.encode()).hexdigest()}"\n'),
):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
print("Created local-only authentication files (mode 0600); values not printed.")
