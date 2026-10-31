"""OS-native writable configuration directory selection."""
import os
import sys
from pathlib import Path


def config_dir(home=None, environ=None, platform=None):
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    if platform == "win32":
        root = env.get("APPDATA")
        return (Path(root) if root else home / "AppData" / "Roaming") / "Bulkrr"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Bulkrr"
    root = env.get("XDG_CONFIG_HOME")
    return (Path(root) if root and Path(root).is_absolute() else home / ".config") / "Bulkrr"
