# Bulkrr Development Roadmap

Bulkrr is an early-beta, community-oriented desktop companion for Radarr and Sonarr. Its initial working foundation was developed with assistance from Claude AI and is shared so users and contributors can improve it.

**Status:** Planning only. None of the features below are claimed as implemented by this roadmap. Items are proposals, not release commitments or deadlines.

## Guiding principles

1. **Stable working beta first.** Preserve the currently functioning v1.5 beta while making improvements.
2. **Backward compatibility.** Protect existing settings, Radarr/Sonarr connections, import workflows, and user expectations.
3. **Safety by default.** Review actions before import; avoid unexpected deletion or destructive library operations.
4. **Readable, maintainable code.** Favor modular design, tests, documentation, and approachable contributions.
5. **Incremental delivery.** Develop and validate changes in branches and pull requests before merging.

## Phase 1 — Foundation and reliability

- [ ] **Modular code architecture** — Separate the user interface, API clients, settings, matching, and import logic.
- [ ] **Automated tests and GitHub CI** — Add regression tests and checks for proposed changes.
- [ ] **Better diagnostics and error recovery** — Clear errors, safe retries, and sanitized log export.
- [ ] **Dry-run mode** — Preview intended Radarr/Sonarr changes without modifying libraries.

## Phase 2 — Import workflow and user experience

- [ ] **Modernized premium interface** — Clear, consistent navigation and polished visual design.
- [ ] **Drag-and-drop title lists** — Accept supported files directly in the app.
- [ ] **CSV, TXT, and Excel imports** — Parse lists from common file formats.
- [ ] **Smart automatic matching** — Improve accuracy while retaining manual review for uncertain matches.
- [ ] **Save and resume import sessions** — Persist progress safely across restarts.
- [ ] **Advanced duplicate detection** — Recognize existing entries across identifiers, alternate titles, and editions.

## Phase 3 — Library management

- [ ] **Missing episodes and movie search** — Find and request searches for missing content in existing libraries.
- [ ] **Batch quality upgrades** — Request searches/upgrades without unexpectedly deleting media.
- [ ] **Multiple Sonarr and Radarr servers** — Configure and manage more than one instance of each service.
- [ ] **Storage estimation before import** — Estimate likely capacity needs with clear uncertainty.

## Phase 4 — Discovery and recommendations

- [ ] **Trending movies and TV** — Browse popular titles and add them to a review queue.
- [ ] **Anime discovery section** — Discover anime by relevant metadata and filters.
- [ ] **Franchise and collection imports** — Review and import titles from an entire collection.
- [ ] **Personalized recommendations** — Suggest titles based on available library information and user preferences.
- [ ] **Release calendar** — Surface upcoming releases and premieres.

## Phase 5 — Ecosystem and distribution

- [ ] **Cross-platform support** — Work toward Linux and macOS compatibility in addition to Windows.
- [ ] **Plugin or extension system** — Define safe extension points for community additions.
- [ ] **In-app update notifications** — Notify users when new releases are available.

## How to contribute

This is a **community wishlist**, not a fixed implementation schedule. Suggestions, design discussions, bug reports, documentation improvements, and pull requests are welcome.

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.
- Open an [issue](https://github.com/oriondd/Bulkrr/issues) to discuss larger features.
- Prefer focused pull requests with testing notes and no unrelated rewrites.
- Do not include API keys, private server addresses, or other sensitive information in reports or commits.

**Current released baseline:** [v1.5.0-beta](https://github.com/oriondd/Bulkrr/releases/tag/v1.5.0-beta). The roadmap does not modify that release.

**License:** [MIT](LICENSE) · **Project:** Developed by DOM
