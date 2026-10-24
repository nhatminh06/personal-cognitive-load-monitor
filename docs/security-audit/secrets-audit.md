# Secrets and Git-history audit

High-confidence local scans covered the working tree, tracked sensitive filename patterns and every local ref/commit for private-key headers and common AWS, GitHub, Google and Slack token forms. No match was found. Model artifacts are ignored/untracked; no environment, private-key, service-account or credential file is tracked.

Examples contain obvious local placeholders, not production credentials. `.dockerignore` excludes `.env`, `.aws`, `.codex`, `.agents`, datasets, reports and Git metadata. `.gitignore` should continue to be checked before publication because ignore rules do not protect previously tracked content.

Gitleaks was unavailable, so the history result is a targeted regex audit rather than a Gitleaks entropy/rule scan. Run pinned Gitleaks locally before publication and rotate any credential if a later scan confirms exposure; do not rewrite history without explicit authorization.
