# Contributing to r-offcall

Thank you for considering a contribution.

## Before opening a pull request

1. Describe the problem and intended behavior in an issue when the change is not trivial.
2. Keep changes scoped: do not mix a feature, formatting sweep, and dependency upgrade in one pull request.
3. Preserve the local-network and privacy boundary documented in the README.
4. Do not add secrets, private certificates, recordings, or real participant data to the repository.

## Local setup and checks

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/verify.py
```

For UI edits, also verify that the JavaScript in `src/ui/index.html` parses and test the affected flow on the relevant platform.

## Pull request expectations

- Explain the user-facing result and any platform-specific effect.
- Add or update deterministic verification where practical.
- Update all three README files when behavior, requirements, or limitations change.
- State clearly which platforms you tested: macOS, Windows, Linux, and/or browser.

## Licensing note

The project has no public open-source license yet. Do not submit third-party code or assets unless you have permission for the project owner to use them.
