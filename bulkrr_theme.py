"""Bulkrr's centralized Qt stylesheet, independent of application logic."""

DARK_THEME = """
QMainWindow, QWidget { background: #111521; color: #e9eefb; font-size: 13px; }
QMainWindow { background: #0d111b; }
QLineEdit, QTextEdit, QComboBox, QTableWidget, QListWidget {
    background: #1a2130; color: #f2f5ff;
    border: 1px solid #344056; border-radius: 8px; padding: 8px;
    selection-background-color: #624bc3;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QListWidget:focus {
    border: 1px solid #8c79ed;
}
QPushButton {
    background: #6652c9; color: white; border: 1px solid #7764dc;
    border-radius: 8px; padding: 10px 14px; font-weight: 600;
}
QPushButton:hover { background: #7967df; }
QPushButton:pressed { background: #4d3ba5; }
QPushButton:disabled { background: #323a4d; border-color: #323a4d; color: #8c96aa; }
QGroupBox {
    border: 1px solid #354158; border-radius: 10px;
    margin-top: 16px; padding: 14px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
QTabWidget::pane { border: 0; }
QTabBar::tab {
    background: #1c2434; color: #aebbd2; border: 0;
    padding: 13px 20px; margin-right: 3px;
}
QTabBar::tab:selected { background: #5643b2; color: white; }
QTabBar::tab:hover:!selected { background: #2c3750; }
QHeaderView::section {
    background: #222b3c; color: #c8d4eb; border: 0;
    border-bottom: 1px solid #354158; padding: 9px; font-weight: 600;
}
QTableWidget { gridline-color: #2d374b; alternate-background-color: #20293a; }
QScrollBar:vertical { background: #171e2b; width: 12px; }
QScrollBar::handle:vertical { background: #46536b; border-radius: 5px; min-height: 28px; }
QStatusBar { background: #171e2b; color: #b4c3dc; }
QLabel#reviewSummary {
    background: #222b40; border: 1px solid #554b94; border-radius: 10px;
    padding: 14px; color: #e0dafa; font-weight: 600;
}
"""
