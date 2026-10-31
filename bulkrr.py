import sys, json, re, os, difflib, urllib.request, urllib.parse, urllib.error, datetime, traceback, logging, copy
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPixmap,
    QPainter,
    QRadialGradient,
    QPen,
    QIcon,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QTabWidget,
    QGroupBox,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QSplashScreen,
    QFileDialog,
    QInputDialog,
)

from bulkrr_paths import config_dir

ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APPDIR = config_dir()
SETTINGS = APPDIR / "settings.json"
APPDIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(APPDIR / "bulkrr.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)


# Preserve the public helper name for compatibility.
from bulkrr_api import get_json


# Re-export these helpers for compatibility with existing integrations.
from bulkrr_core import title_parts, similarity, candidate_score, classify, poster_url
from bulkrr_imports import normalize_titles, read_source, save_session, load_session
from bulkrr_review import review_summary, STATUS_LABELS, match_confidence
from bulkrr_theme import DARK_THEME
from bulkrr_library import missing_movies, missing_series, upgrade_movies
from bulkrr_bulk import plan_searches, plan_episode_searches, estimate_storage
from bulkrr_discovery import normalize_discovery, queue_lines, upcoming
from bulkrr_trending import fetch_trending_anime
from bulkrr_tmdb import fetch_trending, fetch_new_releases, fetch_collection, search_collections
from bulkrr_recommendations import rank_candidates
from bulkrr_genres import favorite_genres
from bulkrr_settings import write_settings
from bulkrr_servers import validate_profiles, legacy_profiles, route_to_profiles, check_routed_libraries, plan_routed_imports, prepare_routed_import_batches, preview_routed_import_batches, execute_routed_adds
from bulkrr_updates import fetch_latest_release, update_available
from bulkrr_sessions import save_review, load_review
from bulkrr_calendar import fetch_schedule
from bulkrr_collections import expand_collection
from bulkrr_extensions import discover_manifests


class PosterWorker(QThread):
    loaded = Signal(str, bytes, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            request = urllib.request.Request(
                self.url, headers={"User-Agent": "Bulkrr/1.5"}
            )
            with urllib.request.urlopen(request, timeout=12) as resp:
                if (
                    resp.headers.get("Content-Length")
                    and int(resp.headers["Content-Length"]) > 4_000_000
                ):
                    raise ValueError("Poster exceeds 4 MB")
                data = resp.read(4_000_001)
                if len(data) > 4_000_000:
                    raise ValueError("Poster exceeds 4 MB")
            self.loaded.emit(self.url, data, "")
        except Exception as exc:
            self.loaded.emit(self.url, b"", str(exc))


class Worker(QThread):
    progress = Signal(str)
    row_progress = Signal(int, str, str)
    finished_data = Signal(object)
    failed = Signal(str)

    def __init__(self, task, connections, items=None, config=None):
        super().__init__()
        self.task = task
        self.connections = connections
        self.items = items or []
        self.config = config or {}
        self._stop_after_current = False

    def request_stop_after_current(self):
        """Cooperative cancellation: allow the current API lookup to finish."""
        self._stop_after_current = True

    def call(self, app, path, method="GET", payload=None):
        c = self.connections[app]
        self.progress.emit(f"API {app.title()}: {method} /api/v3/{path.split('?')[0]}")
        try:
            result = get_json(c["url"], c["key"], path, method, payload)
            self.progress.emit(f"API {app.title()}: {method} completed successfully")
            return result
        except Exception as exc:
            self.progress.emit(
                f"API {app.title()}: {method} failed — {type(exc).__name__}: {exc}"
            )
            raise

    def run(self):
        try:
            if self.task == "check_updates":
                self.finished_data.emit(fetch_latest_release())
            elif self.task == "connect":
                result = {}
                for app in ("radarr", "sonarr"):
                    c = self.connections.get(app, {})
                    if not c.get("url") or not c.get("key"):
                        continue
                    self.progress.emit(f"Connecting to {app.title()}...")
                    info = self.call(app, "system/status")
                    roots = self.call(app, "rootfolder")
                    profiles = self.call(app, "qualityprofile")
                    result[app] = {
                        "version": info.get("version", "?"),
                        "roots": roots,
                        "profiles": profiles,
                    }
                    self.progress.emit(
                        f"{app.title()} connected (v{info.get('version','?')})."
                    )
                self.finished_data.emit(result)
            elif self.task == "collection_lookup":
                if "radarr" not in self.connections:
                    raise ValueError("Connect to Radarr to expand a movie franchise")
                term = urllib.parse.quote(self.config["term"])
                matches = self.call("radarr", f"movie/lookup?term={term}")
                self.finished_data.emit(expand_collection(matches[:100]))
            elif self.task == "trending_anime":
                self.finished_data.emit(fetch_trending_anime())
            elif self.task == "trending_tmdb":
                self.finished_data.emit(fetch_trending(self.config["kind"], self.config["access_token"], window=self.config.get("window", "week")))
            elif self.task == "new_releases_tmdb":
                self.finished_data.emit(fetch_new_releases(
                    self.config["kind"], self.config["access_token"]
                ))
            elif self.task == "tmdb_collection":
                self.finished_data.emit(fetch_collection(self.config["collection_id"], self.config["access_token"]))
            elif self.task == "tmdb_collection_search":
                self.finished_data.emit(search_collections(self.config["term"], self.config["access_token"]))
            elif self.task == "release_calendar":
                self.finished_data.emit(fetch_schedule())
            elif self.task == "discover":
                kind = self.config["kind"]
                app = "radarr" if kind == "movie" else "sonarr"
                if app not in self.connections:
                    raise ValueError(f"Connect to {app.title()} to discover {kind} titles")
                endpoint = "movie" if app == "radarr" else "series"
                term = urllib.parse.quote(self.config["term"])
                records = self.call(app, f"{endpoint}/lookup?term={term}")
                self.finished_data.emit(normalize_discovery(records[:100], kind))
            elif self.task == "bulk_search":
                result = {"queued": 0, "errors": []}
                for app in ("radarr", "sonarr"):
                    for payload in plan_searches(app, self.config.get(app, [])):
                        try:
                            self.call(app, "command", "POST", payload)
                            result["queued"] += 1
                        except Exception as exc:
                            result["errors"].append(f"{app.title()}: {exc}")
                self.finished_data.emit(result)
            elif self.task in ("routed_import_preview", "routed_import_execute"):
                batches = self.config["batches"]
                credentials = self.config["credentials"]
                def fetch(profile):
                    key = credentials.get(profile["id"])
                    if not key:
                        raise ValueError("Missing destination API key")
                    return get_json(profile["url"], key,
                                    "movie" if profile["kind"] == "radarr" else "series")
                if self.task == "routed_import_preview":
                    self.finished_data.emit(preview_routed_import_batches(batches, fetch))
                else:
                    def add(profile, endpoint, payload):
                        key = credentials.get(profile["id"])
                        if not key:
                            raise ValueError("Missing destination API key")
                        return get_json(profile["url"], key, endpoint, "POST", payload)
                    self.finished_data.emit(execute_routed_adds(
                        batches, fetch, add, approved=self.config.get("approved") is True,
                        search=self.config.get("search") is True))
            elif self.task == "routed_library_check":
                routes = self.config.get("routes", [])
                credentials = self.config.get("credentials", {})
                def fetch_profile_library(profile):
                    key = credentials.get(profile["id"])
                    if not isinstance(key, str) or not key:
                        raise ValueError("Missing API key for selected profile")
                    endpoint = "movie" if profile["kind"] == "radarr" else "series"
                    self.progress.emit(f"Checking {profile['label']} ({profile['kind']}) library")
                    return get_json(profile["url"], key, endpoint)
                self.finished_data.emit(check_routed_libraries(routes, fetch_profile_library))
            elif self.task == "episode_upgrade_search":
                ids = self.config.get("episode_ids", [])
                if "sonarr" not in self.connections or not isinstance(ids, list) or not ids or len(ids) > 500 or any(type(i) is not int or i <= 0 for i in ids):
                    raise ValueError("Invalid Sonarr episode search request")
                self.call("sonarr", "command", "POST", {"name": "EpisodeSearch", "episodeIds": ids})
                self.finished_data.emit({"queued": 1, "errors": []})
            elif self.task == "episode_upgrade_preview":
                if "sonarr" not in self.connections:
                    raise ValueError("Connect to Sonarr first")
                ids = self.config.get("series_ids", [])
                if not isinstance(ids, list) or not ids or len(ids) > 100 or any(type(i) is not int or i <= 0 for i in ids):
                    raise ValueError("Select 1–100 valid Sonarr series")
                episodes = []
                for series_id in dict.fromkeys(ids):
                    records = self.call("sonarr", f"episode?seriesId={series_id}&includeEpisodeFile=true")
                    if not isinstance(records, list):
                        raise ValueError("Sonarr returned invalid episode data")
                    episodes.extend(records)
                    if len(episodes) > 5000:
                        raise ValueError("Preview limited to 5000 episodes")
                self.finished_data.emit(plan_episode_searches(episodes))
            elif self.task == "library_scan":
                result = {"movies": [], "series": [], "upgrades": [], "genres": [], "errors": []}
                library_movies = []
                library_series = []
                if "radarr" in self.connections:
                    try:
                        movies = self.call("radarr", "movie")
                        library_movies = movies
                        result["movies"] = missing_movies(movies)
                        result["upgrades"] = upgrade_movies(movies)
                    except Exception as exc:
                        result["errors"].append(f"Radarr: {exc}")
                if "sonarr" in self.connections:
                    try:
                        library_series = self.call("sonarr", "series")
                        result["series"] = missing_series(library_series)
                    except Exception as exc:
                        result["errors"].append(f"Sonarr: {exc}")
                result["genres"] = favorite_genres(library_movies, library_series)
                self.finished_data.emit(result)
            elif self.task == "analyze":
                out = []
                library = {}
                for app, endpoint in (("radarr", "movie"), ("sonarr", "series")):
                    if app in self.connections:
                        try:
                            entries = self.call(app, endpoint)
                            key = "tmdbId" if app == "radarr" else "tvdbId"
                            library[app] = {
                                str(e.get(key)): e for e in entries if e.get(key)
                            }
                            self.progress.emit(
                                f"Library scan: {app.title()} has {len(entries)} entries"
                            )
                        except Exception as exc:
                            library[app] = None
                            self.progress.emit(
                                f"WARNING: {app.title()} library scan failed: {exc}; duplicate checks unavailable"
                            )
                for i, line in enumerate(self.items, 1):
                    if self._stop_after_current:
                        self.progress.emit(f"Analysis stopped after {len(out)} of {len(self.items)} titles")
                        break
                    hint, title, year = title_parts(line)
                    self.progress.emit(
                        f"[{i}/{len(self.items)}] Searching metadata: {title} (requested year: {year or 'unspecified'}, category: {hint or 'auto'})"
                    )
                    self.row_progress.emit(
                        i - 1, "working", "Searching Radarr/Sonarr metadata..."
                    )
                    if not title:
                        continue
                    apps = (
                        [("radarr", "movie")]
                        if hint == "movie"
                        else (
                            [("sonarr", "series")]
                            if hint in ("tv", "anime")
                            else [
                                (a, "movie" if a == "radarr" else "series")
                                for a in ("radarr", "sonarr")
                                if a in self.connections
                            ]
                        )
                    )
                    matches = []
                    for app, kind in apps:
                        if app not in self.connections:
                            continue
                        try:
                            endpoint = f"{kind}/lookup?term=" + urllib.parse.quote(
                                title
                            )
                            for obj in self.call(app, endpoint)[:12]:
                                if not obj.get("title"):
                                    continue
                                score = candidate_score(title, year, obj)
                                if score < 0.60:
                                    continue
                                cat = "movie" if app == "radarr" else classify(obj)
                                if hint in ("tv", "anime"):
                                    cat = hint
                                ident = (
                                    obj.get("tmdbId")
                                    if app == "radarr"
                                    else obj.get("tvdbId")
                                )
                                if not ident:
                                    continue
                                matches.append(
                                    {
                                        "app": app,
                                        "type": cat,
                                        "data": obj,
                                        "score": score,
                                        "id": ident,
                                        "label": f'{obj["title"]} ({obj.get("year") or "?"}) [{cat}]',
                                    }
                                )
                        except Exception as e:
                            self.progress.emit(
                                f"  {app.title()} lookup error for {title}: {e}"
                            )
                    unique = {}
                    for m in matches:
                        k = (m["app"], m["id"])
                        if k not in unique or m["score"] > unique[k]["score"]:
                            unique[k] = m
                    matches = sorted(
                        unique.values(), key=lambda x: x["score"], reverse=True
                    )[:10]
                    top = matches[0] if matches else None
                    ambiguous = (
                        (
                            len(matches) > 1
                            and matches[1]["score"] >= top["score"] - 0.09
                        )
                        if top
                        else False
                    )
                    safe = bool(
                        top
                        and top["score"] >= 0.96
                        and not ambiguous
                        and (hint or top["app"] == "radarr" and len(matches) == 1)
                    )
                    if (
                        year
                        and top
                        and top["data"].get("year")
                        and abs(year - int(top["data"]["year"])) > 1
                    ):
                        safe = False
                    # For unprefixed titles, do not auto-approve category, even with an exact title match.
                    if not hint:
                        safe = False
                    existing = (
                        library.get(top["app"], {}).get(str(top["id"]))
                        if top and library.get(top["app"]) is not None
                        else None
                    )
                    duplicate = None
                    if existing:
                        if top["app"] == "radarr":
                            files = int(
                                bool(
                                    existing.get("hasFile") or existing.get("movieFile")
                                )
                            )
                            total = 1
                        else:
                            stats = existing.get("statistics") or {}
                            files = int(stats.get("episodeFileCount") or 0)
                            total = int(stats.get("totalEpisodeCount") or 0)
                        duplicate = {
                            "existing_id": existing.get("id"),
                            "files": files,
                            "total": total,
                            "app": top["app"],
                            "title": existing.get("title", top["data"].get("title")),
                        }
                    state = "ready" if safe else ("review" if top else "error")
                    message = (
                        "High-confidence match"
                        if safe
                        else (
                            "Confirm title and category"
                            if top
                            else "No matching title found"
                        )
                    )
                    if duplicate:
                        state = "duplicate" if duplicate["files"] else "review"
                        message = (
                            (
                                f"Already downloaded: {duplicate['files']}"
                                + (
                                    f"/{duplicate['total']} episodes"
                                    if top["app"] == "sonarr" and duplicate["total"]
                                    else " file(s)"
                                )
                            )
                            if duplicate["files"]
                            else "Already added; no files detected — choose action"
                        )
                    elif top and library.get(top["app"]) is None:
                        state = "review"
                        message = "Library check unavailable; verify existing titles before import"
                    out.append(
                        {
                            "input": line,
                            "matches": matches,
                            "selected": 0 if top else -1,
                            "status": state,
                            "message": message,
                            "duplicate": duplicate,
                            "action": "skip" if duplicate else "add",
                        }
                    )
                    self.progress.emit(
                        f"  {'Ready' if safe else 'Review' if top else 'Not found'}: {title}; candidates={len(matches)}; best={top['label'] if top else 'none'}"
                    )
                    self.row_progress.emit(i - 1, out[-1]["status"], out[-1]["message"])
                if self._stop_after_current:
                    for line in self.items[len(out):]:
                        out.append({"input": line, "matches": [], "selected": -1,
                                    "status": "skipped", "message": "Analysis stopped before lookup",
                                    "action": "skip"})
                self.finished_data.emit(out)
            elif self.task == "import":
                results = []
                # Cache a library snapshot per destination for this batch.
                existing_by_app = {}
                added_in_batch = set()
                for i, item in enumerate(self.items, 1):
                    m = item["matches"][item["selected"]]
                    app = m["app"]
                    typ = m["type"]
                    obj = dict(m["data"])
                    self.progress.emit(
                        f"[{i}/{len(self.items)}] Checking {obj['title']} in {app.title()} (metadata ID {m['id']}, type {typ})..."
                    )
                    self.row_progress.emit(
                        i - 1,
                        "working",
                        "Checking for existing library entry...",
                    )
                    endpoint = "movie" if app == "radarr" else "series"
                    try:
                        if app not in existing_by_app:
                            library = self.call(app, endpoint)
                            if (
                                not isinstance(library, list)
                                or any(not isinstance(entry, dict) for entry in library)
                            ):
                                raise ValueError(
                                    f"{app.title()} returned an invalid library listing"
                                )
                            existing_by_app[app] = library
                        existing = existing_by_app[app]
                    except Exception as exc:
                        results.append((item["input"], "red", f"Library check failed: {exc}"))
                        self.progress.emit(f"  Could not verify {obj['title']} in {app.title()}: {exc}")
                        continue
                    identifier = "tmdbId" if app == "radarr" else "tvdbId"
                    found = next(
                        (x for x in existing if str(x.get(identifier)) == str(m["id"])),
                        None,
                    )
                    if self.config.get("dry_run", False):
                        action = item.get("action", "skip") if found else "add"
                        if found and action not in ("skip", "upgrade", "replace"):
                            results.append(
                                (item["input"], "red", "Unknown duplicate action")
                            )
                            continue
                        if not found:
                            folder = self.config.get(f"{typ}_folder")
                            profile = self.config.get(f"{app}_profile")
                            if folder is None or folder == "" or profile is None or profile == "":
                                results.append(
                                    (
                                        item["input"],
                                        "red",
                                        "Missing root folder or quality profile",
                                    )
                                )
                                continue
                            try:
                                if isinstance(profile, bool) or (
                                    isinstance(profile, float) and not profile.is_integer()
                                ):
                                    raise ValueError("quality profile must be an integer")
                                profile_id = int(profile)
                                if profile_id <= 0:
                                    raise ValueError("quality profile must be positive")
                            except (TypeError, ValueError, OverflowError):
                                results.append(
                                    (item["input"], "red", "Invalid quality profile ID")
                                )
                                continue
                            if not isinstance(folder, str) or not folder.strip():
                                results.append(
                                    (item["input"], "red", "Invalid root folder path")
                                )
                                continue
                            description = f"Would add to {app.title()} in {folder.strip()} (quality profile {profile_id})"
                        elif action == "skip":
                            description = "Would skip existing library title"
                        elif not self.config.get("search", True):
                            description = (
                                "Would leave existing title unchanged (search disabled)"
                            )
                        else:
                            description = "Would request search for existing title (files retained)"
                        self.progress.emit(f"DRY RUN: {obj['title']}: {description}")
                        results.append(
                            (item["input"], "green", "DRY RUN: " + description)
                        )
                        continue
                    if (app, str(m["id"])) in added_in_batch:
                        results.append((item["input"], "green", "Skipped existing library title"))
                        self.progress.emit(f"  Skipped title already added in this batch: {obj['title']}")
                        continue
                    if found:
                        action = item.get("action", "skip")
                        if action not in ("skip", "upgrade", "replace"):
                            results.append(
                                (item["input"], "red", "Unknown duplicate action")
                            )
                            self.progress.emit(
                                f"  Refused unsafe duplicate action for {obj['title']}: {action!r}"
                            )
                            continue
                        if action == "skip":
                            results.append(
                                (
                                    item["input"],
                                    "green",
                                    "Skipped existing library title",
                                )
                            )
                            self.progress.emit(
                                f"  Skipped existing title: {obj['title']}"
                            )
                            continue
                        if action in ("upgrade", "replace"):
                            if not self.config.get("search", True):
                                results.append(
                                    (
                                        item["input"],
                                        "green",
                                        "Already added; search disabled in preferences",
                                    )
                                )
                                continue
                            existing_id = found.get("id")
                            if (
                                isinstance(existing_id, bool)
                                or not isinstance(existing_id, int)
                                or existing_id <= 0
                            ):
                                results.append(
                                    (item["input"], "red", "Invalid existing library ID; search not submitted")
                                )
                                continue
                            try:
                                if app == "radarr":
                                    self.call(
                                        app,
                                        "command",
                                        "POST",
                                        {
                                            "name": "MoviesSearch",
                                            "movieIds": [found["id"]],
                                        },
                                    )
                                else:
                                    self.call(
                                        app,
                                        "command",
                                        "POST",
                                        {
                                            "name": "SeriesSearch",
                                            "seriesId": found["id"],
                                        },
                                    )
                                results.append(
                                    (
                                        item["input"],
                                        "green",
                                        "Replacement search queued; existing files retained",
                                    )
                                )
                                self.progress.emit(
                                    f"  Requested replacement/upgrade search for {obj['title']}; existing files preserved"
                                )
                            except Exception as exc:
                                results.append(
                                    (
                                        item["input"],
                                        "red",
                                        f"Search request failed: {exc}",
                                    )
                                )
                            continue
                        results.append(
                            (item["input"], "red", "Unknown duplicate action")
                        )
                        continue
                    folder = self.config.get(f"{typ}_folder")
                    profile = self.config.get(f"{app}_profile")
                    if folder is None or folder == "" or profile is None or profile == "":
                        results.append(
                            (
                                item["input"],
                                "red",
                                "Missing root folder or quality profile",
                            )
                        )
                        continue
                    try:
                        if isinstance(profile, bool) or (
                            isinstance(profile, float) and not profile.is_integer()
                        ):
                            raise ValueError("quality profile must be an integer")
                        profile_id = int(profile)
                        if profile_id <= 0:
                            raise ValueError("quality profile must be positive")
                    except (TypeError, ValueError, OverflowError):
                        results.append(
                            (item["input"], "red", "Invalid quality profile ID")
                        )
                        continue
                    if not isinstance(folder, str) or not folder.strip():
                        results.append(
                            (item["input"], "red", "Invalid root folder path")
                        )
                        continue
                    obj["rootFolderPath"] = folder.strip()
                    obj["qualityProfileId"] = profile_id
                    obj["monitored"] = True
                    obj["addOptions"] = (
                        {"searchForMovie": bool(self.config.get("search", True))}
                        if app == "radarr"
                        else {
                            "searchForMissingEpisodes": bool(
                                self.config.get("search", True)
                            )
                        }
                    )
                    if app == "sonarr":
                        obj["seriesType"] = "anime" if typ == "anime" else "standard"
                        obj["seasonFolder"] = True
                    self.progress.emit(
                        f"  Adding {obj['title']} to {folder}; quality profile ID={profile}; search after approval={self.config.get('search',True)}"
                    )
                    self.row_progress.emit(
                        i - 1,
                        "working",
                        "Submitting to " + app.title() + "...",
                    )
                    try:
                        added = self.call(app, endpoint, "POST", obj)
                        added_in_batch.add((app, str(m["id"])))
                        # Keep the cached snapshot current after additions.
                        if (
                            isinstance(added, dict)
                            and str(added.get(identifier, "")) == str(m["id"])
                        ):
                            existing_by_app[app].append(added)
                        else:
                            # An incomplete API response cannot safely prove
                            # what was added. Refresh before the next title.
                            existing_by_app.pop(app, None)
                        results.append(
                            (
                                item["input"],
                                "green",
                                (
                                    "Added; search requested"
                                    if self.config.get("search", True)
                                    else "Added; search disabled"
                                ),
                            )
                        )
                        self.progress.emit(
                            f"  Added successfully: {obj['title']}; search request={'enabled' if self.config.get('search',True) else 'disabled'}"
                        )
                        self.row_progress.emit(
                            i - 1, "done", "Added successfully"
                        )
                    except Exception as e:
                        results.append((item["input"], "red", str(e)[:300]))
                        self.progress.emit(f"  Failed: {obj['title']} — {e}")
                        self.row_progress.emit(
                            i - 1, "failed", str(e)[:180]
                        )
                self.finished_data.emit(results)
        except Exception as e:
            logging.exception("Worker failure task=%s", self.task)
            self.failed.emit(f"{type(e).__name__}: {e}")


class StatusLED(QWidget):
    """Accessible, compact LED with a subtle processing pulse."""

    COLORS = {
        "working": "#53A9FF",
        "skipped": "#8292A9",
        "ready": "#35D883",
        "done": "#35D883",
        "review": "#F5C451",
        "duplicate": "#F16A70",
        "error": "#F16A70",
        "failed": "#F16A70",
        "connected": "#35D883",
        "unconfigured": "#F5C451",
        "disconnected": "#F16A70",
    }
    NAMES = {
        "working": "Processing",
        "ready": "Ready",
        "done": "Added successfully",
        "review": "Needs confirmation",
        "error": "Not found",
        "failed": "Failed",
        "connected": "Connected",
        "unconfigured": "Not configured",
        "disconnected": "Connection failed",
    }

    def __init__(self, status="unconfigured", parent=None):
        super().__init__(parent)
        self.status = status
        self.phase = 0
        self.setFixedSize(32, 30)
        self.setToolTip(self.NAMES.get(status, status))
        self.setAccessibleName(self.NAMES.get(status, status))
        self.timer = QTimer(self)
        self.timer.setInterval(85)
        self.timer.timeout.connect(self.tick)
        self.update_animation()

    def set_status(self, status, detail=""):
        self.status = status
        label = self.NAMES.get(status, status)
        self.setToolTip(label + (": " + detail if detail else ""))
        self.setAccessibleName(label)
        self.update_animation()
        self.update()

    def update_animation(self):
        if self.status == "working":
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def tick(self):
        self.phase = (self.phase + 1) % 30
        self.update()

    def paintEvent(self, event):
        from math import sin, pi

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self.COLORS.get(self.status, "#8292A9"))
        strength = (
            0.68 + 0.32 * (0.5 + 0.5 * sin(self.phase * 2 * pi / 30))
            if self.status == "working"
            else 1.0
        )
        glow = QRadialGradient(16, 15, 15)
        g = QColor(c)
        g.setAlpha(int(105 * strength))
        glow.setColorAt(0, g)
        g.setAlpha(int(42 * strength))
        glow.setColorAt(0.48, g)
        g.setAlpha(0)
        glow.setColorAt(1, g)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(1, 0, 30, 30)
        c.setAlpha(int(255 * strength))
        painter.setBrush(c)
        painter.setPen(QPen(QColor("#dbe5f0"), 0.65))
        painter.drawEllipse(11, 10, 10, 10)
        painter.end()


class TitleInput(QTextEdit):
    """Text input accepting TXT and CSV drops; delegates file handling to Main."""

    files_dropped = Signal(list)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if urls and all(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (".txt", ".csv") for url in urls):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if urls and all(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (".txt", ".csv") for url in urls):
            self.files_dropped.emit([url.toLocalFile() for url in urls])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bulkrr — 2.0 development preview")
        icon_path = ASSET_DIR / "Bulkrr.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1120, 800)
        self.connections = {}
        self.server_data = {}
        self.items = []
        self.worker = None
        self.poster_cache = {}
        self.poster_workers = []
        self.poster_inflight = {}
        self.poster_pending = []
        self.poster_target = None
        self.settings = self.load_settings()
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(14, 10, 14, 10)
        shell_layout.setSpacing(10)
        header = QWidget()
        header.setObjectName("appHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 9, 16, 9)
        branding = QVBoxLayout()
        title = QLabel("Bulkrr")
        title.setObjectName("appTitle")
        branding.addWidget(title)
        subtitle = QLabel("v2.0 preview  •  Analyze, review, then approve")
        subtitle.setObjectName("appSubtitle")
        branding.addWidget(subtitle)
        header_layout.addLayout(branding)
        header_layout.addStretch()
        self.header_status = QLabel("●  Connect Radarr / Sonarr to begin")
        self.header_status.setObjectName("appSubtitle")
        header_layout.addWidget(self.header_status)
        shell_layout.addWidget(header)
        workspace = QHBoxLayout()
        workspace.setSpacing(12)
        self.navigation = QListWidget()
        self.navigation.setObjectName("mainNavigation")
        self.navigation.setMinimumWidth(172)
        self.navigation.setMaximumWidth(220)
        self.navigation.setSpacing(3)
        self.navigation.addItems(["Dashboard", "Import & Review", "Discover", "Library", "Connections", "Activity Log"])
        self.navigation.setToolTip("Choose a workspace. Import & Review is the primary workflow.")
        workspace.addWidget(self.navigation)
        tabs = QTabWidget()
        tabs.setObjectName("workspaceTabs")
        tabs.tabBar().hide()
        workspace.addWidget(tabs, 1)
        shell_layout.addLayout(workspace, 1)
        self._navigation_to_tab = [0, 2, 4, 3, 1, 5]
        self.navigation.currentRowChanged.connect(
            lambda row: tabs.setCurrentIndex(self._navigation_to_tab[row]) if 0 <= row < len(self._navigation_to_tab) else None
        )
        tabs.currentChanged.connect(
            lambda index: self.navigation.setCurrentRow(self._navigation_to_tab.index(index))
            if index in self._navigation_to_tab else None
        )
        self.setCentralWidget(shell)
        setup = QWidget()
        self.setup_layout = QVBoxLayout(setup)
        self.url = {}
        self.key = {}
        self.connection_labels = {}
        self.connection_leds = {}
        for app, default in (
            ("radarr", "http://localhost:7878"),
            ("sonarr", "http://localhost:8989"),
        ):
            group = QGroupBox(app.title())
            form = QFormLayout(group)
            self.url[app] = QLineEdit(self.settings.get(app + "_url", default))
            self.key[app] = QLineEdit()
            self.key[app].setEchoMode(QLineEdit.EchoMode.Password)
            self.key[app].setPlaceholderText(
                "API key (stored in your OS keyring when available)"
            )
            try:
                import keyring

                self.key[app].setText(keyring.get_password("Bulkrr", app) or "")
            except Exception:
                pass
            self.connection_labels[app] = QLabel("Not tested")
            self.connection_leds[app] = StatusLED("unconfigured")
            status_box = QWidget()
            status_row = QHBoxLayout(status_box)
            status_row.setContentsMargins(0, 0, 0, 0)
            status_row.setSpacing(4)
            status_row.addWidget(self.connection_leds[app])
            status_row.addWidget(self.connection_labels[app])
            status_row.addStretch()
            form.addRow("Server URL", self.url[app])
            form.addRow("API key", self.key[app])
            form.addRow("Status", status_box)
            self.setup_layout.addWidget(group)
        try:
            self.extra_profiles = validate_profiles(self.settings.get("extra_profiles", []))
        except ValueError:
            self.extra_profiles = []
        self.extra_connections = {}
        extra_row = QHBoxLayout()
        self.extra_list = QListWidget()
        self.extra_list.setMaximumHeight(100)
        self.refresh_extra_list()
        extra_row.addWidget(self.extra_list)
        extra_buttons = QVBoxLayout()
        add_extra = QPushButton("Add another server")
        add_extra.clicked.connect(self.add_extra_server)
        extra_buttons.addWidget(add_extra)
        remove_extra = QPushButton("Remove selected")
        remove_extra.clicked.connect(self.remove_extra_server)
        extra_buttons.addWidget(remove_extra)
        activate_extra = QPushButton("Use selected server")
        activate_extra.clicked.connect(self.activate_extra_server)
        extra_buttons.addWidget(activate_extra)
        route_preview = QPushButton("Preview routing of selected review titles")
        route_preview.clicked.connect(self.preview_extra_routing)
        extra_buttons.addWidget(route_preview)
        check_routes = QPushButton("Check selected destination library")
        check_routes.clicked.connect(self.check_extra_routing)
        extra_buttons.addWidget(check_routes)
        import_routes = QPushButton("Route selected titles to servers and confirm imports")
        import_routes.clicked.connect(self.prepare_extra_import)
        extra_buttons.addWidget(import_routes)
        extra_row.addLayout(extra_buttons)
        extra_panel = QGroupBox("Additional Sonarr / Radarr instances")
        extra_panel.setCheckable(True)
        extra_panel.setChecked(bool(self.extra_profiles))
        extra_panel_layout = QVBoxLayout(extra_panel)
        extra_panel_layout.addLayout(extra_row)
        self.setup_layout.addWidget(extra_panel)
        self.connect_btn = QPushButton("Test connections and load settings")
        self.connect_btn.clicked.connect(self.connect_servers)
        self.setup_layout.addWidget(self.connect_btn)
        self.update_button = QPushButton("Check for Bulkrr updates")
        self.update_button.clicked.connect(self.check_updates)
        self.update_button.setObjectName("secondaryAction")
        self.extension_btn = QPushButton("Load title-list extension")
        self.extension_btn.clicked.connect(self.load_extension)
        self.extension_btn.setObjectName("secondaryAction")
        utilities_row = QHBoxLayout()
        utilities_row.addWidget(self.update_button)
        utilities_row.addWidget(self.extension_btn)
        self.setup_layout.addLayout(utilities_row)
        self.form = QFormLayout()
        self.combo = {}
        for name, label in (
            ("movie_folder", "Radarr movies folder"),
            ("radarr_profile", "Radarr quality profile"),
            ("tv_folder", "Sonarr TV folder"),
            ("anime_folder", "Sonarr anime folder"),
            ("sonarr_profile", "Sonarr quality profile"),
        ):
            c = QComboBox()
            self.combo[name] = c
            self.form.addRow(label, c)
        self.setup_layout.addLayout(self.form)
        self.search = QCheckBox("Search for missing content after approving import")
        self.search.setChecked(self.settings.get("search", True))
        self.setup_layout.addWidget(self.search)
        self.dry_run = QCheckBox("Dry run: preview without changing Radarr/Sonarr")
        self.dry_run.setChecked(False)
        self.setup_layout.addWidget(self.dry_run)
        save = QPushButton("Save preferences")
        save.clicked.connect(self.save_preferences)
        self.setup_layout.addWidget(save)
        self.setup_layout.addStretch()
        tabs.addTab(setup, "1. Connect & configure")
        importer = QWidget()
        v = QVBoxLayout(importer)
        v.addWidget(QLabel("Bulk Import  /  Add titles → Review matches → Approve"))
        input_panel = QGroupBox("1. Add titles")
        input_layout = QVBoxLayout(input_panel)
        self.input = TitleInput()
        self.input.files_dropped.connect(self.import_files)
        self.input.setAcceptDrops(True)
        self.input.setPlaceholderText(
            "movie: The Raid (2011)\ntv: Breaking Bad (2008)\nanime: Death Note (2006)"
        )
        self.input.setMaximumHeight(155)
        input_layout.addWidget(QLabel("One title per line. Use movie:, tv: or anime: when needed."))
        input_layout.addWidget(self.input)
        source_rows = [QHBoxLayout(), QHBoxLayout()]
        for index, (label, handler) in enumerate((
            ("Import TXT / CSV", self.choose_import_files),
            ("Save title list", self.save_import_session),
            ("Load title list", self.resume_import_session),
            ("Save review snapshot", self.save_review_snapshot),
            ("Load review snapshot", self.load_review_snapshot),
        )):
            button = QPushButton(label)
            button.setObjectName("secondaryAction")
            button.clicked.connect(handler)
            source_rows[0 if index < 3 else 1].addWidget(button)
        for source_row in source_rows:
            source_row.addStretch()
            input_layout.addLayout(source_row)
        analysis_actions = QHBoxLayout()
        self.analyze_btn = QPushButton("Analyze titles (no changes)")
        self.analyze_btn.clicked.connect(self.analyze)
        analysis_actions.addWidget(self.analyze_btn, 2)
        self.stop_analysis_btn = QPushButton("Stop after current title")
        self.stop_analysis_btn.clicked.connect(self.stop_analysis)
        self.stop_analysis_btn.setEnabled(False)
        self.stop_analysis_btn.setObjectName("dangerAction")
        analysis_actions.addWidget(self.stop_analysis_btn, 1)
        input_layout.addLayout(analysis_actions)
        followup_actions = QHBoxLayout()
        self.resume_analysis_btn = QPushButton("Resume remaining analysis")
        self.resume_analysis_btn.setObjectName("secondaryAction")
        self.resume_analysis_btn.setEnabled(False)
        self.resume_analysis_btn.clicked.connect(self.resume_analysis)
        followup_actions.addWidget(self.resume_analysis_btn)
        self.clear_analysis_btn = QPushButton("Clear results and start new list")
        self.clear_analysis_btn.clicked.connect(self.clear_analysis)
        self.clear_analysis_btn.setObjectName("secondaryAction")
        self.clear_analysis_btn.setEnabled(False)
        followup_actions.addWidget(self.clear_analysis_btn)
        input_layout.addLayout(followup_actions)
        v.addWidget(input_panel)
        self.category_policy_label = QLabel(
            "Batch rules (preview only): existing = skip | unmatched = exclude | "
            "ambiguous = review. Nothing is sent to Radarr/Sonarr until final approval."
        )
        self.category_policy_label.setWordWrap(True)
        self.category_policy_label.setObjectName("categoryPolicy")
        v.addWidget(self.category_policy_label)
        v.addWidget(QLabel("2. Review matches"))
        self.review_summary_label = QLabel(review_summary([]))
        self.review_summary_label.setWordWrap(True)
        self.review_summary_label.setObjectName("reviewSummary")
        v.addWidget(self.review_summary_label)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show results:"))
        self.review_filter = QComboBox()
        self.review_filter.addItems(["All titles", "Needs review", "Ready", "Skipped / excluded", "Unmatched"])
        self.review_filter.currentIndexChanged.connect(self.apply_review_filter)
        filter_row.addWidget(self.review_filter)
        self.review_search = QLineEdit()
        self.review_search.setPlaceholderText("Find title in this batch...")
        self.review_search.setClearButtonEnabled(True)
        self.review_search.textChanged.connect(self.apply_review_filter)
        filter_row.addWidget(self.review_search, 1)
        self.review_visible_count = QLabel("0 shown")
        filter_row.addWidget(self.review_visible_count)
        filter_row.addStretch()
        v.addLayout(filter_row)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "●",
                "Input title",
                "Matched title / year",
                "Type",
                "Destination",
                "Quality",
                "Details",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.setWordWrap(False)
        self.table.setObjectName("reviewResults")
        self.table.setSortingEnabled(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setMinimumHeight(360)
        self.table.setToolTip("Select to inspect metadata; double-click a title to review or correct its match.")
        # Keep short metadata columns compact so title text gets the space.
        review_header = self.table.horizontalHeader()
        review_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        review_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        review_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        review_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(3, 82)
        self.table.setColumnWidth(4, 118)
        self.table.setColumnWidth(5, 105)
        self.table.setColumnWidth(6, 145)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_poster)
        self.table.itemSelectionChanged.connect(self.update_review_actions)
        self.table.cellDoubleClicked.connect(self.review_row)
        review_workspace = QSplitter(Qt.Orientation.Horizontal)
        review_workspace.setChildrenCollapsible(False)
        review_workspace.addWidget(self.table)
        preview = QGroupBox("Selected title — artwork and metadata")
        preview_layout = QVBoxLayout(preview)
        self.poster = QLabel("Select a result to view its poster")
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setFixedSize(174, 248)
        self.poster.setStyleSheet(
            "background:#222a37;border:1px solid #39465a;border-radius:6px;color:#aab2c1"
        )
        preview_layout.addWidget(self.poster, 0, Qt.AlignmentFlag.AlignHCenter)
        self.preview_info = QLabel(
            "The selected metadata match, description and poster will appear here."
        )
        self.preview_info.setWordWrap(True)
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignTop)
        preview_layout.addWidget(self.preview_info, 1)
        self.review_detail_status = QLabel("Awaiting analysis")
        self.review_detail_status.setObjectName("reviewDetailStatus")
        self.review_detail_status.setWordWrap(True)
        preview_layout.addWidget(self.review_detail_status)
        self.review_detail_action = QPushButton("Review or change match")
        self.review_detail_action.setObjectName("secondaryAction")
        self.review_detail_action.clicked.connect(self.review)
        preview_layout.addWidget(self.review_detail_action)
        preview.setMinimumWidth(275)
        preview.setMaximumWidth(370)
        review_workspace.addWidget(preview)
        review_workspace.setStretchFactor(0, 4)
        review_workspace.setStretchFactor(1, 2)
        v.addWidget(review_workspace, 1)
        advanced_review_panel = QGroupBox("Advanced review actions")
        advanced_review_panel.setCheckable(True)
        advanced_review_panel.setChecked(False)
        row = QHBoxLayout(advanced_review_panel)
        self.duplicate_btn = QPushButton("Existing title: Skip / Upgrade / Replace")
        self.duplicate_btn.clicked.connect(self.duplicate_action)
        self.duplicate_btn.setObjectName("secondaryAction")
        row.addWidget(self.duplicate_btn)
        self.bulk_skip_btn = QPushButton("Skip all existing titles")
        self.bulk_skip_btn.clicked.connect(self.skip_all_duplicates)
        self.bulk_skip_btn.setObjectName("secondaryAction")
        row.addWidget(self.bulk_skip_btn)
        self.bulk_review_skip_btn = QPushButton("Skip all unresolved matches")
        self.bulk_review_skip_btn.clicked.connect(self.skip_all_unresolved)
        self.bulk_review_skip_btn.setObjectName("secondaryAction")
        row.addWidget(self.bulk_review_skip_btn)
        self.skip_selected_btn = QPushButton("Skip selected rows")
        self.skip_selected_btn.setObjectName("secondaryAction")
        self.skip_selected_btn.clicked.connect(self.skip_selected_rows)
        row.addWidget(self.skip_selected_btn)
        self.restore_selected_btn = QPushButton("Restore excluded rows")
        self.restore_selected_btn.setObjectName("secondaryAction")
        self.restore_selected_btn.clicked.connect(self.restore_selected_rows)
        row.addWidget(self.restore_selected_btn)
        self.edit_title_btn = QPushButton("Edit title and recheck")
        self.edit_title_btn.setObjectName("secondaryAction")
        self.edit_title_btn.clicked.connect(self.edit_selected_title)
        row.addWidget(self.edit_title_btn)
        row.addStretch()
        self.review_btn = QPushButton("Confirm / change selected match")
        self.review_btn.clicked.connect(self.review)
        self.review_btn.setObjectName("secondaryAction")
        self.add_btn = QPushButton("Approve and import")
        self.add_btn.clicked.connect(self.import_items)
        v.addWidget(advanced_review_panel)
        v.addWidget(QLabel("3. Approve import"))
        approval_row = QHBoxLayout()
        approval_row.addStretch()
        approval_row.addWidget(self.review_btn)
        approval_row.addWidget(self.add_btn)
        v.addLayout(approval_row)
        tabs.addTab(importer, "2. Import & review")
        library_page = QWidget()
        library_layout = QVBoxLayout(library_page)
        library_layout.addWidget(QLabel("Read-only inventory of missing titles and below-cutoff Radarr movie files. Searches require confirmation."))
        self.library_scan_btn = QPushButton("Scan connected libraries")
        self.library_scan_btn.clicked.connect(self.scan_library)
        self.library_search_btn = QPushButton("Search selected missing titles")
        self.library_search_btn.clicked.connect(self.search_missing)
        self.library_upgrade_btn = QPushButton("Search selected Radarr quality upgrades")
        self.library_upgrade_btn.clicked.connect(self.search_upgrades)
        self.sonarr_upgrade_btn = QPushButton("Preview selected Sonarr episode upgrades")
        self.sonarr_upgrade_btn.clicked.connect(self.preview_episode_upgrades)
        library_layout.addWidget(self.library_scan_btn)
        library_actions = QGroupBox("Search and upgrade actions")
        library_actions.setCheckable(True)
        library_actions.setChecked(False)
        library_actions_layout = QHBoxLayout(library_actions)
        for button in (self.library_search_btn, self.library_upgrade_btn, self.sonarr_upgrade_btn):
            button.setObjectName("secondaryAction")
            library_actions_layout.addWidget(button)
        library_layout.addWidget(library_actions)
        self.library_summary = QLabel("Connect to Radarr/Sonarr, then scan.")
        sizes = QHBoxLayout()
        sizes.addWidget(QLabel("Average movie GiB:"))
        self.movie_size = QLineEdit("4")
        self.movie_size.setMaximumWidth(70)
        sizes.addWidget(self.movie_size)
        sizes.addWidget(QLabel("Average episode GiB:"))
        self.episode_size = QLineEdit("1")
        self.episode_size.setMaximumWidth(70)
        sizes.addWidget(self.episode_size)
        sizes.addStretch()
        library_layout.addLayout(sizes)
        self.storage_estimate = QLabel("Estimated storage: —")
        library_layout.addWidget(self.storage_estimate)
        self.movie_size.editingFinished.connect(self.update_storage_estimate)
        self.episode_size.editingFinished.connect(self.update_storage_estimate)
        self.library_layout_table = QTableWidget(0, 6)
        self.library_layout_table.setHorizontalHeaderLabels(["Server", "Title", "Year", "Status", "Missing", "Monitored"])
        self.library_layout_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.library_layout_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.library_layout_table.setAlternatingRowColors(True)
        self.library_layout_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        library_layout.addWidget(self.library_summary)
        library_layout.addWidget(self.library_layout_table)
        tabs.addTab(library_page, "3. Library inventory")
        discover_page = QWidget()
        discover_layout = QVBoxLayout(discover_page)
        discover_layout.addWidget(QLabel("Discover movies, TV and anime. Queue selections for review before importing."))
        self.discover_kind = QComboBox()
        self.discover_kind.addItems(["movie", "tv", "anime"])
        self.discover_query = QLineEdit()
        self.discover_query.setPlaceholderText("Search for movies, shows or anime")
        self.discover_button = QPushButton("Find titles")
        self.discover_button.clicked.connect(self.discover_titles)
        self.trending_anime_button = QPushButton("Explore trending anime (AniList)")
        self.trending_anime_button.clicked.connect(self.load_trending_anime)
        self.tmdb_movie_button = QPushButton("Trending movies (TMDB)")
        self.tmdb_movie_button.clicked.connect(lambda: self.load_tmdb_trending("movie"))
        self.tmdb_tv_button = QPushButton("Trending TV (TMDB)")
        self.tmdb_tv_button.clicked.connect(lambda: self.load_tmdb_trending("tv"))
        self.tmdb_collection_search_button = QPushButton("Find TMDB collection IDs by name")
        self.tmdb_collection_search_button.clicked.connect(self.search_tmdb_collections)
        self.tmdb_collection_button = QPushButton("Explore a verified TMDB movie collection by ID")
        self.tmdb_collection_button.clicked.connect(self.load_tmdb_collection)
        self.recommend_interests = QLineEdit()
        self.recommend_interests.setPlaceholderText("Interests, e.g. horror mystery space")
        recommend_btn = QPushButton("Rank current results by my interests")
        recommend_btn.clicked.connect(self.rank_discovery)
        self.library_recommend_btn = QPushButton("Rank results using genres in my library")
        self.library_recommend_btn.clicked.connect(self.rank_from_library)
        self.genre_filter = QLineEdit()
        self.genre_filter.setPlaceholderText("Filter current results by genre (e.g. Horror, Action)")
        self.genre_filter_button = QPushButton("Filter current results by genre")
        self.genre_filter_button.clicked.connect(self.filter_discovery_genre)
        self.reset_discovery_button = QPushButton("Show all current discovery results")
        self.reset_discovery_button.clicked.connect(self.reset_discovery_filter)
        self.discover_results = QListWidget()
        self.discover_results.setObjectName("mediaCatalog")
        self.discover_results.setViewMode(QListWidget.ViewMode.IconMode)
        self.discover_results.setFlow(QListWidget.Flow.LeftToRight)
        self.discover_results.setWrapping(True)
        self.discover_results.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.discover_results.setMovement(QListWidget.Movement.Static)
        self.discover_results.setSpacing(14)
        self.discover_results.setIconSize(QSize(132, 188))
        self.discover_results.setGridSize(QSize(176, 246))
        self.discover_results.setWordWrap(True)
        self.discover_results.setUniformItemSizes(True)
        self.discover_results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.discover_add = QPushButton("Add selected titles to import review")
        self.discover_add.clicked.connect(self.queue_discovered)
        collection_btn = QPushButton("Find franchise movies by title")
        collection_btn.clicked.connect(self.find_collection)
        calendar_btn = QPushButton("Load today's US TV release calendar")
        calendar_btn.clicked.connect(self.load_calendar)
        self.calendar_results = QListWidget()
        search_panel = QGroupBox("Search catalog")
        search_row = QHBoxLayout(search_panel)
        self.discover_kind.setMaximumWidth(130)
        search_row.addWidget(self.discover_kind)
        search_row.addWidget(self.discover_query, 1)
        search_row.addWidget(self.discover_button)
        discover_layout.addWidget(search_panel)

        trending_panel = QGroupBox("Browse collections")
        trending_row = QHBoxLayout(trending_panel)
        self.discover_category = QComboBox()
        self.discover_category.addItems([
            "Trending movies", "Trending TV", "Trending anime",
            "Trending today (movies)", "Trending today (TV)",
            "New releases (movies)", "New releases (TV)",
        ])
        self.discover_category.setMinimumWidth(205)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_discovery_category)
        trending_row.addWidget(self.discover_category)
        trending_row.addWidget(browse_btn)
        self.tmdb_token_reset = QPushButton("Change TMDB token")
        self.tmdb_token_reset.setObjectName("secondaryAction")
        self.tmdb_token_reset.setToolTip(
            "Forget the in-memory TMDB token and prompt for a new one on your next TMDB browse"
        )
        self.tmdb_token_reset.clicked.connect(self.clear_tmdb_token)
        trending_row.addWidget(self.tmdb_token_reset)
        for button in (self.trending_anime_button, self.tmdb_movie_button, self.tmdb_tv_button):
            button.setObjectName("secondaryAction")
            trending_row.addWidget(button)
        discover_layout.addWidget(trending_panel)

        advanced_panel = QGroupBox("Advanced discovery and recommendations")
        advanced_panel.setCheckable(True)
        advanced_panel.setChecked(False)
        advanced_layout = QVBoxLayout(advanced_panel)
        collections_row = QHBoxLayout()
        for button in (self.tmdb_collection_search_button, self.tmdb_collection_button, collection_btn):
            button.setObjectName("secondaryAction")
            collections_row.addWidget(button)
        advanced_layout.addLayout(collections_row)
        interests_row = QHBoxLayout()
        interests_row.addWidget(self.recommend_interests, 1)
        recommend_btn.setObjectName("secondaryAction")
        interests_row.addWidget(recommend_btn)
        self.library_recommend_btn.setObjectName("secondaryAction")
        interests_row.addWidget(self.library_recommend_btn)
        advanced_layout.addLayout(interests_row)
        genre_row = QHBoxLayout()
        genre_row.addWidget(self.genre_filter, 1)
        for button in (self.genre_filter_button, self.reset_discovery_button):
            button.setObjectName("secondaryAction")
            genre_row.addWidget(button)
        advanced_layout.addLayout(genre_row)
        discover_layout.addWidget(advanced_panel)

        catalog_heading = QHBoxLayout()
        self.discover_section_title = QLabel("Explore the catalog")
        self.discover_section_title.setObjectName("catalogHeading")
        catalog_heading.addWidget(self.discover_section_title)
        catalog_heading.addStretch()
        self.discover_count = QLabel("Choose a category or search to load titles")
        self.discover_count.setObjectName("appSubtitle")
        catalog_heading.addWidget(self.discover_count)
        discover_layout.addLayout(catalog_heading)
        catalog_row = QHBoxLayout()
        catalog_row.addWidget(self.discover_results, 3)
        detail_panel = QGroupBox("Media details")
        detail_panel.setMinimumWidth(265)
        detail_panel.setMaximumWidth(360)
        detail_layout = QVBoxLayout(detail_panel)
        self.discover_detail_poster = QLabel("Select a title")
        self.discover_detail_poster.setObjectName("detailPoster")
        self.discover_detail_poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.discover_detail_poster.setFixedSize(172, 242)
        detail_layout.addWidget(self.discover_detail_poster, 0, Qt.AlignmentFlag.AlignHCenter)
        self.discover_detail_title = QLabel("Choose a poster to explore")
        self.discover_detail_title.setObjectName("detailTitle")
        self.discover_detail_title.setWordWrap(True)
        detail_layout.addWidget(self.discover_detail_title)
        self.discover_detail_meta = QLabel("Movie · TV · Anime")
        self.discover_detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.discover_detail_meta)
        self.discover_detail_overview = QLabel("Metadata, genres, and synopsis will appear here.")
        self.discover_detail_overview.setWordWrap(True)
        self.discover_detail_overview.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(self.discover_detail_overview)
        detail_layout.addStretch()
        self.discover_detail_queue = QPushButton("Add this title to import review")
        self.discover_detail_queue.setEnabled(False)
        self.discover_detail_queue.clicked.connect(self.queue_discovery_detail)
        detail_layout.addWidget(self.discover_detail_queue)
        self.discover_results.currentRowChanged.connect(self.show_discovery_details)
        catalog_row.addWidget(detail_panel, 1)
        discover_layout.addLayout(catalog_row, 1)
        discover_layout.addWidget(self.discover_add)
        calendar_panel = QGroupBox("TV release calendar")
        calendar_panel.setCheckable(True)
        calendar_panel.setChecked(False)
        calendar_layout = QVBoxLayout(calendar_panel)
        calendar_btn.setObjectName("secondaryAction")
        calendar_layout.addWidget(calendar_btn)
        calendar_layout.addWidget(self.calendar_results)
        discover_layout.addWidget(calendar_panel)
        tabs.addTab(discover_page, "4. Discover")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(
            "Timestamped connection, lookup, import and error details will appear here. A persistent log is saved in AppData\\Roaming\\Bulkrr\\bulkrr.log"
        )
        tabs.addTab(self.log, "Activity log")
        dashboard = QWidget()
        dashboard_layout = QVBoxLayout(dashboard)
        dashboard_layout.setSpacing(18)
        welcome = QLabel("Your media. One workspace.")
        welcome.setObjectName("dashboardHero")
        dashboard_layout.addWidget(welcome)
        dashboard_layout.addWidget(QLabel(
            "Discover titles, review matches, and manage your Radarr / Sonarr library."
        ))
        dashboard_status = QGroupBox("Connected services")
        status_layout = QHBoxLayout(dashboard_status)
        self.dashboard_radarr = QLabel("●  Radarr  ·  Not connected")
        self.dashboard_sonarr = QLabel("●  Sonarr  ·  Not connected")
        status_layout.addWidget(self.dashboard_radarr)
        status_layout.addWidget(self.dashboard_sonarr)
        dashboard_layout.addWidget(dashboard_status)
        dashboard_layout.addWidget(QLabel("Library overview"))
        overview_row = QHBoxLayout()
        for heading, attr in (
            ("Movies missing", "dashboard_missing_movies"),
            ("Episodes missing", "dashboard_missing_episodes"),
            ("Series with gaps", "dashboard_series_gaps"),
            ("Upgrade candidates", "dashboard_upgrades"),
        ):
            card = QGroupBox(heading)
            card_layout = QVBoxLayout(card)
            value = QLabel("—")
            value.setObjectName("dashboardMetric")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(value)
            setattr(self, attr, value)
            overview_row.addWidget(card)
        dashboard_layout.addLayout(overview_row)
        self.dashboard_scan = QPushButton("Refresh library overview")
        self.dashboard_scan.setObjectName("secondaryAction")
        self.dashboard_scan.clicked.connect(self.scan_library)
        dashboard_layout.addWidget(self.dashboard_scan)
        dashboard_layout.addWidget(QLabel("Start exploring"))
        quick_actions = QHBoxLayout()
        for title, destination in (
            ("Discover movies, TV & anime", 4),
            ("Import a title list", 2),
            ("Browse library", 3),
        ):
            button = QPushButton(title)
            button.setMinimumHeight(58)
            button.clicked.connect(lambda checked=False, page=destination: tabs.setCurrentIndex(page))
            quick_actions.addWidget(button)
        dashboard_layout.addLayout(quick_actions)
        dashboard_layout.addWidget(QLabel("Recent activity"))
        self.dashboard_activity = QLabel("Your latest imports and searches will appear in Activity Log.")
        self.dashboard_activity.setWordWrap(True)
        dashboard_layout.addWidget(self.dashboard_activity)
        dashboard_layout.addWidget(QLabel("Discover highlights"))
        self.dashboard_discover_note = QLabel("Explore trending movies, TV, and anime to populate this section.")
        self.dashboard_discover_note.setWordWrap(True)
        dashboard_layout.addWidget(self.dashboard_discover_note)
        self.dashboard_featured = QListWidget()
        self.dashboard_featured.setObjectName("dashboardFeatured")
        self.dashboard_featured.setViewMode(QListWidget.ViewMode.IconMode)
        self.dashboard_featured.setFlow(QListWidget.Flow.LeftToRight)
        self.dashboard_featured.setWrapping(False)
        self.dashboard_featured.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.dashboard_featured.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dashboard_featured.setIconSize(QSize(90, 128))
        self.dashboard_featured.setGridSize(QSize(130, 174))
        self.dashboard_featured.setFixedHeight(205)
        self.dashboard_featured.itemDoubleClicked.connect(
            lambda item: tabs.setCurrentIndex(4)
        )
        dashboard_layout.addWidget(self.dashboard_featured)
        dashboard_layout.addStretch()
        tabs.insertTab(0, dashboard, "Dashboard")
        self.tabs = tabs
        # Keep dense pages usable without relying on hidden tab navigation.
        for page_index in range(tabs.count()):
            page = tabs.widget(page_index)
            if isinstance(page, QWidget):
                page.setMinimumWidth(0)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage("Connect to Radarr/Sonarr to begin")
        self.setStyleSheet(DARK_THEME)
        self.update_review_actions()

    def scan_library(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.server_data:
            QMessageBox.information(self, "Connect first", "Connect to Sonarr or Radarr before scanning.")
            return
        self.library_summary.setText("Scanning connected libraries...")
        self.library_scan_btn.setEnabled(False)
        self.run_worker("library_scan", done=self.library_scanned)

    def library_scanned(self, data):
        self.library_scan_btn.setEnabled(True)
        rows = [("Radarr", m, "1") for m in data["movies"]]
        rows += [("Sonarr", s, str(s["missing"])) for s in data["series"]]
        rows += [("Radarr", m, "—") for m in data.get("upgrades", [])]
        self.library_entries = rows
        self.library_genres = data.get("genres", [])
        self.library_counts = (len(data["movies"]), sum(show["missing"] for show in data["series"]))
        self.dashboard_missing_movies.setText(str(len(data["movies"])))
        self.dashboard_missing_episodes.setText(str(sum(show["missing"] for show in data["series"])))
        self.dashboard_series_gaps.setText(str(len(data["series"])))
        self.dashboard_upgrades.setText(str(len(data.get("upgrades", []))))
        if data.get("errors"):
            QMessageBox.warning(self, "Incomplete library scan", "\n".join(data["errors"]))
        self.update_storage_estimate()
        self.library_layout_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library_layout_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.library_layout_table.setRowCount(len(rows))
        for row, (app, entry, count) in enumerate(rows):
            for col, value in enumerate((app, entry["title"], entry.get("year") or "—", "Upgrade" if entry.get("status") == "upgrade" else "Missing", count, "Yes" if entry["monitored"] else "No")):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.library_layout_table.setItem(row, col, cell)
        summary = f"{len(data['movies'])} missing movies; {sum(s['missing'] for s in data['series'])} missing episodes across {len(data['series'])} shows"
        summary += f"; {len(data.get('upgrades', []))} Radarr movies below quality cutoff"
        if data["errors"]:
            summary += " | Errors: " + "; ".join(data["errors"])
        self.library_summary.setText(summary)
        self.logmsg("Library inventory: " + summary)

    def find_collection(self):
        if self.worker and self.worker.isRunning():
            return
        term = self.discover_query.text().strip()
        if not term:
            QMessageBox.information(self, "Franchise search", "Enter a franchise name in the search box first.")
            return
        self.run_worker("collection_lookup", config={"term": term}, done=self.collection_found)

    def collection_found(self, titles):
        if not titles:
            QMessageBox.information(self, "No results", "No franchise candidates were returned.")
            return
        answer = QMessageBox.question(self, "Queue franchise candidates", f"Queue {len(titles)} matching movie titles for manual review? Search results may include unrelated movies.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        combined = normalize_titles(self.input.toPlainText().splitlines() + titles)
        self.input.setPlainText("\n".join(combined))
        self.items = []
        self.refresh()
        self.tabs.setCurrentIndex(2)

    def load_calendar(self):
        if self.worker and self.worker.isRunning():
            return
        self.run_worker("release_calendar", done=self.calendar_loaded)

    def calendar_loaded(self, entries):
        self.calendar_results.clear()
        for entry in entries:
            season = entry["season"]
            episode = entry["episode"]
            detail = f"S{season:02d}E{episode:02d}" if isinstance(season, int) and isinstance(episode, int) else "New episode"
            self.calendar_results.addItem(f"{entry['date']} — {entry['title']} — {detail}")
        self.logmsg(f"Loaded {len(entries)} scheduled US TV episodes")

    def discover_titles(self):
        if self.worker and self.worker.isRunning():
            return
        term = self.discover_query.text().strip()
        if not term:
            QMessageBox.information(self, "Search term", "Enter a title to discover.")
            return
        self.discover_button.setEnabled(False)
        self.run_worker("discover", config={"kind": self.discover_kind.currentText(), "term": term}, done=self.discovered)

    def search_tmdb_collections(self):
        if self.worker and self.worker.isRunning():
            return
        term, accepted = QInputDialog.getText(
            self, "Find TMDB collection", "Collection name (e.g. Spider-Man):",
        )
        if not accepted or not term.strip():
            return
        access_token, accepted = QInputDialog.getText(
            self, "TMDB collection search",
            "Enter your TMDB API read access token (not saved):",
            QLineEdit.EchoMode.Password,
        )
        if not accepted or not access_token.strip():
            return
        self.tmdb_collection_search_button.setEnabled(False)
        self.run_worker(
            "tmdb_collection_search",
            config={"term": term.strip(), "access_token": access_token.strip()},
            done=self.tmdb_collections_found,
        )

    def tmdb_collections_found(self, records):
        if not records:
            QMessageBox.information(self, "No TMDB collections", "No matching collections were found.")
            return
        labels = [f"{item['name']} (TMDB ID: {item['id']})" for item in records]
        choice, accepted = QInputDialog.getItem(
            self, "TMDB collections", "Select a collection to view its ID:",
            labels, 0, False,
        )
        if not accepted:
            return
        index = labels.index(choice)
        selected = records[index]
        QMessageBox.information(
            self, "Verified TMDB collection",
            f"{selected['name']}\\nTMDB collection ID: {selected['id']}\\n"
            "Use 'Explore a verified TMDB movie collection by ID' to retrieve its films.",
        )

    def load_tmdb_collection(self):
        if self.worker and self.worker.isRunning():
            return
        collection_id, accepted = QInputDialog.getInt(
            self, "TMDB collection", "Enter the numeric TMDB collection ID:",
            1, 1, 2_147_483_647,
        )
        if not accepted:
            return
        access_token, accepted = QInputDialog.getText(
            self, "TMDB collection", "Enter your TMDB API read access token (not saved):",
            QLineEdit.EchoMode.Password,
        )
        if not accepted or not access_token.strip():
            return
        self.tmdb_collection_button.setEnabled(False)
        self.run_worker(
            "tmdb_collection",
            config={"collection_id": collection_id, "access_token": access_token.strip()},
            done=self.tmdb_collection_loaded,
        )

    def tmdb_collection_loaded(self, records):
        self.discovered(records)
        self.logmsg(f"Loaded {len(records)} verified TMDB collection movies for manual review")

    def browse_discovery_category(self):
        category = self.discover_category.currentText()
        self.discover_section_title.setText(category)
        if category == "Trending anime":
            self.load_trending_anime()
        elif category == "Trending TV":
            self.load_tmdb_trending("tv")
        elif category == "Trending movies":
            self.load_tmdb_trending("movie")
        elif category == "Trending today (movies)":
            self.load_tmdb_trending("movie", window="day")
        elif category == "Trending today (TV)":
            self.load_tmdb_trending("tv", window="day")
        elif category == "New releases (movies)":
            self.load_tmdb_new_releases("movie")
        elif category == "New releases (TV)":
            self.load_tmdb_new_releases("tv")

    def clear_tmdb_token(self):
        """Discard session credentials so invalid or rotated tokens can be replaced."""
        self._tmdb_session_token = ""
        self.logmsg("TMDB session token cleared; a new token will be requested on next browse")

    def get_tmdb_token(self):
        """Reuse the TMDB read token for this session only; never persist it."""
        token = getattr(self, "_tmdb_session_token", "")
        if token:
            return token
        token, accepted = QInputDialog.getText(
            self, "TMDB discovery",
            "Enter your TMDB API read access token (kept in memory for this session only):",
            QLineEdit.EchoMode.Password,
        )
        if not accepted or not token.strip():
            return ""
        token = token.strip()
        if len(token) > 512 or any(char.isspace() for char in token):
            QMessageBox.warning(self, "Invalid token", "Enter a valid TMDB read access token.")
            return ""
        self._tmdb_session_token = token
        return token

    def load_tmdb_new_releases(self, kind):
        if self.worker and self.worker.isRunning():
            return
        access_token = self.get_tmdb_token()
        if not access_token:
            return
        self.run_worker(
            "new_releases_tmdb",
            config={"kind": kind, "access_token": access_token.strip()},
            done=self.tmdb_new_releases_loaded,
        )

    def tmdb_new_releases_loaded(self, records):
        self.discovered(records)
        self.logmsg(
            f"Loaded {len(records)} recently released titles from TMDB (last 45 days)"
        )

    def load_tmdb_trending(self, kind, window="week"):
        if self.worker and self.worker.isRunning():
            return
        access_token = self.get_tmdb_token()
        if not access_token:
            return
        self.tmdb_movie_button.setEnabled(False)
        self.tmdb_tv_button.setEnabled(False)
        self.run_worker("trending_tmdb", config={"kind": kind, "window": window, "access_token": access_token.strip()},
                        done=self.tmdb_trending_loaded)

    def tmdb_trending_loaded(self, records):
        self.discovered(records)
        self.logmsg("Trending movie/TV metadata supplied by TMDB; review before importing")

    def load_trending_anime(self):
        if self.worker and self.worker.isRunning():
            return
        self.trending_anime_button.setEnabled(False)
        self.run_worker("trending_anime", done=self.trending_anime_loaded)

    def trending_anime_loaded(self, records):
        self.trending_anime_button.setEnabled(True)
        self.discovered(records)
        self.logmsg("Trending anime results supplied by AniList; review titles before importing")

    def discovered(self, records):
        self.discover_button.setEnabled(True)
        self.discover_records = records
        if not getattr(self, "_ranking_discovery", False):
            self.discover_source_records = list(records)
        self.discover_results.clear()
        self.show_discovery_details(-1)
        self.discover_count.setText(f"{len(records)} titles")
        self.dashboard_featured.clear()
        self.dashboard_discover_note.setText(
            f"{len(records)} titles from your latest discovery. Double-click to open Discover."
            if records else "No results yet. Try searching or browsing trending titles."
        )
        for entry in records:
            title = entry["title"]
            year = entry.get("year") or "—"
            item = QListWidgetItem(f"{title}\\n{year}  ·  {entry['type'].upper()}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setToolTip(f"{title} ({year})\\n{str(entry.get('overview') or '')[:500]}")
            self.discover_results.addItem(item)
            if self.dashboard_featured.count() < 12:
                featured = QListWidgetItem(f"{title}\\n{year}")
                featured.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                self.dashboard_featured.addItem(featured)
            url = entry.get("poster_url")
            if isinstance(url, str) and url.startswith(("https://image.tmdb.org/t/p/", "https://s4.anilist.co/", "https://s3.anilist.co/")):
                self.fetch_discovery_artwork(url, item)
                if self.dashboard_featured.count() <= 12 and self.discover_results.row(item) < 12:
                    self.fetch_discovery_artwork(url, self.dashboard_featured.item(self.discover_results.row(item)))
        self.logmsg(f"Discovery returned {len(records)} matching titles")

    def fetch_discovery_artwork(self, url, item):
        """Load metadata artwork asynchronously; never block the catalog UI."""
        if url in self.poster_cache:
            self.apply_discovery_artwork(item, url, self.poster_cache[url])
            return
        if url in self.poster_inflight:
            self.poster_inflight[url].append(item)
            return
        self.poster_inflight[url] = [item]
        self.poster_pending.append(url)
        self.start_pending_posters()

    def apply_discovery_artwork(self, item, url, data):
        if not data or (self.discover_results.row(item) < 0 and self.dashboard_featured.row(item) < 0):
            return
        pix = QPixmap()
        if pix.loadFromData(data):
            item.setIcon(QIcon(pix.scaled(
                QSize(132, 188),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )))


    def show_discovery_details(self, row):
        records = getattr(self, "discover_records", [])
        self.discover_detail_queue.setEnabled(0 <= row < len(records))
        if not 0 <= row < len(records):
            self.discover_detail_title.setText("Choose a poster to explore")
            self.discover_detail_meta.setText("Movie · TV · Anime")
            self.discover_detail_overview.setText("Metadata, genres, and synopsis will appear here.")
            self.discover_detail_poster.setProperty("poster_url", "")
            self.discover_detail_poster.setPixmap(QPixmap())
            self.discover_detail_poster.setText("Select a title")
            return
        entry = records[row]
        self.discover_detail_title.setText(entry.get("title", "Unknown title"))
        self.discover_detail_meta.setText(
            f"{entry.get('year') or 'Year unknown'}  ·  {entry.get('type', 'media').upper()}\\n"
            + "  ·  ".join(entry.get("genres") or [])
        )
        overview = str(entry.get("overview") or "No synopsis available.").strip()
        self.discover_detail_overview.setText(overview[:750] + ("…" if len(overview) > 750 else ""))
        url = entry.get("poster_url")
        self.discover_detail_poster.setProperty("poster_url", "")
        self.discover_detail_poster.setPixmap(QPixmap())
        self.discover_detail_poster.setText("Artwork unavailable")
        if isinstance(url, str) and url.startswith(("https://image.tmdb.org/t/p/", "https://s4.anilist.co/", "https://s3.anilist.co/")):
            self.fetch_poster_url(url, self.discover_detail_poster)

    def queue_discovery_detail(self):
        row = self.discover_results.currentRow()
        if row < 0 or row >= len(getattr(self, "discover_records", [])):
            return
        self.discover_results.clearSelection()
        self.discover_results.item(row).setSelected(True)
        self.queue_discovered()

    def fetch_poster_url(self, url, target):
        target.setProperty("poster_url", url)
        if url in self.poster_cache:
            self.display_poster(target, url, self.poster_cache[url])
            return
        if url in self.poster_inflight:
            self.poster_inflight[url].append(target)
            return
        self.poster_inflight[url] = [target]
        self.poster_pending.append(url)
        self.start_pending_posters()

    def rank_discovery(self):
        records = getattr(self, "discover_source_records", [])
        if not records:
            QMessageBox.information(self, "No discovery results", "Discover titles or load trending anime first.")
            return
        try:
            ranked = rank_candidates(records, self.recommend_interests.text())
        except ValueError as exc:
            QMessageBox.information(self, "Recommendation interests", str(exc))
            return
        if not ranked:
            QMessageBox.information(self, "No matching suggestions", "No current titles match those interests. Try different keywords.")
            return
        self._ranking_discovery = True
        try:
            self.discovered(ranked)
        finally:
            self._ranking_discovery = False
        self.logmsg(f"Locally ranked {len(ranked)} discovery candidates by entered interests")

    def rank_from_library(self):
        records = getattr(self, "discover_source_records", [])
        genres = getattr(self, "library_genres", [])
        if not records:
            QMessageBox.information(self, "No discovery results", "Discover titles or load trending anime first.")
            return
        if not genres:
            QMessageBox.information(self, "No library preferences", "Scan a connected library with genre metadata first.")
            return
        try:
            ranked = rank_candidates(records, preferred_genres=genres)
        except ValueError as exc:
            QMessageBox.warning(self, "Recommendation unavailable", str(exc))
            return
        if not ranked:
            QMessageBox.information(self, "No matching suggestions", "No current discovery results match the most common genres in your library.")
            return
        self._ranking_discovery = True
        try:
            self.discovered(ranked)
        finally:
            self._ranking_discovery = False
        self.logmsg(f"Locally ranked {len(ranked)} discovery titles using library genre metadata")

    def filter_discovery_genre(self):
        records = getattr(self, "discover_source_records", [])
        genre = self.genre_filter.text().strip().casefold()
        if not records:
            QMessageBox.information(self, "No discovery results", "Discover titles first.")
            return
        if not genre:
            QMessageBox.information(self, "Genre required", "Enter a genre to filter by.")
            return
        filtered = [
            entry for entry in records
            if isinstance(entry.get("genres"), list)
            and any(isinstance(value, str) and genre in value.casefold()
                    for value in entry["genres"])
        ]
        self._ranking_discovery = True
        try:
            self.discovered(filtered)
        finally:
            self._ranking_discovery = False
        self.logmsg(f"Filtered {len(filtered)} titles by genre; original results retained")

    def reset_discovery_filter(self):
        records = getattr(self, "discover_source_records", [])
        if not records:
            return
        self._ranking_discovery = True
        try:
            self.discovered(records)
        finally:
            self._ranking_discovery = False

    def queue_discovered(self):
        records = getattr(self, "discover_records", [])
        selected = [records[index.row()] for index in self.discover_results.selectionModel().selectedRows() if index.row() < len(records)]
        lines = queue_lines(selected)
        if not lines:
            return
        titles = normalize_titles(self.input.toPlainText().splitlines() + lines)
        self.input.setPlainText("\n".join(titles))
        self.items = []
        self.refresh()
        self.tabs.setCurrentIndex(2)
        self.logmsg(f"Queued {len(lines)} discovered titles for manual review")

    def update_storage_estimate(self):
        try:
            movie_gib = float(self.movie_size.text())
            episode_gib = float(self.episode_size.text())
            if not (0 <= movie_gib <= 10000 and 0 <= episode_gib <= 10000):
                raise ValueError("Invalid size")
            movies, episodes = getattr(self, "library_counts", (0, 0))
            total = estimate_storage(movies, movie_gib) + estimate_storage(episodes, episode_gib)
            self.storage_estimate.setText(f"Estimated storage: {total:,.1f} GiB (assumption-based)")
        except ValueError:
            self.storage_estimate.setText("Enter valid nonnegative sizes")

    def search_missing(self):
        if self.worker and self.worker.isRunning():
            return
        selected = {"radarr": [], "sonarr": []}
        for index in self.library_layout_table.selectionModel().selectedRows():
            row = index.row()
            if row >= len(getattr(self, "library_entries", [])):
                continue
            app, entry, _ = self.library_entries[row]
            if entry.get("status") != "upgrade" and entry.get("monitored") and type(entry.get("id")) is int:
                selected[app.lower()].append(entry["id"])
        count = sum(len(ids) for ids in selected.values())
        if not count or count > 500:
            QMessageBox.information(self, "Selection required", "Select 1–500 monitored missing titles.")
            return
        answer = QMessageBox.question(
            self, "Confirm search",
            f"Request searches for {count} titles? Sonarr/Radarr may download media and consume storage.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_worker("bulk_search", config=selected, done=self.bulk_search_done)

    def preview_episode_upgrades(self):
        if self.worker and self.worker.isRunning():
            return
        ids = []
        for index in self.library_layout_table.selectionModel().selectedRows():
            row = index.row()
            if row >= len(getattr(self, "library_entries", [])):
                continue
            app, entry, _ = self.library_entries[row]
            if (app == "Sonarr" and entry.get("monitored")
                    and type(entry.get("id")) is int and entry["id"] > 0):
                ids.append(entry["id"])
        ids = list(dict.fromkeys(ids))
        if not ids or len(ids) > 100:
            QMessageBox.information(self, "Selection required",
                                    "Select 1–100 monitored Sonarr series rows.")
            return
        self.run_worker("episode_upgrade_preview", config={"series_ids": ids},
                        done=self.episode_upgrades_previewed)

    def episode_upgrades_previewed(self, commands):
        ids = commands[0]["episodeIds"] if commands else []
        if not ids:
            QMessageBox.information(self, "Sonarr episode upgrades",
                                    "No episodes explicitly below their quality cutoff were found.")
            return
        answer = QMessageBox.question(
            self, "Confirm Sonarr episode upgrade searches",
            f"Search {len(ids)} monitored, aired episodes below their quality cutoff? "
            "Sonarr may download replacements and remove old files according to its settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_worker("episode_upgrade_search", config={"episode_ids": ids},
                            done=self.bulk_search_done)

    def search_upgrades(self):
        if self.worker and self.worker.isRunning():
            return
        selected = []
        for index in self.library_layout_table.selectionModel().selectedRows():
            row = index.row()
            if row >= len(getattr(self, "library_entries", [])):
                continue
            app, entry, _ = self.library_entries[row]
            if (app == "Radarr" and entry.get("status") == "upgrade"
                    and entry.get("monitored") and type(entry.get("id")) is int):
                selected.append(entry["id"])
        if not selected or len(selected) > 500:
            QMessageBox.information(
                self, "Selection required",
                "Select 1–500 monitored Radarr movie rows marked Upgrade."
            )
            return
        answer = QMessageBox.question(
            self, "Confirm quality upgrade search",
            f"Ask Radarr to search {len(selected)} movies with files below their configured quality cutoff? "
            "Radarr decides which releases qualify and may download replacements, consume storage, "
            "and remove replaced files according to its settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_worker("bulk_search", config={"radarr": selected}, done=self.bulk_search_done)

    def bulk_search_done(self, result):
        message = f"Queued {result['queued']} search commands."
        if result["errors"]:
            message += " Errors: " + "; ".join(result["errors"])
        self.logmsg(message)
        QMessageBox.information(self, "Search results", message)

    def load_settings(self):
        try:
            return json.loads(SETTINGS.read_text())
        except Exception:
            return {}

    def logmsg(self, s):
        timestamp = (
            datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        )
        entry = f"[{timestamp}] {s}"
        self.log.append(entry)
        if hasattr(self, "dashboard_activity"):
            self.dashboard_activity.setText(s[:200])
        logging.info("%s", s)
        self.statusBar().showMessage(s[:150])

    def row_update(self, index, status, message):
        if (
            self.worker
            and self.worker.task == "analyze"
            and getattr(self, "active_analysis_rows", None) is not None
        ):
            mapping = self.active_analysis_rows
            index = mapping[index] if 0 <= index < len(mapping) else -1
        if (
            self.worker
            and self.worker.task == "import"
            and hasattr(self, "active_import_rows")
        ):
            index = (
                self.active_import_rows[index]
                if 0 <= index < len(self.active_import_rows)
                else -1
            )
        if 0 <= index < len(self.items):
            self.items[index]["status"] = status
            self.items[index]["message"] = message
            # Progress events can arrive thousands of times during a bulk import.
            # Update the affected row instead of rebuilding the entire table.
            if self.table.rowCount() != len(self.items) or not self.table.item(index, 0):
                self.refresh()
            else:
                colors = {
                    "ready": "#62e49b", "done": "#62e49b",
                    "skipped": "#8292A9", "review": "#ffce69",
                    "duplicate": "#ff7272", "error": "#ff7272",
                    "failed": "#ff7272", "working": "#77bfff",
                }
                color = QBrush(QColor(colors.get(status, "#e9edf6")))
                indicator = self.table.item(index, 0)
                indicator.setForeground(color)
                indicator.setToolTip(f"{status}: {message}")
                message_cell = self.table.item(index, 6)
                if message_cell:
                    message_cell.setText(message)
                for col in range(1, 7):
                    cell = self.table.item(index, col)
                    if cell:
                        cell.setForeground(color)
                self.review_summary_label.setText(review_summary(self.items))
                # Only the changed row can enter or leave the active filter.
                was_visible = not self.table.isRowHidden(index)
                now_visible = self.review_row_visible(self.items[index])
                if was_visible != now_visible:
                    self.table.setRowHidden(index, not now_visible)
                    self._review_visible_total = getattr(
                        self, "_review_visible_total", 0
                    ) + (1 if now_visible else -1)
                # Full refresh/filter resets the cached count; progress is O(1).
                self.review_visible_count.setText(
                    f"{self._review_visible_total:,} of {len(self.items):,} shown"
                )
                self.update_review_actions()

    def run_worker(self, task, items=None, config=None, done=None):
        if self.worker and self.worker.isRunning():
            return
        if task == "analyze" and done not in (self.resumed_analysis, self.edited_title_analyzed):
            self.active_analysis_rows = None
        self.worker = Worker(task, dict(self.connections), items, config)
        self.worker.progress.connect(self.logmsg)
        self.worker.row_progress.connect(self.row_update)
        if task == "analyze" and done == self.edited_title_analyzed:
            self.worker.failed.connect(self.edited_title_failed)
        if task == "analyze" and done == self.resumed_analysis:
            self.worker.failed.connect(self.resume_analysis_failed)
        if task == "import":
            self.worker.failed.connect(self.import_failed)
        self.worker.failed.connect(
            lambda e: (
                self.connection_error() if task == "connect" else None,
                self.logmsg("ERROR: " + e),
                QMessageBox.warning(self, "Error", e),
            )
        )
        if done is not None:
            self.worker.finished_data.connect(done)
        self.worker.finished.connect(self.update_review_actions)
        if task == "analyze":
            self.stop_analysis_btn.setEnabled(True)
            self.analyze_btn.setEnabled(False)
            self.worker.finished.connect(self.analysis_worker_finished)
        if task == "library_scan":
            self.worker.finished.connect(lambda: self.library_scan_btn.setEnabled(True))
        if task == "discover":
            self.worker.finished.connect(lambda: self.discover_button.setEnabled(True))
        if task == "trending_anime":
            self.worker.finished.connect(lambda: self.trending_anime_button.setEnabled(True))
        if task == "trending_tmdb":
            self.worker.finished.connect(lambda: self.tmdb_movie_button.setEnabled(True))
            self.worker.finished.connect(lambda: self.tmdb_tv_button.setEnabled(True))
        if task == "tmdb_collection":
            self.worker.finished.connect(lambda: self.tmdb_collection_button.setEnabled(True))
        if task == "tmdb_collection_search":
            self.worker.finished.connect(lambda: self.tmdb_collection_search_button.setEnabled(True))
        self.worker.start()
        self.update_review_actions()

    def connection_error(self):
        self.server_data = {}
        self.items = []
        self.library_entries = []
        self.library_counts = (0, 0)
        self.library_genres = []
        if hasattr(self, "library_layout_table"):
            self.library_layout_table.setRowCount(0)
        if hasattr(self, "library_summary"):
            self.library_summary.setText("Reconnect and scan to refresh library inventory")
        self.update_storage_estimate()
        self.refresh()
        for combo in self.combo.values():
            combo.clear()
        for app in self.connections:
            self.connection_leds[app].set_status("disconnected")
            self.connection_labels[app].setText("Connection failed — see Activity log")
        self.connections = {}

    def load_extension(self):
        folder = APPDIR / "extensions"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            found = discover_manifests(folder)
        except OSError as exc:
            QMessageBox.warning(self, "Extension directory unavailable", str(exc))
            return
        if not found:
            QMessageBox.information(self, "No extensions", f"No valid JSON title-list extensions found in {folder}")
            return
        labels = [f"{entry['name']} — {len(entry['titles'])} titles" for _, entry in found]
        from PySide6.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getItem(self, "Load extension", "Choose a title-list extension", labels, 0, False)
        if not ok:
            return
        index = labels.index(choice)
        entry = found[index][1]
        titles = normalize_titles(self.input.toPlainText().splitlines() + entry["titles"])
        self.input.setPlainText("\n".join(titles))
        self.items = []
        self.refresh()
        self.tabs.setCurrentIndex(2)
        self.logmsg(f"Loaded extension '{entry['name']}' for manual review")

    def check_updates(self):
        if self.worker and self.worker.isRunning():
            return
        self.run_worker("check_updates", done=self.updates_checked)

    def updates_checked(self, release):
        if release is None:
            QMessageBox.information(
                self, "No published release",
                "Bulkrr has no published GitHub release to compare against yet. "
                "This development preview can still be used normally."
            )
            return
        if update_available("2.0.0-beta", release["tag"]):
            answer = QMessageBox.question(self, "Update available", f"Bulkrr {release['tag']} is available. Open the official GitHub release page?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                import webbrowser
                webbrowser.open(release["url"])
        else:
            QMessageBox.information(self, "Up to date", "No newer stable GitHub release found.")

    def refresh_extra_list(self):
        if not hasattr(self, "extra_list"):
            return
        self.extra_list.clear()
        for profile in self.extra_profiles:
            self.extra_list.addItem(f"{profile['kind'].title()}: {profile['label']} — {profile['url']}")

    def add_extra_server(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add server profile")
        form = QFormLayout(dialog)
        kind = QComboBox()
        kind.addItems(["sonarr", "radarr"])
        label = QLineEdit()
        url = QLineEdit()
        key = QLineEdit()
        key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Server type", kind)
        form.addRow("Label", label)
        form.addRow("Server URL", url)
        form.addRow("API key", key)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        identifier = f"{kind.currentText()}_{len(self.extra_profiles) + 1}"
        existing = {p["id"] for p in self.extra_profiles}
        while identifier in existing:
            identifier += "_new"
        try:
            profile = validate_profiles([{"id": identifier, "kind": kind.currentText(), "url": url.text().strip(), "label": label.text().strip()}])[0]
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid server", str(exc))
            return
        if not key.text().strip():
            QMessageBox.warning(self, "Missing API key", "Enter an API key for the additional server.")
            return
        try:
            import keyring
            keyring.set_password("Bulkrr", "profile:" + identifier, key.text().strip())
        except Exception:
            QMessageBox.warning(self, "Keyring unavailable", "Could not securely save the API key. Additional server was not added.")
            return
        updated = self.extra_profiles + [profile]
        try:
            saved = dict(self.settings)
            saved["extra_profiles"] = validate_profiles(updated)
            write_settings(SETTINGS, saved)
        except (OSError, ValueError) as exc:
            try:
                keyring.delete_password("Bulkrr", "profile:" + identifier)
            except Exception:
                pass
            QMessageBox.warning(self, "Could not save server profile", str(exc))
            return
        self.extra_profiles = updated
        self.settings = saved
        self.refresh_extra_list()

    def preview_extra_routing(self):
        """Show a non-executing routing preview for explicitly selected titles."""
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the active operation.")
            return
        profile_row = self.extra_list.currentRow()
        if profile_row < 0 or profile_row >= len(self.extra_profiles):
            QMessageBox.information(self, "Select destination", "Select an additional server profile first.")
            return
        profile = self.extra_profiles[profile_row]
        selection = self.table.selectionModel()
        rows = sorted({index.row() for index in selection.selectedRows()}) if selection else []
        assignments = []
        for row in rows:
            if row >= len(self.items):
                continue
            item = self.items[row]
            matches = item.get("matches") or []
            index = item.get("selected", -1)
            if type(index) is not int or index < 0 or index >= len(matches):
                QMessageBox.warning(self, "Review required", "Every selected title needs a confirmed metadata match.")
                return
            match = matches[index]
            kind = match.get("app") if isinstance(match, dict) else None
            if kind != profile["kind"]:
                QMessageBox.warning(self, "Server mismatch",
                                    "All selected titles must match the destination server type.")
                return
            assignments.append({"item_id": row + 1, "kind": kind, "profile_id": profile["id"]})
        if not assignments:
            QMessageBox.information(self, "Select titles", "Select review-table rows to preview.")
            return
        try:
            routes = route_to_profiles(self.extra_profiles, assignments)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid routing plan", str(exc))
            return
        count = sum(len(route["item_ids"]) for route in routes)
        QMessageBox.information(
            self, "Read-only routing preview",
            f"{count} selected title(s) would route to {profile['label']} ({profile['kind'].title()}) "
            f"at {profile['url']}. No server requests or imports have been made. "
            "To use this destination now, activate the profile and reconnect; simultaneous routing is not yet enabled.",
        )

    def check_extra_routing(self):
        """Read-only inventory check for selected reviewed titles and destination."""
        if self.worker and self.worker.isRunning():
            return
        profile_row = self.extra_list.currentRow()
        if profile_row < 0 or profile_row >= len(self.extra_profiles):
            QMessageBox.information(self, "Select destination", "Select an additional server profile.")
            return
        profile = self.extra_profiles[profile_row]
        selection = self.table.selectionModel()
        rows = sorted({index.row() for index in selection.selectedRows()}) if selection else []
        assignments = []
        for row in rows:
            if row >= len(self.items):
                continue
            item = self.items[row]
            matches = item.get("matches") or []
            index = item.get("selected", -1)
            if type(index) is not int or index < 0 or index >= len(matches):
                QMessageBox.warning(self, "Review required", "Select titles with reviewed metadata matches.")
                return
            match = matches[index]
            if not isinstance(match, dict) or match.get("app") != profile["kind"]:
                QMessageBox.warning(self, "Server mismatch", "Selected title type must match the destination.")
                return
            assignments.append({"item_id": row + 1, "kind": profile["kind"], "profile_id": profile["id"]})
        if not assignments:
            QMessageBox.information(self, "Select titles", "Select review-table titles first.")
            return
        try:
            routes = route_to_profiles(self.extra_profiles, assignments)
            import keyring
            secret = keyring.get_password("Bulkrr", "profile:" + profile["id"])
        except Exception as exc:
            QMessageBox.warning(self, "Cannot check destination", str(exc))
            return
        if not secret:
            QMessageBox.warning(self, "Missing API key", "Destination API key is unavailable in the keyring.")
            return
        self.run_worker("routed_library_check",
                        config={"routes": routes, "credentials": {profile["id"]: secret}},
                        done=self.routed_library_checked)

    def routed_library_checked(self, results):
        messages = []
        for result in results:
            if result["error"]:
                messages.append(f"{result['profile_id']}: {result['error']}")
            else:
                messages.append(f"{result['profile_id']}: {result['library_count']} existing library records")
        QMessageBox.information(self, "Read-only destination checks",
                                "\n".join(messages) + "\nNo imports or searches were requested.")

    def prepare_extra_import(self):
        """Explicitly assign each selected title to a destination server."""
        if self.worker and self.worker.isRunning():
            return
        selection = self.table.selectionModel()
        rows = sorted({index.row() for index in selection.selectedRows()}) if selection else []
        if not rows:
            QMessageBox.information(self, "Select titles", "Select reviewed titles in the review table.")
            return
        assignments = []
        selected_profiles = {}
        for index in rows:
            if index >= len(self.items):
                continue
            item = self.items[index]
            matches = item.get("matches") or []
            selected = item.get("selected", -1)
            if type(selected) is not int or selected < 0 or selected >= len(matches):
                QMessageBox.warning(self, "Review required", "Review metadata for every selected title.")
                return
            match = matches[selected]
            choices = [profile for profile in self.extra_profiles
                       if profile["kind"] == match.get("app")]
            if not choices:
                QMessageBox.warning(self, "No matching server",
                                    "Add a server profile matching the selected title type.")
                return
            labels = [f"{p['label']} ({p['id']})" for p in choices]
            destination, ok = QInputDialog.getItem(
                self, "Choose title destination",
                f"Destination for {match.get('data', {}).get('title', item.get('input', 'title'))}:",
                labels, 0, False)
            if not ok:
                return
            profile = choices[labels.index(destination)]
            selected_profiles[profile["id"]] = profile
            assignments.append({"item_id": index + 1, "kind": profile["kind"],
                                "profile_id": profile["id"]})
        destinations = {}
        credentials = {}
        try:
            import keyring
            for profile in selected_profiles.values():
                secret = keyring.get_password("Bulkrr", "profile:" + profile["id"])
                if not secret:
                    raise ValueError("Missing API key for " + profile["label"])
                credentials[profile["id"]] = secret
                quality, ok = QInputDialog.getInt(
                    self, "Destination quality profile",
                    f"Quality profile ID for {profile['label']}:", 1, 1, 999999)
                if not ok:
                    return
                folders = {}
                for category in (("movie",) if profile["kind"] == "radarr" else ("tv", "anime")):
                    folder, ok = QInputDialog.getText(
                        self, "Destination root folder",
                        f"{category.title()} root folder on {profile['label']}:")
                    if not ok:
                        return
                    folders[category] = folder.strip()
                destinations[profile["id"]] = {
                    "quality_profile_id": quality, "root_folders": folders}
            plans = plan_routed_imports(self.extra_profiles, assignments, destinations)
            batches = prepare_routed_import_batches(plans, self.items)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid destination plan", str(exc))
            return
        self.pending_routed_import = {"batches": batches, "credentials": credentials}
        self.run_worker("routed_import_preview", config=self.pending_routed_import,
                        done=self.routed_import_previewed)

    def routed_import_previewed(self, results):
        pending = getattr(self, "pending_routed_import", None)
        if not pending:
            return
        if any(result["error"] for result in results):
            QMessageBox.warning(self, "Destination unavailable",
                                "A destination library check failed. No imports were made.")
            self.pending_routed_import = None
            return
        additions = sum(result["action"] == "add" for result in results)
        skipped = len(results) - additions
        if additions == 0:
            self.pending_routed_import = None
            QMessageBox.information(self, "Nothing to import",
                                    "All selected titles already exist at their destinations.")
            return
        answer = QMessageBox.question(
            self, "Confirm destination imports",
            f"Add {additions} new title(s) to the selected destination? "
            f"{skipped} existing title(s) will be skipped. "
            "The destination library will be checked again before writing.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self.pending_routed_import = None
            return
        search_answer = QMessageBox.question(
            self, "Search for missing content?",
            "Automatically search for missing movies and episodes after adding "
            "the approved titles? Choose No to add without searching.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        config = dict(pending)
        config.update({"approved": True,
                       "search": search_answer == QMessageBox.StandardButton.Yes})
        self.pending_routed_import = None
        # The preview's finished_data signal can arrive before its thread exits.
        # Start the write worker only after that thread has fully finished.
        preview_worker = self.worker
        preview_worker.finished.connect(
            lambda: QTimer.singleShot(0, lambda: self.run_worker(
                "routed_import_execute", config=config, done=self.routed_import_finished)))

    def routed_import_finished(self, results):
        counts = {status: sum(r["status"] == status for r in results)
                  for status in ("added", "skipped", "blocked", "failed")}
        QMessageBox.information(self, "Destination import results",
                                ", ".join(f"{key}: {value}" for key, value in counts.items()))
        self.logmsg("Routed import results: " + str(counts))

    def activate_extra_server(self):
        row = self.extra_list.currentRow()
        if row < 0:
            return
        profile = self.extra_profiles[row]
        try:
            import keyring
            secret = keyring.get_password("Bulkrr", "profile:" + profile["id"])
        except Exception:
            secret = None
        if not secret:
            QMessageBox.warning(self, "Missing credentials", "API key unavailable in the system keyring.")
            return
        app = profile["kind"]
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the active operation before switching servers.")
            return
        self.connections = {}
        self.server_data = {}
        self.items = []
        self.library_entries = []
        self.library_counts = (0, 0)
        self.library_genres = []
        self.library_layout_table.setRowCount(0)
        self.library_summary.setText("Reconnect and scan to refresh library inventory")
        self.update_storage_estimate()
        for setting in ("movie_folder", "tv_folder", "anime_folder", "radarr_profile", "sonarr_profile"):
            self.settings.pop(setting, None)
        self.refresh()
        self.url[app].setText(profile["url"])
        self.key[app].setText(secret)
        # Clear the other server's credentials: a profile switch must not
        # silently reuse an unrelated destination from the previous session.
        other = "sonarr" if app == "radarr" else "radarr"
        self.url[other].clear()
        self.key[other].clear()
        for name, combo in self.combo.items():
            combo.clear()
        for name in self.connection_labels:
            self.connection_labels[name].setText("Reconnect required")
            self.connection_leds[name].set_status("unconfigured")
        self.logmsg(f"Selected {app.title()} profile: {profile['label']}. Test connections to activate.")
        self.statusBar().showMessage("Server changed — reconnect and review destinations before importing")

    def remove_extra_server(self):
        row = self.extra_list.currentRow()
        if row < 0:
            return
        profile = self.extra_profiles[row]
        answer = QMessageBox.question(
            self, "Remove server profile",
            f"Remove saved profile '{profile['label']}'? This does not delete any Sonarr/Radarr library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        updated = self.extra_profiles[:row] + self.extra_profiles[row + 1:]
        try:
            saved = dict(self.settings)
            saved["extra_profiles"] = validate_profiles(updated)
            write_settings(SETTINGS, saved)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not remove profile", str(exc))
            return
        self.extra_profiles = updated
        self.settings = saved
        self.refresh_extra_list()
        try:
            import keyring
            keyring.delete_password("Bulkrr", "profile:" + profile["id"])
        except Exception:
            self.logmsg("Profile removed; keyring cleanup was not available.")

    def connect_servers(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the active operation before reconnecting.")
            return
        self.connections = {}
        self.server_data = {}
        self.items = []
        self.library_entries = []
        self.library_counts = (0, 0)
        self.library_genres = []
        if hasattr(self, "library_layout_table"):
            self.library_layout_table.setRowCount(0)
        if hasattr(self, "library_summary"):
            self.library_summary.setText("Reconnect and scan to refresh library inventory")
        self.update_storage_estimate()
        self.refresh()
        for combo in self.combo.values():
            combo.clear()
        for app in ("radarr", "sonarr"):
            url = self.url[app].text().strip().rstrip("/")
            key = self.key[app].text().strip()
            if url and key:
                self.connections[app] = {"url": url, "key": key}
            self.connection_labels[app].setText(
                "Testing connection..." if url and key else "Not configured"
            )
            self.connection_leds[app].set_status(
                "working" if url and key else "unconfigured"
            )
        if not self.connections:
            QMessageBox.warning(
                self,
                "Missing credentials",
                "Enter at least one server URL and API key.",
            )
            return
        self.run_worker("connect", done=self.connected)

    def connected(self, data):
        self.server_data = data
        self.dashboard_radarr.setText("●  Radarr  ·  " + ("Connected" if "radarr" in data else "Not connected"))
        self.dashboard_sonarr.setText("●  Sonarr  ·  " + ("Connected" if "sonarr" in data else "Not connected"))
        connected_names = [app.title() for app in ("radarr", "sonarr") if app in data]
        self.header_status.setText(
            "●  " + " + ".join(connected_names) + " connected"
            if connected_names else "●  Connect Radarr / Sonarr to begin"
        )
        for app in ("radarr", "sonarr"):
            self.connection_labels[app].setText(
                "Connected and authenticated" if app in data else "Not configured"
            )
            self.connection_leds[app].set_status(
                "connected" if app in data else "unconfigured"
            )
        for name, combo in self.combo.items():
            combo.clear()
            app = "radarr" if name.startswith(("movie", "radarr")) else "sonarr"
            if app not in data:
                continue
            if name.endswith("profile"):
                for p in data[app]["profiles"]:
                    combo.addItem(p["name"], p["id"])
            else:
                for f in data[app]["roots"]:
                    combo.addItem(f["path"], f["path"])
            desired = self.settings.get(name)
            idx = combo.findData(desired)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif name.endswith("profile"):
                idx = combo.findText("HD-1080p")
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            elif name == "anime_folder":
                idx = next(
                    (
                        i
                        for i in range(combo.count())
                        if "anime" in combo.itemText(i).lower()
                    ),
                    -1,
                )
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            elif name == "tv_folder":
                idx = next(
                    (
                        i
                        for i in range(combo.count())
                        if "tv" in combo.itemText(i).lower()
                    ),
                    -1,
                )
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        self.logmsg(
            "Connections tested. Review folder and quality selections, then save preferences."
        )

    def save_preferences(self):
        if not self.server_data:
            QMessageBox.warning(
                self, "Connect first", "Test your connections before saving."
            )
            return
        data = {"search": self.search.isChecked(), "extra_profiles": validate_profiles(self.extra_profiles)}
        for app in ("radarr", "sonarr"):
            data[app + "_url"] = self.url[app].text().strip()
        for name, c in self.combo.items():
            data[name] = c.currentData()
        for app in self.server_data:
            if not data.get(f"{app}_profile") or not data.get(
                "movie_folder" if app == "radarr" else "tv_folder"
            ):
                QMessageBox.warning(
                    self, "Incomplete", "Choose required folders and quality profiles."
                )
                return
        try:
            import keyring
            for app in self.server_data:
                keyring.set_password("Bulkrr", app, self.key[app].text().strip())
        except Exception as exc:
            QMessageBox.warning(
                self, "API keys not saved",
                "The operating system credential store could not save API keys. "
                "Your preferences will not be written until credentials are secure. "
                f"Details: {type(exc).__name__}"
            )
            return
        try:
            write_settings(SETTINGS, data)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not save preferences", str(exc))
            return
        self.settings = data
        self.logmsg("Preferences saved. Ready for bulk imports.")
        QMessageBox.information(
            self, "Ready", "Connected and configured. You can now analyze titles."
        )
        self.tabs.setCurrentIndex(2)

    def choose_import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import title lists", "", "Title lists (*.txt *.csv)"
        )
        if paths:
            self.import_files(paths)

    def import_files(self, paths):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        try:
            titles = normalize_titles(
                self.input.toPlainText().splitlines()
                + [title for path in paths for title in read_source(path)]
            )
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, "File import failed", str(error))
            return
        self.input.setPlainText("\n".join(titles))
        self.items = []
        self.refresh()
        self.logmsg(f"Loaded {len(paths)} file(s); {len(titles)} unique titles ready for analysis")

    def save_review_snapshot(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save review snapshot", "bulkrr-review.json", "Bulkrr review (*.json)")
        if not path:
            return
        try:
            save_review(path, self.input.toPlainText(), self.items)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not save review", str(exc))
            return
        self.logmsg("Review snapshot saved (credentials excluded)")

    def load_review_snapshot(self):
        if self.worker and self.worker.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load review snapshot", "", "Bulkrr review (*.json)")
        if not path:
            return
        try:
            data = load_review(path)
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, "Could not load review", str(exc))
            return
        self.input.setPlainText("\n".join(data["titles"]))
        self.items = []
        self.refresh()
        self.logmsg(f"Restored {len(data['titles'])} titles and {len(data['review'])} historical review records; reanalyze to verify live matches and duplicates")
        QMessageBox.information(self, "Review restored", "Title inputs restored. Saved review decisions are historical only; run Analyze to refresh matches and duplicate checks before importing.")

    def save_import_session(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save import session", "bulkrr-session.json", "Bulkrr session (*.json)"
        )
        if not path:
            return
        try:
            count = save_session(path, self.input.toPlainText())
        except OSError as error:
            QMessageBox.warning(self, "Session save failed", str(error))
            return
        self.logmsg(f"Saved session with {count} title(s)")

    def resume_import_session(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Resume import session", "", "Bulkrr session (*.json)"
        )
        if not path:
            return
        try:
            titles = load_session(path)
        except (OSError, ValueError, UnicodeError) as error:
            QMessageBox.warning(self, "Session load failed", str(error))
            return
        self.input.setPlainText("\n".join(titles))
        self.items = []
        self.refresh()
        self.logmsg(f"Resumed session with {len(titles)} title(s); analyze again to refresh server matches")

    def analyze(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        if not self.server_data:
            QMessageBox.warning(
                self, "Not connected", "Connect and configure a server first."
            )
            return
        lines = normalize_titles(self.input.toPlainText().splitlines())
        if not lines:
            return
        self.items = [
            {
                "input": line,
                "matches": [],
                "selected": -1,
                "status": "working",
                "message": "Queued for analysis",
            }
            for line in lines
        ]
        self.refresh()
        self.logmsg(
            f"Starting analysis for {len(lines)} title(s); remaining on Bulk import tab."
        )
        self.run_worker("analyze", items=lines, done=self.analyzed)

    def resume_analysis(self):
        """Recheck only titles that were not looked up before Stop."""
        if self.worker and self.worker.isRunning():
            return
        if not self.server_data:
            QMessageBox.warning(self, "Not connected", "Reconnect before resuming analysis.")
            return
        pending = [
            item["input"] for item in self.items
            if item.get("message") == "Analysis stopped before lookup"
        ]
        if not pending:
            return
        self._resume_previous_items = [dict(item) for item in self.items]
        self.active_analysis_rows = [
            index for index, item in enumerate(self.items)
            if item.get("message") == "Analysis stopped before lookup"
        ]
        self.resume_analysis_btn.setEnabled(False)
        self.logmsg(f"Resuming {len(pending)} unfinished title(s); completed results preserved")
        self.run_worker("analyze", items=pending, done=self.resumed_analysis)

    def resume_analysis_failed(self, error):
        """Restore review state if a partial resume fails before producing results."""
        previous = getattr(self, "_resume_previous_items", [])
        if previous:
            self.items = previous
            self._resume_previous_items = []
            self.refresh()
        self.active_analysis_rows = None
        self.logmsg("Resume failed; previous review decisions were restored")

    def resumed_analysis(self, items):
        """Merge resumed results into their original positions, retaining unfinished rows."""
        previous = getattr(self, "_resume_previous_items", [])
        by_input = {item["input"]: item for item in items}
        self.items = [
            by_input.get(item["input"], item)
            if item.get("message") == "Analysis stopped before lookup"
            else item
            for item in previous
        ]
        self._resume_previous_items = []
        self.apply_category_decisions([
            item for item in items
            if item.get("message") != "Analysis stopped before lookup"
        ])
        self.refresh()
        self.logmsg(f"Resume pass processed {len(items)} title(s)")

    def stop_analysis(self):
        if not self.worker or not self.worker.isRunning() or self.worker.task != "analyze":
            return
        self.worker.request_stop_after_current()
        self.stop_analysis_btn.setEnabled(False)
        self.stop_analysis_btn.setText("Stopping after current title...")
        self.logmsg("Stop requested; waiting for the active metadata lookup to finish")

    def analysis_worker_finished(self):
        self.active_analysis_rows = None
        self.stop_analysis_btn.setEnabled(False)
        self.stop_analysis_btn.setText("Stop after current title")
        self.analyze_btn.setEnabled(True)
        self.update_review_actions()

    def analyzed(self, items):
        self.items = items
        self.apply_category_decisions()
        self.refresh()
        self.logmsg(
            f"Analysis finished: {len(items)} titles; "
            f"{sum(bool(x.get('duplicate')) for x in items)} existing library titles detected. "
            "Existing titles were skipped and unmatched titles excluded; review remaining yellow entries."
        )

    def apply_category_decisions(self, items=None):
        """Local review decisions only. Preserve prior manual choices on partial rechecks."""
        counts = {"existing": 0, "unmatched": 0, "ambiguous": 0}
        for item in (self.items if items is None else items):
            if item.get("message") == "Analysis stopped before lookup":
                continue
            if item.get("duplicate"):
                item["status"] = "skipped"
                item["action"] = "skip"
                item["message"] = "Existing library title — skipped automatically"
                counts["existing"] += 1
            elif not item.get("matches") and item.get("status") == "error":
                item["status"] = "skipped"
                item["action"] = "skip"
                item["message"] = "No reliable metadata match — excluded from import"
                counts["unmatched"] += 1
            elif item.get("status") == "review":
                item["action"] = "review"
                counts["ambiguous"] += 1
        self.logmsg(
            "Preview-only category decisions: "
            f"{counts['existing']} existing skipped, "
            f"{counts['unmatched']} unmatched excluded, "
            f"{counts['ambiguous']} held for manual review"
        )

    def refresh(self):
        self.review_summary_label.setText(review_summary(self.items))
        previous_row = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        # Review actions use source-list row indices. Keep sorting disabled
        # so a visual sort cannot target a different title for an import action.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            status = item["status"]
            labels = {
                "working": "BLUE · Processing",
                "ready": "GREEN · Ready",
                "skipped": "Skipped",
                "review": "YELLOW · Review",
                "duplicate": "RED · Already in library",
                "error": "RED · Not found",
                "done": "GREEN · Added",
                "failed": "RED · Failed",
            }
            match = (
                item["matches"][item["selected"]]
                if 0 <= item.get("selected", -1) < len(item.get("matches", []))
                else None
            )
            kind = match["type"] if match else "—"
            app = match["app"] if match else None
            folder = self.settings.get(f"{kind}_folder") if kind != "—" else None
            quality = next(
                (
                    self.combo[f"{app}_profile"].currentText()
                    for _ in [0]
                    if app and f"{app}_profile" in self.combo
                ),
                "—",
            )
            values = (
                item["input"],
                (match.get("label") or match.get("data", {}).get("title") or item["input"]) if match else "—",
                kind,
                folder or "—",
                quality,
                item.get("message", ""),
            )
            # Avoid creating one QWidget per title in large imports.
            indicator = QTableWidgetItem("●")
            indicator.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setToolTip(labels.get(status, status) + "\n" + item.get("message", ""))
            indicator.setFlags(indicator.flags() & ~Qt.ItemFlag.ItemIsEditable)
            indicator.setForeground(QBrush(QColor({
                "ready": "#62e49b", "done": "#62e49b",
                "skipped": "#8292A9", "review": "#ffce69",
                "duplicate": "#ff7272", "error": "#ff7272",
                "failed": "#ff7272", "working": "#77bfff",
            }.get(status, "#e9edf6"))))
            self.table.setItem(row, 0, indicator)
            for col, value in enumerate(values, 1):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                color = {
                    "ready": "#62e49b",
                    "skipped": "#8292A9",
                    "done": "#62e49b",
                    "review": "#ffce69",
                    "duplicate": "#ff7272",
                    "error": "#ff7272",
                    "failed": "#ff7272",
                    "working": "#77bfff",
                }.get(status, "#e9edf6")
                cell.setForeground(QBrush(QColor(color)))
                if col in (1, 2):
                    cell.setToolTip(str(value))
                if col == 1:
                    font = cell.font()
                    font.setBold(True)
                    cell.setFont(font)
                self.table.setItem(row, col, cell)
        if 0 <= previous_row < len(self.items):
            self.table.selectRow(previous_row)
        self.table.blockSignals(False)
        self.apply_review_filter()
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        self.show_selected_poster()
        self.update_review_actions()

    def review_row_visible(self, item, choice=None, search=None):
        """Evaluate one row without traversing the entire review batch."""
        if choice is None:
            choice = self.review_filter.currentIndex()
        if search is None:
            search = self.review_search.text().strip().casefold()
        status = item.get("status")
        show = (
            choice == 0
            or choice == 1 and status in ("review", "duplicate", "error", "failed")
            or choice == 2 and status == "ready"
            or choice == 3 and status == "skipped"
            or choice == 4 and not item.get("matches")
        )
        if search and show:
            matches = item.get("matches") or []
            selected = item.get("selected", -1)
            match = matches[selected] if isinstance(selected, int) and 0 <= selected < len(matches) else None
            title = (match or {}).get("label") or (match or {}).get("data", {}).get("title", "")
            show = search in (item.get("input", "") + " " + title).casefold()
        return bool(show)

    def apply_review_filter(self, *_):
        if not hasattr(self, "table") or not hasattr(self, "review_filter"):
            return
        choice = self.review_filter.currentIndex()
        search = self.review_search.text().strip().casefold()
        visible = 0
        for row, item in enumerate(self.items):
            show = self.review_row_visible(item, choice, search)
            if self.table.isRowHidden(row) == show:
                self.table.setRowHidden(row, not show)
            visible += int(show)
        self._review_visible_total = visible
        self.review_visible_count.setText(f"{visible:,} of {len(self.items):,} shown")

    def update_review_actions(self):
        row = self.table.currentRow()
        selected = self.items[row] if 0 <= row < len(self.items) else None
        busy = bool(self.worker and self.worker.isRunning())
        self.review_btn.setEnabled(bool(selected and selected.get("matches")) and not busy)
        self.review_detail_action.setEnabled(bool(selected and selected.get("matches")) and not busy)
        self.edit_title_btn.setEnabled(bool(selected) and bool(self.server_data) and not busy)
        self.duplicate_btn.setEnabled(bool(selected and selected.get("duplicate")) and not busy)
        self.skip_selected_btn.setEnabled(
            not busy and any(
                0 <= index.row() < len(self.items)
                and self.items[index.row()].get("status") in ("ready", "review", "duplicate", "error")
                for index in self.table.selectionModel().selectedRows()
            )
        )
        self.restore_selected_btn.setEnabled(not busy and any(
            0 <= index.row() < len(self.items)
            and self.items[index.row()].get("status") == "skipped"
            and self.items[index.row()].get("message") == "Excluded from import by user selection"
            for index in self.table.selectionModel().selectedRows()
        ))
        self.add_btn.setEnabled(
            not busy and any(item.get("status") == "ready" for item in self.items)
        )
        self.bulk_skip_btn.setEnabled(not busy and any(
            item.get("status") == "duplicate" for item in self.items))
        self.bulk_review_skip_btn.setEnabled(not busy and any(
            item.get("status") in ("review", "error") for item in self.items))
        self.clear_analysis_btn.setEnabled(not busy and bool(
            self.items or self.input.toPlainText().strip()))
        self.resume_analysis_btn.setEnabled(
            not busy and bool(self.server_data) and any(
                item.get("message") == "Analysis stopped before lookup"
                for item in self.items
            )
        )

    def fetch_poster(self, match, target):
        url = poster_url(match)
        target.setText("Loading poster..." if url else "No poster available")
        target.setPixmap(QPixmap())
        target.setProperty("poster_url", url or "")
        if not url:
            return
        if url in self.poster_cache:
            self.display_poster(target, url, self.poster_cache[url])
            return
        if url in self.poster_inflight:
            if target not in self.poster_inflight[url]:
                self.poster_inflight[url].append(target)
            return
        self.poster_inflight[url] = [target]
        self.poster_pending.append(url)
        self.start_pending_posters()

    def start_pending_posters(self):
        """Bound artwork requests so a large catalog does not spawn dozens of threads."""
        while self.poster_pending and len(self.poster_workers) < 5:
            url = self.poster_pending.pop(0)
            if url not in self.poster_inflight:
                continue
            worker = PosterWorker(url)
            self.poster_workers.append(worker)
            worker.loaded.connect(self.poster_loaded)
            worker.finished.connect(lambda worker=worker: self.poster_worker_finished(worker))
            worker.start()

    def poster_worker_finished(self, worker):
        if worker in self.poster_workers:
            self.poster_workers.remove(worker)
        self.start_pending_posters()

    def display_poster(self, target, url, data):
        if target.property("poster_url") != url:
            return
        pix = QPixmap()
        if data and pix.loadFromData(data):
            target.setPixmap(
                pix.scaled(
                    target.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            target.setText("")
        else:
            target.setText("Poster unavailable")

    def poster_loaded(self, url, data, error):
        if data:
            self.poster_cache[url] = data
        for target in self.poster_inflight.pop(url, []):
            if isinstance(target, QListWidgetItem):
                self.apply_discovery_artwork(target, url, data)
            else:
                self.display_poster(target, url, data)
        if error:
            self.logmsg(
                f"Artwork unavailable ({urllib.parse.urlparse(url).hostname}): {error}"
            )

    def show_selected_poster(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            self.review_detail_status.setText("Awaiting analysis")
            self.review_detail_action.setEnabled(False)
            self.poster.setPixmap(QPixmap())
            self.poster.setText("Select a result")
            self.preview_info.setText("Choose a row to inspect the match, synopsis, and review status.")
            return
        item = self.items[row]
        self.review_detail_status.setText(
            "STATUS  ·  " + item.get("status", "unknown").upper()
            + ("  —  " + str(item.get("message", ""))[:140] if item.get("message") else "")
        )
        self.review_detail_action.setEnabled(bool(item.get("matches")) and not (
            self.worker and self.worker.isRunning()
        ))
        index = item.get("selected", -1)
        match = (
            item.get("matches", [])[index]
            if 0 <= index < len(item.get("matches", []))
            else None
        )
        if not match:
            self.poster.setPixmap(QPixmap())
            self.poster.setText("No poster available")
            self.preview_info.setText(item.get("message", "No metadata match"))
            return
        obj = match.get("data") or {}
        overview = (obj.get("overview") or "No synopsis available.").strip()
        if len(overview) > 440:
            overview = overview[:437] + "..."
        self.preview_info.setText(
            f"{obj.get('title','Unknown')} ({obj.get('year') or '?'})\n"
            f"{match.get('type', 'unknown').upper()} · {match.get('app', 'unknown').title()} · Match score: {match.get('score', 0):.0%}\n"
            f"{match_confidence(match, item.get('matches', []))}\n"
            f"{item.get('message', '')}\n\n{overview}"
        )
        self.fetch_poster(match, self.poster)

    def edit_selected_title(self):
        """Correct one input and recheck its metadata and library status only."""
        if self.worker and self.worker.isRunning():
            return
        row = self.table.currentRow()
        if not 0 <= row < len(self.items):
            return
        if not self.server_data:
            QMessageBox.warning(self, "Not connected", "Connect to your servers before rechecking a title.")
            return
        previous = self.items[row]["input"]
        updated, accepted = QInputDialog.getText(
            self, "Correct input title", "Title, optionally prefixed movie: / tv: / anime:",
            text=previous,
        )
        if not accepted:
            return
        updated = updated.strip()
        if not updated or updated == previous:
            return
        lines = self.input.toPlainText().splitlines()
        if previous not in lines:
            QMessageBox.warning(
                self, "Input changed",
                "The original title is no longer in the input list. Analyze the updated list first.",
            )
            return
        if updated in lines and updated != previous:
            QMessageBox.warning(
                self, "Duplicate input",
                "That corrected title is already in the input list. Choose a distinct title.",
            )
            return
        lines[lines.index(previous)] = updated
        self.input.setPlainText("\n".join(lines))
        self._edit_recheck_row = row
        self.active_analysis_rows = [row]
        self._edit_recheck_previous = list(self.items)
        self.items[row] = {
            "input": updated, "matches": [], "selected": -1,
            "status": "working", "message": "Rechecking corrected title",
            "action": "review",
        }
        self.refresh()
        self.logmsg(f"Rechecking corrected title: {previous} -> {updated}")
        self.run_worker("analyze", items=[updated], done=self.edited_title_analyzed)

    def edited_title_failed(self, error):
        """Make a failed recheck explicit rather than leaving a working placeholder."""
        row = getattr(self, "_edit_recheck_row", -1)
        if 0 <= row < len(self.items):
            self.items[row]["status"] = "error"
            self.items[row]["action"] = "review"
            self.items[row]["message"] = "Title recheck failed — retry before importing"
            self.refresh()
        self._edit_recheck_row = -1
        self._edit_recheck_previous = []

    def edited_title_analyzed(self, results):
        row = getattr(self, "_edit_recheck_row", -1)
        if 0 <= row < len(self.items):
            if results:
                self.items[row] = results[0]
                self.apply_category_decisions(results[:1])
            else:
                self.items[row].update({
                    "status": "error",
                    "action": "review",
                    "message": "Recheck returned no results — retry analysis before importing",
                })
        self._edit_recheck_row = -1
        self._edit_recheck_previous = []
        self.refresh()
        if 0 <= row < len(self.items):
            self.table.selectRow(row)

    def review_row(self, row, column):
        """Open the correction dialog directly from the selected review row."""
        if row < 0 or row >= len(self.items):
            return
        if not self.items[row].get("matches"):
            return
        self.table.selectRow(row)
        self.review()

    def review(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            QMessageBox.information(
                self, "Select a title", "Select a row in the results table first."
            )
            return
        item = self.items[row]
        if not item["matches"]:
            QMessageBox.information(
                self,
                "No matches",
                "Try a more specific title or year and analyze again.",
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Verify match — " + item["input"])
        dialog.resize(700, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Select the correct title. Artwork and synopsis update as you browse:"
            )
        )
        body = QHBoxLayout()
        layout.addLayout(body)
        choices = QListWidget()
        body.addWidget(choices, 2)
        right = QVBoxLayout()
        body.addLayout(right, 1)
        poster = QLabel("Loading poster...")
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setFixedSize(150, 215)
        right.addWidget(poster)
        synopsis = QLabel()
        synopsis.setWordWrap(True)
        synopsis.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(synopsis)
        for m in item["matches"]:
            choices.addItem(f"{m['label']} · {match_confidence(m, item['matches'])} · score {m['score']:.0%}")

        def update_match(idx):
            if idx < 0:
                return
            match = item["matches"][idx]
            obj = match["data"]
            overview = obj.get("overview") or "No synopsis available"
            synopsis.setText(overview[:330] + ("..." if len(overview) > 330 else ""))
            self.fetch_poster(match, poster)

        choices.currentRowChanged.connect(update_match)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        choices.setCurrentRow(max(0, item["selected"]))
        if dialog.exec() == QDialog.DialogCode.Accepted and choices.currentRow() >= 0:
            previous = item.get("selected", -1)
            selected = choices.currentRow()
            if selected != previous:
                QMessageBox.information(
                    self,
                    "Reanalysis required",
                    "Selecting another metadata ID requires a fresh library check. "
                    "Update the input title to identify your preferred match and run Analyze again "
                    "so duplicate detection remains accurate.",
                )
                return
            item["selected"] = selected
            item["status"] = "duplicate" if item.get("duplicate") else "ready"
            item["message"] = (
                "Already in library — choose Skip / Upgrade / Replace"
                if item.get("duplicate")
                else "Manually confirmed against metadata and poster"
            )
            self.logmsg(
                f"User confirmed {item['input']} -> {item['matches'][item['selected']]['label']}"
            )
            self.refresh()
            self.table.selectRow(row)
            self.show_selected_poster()

    def duplicate_action(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            QMessageBox.information(
                self, "Select a title", "Select a library result first."
            )
            return
        item = self.items[row]
        if not item.get("duplicate"):
            QMessageBox.information(
                self,
                "Not in library",
                "This title was not detected in your existing library.",
            )
            return
        d = item["duplicate"]
        box = QMessageBox(self)
        box.setWindowTitle("Existing library title — choose action")
        box.setText(
            f"{d['title']} is already in {d['app'].title()}.\nDetected files: {d['files']}"
            + (f" / {d['total']} episodes" if d["total"] else "")
        )
        box.setInformativeText(
            "Skip keeps everything unchanged. Upgrade requests a search for a better release. Replace requests a fresh search while preserving existing files until Radarr/Sonarr handles replacement. No files are deleted by Bulkrr."
        )
        skip = box.addButton("Skip", QMessageBox.ButtonRole.AcceptRole)
        upgrade = box.addButton("Upgrade / search", QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton(
            "Replace / search again", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        choice = box.clickedButton()
        if choice not in (skip, upgrade, replace):
            return
        action = (
            "skip" if choice == skip else "upgrade" if choice == upgrade else "replace"
        )
        item["action"] = action
        item["status"] = "skipped" if action == "skip" else "ready"
        item["message"] = {
            "skip": "Existing title — skipped (files preserved)",
            "upgrade": "Upgrade search approved — files preserved",
            "replace": "Replacement search approved — files preserved",
        }[action]
        self.logmsg(
            f"Duplicate action for {item['input']}: {action}; existing media will not be deleted"
        )
        self.refresh()
        self.table.selectRow(row)

    def skip_selected_rows(self):
        """Exclude only explicitly selected rows, without network writes."""
        if self.worker and self.worker.isRunning():
            return
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        candidates = [
            row for row in rows
            if 0 <= row < len(self.items)
            and self.items[row].get("status") in ("ready", "review", "duplicate", "error")
        ]
        if not candidates:
            return
        if QMessageBox.question(
            self, "Exclude selected titles",
            f"Exclude {len(candidates)} selected title(s) from this import preview?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        for row in candidates:
            item = self.items[row]
            item["status"] = "skipped"
            item["action"] = "skip"
            item["message"] = "Excluded from import by user selection"
        self.logmsg(f"Excluded {len(candidates)} selected titles (preview only)")
        self.refresh()

    def restore_selected_rows(self):
        """Undo manual exclusions without approving an uncertain metadata match."""
        if self.worker and self.worker.isRunning():
            return
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        count = 0
        for row in rows:
            if not 0 <= row < len(self.items):
                continue
            item = self.items[row]
            if item.get("status") != "skipped" or item.get("message") != "Excluded from import by user selection":
                continue
            item["status"] = "review" if item.get("matches") else "error"
            item["action"] = "review" if item.get("matches") else "skip"
            item["message"] = "Restored exclusion — verify match before approving"
            count += 1
        if count:
            self.logmsg(f"Restored {count} manually excluded title(s) for review")
            self.refresh()

    def skip_all_duplicates(self):
        if self.worker and self.worker.isRunning():
            return
        candidates = [item for item in self.items if item.get("duplicate")
                      and item.get("status") == "duplicate"]
        if not candidates:
            return
        if QMessageBox.question(
            self, "Skip existing titles",
            f"Skip {len(candidates)} existing library title(s)? No files will be changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        for item in candidates:
            item["action"] = "skip"
            item["status"] = "skipped"
            item["message"] = "Existing title — skipped in bulk (files preserved)"
        self.logmsg(f"Bulk skipped {len(candidates)} existing library titles")
        self.refresh()

    def skip_all_unresolved(self):
        if self.worker and self.worker.isRunning():
            return
        candidates = [item for item in self.items
                      if item.get("status") in ("review", "error")]
        if not candidates:
            return
        if QMessageBox.question(
            self, "Skip unresolved matches",
            f"Skip {len(candidates)} ambiguous or unmatched title(s)? "
            "Only already-confirmed titles will remain eligible for import.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        for item in candidates:
            item["status"] = "skipped"
            item["action"] = "skip"
            item["message"] = "Unresolved match — skipped in bulk"
        self.logmsg(f"Bulk skipped {len(candidates)} unresolved matches")
        self.refresh()

    def clear_analysis(self):
        if self.worker and self.worker.isRunning():
            return
        if QMessageBox.question(
            self, "Start new list",
            "Clear the current input list and analysis results?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.items = []
        self.input.clear()
        self.refresh()
        self.logmsg("Cleared analysis and input list")

    def import_items(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        if not self.settings or not self.server_data:
            QMessageBox.warning(
                self, "Setup needed", "Save your connection preferences first."
            )
            return
        # Reject malformed review selections rather than raising during approval.
        malformed_selection = [
            i for i in self.items
            if i.get("status") == "ready"
            and (
                not isinstance(i.get("selected"), int)
                or isinstance(i.get("selected"), bool)
                or i.get("selected", -1) < 0
            )
        ]
        if malformed_selection:
            QMessageBox.warning(
                self, "Invalid review selection",
                f"{len(malformed_selection)} ready title(s) have invalid match selections. "
                "Reanalyze or review them before importing.",
            )
            return
        pending = [
            i for i in self.items if i["status"] == "ready" and i["selected"] >= 0
        ]
        # Input names are also result correlation keys. Empty names cannot be
        # mapped safely to the approved rows.
        unnamed = [item for item in pending if not str(item.get("input", "")).strip()]
        if unnamed:
            QMessageBox.warning(
                self, "Missing approved titles",
                f"{len(unnamed)} approved row(s) have no input title. "
                "Correct or remove them before importing.",
            )
            return
        duplicate_inputs = set()
        seen_inputs = set()
        for item in pending:
            key = " ".join(str(item.get("input", "")).split()).casefold()
            if key in seen_inputs:
                duplicate_inputs.add(key)
            seen_inputs.add(key)
        if duplicate_inputs:
            QMessageBox.warning(
                self, "Duplicate approved titles",
                f"{len(duplicate_inputs)} title name(s) appear more than once in the "
                "approved batch. Remove or resolve duplicates before importing.",
            )
            return
        unfinished = sum(
            item.get("status") == "working"
            or item.get("message") == "Analysis stopped before lookup"
            for item in self.items
        )
        if unfinished:
            QMessageBox.warning(
                self, "Analysis incomplete",
                f"{unfinished} title(s) are still being analyzed or awaiting resume. "
                "Finish or resolve them before approving an import.",
            )
            return
        yellow = sum(i["status"] == "review" for i in self.items)
        unresolved = sum(i["status"] == "duplicate" for i in self.items)
        if unresolved:
            QMessageBox.warning(
                self,
                "Duplicates need a decision",
                f"{unresolved} existing title(s) need a Skip / Upgrade / Replace choice.",
            )
            return
        if yellow:
            QMessageBox.warning(
                self,
                "Review required",
                f"{yellow} title(s) need confirmation. Select each yellow row and click Confirm.",
            )
            return
        if not pending:
            QMessageBox.information(
                self, "Nothing to import", "No confirmed titles ready."
            )
            return
        invalid = [
            item.get("input", "Unknown title")
            for item in pending
            if not isinstance(item.get("matches"), list)
            or not 0 <= item["selected"] < len(item["matches"])
            or not isinstance(item["matches"][item["selected"]], dict)
            or item["matches"][item["selected"]].get("app") not in ("radarr", "sonarr")
            or item["matches"][item["selected"]].get("type") not in ("movie", "series", "anime")
            or not isinstance(item["matches"][item["selected"]].get("data"), dict)
            or not str(item["matches"][item["selected"]].get("id") or "").strip()
            or not re.fullmatch(
                r"[0-9]{1,18}",
                str(item["matches"][item["selected"]].get("id") or ""),
            )
            or not str(item["matches"][item["selected"]].get("id") or "").strip("0")
            or not str(
                item["matches"][item["selected"]].get("data", {}).get("title") or ""
            ).strip()
            or (
                item["matches"][item["selected"]].get("app") == "radarr"
                and item["matches"][item["selected"]].get("type") != "movie"
            )
            or (
                item["matches"][item["selected"]].get("app") == "sonarr"
                and item["matches"][item["selected"]].get("type") == "movie"
            )
        ]
        invalid_actions = [
            item.get("input", "Unknown title")
            for item in pending
            if (
                not isinstance(item.get("action", "add"), str)
                or item.get("action", "add") not in ("add", "skip", "upgrade", "replace")
            )
        ]
        if invalid_actions:
            QMessageBox.warning(
                self, "Invalid import actions",
                f"{len(invalid_actions)} approved title(s) have unknown actions. "
                "Review them before importing: " + ", ".join(invalid_actions[:5]),
            )
            return
        if invalid:
            QMessageBox.warning(
                self, "Invalid approved matches",
                f"{len(invalid)} title(s) have missing or invalid selected metadata. "
                "Recheck these titles before importing: " + ", ".join(invalid[:5]),
            )
            return
        dry_run = self.dry_run.isChecked()
        # The visible checkbox is authoritative for this import, even if the
        # user has not saved connection preferences again.
        search_after_approval = self.search.isChecked()
        action = (
            "and request searches for missing content"
            if search_after_approval
            else "without starting searches"
        )
        if (
            QMessageBox.question(
                self,
                "Approve dry run" if dry_run else "Approve import",
                (
                    f"Preview {len(pending)} confirmed title(s)?\n\nNo Radarr/Sonarr changes will be made."
                    if dry_run
                    else f"Add {len(pending)} confirmed title(s) {action}?\n\nThis will change your Radarr/Sonarr libraries."
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.active_dry_run = dry_run
        self.active_import_rows = [
            i for i, item in enumerate(self.items)
            if item["status"] == "ready" and item["selected"] >= 0
        ]
        self.logmsg(
            f"Import approved for {len(pending)} titles; automatic searches={'on' if search_after_approval else 'off'}"
        )
        # Freeze the exact approved matches and actions before changing GUI
        # statuses; the worker must not share mutable review dictionaries.
        approved_snapshot = copy.deepcopy(pending)
        for item in pending:
            item["status"] = "working"
            item["message"] = "Queued for import"
        self.refresh()
        self.run_worker(
            "import",
            items=approved_snapshot,
            config={**self.settings, "dry_run": dry_run, "search": search_after_approval},
            done=self.imported,
        )

    def import_failed(self, error):
        """Do not leave queued import rows looking indefinitely in progress."""
        for row in getattr(self, "active_import_rows", []):
            if 0 <= row < len(self.items) and self.items[row].get("status") == "working":
                self.items[row]["status"] = "failed"
                self.items[row]["message"] = "Import interrupted — verify server state before retrying"
        self.active_import_rows = []
        self.refresh()
        self.logmsg("Import worker failed; verify Radarr/Sonarr before retrying")

    def imported(self, results):
        # The approved import snapshot supplies stable row identities. Never
        # update an unrelated row that happens to share an input title.
        rows = getattr(self, "active_import_rows", [])
        pending = {
            self.items[row]["input"]: row
            for row in rows
            if 0 <= row < len(self.items)
        }
        processed = set()
        succeeded = 0
        failed = 0
        for name, status, message in results:
            row = pending.get(name)
            if row is None:
                self.logmsg(f"Ignored unexpected import result for {name}")
                continue
            if row in processed:
                self.logmsg(f"Ignored duplicate import result for {name}")
                continue
            item = self.items[row]
            if item.get("status") not in ("ready", "working", "done", "failed"):
                continue
            item["status"] = (
                ("ready" if status == "green" else "failed")
                if getattr(self, "active_dry_run", False)
                else ("done" if status == "green" else "failed")
            )
            item["message"] = message
            processed.add(row)
            if status == "green":
                succeeded += 1
            else:
                failed += 1
        for row in rows:
            if 0 <= row < len(self.items) and row not in processed:
                item = self.items[row]
                if item.get("status") == "working":
                    item["status"] = "failed"
                    item["message"] = "No import result received — verify server state before retrying"
                    failed += 1
        self.active_import_rows = []
        self.refresh()
        self.logmsg(
            f"{'Dry run finished' if getattr(self, 'active_dry_run', False) else 'Import finished'}: "
            f"{succeeded} {'simulated' if getattr(self, 'active_dry_run', False) else 'successful'}, "
            f"{failed} failed."
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ASSET_DIR / "Bulkrr.ico")))
    pix = QPixmap(str(ASSET_DIR / "Bulkrr-splash.png"))
    splash = QSplashScreen(pix) if not pix.isNull() else None
    if splash:
        splash.show()
        app.processEvents()
    w = Main()

    # Let the splash remain visible briefly without blocking startup.
    def show_main():
        w.show()
        if splash:
            splash.finish(w)

    QTimer.singleShot(1800 if splash else 0, show_main)
    sys.exit(app.exec())
