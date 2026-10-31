# Bulkrr 2.0 — Unified Delivery Plan

This branch combines Phase 3 (library management), Phase 4 (discovery), and Phase 5 (distribution) into **one integration cycle**. Work is staged in commits on this branch, with **one Windows acceptance test and one merge** after the entire implementation passes CI.

## Phase 3 — Library management
- Read-only missing movie and episode inventory with clear monitored and missing status
- Explicitly confirmed bulk searches and safe quality-upgrade requests
- Multiple Sonarr/Radarr server profiles and routing
- Storage estimates with assumptions shown
- Full analysis and review session persistence with schema validation

## Phase 4 — Discovery
- Trending movie and television discovery
- Anime discovery with relevant filters
- Collection/franchise batch queue
- Library-based recommendations
- Upcoming release calendar

## Phase 5 — Distribution
- Windows packaging and installable release artifacts
- In-app update notification with official release links
- Linux and macOS compatibility work and CI coverage
- Documented, versioned extension interface with safe boundaries

## Implemented in the current preview

- Missing movie/episode inventory, storage estimates, confirmed searches, and
  conservative Radarr movie upgrades only when the API explicitly reports
  that a downloaded file is below the quality cutoff.
- Named server profiles, saved review snapshots, lookup discovery, public
  AniList trending anime, local keyword-based ranking of discovered titles, and local recommendations\n  based on genre frequencies in connected libraries.
- US TVMaze episode schedule, title-based franchise candidates, declarative
  title-list extensions, update links, and Windows portable/installer previews.
- Cross-platform test matrix and an additional headless Qt startup smoke test.

## Remaining limitations before release

- Sonarr episode-level quality upgrade identification is not yet implemented.
- Trending movie/TV ranking requires a reliable live data source; title lookup
  is not presented as trending.
- Local recommendations use only genre frequencies in connected library\n  metadata; viewing history and playback activity are not collected.
- Franchise matching is title-based, not authoritative TMDB collection lookup.
- Named server profiles switch the active destination; simultaneous multi-server
  import routing is not implemented.
- CI results and the Windows installer still require verification before the
  single end-to-end acceptance test.

## Release gates
1. Unit and integration tests for new features; mocked APIs must not modify user libraries.
2. CI passing on all supported build targets.
3. Confirmed migration of existing settings, keyring entries, and Phase 2 import workflows.
4. One Windows acceptance test covering end-to-end imports, discovery, multi-server routing, and safe bulk actions.
5. Explicit user approval, followed by a **single** squash merge into main.
6. Publish v2.0.0-beta release notes and binaries only after the merge and release validation.

**Do not merge partially implemented features or claim the release is published before it exists.**
