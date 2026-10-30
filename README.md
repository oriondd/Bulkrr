<div align="center">

# Bulkrr

**Bulk import movies, TV shows, and anime into Radarr and Sonarr — with a preview before you commit.**

A Windows desktop companion for organizing large media wish lists, reviewing title matches, and avoiding duplicate library entries.

**Developed by DOM**

[**Download latest beta**](https://github.com/oriondd/Bulkrr/releases/latest) · [**v1.5 beta release**](https://github.com/oriondd/Bulkrr/releases/tag/v1.5.0-beta) · [**Report an issue**](https://github.com/oriondd/Bulkrr/issues)

</div>

> [!IMPORTANT]
> **Beta software:** Bulkrr is under active development. Review matches and destinations carefully before importing. Test with a small batch first.

## What is Bulkrr?

Bulkrr helps you paste a list of titles, look up matching metadata through your own Radarr and Sonarr instances, and review the results before adding them. It is designed for people who manage large movie, television, and anime libraries and want more visibility than a one-title-at-a-time workflow.

## Project origins and community goal

**Transparency:** Bulkrr was initially created with the help of Claude AI. It began as a practical way to solve a problem with bulk-adding titles to Radarr and Sonarr, rather than as a polished, production-ready software project.

The goal is to share a **working, barebones foundation** that anyone can use, inspect, improve, and build upon. The current beta is a starting point, not a finished product. Code cleanup, bug fixes, testing, documentation, accessibility improvements, and new features are all welcome.

You don't need to be an expert to contribute. If you spot something that could be clearer, safer, or easier to use, please [open an issue](https://github.com/oriondd/Bulkrr/issues) or read the [contribution guidelines](CONTRIBUTING.md) to submit a pull request. Bulkrr is available under the [MIT License](LICENSE).

## Features

- **Bulk title analysis:** Paste multiple titles in one batch, including `movie:`, `tv:`, and `anime:` prefixes.
- **Review before import:** Inspect matched names, years, media types, destinations, and quality profiles before approving additions.
- **Artwork and descriptions:** See cover art and available synopsis information to help confirm matches.
- **Duplicate detection:** Check whether titles already exist in your connected Radarr or Sonarr library, including available file or episode information.
- **Existing-title choices:** Skip an entry or request a new search. The current **Replace / Search Again** action does **not** delete existing files.
- **Status lights:** Green for ready/success, yellow for review, red for existing media/errors, and blue while processing. Read the accompanying details to distinguish different red states.
- **Activity log:** Timestamped diagnostic information for analysis and import activity.
- **Personalized setup:** Configure Radarr/Sonarr endpoints, root folders, quality profiles, and search preferences.
- **Custom branding:** Bulkrr application icon and startup splash screen.

## Download and install

**Current beta:** [Bulkrr v1.5.0-beta](https://github.com/oriondd/Bulkrr/releases/tag/v1.5.0-beta)

1. Open the release page above and download the **Windows installer ZIP** from **Assets**.
2. Extract the entire ZIP to a folder.
3. Run **`Install Bulkrr.bat`** from the extracted folder.
4. Follow the installer prompts, then launch Bulkrr using its desktop shortcut.
5. In Bulkrr, enter your **own** Radarr and/or Sonarr server URL and API key, select your root folders and quality profiles, and test the connections.

**Requirements:** Windows 10 or 11, network access to your Radarr and/or Sonarr instance, and internet access during initial installation if dependencies must be installed. The current beta installer may install Python and required packages; it is **not yet** a self-contained Windows executable.

> [!NOTE]
> Only download Bulkrr from this repository's official Releases page. If Windows displays a security warning, verify the source before proceeding. This beta is not presented as a digitally signed application.

## Quick start

Paste a batch such as:

```text
movie: Dredd (2012)
movie: The Raid (2011)
tv: Severance (2022)
anime: 91 Days (2016)
```

1. Click **Analyze Titles**.
2. Review each match, poster, destination, and status light.
3. Confirm or change uncertain matches.
4. For titles already in your library, choose whether to skip or request a new search.
5. Approve the import only after the results look correct.
6. Open **Activity Log** if you need to troubleshoot.

Bulkrr requests searches from Radarr/Sonarr according to your selected settings; it does not directly download media files itself.

## Understanding status indicators

| Light | Meaning |
| --- | --- |
| 🟢 Green | Ready to import or successfully processed |
| 🟡 Yellow | Needs review or exists in the library without detected media |
| 🔴 Red | Existing downloaded media or an error — check the details |
| 🔵 Blue | Currently analyzing or importing |

**Safety:** Analysis should not delete files. The beta's **Replace / Search Again** option triggers a search request; it does not erase existing media. Review all actions carefully, particularly when working with a large library.

## Screenshots

_Add screenshots of the Bulk Import tab, poster preview, duplicate detection dialog, and Activity Log here._

For example, after adding an image at `docs/screenshots/bulk-import.png`, include:

```markdown
![Bulkrr bulk import screen](docs/screenshots/bulk-import.png)
```

## Privacy and security

- Connect Bulkrr only to Radarr/Sonarr servers you own or are authorized to manage.
- **Never** post API keys, passwords, private server URLs, or configuration files in GitHub issues or screenshots.
- Keep remote services protected with HTTPS and appropriate access controls.
- Bulkrr is a management interface for Radarr/Sonarr, not a media host or content provider.

## Bugs and feedback

Found a bug or have an idea? [Open a GitHub issue](https://github.com/oriondd/Bulkrr/issues) and include:

- Bulkrr version and Windows version
- Whether you were using Radarr or Sonarr
- Steps to reproduce the problem
- Expected versus actual behavior
- A screenshot or relevant **redacted** Activity Log excerpt

Please remove API keys, credentials, and identifying server information before posting logs.

## Project status

**v1.5.0-beta** — Early public beta. Features, behavior, and installation may change as testing continues.

## License

Bulkrr is open source under the [MIT License](LICENSE). Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

<div align="center">

**Bulkrr · Developed by DOM**

*Independent community project. Not affiliated with or endorsed by Radarr or Sonarr.*

</div>
