# AI development tool review

Ponytail 5.3.2 and Graphify 0.9.92 are already installed locally. Both skills can direct shell/filesystem work and therefore inherit the agent's permissions; repository content can influence analysis, so approvals and workspace boundaries remain necessary. Graphify's existing graph was queried locally and no external semantic backend was enabled for this audit.

UI/UX Pro Max was **not installed**. npm registry metadata and the unpacked `ui-ux-pro-max-cli@2.15.0` tarball were inspected without execution. The package has no install/postinstall lifecycle hook and declares four small runtime dependencies. Its CLI can:

- write or replace skill files under the current project, or the home directory with `--global`;
- fetch GitHub releases and read `UI_PRO_MAX_GITHUB_TOKEN` or `GITHUB_TOKEN` for authorization;
- invoke `unzip`/PowerShell and fallback copy commands;
- recursively remove its known skill directories during uninstall;
- run a global npm update from its update command.

Conditional approval: if needed later, use the reviewed immutable package version and integrity (`2.15.0`, npm SHA-512 integrity recorded by npm), run local/non-global init in a clean diff, unset `GITHUB_TOKEN`, avoid `update` and `--global`, and review generated skills before granting shell/network access. Do not use unpinned `npx ...@latest`. Package authorship/source identity and dependency advisories were not independently cryptographically attested, so this is not unconditional approval.
