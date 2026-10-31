"""Bulkrr's centralized Qt stylesheet, independent of application logic."""

DARK_THEME = """
QMainWindow, QWidget { background: #0b101b; color: #e8edf9; font-size: 13px; }
QWidget:disabled { color: #8995ad; }
QToolTip { background: #202c42; color: #f2f5ff; border: 1px solid #657394; padding: 6px; }
QSplitter::handle { background: #263650; }
QSplitter::handle:hover { background: #6d57df; }
QMainWindow { background: #080d16; }
QLabel { background: transparent; }
QLabel#appTitle { color: #ffffff; font-size: 27px; font-weight: 800; }
QLabel#appSubtitle { color: #a9b6d3; font-size: 12px; }
QWidget#appHeader { background: #10192a; border-bottom: 1px solid #273653; }
QLineEdit, QTextEdit, QComboBox, QTableWidget, QListWidget {
    background: #131d2d; color: #f2f5ff;
    border: 1px solid #2c3b55; border-radius: 9px; padding: 8px;
    selection-background-color: #5746b7;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus {
    border: 1px solid #947cff;
}
QPushButton {
    background: #6d57df; color: #fff; border: 1px solid #8976ed;
    border-radius: 8px; padding: 10px 14px; font-weight: 600;
}
QPushButton:hover { background: #806cf0; }
QPushButton:focus { border: 2px solid #c5b8ff; }
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled { background: #111927; color: #8995ad; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #172238; color: #f2f5ff; selection-background-color: #5141b4; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; }
QTableWidget::item { padding: 5px 7px; }
QTableWidget::item:selected { background: #5141a0; color: #ffffff; }
QTableCornerButton::section { background: #1b2940; border: none; }
QScrollBar:horizontal { background: #111b2b; height: 11px; }
QScrollBar::handle:horizontal { background: #445675; border-radius: 5px; min-width: 28px; }
QPushButton:pressed { background: #5141b4; }
QPushButton:disabled { background: #273246; border-color: #273246; color: #8895ac; }
QPushButton#secondaryAction { background: #172238; border-color: #364665; }
QPushButton#secondaryAction:hover { background: #243451; }
QPushButton#dangerAction { background: #a52d42; border-color: #cc445c; }
QPushButton#dangerAction:hover { background: #c33a51; }
QGroupBox {
    background: #101827; border: 1px solid #293750; border-radius: 12px;
    margin-top: 17px; padding: 16px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #b39aff; }
QTabWidget::pane { border: 1px solid #26334a; border-radius: 10px; background: #0d1421; }
QTabBar::tab {
    background: #141e30; color: #aebbd2; border: 1px solid #25344e;
    border-bottom: 0; border-top-left-radius: 8px; border-top-right-radius: 8px;
    padding: 12px 19px; margin-right: 4px;
}
QTabBar::tab:selected { background: #493c9b; color: white; border-color: #8b71f0; }
QTabBar::tab:hover:!selected { background: #253450; }
QHeaderView::section {
    background: #1b2940; color: #c8d4eb; border: 0;
    border-bottom: 1px solid #364661; padding: 10px; font-weight: 600;
}
QTableWidget { gridline-color: #28384e; alternate-background-color: #172235; }
QScrollBar:vertical { background: #111b2b; width: 11px; }
QScrollBar::handle:vertical { background: #445675; border-radius: 5px; min-height: 28px; }
QStatusBar { background: #111c2e; color: #b4c3dc; }
QLabel#reviewSummary {
    background: #192640; border: 1px solid #574b9c; border-radius: 10px;
    padding: 14px; color: #e0dafa; font-weight: 600;
}
QListWidget#mainNavigation {
    background: #10192a; border: 1px solid #283852;
    border-radius: 12px; padding: 8px; font-size: 14px;
}
QListWidget#mainNavigation::item {
    border-radius: 8px; padding: 14px 10px; margin: 3px;
    color: #b9c7df;
}
QListWidget#mainNavigation::item:selected {
    background: #453a96; color: #fff;
}
QListWidget#mainNavigation::item:hover:!selected { background: #22314b; }
QLabel#categoryPolicy {
    background: #14243a; color: #b8c9e5; border: 1px solid #34496b;
    border-radius: 8px; padding: 10px;
}
"""
