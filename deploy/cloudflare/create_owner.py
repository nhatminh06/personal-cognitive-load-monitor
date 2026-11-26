"""Prepare a new production-only owner credential locally, without publishing or printing it."""
import hashlib
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
paths = (root / ".owner-credential", root / ".owner-credential.sha256")
if any(path.exists() for path in paths):
    raise SystemExit("Owner credential files already exist; preserved.")
credential = secrets.token_urlsafe(32)
for path, value in zip(paths, (credential, hashlib.sha256(credential.encode()).hexdigest())):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(value)
print("Created owner credential and hash files (0600); save the credential privately in a password manager.")
