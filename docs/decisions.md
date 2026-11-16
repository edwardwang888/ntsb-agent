# Decision Log

One entry per meaningful design choice. Newest at the bottom.

Template:

## YYYY-MM-DD — <decision title>
- **Decision:**
- **Alternatives considered:**
- **Why:**
- **Revisit when:**

---

## 2026-11-16 — Secret scanning with gitleaks in CI
- **Decision:** A GitHub Actions workflow (`.github/workflows/secret-scan.yml`) runs `gitleaks/gitleaks-action` on every push and pull request, scanning each commit in the range rather than only the final tree.
- **Alternatives considered:** A local pre-commit hook (catches a secret before it ever leaves the machine, but needs the `pre-commit` tool installed on every clone and can be skipped with `--no-verify`); TruffleHog (verifies live keys against provider APIs, heavier and noisier for a small repo); relying on GitHub's built-in push protection alone (only covers partner-registered token formats).
- **Why:** CI can't be skipped and needs nothing installed locally. Scanning per commit matters because a key added and then deleted is still in history. No new Python dependency.
- **Revisit when:** A secret slips through (add a pre-commit hook for earlier blocking), we get false positives (add a `.gitleaks.toml` allowlist), or the repo moves under a GitHub organization (the action then needs a free `GITLEAKS_LICENSE` key).
