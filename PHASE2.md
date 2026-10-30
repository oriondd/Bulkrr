# Phase 2 development acceptance checklist

This document applies to the **feature/phase2-import-experience** branch only. The v1.5 beta release and `main` remain unchanged until explicit approval.

## Running from source (Windows)

```powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
.\\.venv\\Scripts\\python.exe bulkrr.py
```

## Acceptance scenarios

1. Open the application and confirm the updated dark styling and the Import & review tab display correctly.
2. Drop a UTF-8 TXT file with two lines into the title box. Confirm two separate lines appear. Import a CSV with `title,type,year` columns and confirm prefixes and years are preserved.
3. Save a title list, clear the input, then load it. **Sessions currently restore title input only**, not previously approved matches. Reanalyze after loading.
4. Connect Radarr/Sonarr, analyze a small mix of movie, TV, and anime titles, and inspect match confidence, posters, and the review counters.
5. Confirm an ambiguous match manually; check that duplicates require an explicit action and that changing a duplicate's metadata match requires reanalysis.
6. Choose Skip for an existing title and confirm it is not submitted. Try Upgrade/Search and Replace/Search Again with **dry run enabled** first. Both actions request a search and do not delete files; they are not distinct deletion/replacement mechanisms.
7. Run a small **dry run** first, confirm that no library entries change, then explicitly approve a real import of a safe test title.
8. Verify that errors for one title do not stop the rest of the import batch, and check the Activity log for useful details.

## Release gate

- Run the unit and GUI smoke tests on Python 3.12.
- Confirm GitHub Actions checks pass (or document why CI is unavailable).
- Complete the Windows acceptance scenarios above.
- Review any reported failures and fix them before merging.
- **Do not merge the draft PR or publish a release without approval.**
