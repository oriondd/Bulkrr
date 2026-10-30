# Phase 1: Foundation and reliability

This document describes the **unreleased development branch**, not the published v1.5 beta.

## Implemented on the development branch

- **Modularization:** `bulkrr_core.py` holds pure title parsing, matching, anime classification, and poster URL selection. `bulkrr_api.py` holds the HTTP client. `bulkrr.py` remains the PySide6 application and re-exports existing helpers for compatibility.
- **Regression tests and CI:** `tests/` contains core, API, and dry-run tests. GitHub Actions runs syntax checks and unit tests on pushes and pull requests.
- **Diagnostics and recovery:** The API client retries temporary GET failures (HTTP 429/502/503/504 and connection errors), but never automatically retries POST requests. Error messages omit server response bodies to reduce accidental secret disclosure. Existing activity logging remains available.
- **Dry-run preview:** The setup tab has an opt-in checkbox (off by default). After analyzing and approving titles, the import workflow reads current library entries and describes what it **would** add, skip, or search. It does **not** send POST requests. Disable the checkbox to perform a real import.

## Important limitations

- The graphical interface and worker are still in one large `bulkrr.py` module. Further UI/worker separation can happen incrementally once Windows behavior is validated.
- Dry-run previews depend on the current library and saved folder/profile configuration; actual imports can differ if server state changes.
- CI runs on Linux and is not a substitute for manual Windows testing.
- Redaction of server error bodies does not guarantee every log entry or screenshot is free of secrets. Review before sharing.

## Windows smoke-test checklist before merging

1. Start the app and connect to Radarr and Sonarr.
2. Confirm saved settings and API key loading still work.
3. Analyze a mixed movie/TV/anime list; inspect posters and match selection.
4. Confirm existing library titles trigger duplicate review.
5. Turn on **Dry run** in Connect & configure. Approve the import and confirm the Activity Log shows `DRY RUN` results.
6. Verify no new library entries or search commands were created on either server.
7. Turn off Dry run. Import one intentionally selected, non-duplicate test title and confirm expected behavior.
8. Confirm error messages, missing profile validation, and retry behavior are understandable.
9. Review CI results and code changes in the pull request.

Do not merge or release the branch until CI passes and Windows smoke testing is completed.
