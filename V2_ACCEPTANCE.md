# Bulkrr 2.0 unified Windows acceptance checklist

This is **one acceptance pass** for the combined Phase 3–5 development branch.
Do not merge or publish the v2.0.0-beta release until the tester approves it.

## Obtain the test build

Open the latest successful **Bulkrr Windows preview build** GitHub Actions run
on `feature/v2-unified-roadmap`. Download its
`Bulkrr-2.0-Windows-preview` artifact, unzip the complete directory, and
launch `Bulkrr-2.0-preview.exe`. Keep the folder intact. The separate `Bulkrr-2.0-Windows-installer-preview` artifact can also be used to test installation and removal.

The preview is not signed and is not a public release. The existing v1.5
release remains unaffected.

## Acceptance run

1. **Connection and settings:** Connect to Sonarr and Radarr. Save settings,
   restart the app, and confirm URLs, profiles and root folders are retained.
   Verify API keys are not written into `settings.json`.
2. **Multiple instances:** Add an additional server profile, restart, select
   it, and test the connection. Verify the active server's folder/profile
   choices refresh and imports target only the chosen instance.
3. **Library inventory:** Scan libraries. Check missing-movie and missing-show
   counts against Sonarr/Radarr. Adjust average storage assumptions. Try a
   disconnected scan to confirm the button recovers after an error. Inspect below-cutoff Radarr movie candidates.
4. **Search actions:** Select a missing movie or show and explicitly approve
   the search. Confirm the expected search command appears in the relevant
   server's activity. Avoid testing large batches first.
5. **Discovery:** Search movie, TV, and anime titles. Queue selections and
   confirm they enter the normal review workflow without automatic import.
   Search a franchise and inspect unrelated candidate filtering. Load trending anime from AniList and rank results using interest keywords. Test TMDB trending movies and TV using a temporary API read access token, and confirm cancellation makes no network request. Scan your library and rank discovered titles by its common genres. Confirm no automatic imports occur.
6. **Release calendar:** Load today's US TV schedule. Confirm the UI remains
   responsive if the network is unavailable.
7. **Session recovery:** Save a review snapshot, reopen it, and confirm live
   reanalysis is required before import. Ensure no API key is in the snapshot.
8. **Extensions:** Create a schema-1 JSON title list in the extensions folder,
   load it, and confirm its entries require normal review.
9. **Updates:** Check for updates; ensure only official GitHub links are
   offered and no automatic installer runs.
10. **Installer:** Test setup, launch, uninstall, and preservation of user configuration outside the application folder.
11. **Regression:** Paste and import a small mixed title list, check duplicate
    handling, CSV/TXT drag-and-drop, and confirm log messages are useful.
12. **Platform checks:** Confirm Windows/macOS/Linux CI test matrix passes.
    Linux/macOS UI smoke testing may require separate testers.

Record any failures with exact steps and a redacted screenshot or log excerpt.
After the full acceptance pass, request explicit approval before merging to
`main` and creating `v2.0.0-beta`.
