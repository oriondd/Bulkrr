"""One QApplication shared by all GUI smoke-test modules.

Qt supports only one application instance per process. Keeping a module-level
reference prevents its native C++ instance from being destroyed between test
classes while PySide6 widgets and signal wrappers may still be alive.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

APP = QApplication.instance() or QApplication([])

# Explicitly shut down Qt before Python unloads PySide6 extension modules.
# Qt may otherwise destroy its global application after Python wrappers vanish.
import atexit
import gc

def _shutdown_qt():
    APP.closeAllWindows()
    APP.processEvents()
    gc.collect()
    APP.processEvents()
    APP.quit()

atexit.register(_shutdown_qt)
