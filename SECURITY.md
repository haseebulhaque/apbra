# Security and public-data policy

APBRA is a public engineering demonstration in development, not a production-assured service. Never publish real secrets or customer data in code, branches, old commits, PRs, issues, screenshots, logs, build artifacts or generated Power BI files.

## Prevent accidental publication

Use synthetic data and documented placeholders. Keep local credentials outside Git; `.gitignore` blocks common environment, key, state and database files but cannot protect a tracked file or old revision. Review `git diff --cached` before every push. Do not commit authenticated download links, signed storage URLs, raw connector responses, exported tenant credentials, tokens or full private transcripts. Public usernames, requirement IDs and access-controlled documentation links are not authentication credentials.

GitHub documents automatic free secret scanning for public repositories. Its native alert state must be checked by an authorized owner; this connection has not verified those alerts. The additional Gitleaks CLI check scans fetched history and the tracked tree, redacts findings and fails on detection or incomplete execution. No ignore baseline or broad suppression is authorized. A passing detector is not proof of the absence of every possible secret.

## Report a concern safely

Do not paste a secret into a public issue or comment. Use the repository's private security-reporting option if the owner has enabled it; otherwise contact the owner through an existing private channel. This file does not claim private reporting has been enabled. Provide affected paths/commit IDs and impact without repeating credential values.

## Respond to an actual exposure

1. Notify the owner privately and revoke or rotate the affected credential at its issuer. Treat a valid public credential as compromised; do not test it against production.
2. Remove the value from current files and replace it with a non-secret configuration reference. Check other branches, PR text, logs and artifacts.
3. Identify affected historical commits and refs. Plan any history rewrite with the owner, account for collaborators and PR references, and use GitHub's sensitive-data removal guidance. Do not force-push unrelated history just to hide a failed test.
4. Coordinate removal of cached or forked copies where possible. Deleting the latest file, closing a PR or changing visibility cannot recall existing clones or guarantee cache removal.
5. Rerun scanning, record only safe incident metadata, and add a regression control. Never declare an incident resolved merely because a current-file scan passes.

## CI boundary

Only standard GitHub-hosted ephemeral runners for public PRs. No production-connected self-hosted runner, cloud secret, privileged pull_request_target execution, deployment, automatic merge or write token for the scanner. Downloaded tooling is version/checksum pinned. Keep evidence small and retention bounded; never upload raw secret findings as a public artifact.

References:
- https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- https://github.com/gitleaks/gitleaks/blob/v8.30.1/LICENSE
