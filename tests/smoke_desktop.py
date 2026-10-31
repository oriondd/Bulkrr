"""Offscreen startup smoke test for the packaged desktop application's main window.

Run with QT_QPA_PLATFORM=offscreen python tests/smoke_desktop.py
This verifies UI construction without starting imports or network searches.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from bulkrr import Main


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = Main()
    window.show()
    app.processEvents()

    assert window.isVisible(), "Bulkrr main window did not become visible"
    assert window.tabs.count() >= 5, "Expected Bulkrr workspaces were not constructed"
    assert window.tabs.indexOf(window.discover_page) >= 0, "Discover workspace is missing"
    assert window.discover_results is not None, "Discover catalog was not initialized"
    assert window.dashboard_featured is not None, "Dashboard featured catalog is missing"

    QTimer.singleShot(200, app.quit)
    result = app.exec()
    window.close()
    if result:
        raise SystemExit(result)
    print("Bulkrr offscreen desktop startup smoke test passed")


if __name__ == "__main__":
    main()
