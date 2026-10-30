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
                        self.items.index(item),
                        "working",
                        "Checking for existing library entry...",
                    )
                    endpoint = "movie" if app == "radarr" else "series"
                    existing = self.call(app, endpoint)
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
                        self.items.index(item),
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
                            self.items.index(item), "done", "Added successfully"
                        )
                    except Exception as e:
                        results.append((item["input"], "red", str(e)[:300]))
                        self.progress.emit(f"  Failed: {obj['title']} — {e}")
                        self.row_progress.emit(
                            self.items.index(item), "failed", str(e)[:180]
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
        self.setWindowTitle("Bulkrr — Phase 2 development")
        self.setWindowIcon(QIcon(str(ASSET_DIR / "Bulkrr.ico")))
        self.resize(1000, 740)
        self.connections = {}
        self.server_data = {}
        self.items = []
        self.worker = None
        self.poster_cache = {}
        self.poster_workers = []
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
        self.input.setPlaceholderText(
            "movie: The Raid (2011)\ntv: Breaking Bad (2008)\nanime: Death Note (2006)"
        )
        v.addWidget(self.input)
        source_row = QHBoxLayout()
        for label, handler in (
            ("Import TXT / CSV", self.choose_import_files),
            ("Save session", self.save_import_session),
            ("Resume session", self.resume_import_session),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            source_row.addWidget(button)
        v.addLayout(source_row)
        self.analyze_btn = QPushButton("Analyze titles (no changes)")
        self.analyze_btn.clicked.connect(self.analyze)
        v.addWidget(self.analyze_btn)
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
        self.table.setMinimumHeight(270)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(0, 55)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_poster)
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
        tabs.addTab(importer, "2. Bulk import")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(
            "Timestamped connection, lookup, import and error details will appear here. A persistent log is saved in AppData\\Roaming\\Bulkrr\\bulkrr.log"
        )
        tabs.addTab(self.log, "Activity log")
        self.tabs = tabs
        self.statusBar().showMessage("Connect to Radarr/Sonarr to begin")
        self.setStyleSheet(
            """
          QMainWindow,QWidget {background:#151923;color:#e9edf6;font-size:13px}
          QLineEdit,QTextEdit,QComboBox,QTableWidget {background:#222a37;color:#f3f6fc;border:1px solid #39465a;border-radius:5px;padding:5px}
          QPushButton {background:#2874bd;color:white;border:0;border-radius:6px;padding:9px;font-weight:600}
          QPushButton:hover {background:#358ad9}
          QPushButton:disabled {background:#45505f;color:#aab2c1}
          QGroupBox {border:1px solid #39465a;border-radius:8px;margin-top:12px;padding:10px}
          QTabBar::tab {background:#242b38;padding:11px}
          QTabBar::tab:selected {background:#2874bd}
        """
        )

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
        self.worker.start()

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
        try:
            titles = normalize_titles(
                self.input.toPlainText().splitlines()
                + [title for path in paths for title in read_source(path)]
            )
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, "File import failed", str(error))
            return
        self.input.setPlainText("\n".join(titles))
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
        self.table.viewport().update()
        self.show_selected_poster()

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
        worker = PosterWorker(url)
        self.poster_workers.append(worker)
        worker.loaded.connect(
            lambda fetched, data, error: self.poster_loaded(
                fetched, data, error, target
            )
        )
        worker.finished.connect(
            lambda: (
                self.poster_workers.remove(worker)
                if worker in self.poster_workers
                else None
            )
        )
        worker.start()

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

    def poster_loaded(self, url, data, error, target):
        if data:
            self.poster_cache[url] = data
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
            f"{item['message']}\n\n{overview}"
        )
        self.fetch_poster(match, self.poster)

    def review(self):
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
            choices.addItem(f"{m['label']} · score {m['score']:.0%}")

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
            item["selected"] = choices.currentRow()
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
            i for i, item in enumerate(self.items) if item in pending
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
