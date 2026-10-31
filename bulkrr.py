import sys, json, re, os, difflib, urllib.request, urllib.parse, urllib.error, datetime, traceback, logging
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer
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
    QSplitter,
    QSplashScreen,
    QFileDialog,
)

ASSET_DIR = Path(__file__).resolve().parent
APPDIR = Path(os.getenv("APPDATA") or Path.home()) / "Bulkrr"
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
from bulkrr_library import missing_movies, missing_series
from bulkrr_bulk import plan_searches, estimate_storage
from bulkrr_discovery import normalize_discovery, queue_lines, upcoming


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
            if self.task == "connect":
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
            elif self.task == "library_scan":
                result = {"movies": [], "series": [], "errors": []}
                for app, endpoint, target, parser in (("radarr", "movie", "movies", missing_movies), ("sonarr", "series", "series", missing_series)):
                    if app not in self.connections:
                        continue
                    try:
                        result[target] = parser(self.call(app, endpoint))
                    except Exception as exc:
                        result["errors"].append(f"{app.title()}: {exc}")
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
                self.finished_data.emit(out)
            elif self.task == "import":
                results = []
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
                        existing = self.call(app, endpoint)
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
                            if not folder or not profile:
                                results.append(
                                    (
                                        item["input"],
                                        "red",
                                        "Missing root folder or quality profile",
                                    )
                                )
                                continue
                            description = f"Would add to {app.title()} in {folder} (quality profile {profile})"
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
                    if found:
                        action = item.get("action", "skip")
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
                    if not folder or not profile:
                        results.append(
                            (
                                item["input"],
                                "red",
                                "Missing root folder or quality profile",
                            )
                        )
                        continue
                    obj["rootFolderPath"] = folder
                    obj["qualityProfileId"] = int(profile)
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
                        self.call(app, endpoint, "POST", obj)
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
        self.setWindowIcon(QIcon(str(ASSET_DIR / "Bulkrr.ico")))
        self.resize(1120, 800)
        self.connections = {}
        self.server_data = {}
        self.items = []
        self.worker = None
        self.poster_cache = {}
        self.poster_workers = []
        self.poster_inflight = {}
        self.poster_target = None
        self.settings = self.load_settings()
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
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
        self.connect_btn = QPushButton("Test connections and load settings")
        self.connect_btn.clicked.connect(self.connect_servers)
        self.setup_layout.addWidget(self.connect_btn)
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
        v.addWidget(
            QLabel(
                "Paste one title per line. Optional prefixes: movie:, tv:, anime:. Year optional: (2012)."
            )
        )
        self.input = TitleInput()
        self.input.files_dropped.connect(self.import_files)
        self.input.setAcceptDrops(True)
        self.input.setPlaceholderText(
            "movie: The Raid (2011)\ntv: Breaking Bad (2008)\nanime: Death Note (2006)"
        )
        v.addWidget(QLabel("Drop .txt or .csv files here, or paste titles below."))
        v.addWidget(self.input)
        source_row = QHBoxLayout()
        for label, handler in (
            ("Import TXT / CSV", self.choose_import_files),
            ("Save title list", self.save_import_session),
            ("Load title list", self.resume_import_session),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            source_row.addWidget(button)
        v.addLayout(source_row)
        self.analyze_btn = QPushButton("Analyze titles (no changes)")
        self.analyze_btn.clicked.connect(self.analyze)
        v.addWidget(self.analyze_btn)
        self.review_summary_label = QLabel(review_summary([]))
        self.review_summary_label.setWordWrap(True)
        self.review_summary_label.setObjectName("reviewSummary")
        v.addWidget(self.review_summary_label)
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
        self.table.setSortingEnabled(False)
        self.table.setMinimumHeight(270)
        self.table.setToolTip("Select a row to inspect its poster and metadata; use Confirm to choose an alternate match.")
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(0, 55)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_poster)
        self.table.itemSelectionChanged.connect(self.update_review_actions)
        v.addWidget(self.table)
        preview = QGroupBox("Selected title — artwork and metadata")
        preview_layout = QHBoxLayout(preview)
        self.poster = QLabel("Select a result to view its poster")
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setFixedSize(112, 160)
        self.poster.setStyleSheet(
            "background:#222a37;border:1px solid #39465a;border-radius:6px;color:#aab2c1"
        )
        preview_layout.addWidget(self.poster)
        self.preview_info = QLabel(
            "The selected metadata match, description and poster will appear here."
        )
        self.preview_info.setWordWrap(True)
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignTop)
        preview_layout.addWidget(self.preview_info, 1)
        v.addWidget(preview)
        row = QHBoxLayout()
        self.duplicate_btn = QPushButton("Existing title: Skip / Upgrade / Replace")
        self.duplicate_btn.clicked.connect(self.duplicate_action)
        row.addWidget(self.duplicate_btn)
        self.review_btn = QPushButton("Confirm / change selected match")
        self.review_btn.clicked.connect(self.review)
        self.add_btn = QPushButton("Approve and import")
        self.add_btn.clicked.connect(self.import_items)
        row.addWidget(self.review_btn)
        row.addWidget(self.add_btn)
        v.addLayout(row)
        tabs.addTab(importer, "2. Import & review")
        library_page = QWidget()
        library_layout = QVBoxLayout(library_page)
        library_layout.addWidget(QLabel("Read-only inventory of missing movies and TV episodes. No searches or changes are made."))
        self.library_scan_btn = QPushButton("Scan connected libraries")
        self.library_scan_btn.clicked.connect(self.scan_library)
        self.library_search_btn = QPushButton("Search selected missing titles")
        self.library_search_btn.clicked.connect(self.search_missing)
        library_layout.addWidget(self.library_search_btn)
        library_layout.addWidget(self.library_scan_btn)
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
        self.library_layout_table = QTableWidget(0, 5)
        self.library_layout_table.setHorizontalHeaderLabels(["Server", "Title", "Year", "Missing", "Monitored"])
        self.library_layout_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        library_layout.addWidget(self.library_summary)
        library_layout.addWidget(self.library_layout_table)
        tabs.addTab(library_page, "3. Library inventory")
        discover_page = QWidget()
        discover_layout = QVBoxLayout(discover_page)
        discover_layout.addWidget(QLabel("Browse metadata from your connected servers; review every title before import."))
        self.discover_kind = QComboBox()
        self.discover_kind.addItems(["movie", "tv", "anime"])
        discover_layout.addWidget(self.discover_kind)
        self.discover_query = QLineEdit()
        self.discover_query.setPlaceholderText("Search for movies, shows or anime")
        discover_layout.addWidget(self.discover_query)
        self.discover_button = QPushButton("Find titles")
        self.discover_button.clicked.connect(self.discover_titles)
        discover_layout.addWidget(self.discover_button)
        self.discover_results = QListWidget()
        self.discover_results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        discover_layout.addWidget(self.discover_results)
        self.discover_add = QPushButton("Add selected titles to import review")
        self.discover_add.clicked.connect(self.queue_discovered)
        discover_layout.addWidget(self.discover_add)
        tabs.addTab(discover_page, "4. Discover")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(
            "Timestamped connection, lookup, import and error details will appear here. A persistent log is saved in AppData\\Roaming\\Bulkrr\\bulkrr.log"
        )
        tabs.addTab(self.log, "Activity log")
        self.tabs = tabs
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
        self.library_entries = rows
        self.library_counts = (len(data["movies"]), sum(show["missing"] for show in data["series"]))
        self.update_storage_estimate()
        self.library_layout_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library_layout_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.library_layout_table.setRowCount(len(rows))
        for row, (app, entry, count) in enumerate(rows):
            for col, value in enumerate((app, entry["title"], entry.get("year") or "—", count, "Yes" if entry["monitored"] else "No")):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.library_layout_table.setItem(row, col, cell)
        summary = f"{len(data['movies'])} missing movies; {sum(s['missing'] for s in data['series'])} missing episodes across {len(data['series'])} shows"
        if data["errors"]:
            summary += " | Errors: " + "; ".join(data["errors"])
        self.library_summary.setText(summary)
        self.logmsg("Library inventory: " + summary)

    def discover_titles(self):
        if self.worker and self.worker.isRunning():
            return
        term = self.discover_query.text().strip()
        if not term:
            QMessageBox.information(self, "Search term", "Enter a title to discover.")
            return
        self.discover_button.setEnabled(False)
        self.run_worker("discover", config={"kind": self.discover_kind.currentText(), "term": term}, done=self.discovered)

    def discovered(self, records):
        self.discover_button.setEnabled(True)
        self.discover_records = records
        self.discover_results.clear()
        for entry in records:
            self.discover_results.addItem(f"{entry['title']} ({entry['year'] or '?'}) — {entry['type']}")
        self.logmsg(f"Discovery returned {len(records)} matching titles")

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
        self.tabs.setCurrentIndex(1)
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
            if entry.get("monitored") and type(entry.get("id")) is int:
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
        logging.info("%s", s)
        self.statusBar().showMessage(s[:150])

    def row_update(self, index, status, message):
        if (
            self.worker
            and self.worker.task == "import"
            and hasattr(self, "active_import_rows")
        ):
            index = (
                self.active_import_rows[index]
                if index < len(self.active_import_rows)
                else -1
            )
        if 0 <= index < len(self.items):
            self.items[index]["status"] = status
            self.items[index]["message"] = message
            self.refresh()

    def run_worker(self, task, items=None, config=None, done=None):
        if self.worker and self.worker.isRunning():
            return
        self.worker = Worker(task, dict(self.connections), items, config)
        self.worker.progress.connect(self.logmsg)
        self.worker.row_progress.connect(self.row_update)
        self.worker.failed.connect(
            lambda e: (
                self.connection_error() if task == "connect" else None,
                self.logmsg("ERROR: " + e),
                QMessageBox.warning(self, "Error", e),
            )
        )
        self.worker.finished_data.connect(done)
        self.worker.finished.connect(self.update_review_actions)
        self.worker.start()
        self.update_review_actions()

    def connection_error(self):
        for app in self.connections:
            self.connection_leds[app].set_status("disconnected")
            self.connection_labels[app].setText("Connection failed — see Activity log")

    def connect_servers(self):
        self.connections = {}
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
        data = {"search": self.search.isChecked()}
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
        APPDIR.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=2))
        self.settings = data
        try:
            import keyring

            for app in self.server_data:
                keyring.set_password("Bulkrr", app, self.key[app].text().strip())
        except Exception:
            QMessageBox.information(
                self,
                "API keys not saved",
                "Install the optional 'keyring' package to securely remember API keys. You can re-enter them next time.",
            )
        self.logmsg("Preferences saved. Ready for bulk imports.")
        QMessageBox.information(
            self, "Ready", "Connected and configured. You can now analyze titles."
        )
        self.tabs.setCurrentIndex(1)

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

    def analyzed(self, items):
        self.items = items
        self.refresh()
        self.logmsg(
            f"Analysis finished: {len(items)} titles; {sum(bool(x.get('duplicate')) for x in items)} existing library titles detected. Review yellow and red duplicate items before importing."
        )

    def refresh(self):
        self.review_summary_label.setText(review_summary(self.items))
        previous_row = self.table.currentRow()
        self.table.blockSignals(True)
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
                if item.get("selected", -1) >= 0 and item.get("matches")
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
                match["label"] if match else "—",
                kind,
                folder or "—",
                quality,
                item["message"],
            )
            led = StatusLED(status)
            led.set_status(status, item["message"])
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.addStretch()
            holder_layout.addWidget(led)
            holder_layout.addStretch()
            self.table.setCellWidget(row, 0, holder)
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
                self.table.setItem(row, col, cell)
        if 0 <= previous_row < len(self.items):
            self.table.selectRow(previous_row)
        self.table.blockSignals(False)
        self.table.viewport().update()
        self.show_selected_poster()
        self.update_review_actions()

    def update_review_actions(self):
        row = self.table.currentRow()
        selected = self.items[row] if 0 <= row < len(self.items) else None
        busy = bool(self.worker and self.worker.isRunning())
        self.review_btn.setEnabled(bool(selected and selected.get("matches")) and not busy)
        self.duplicate_btn.setEnabled(bool(selected and selected.get("duplicate")) and not busy)
        self.add_btn.setEnabled(
            not busy and any(item.get("status") == "ready" for item in self.items)
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
        worker = PosterWorker(url)
        self.poster_workers.append(worker)
        worker.loaded.connect(self.poster_loaded)
        worker.finished.connect(lambda: self.poster_worker_finished(worker))
        worker.start()

    def poster_worker_finished(self, worker):
        if worker in self.poster_workers:
            self.poster_workers.remove(worker)

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
            self.display_poster(target, url, data)
        if error:
            self.logmsg(
                f"Artwork unavailable ({urllib.parse.urlparse(url).hostname}): {error}"
            )

    def show_selected_poster(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            self.poster.setPixmap(QPixmap())
            self.poster.setText("Select a result")
            self.preview_info.setText("Choose a row to inspect the match, synopsis, and review status.")
            return
        item = self.items[row]
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
        obj = match["data"]
        overview = (obj.get("overview") or "No synopsis available.").strip()
        if len(overview) > 440:
            overview = overview[:437] + "..."
        self.preview_info.setText(
            f"{obj.get('title','Unknown')} ({obj.get('year') or '?'})\n"
            f"{match['type'].upper()} · {match['app'].title()} · Match score: {match['score']:.0%}\n"
            f"{match_confidence(match, item.get('matches', []))}\n"
            f"{item['message']}\n\n{overview}"
        )
        self.fetch_poster(match, self.poster)

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

    def import_items(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        if not self.settings or not self.server_data:
            QMessageBox.warning(
                self, "Setup needed", "Save your connection preferences first."
            )
            return
        pending = [
            i for i in self.items if i["status"] == "ready" and i["selected"] >= 0
        ]
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
        dry_run = self.dry_run.isChecked()
        action = (
            "and request searches for missing content"
            if self.settings.get("search", True)
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
            f"Import approved for {len(pending)} titles; automatic searches={'on' if self.settings.get('search',True) else 'off'}"
        )
        for item in pending:
            item["status"] = "working"
            item["message"] = "Queued for import"
        self.refresh()
        self.run_worker(
            "import",
            items=pending,
            config={**self.settings, "dry_run": dry_run},
            done=self.imported,
        )

    def imported(self, results):
        for name, status, message in results:
            for item in self.items:
                if item["input"] == name and item["status"] in (
                    "ready",
                    "working",
                    "done",
                    "failed",
                ):
                    item["status"] = (
                        ("ready" if status == "green" else "failed")
                        if getattr(self, "active_dry_run", False)
                        else ("done" if status == "green" else "failed")
                    )
                    item["message"] = message
                    break
        self.refresh()
        self.logmsg(
            f"{'Dry run finished' if getattr(self, 'active_dry_run', False) else 'Import finished'}: "
            f"{sum(x[1]=='green' for x in results)} {'simulated' if getattr(self, 'active_dry_run', False) else 'successful'}, "
            f"{sum(x[1]=='red' for x in results)} failed."
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
