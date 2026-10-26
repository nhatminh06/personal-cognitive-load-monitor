# Secrets and Git-history audit

High-confidence local scans covered the working tree, tracked sensitive filename patterns and every local ref/commit for private-key headers and common AWS, GitHub, Google and Slack token forms. No match was found. Model artifacts are ignored/untracked; no environment, private-key, service-account or credential file is tracked.

Examples contain obvious local placeholders, not production credentials. `.dockerignore` excludes `.env`, `.aws`, `.codex`, `.agents`, datasets, reports and Git metadata. `.gitignore` should continue to be checked before publication because ignore rules do not protect previously tracked content.

Gitleaks 8.30.1 was checksum-verified and run against a snapshot containing only tracked working-tree files: 0 findings. Its full-history scan reported three `curl-auth-user` matches, all the literal `YOUR_STRONG_PASSWORD` documentation placeholder in commit `2a2f16b`; no revocation is required. An initial unfiltered directory scan also matched ignored Jupyter and Graphify caches, so it is not used as publication evidence.
