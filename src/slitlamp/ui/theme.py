STYLE = """
QWidget { color: #e8edf5; font-family: 'Segoe UI', 'Arial'; font-size: 13px; }
QMainWindow, QDialog { background: #0d1523; }
QFrame#panel { background: #162234; border: 1px solid #25334a; border-radius: 10px; }
QLabel#brand { color: #f8fafc; font-size: 23px; font-weight: 700; letter-spacing: 3px; }
QLabel#eyebrow { color: #59d4c3; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#patientTitle { font-size: 24px; font-weight: 600; }
QLabel#muted { color: #99aac0; }
QLabel#preview { background: #070d16; border: 1px solid #25334a; border-radius: 8px; color: #7f91aa; }
QPushButton { background: #22324a; border: 1px solid #34435c; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #2e425f; border-color: #6693ab; }
QPushButton:pressed { background: #0c786e; }
QPushButton:disabled { color: #65728a; background: #192333; border-color: #243247; }
QPushButton#primary { color: #062c29; background: #58ddc6; border: 0; font-weight: 700; padding: 13px 18px; }
QPushButton#primary:hover { background: #83eddc; }
QPushButton#primary:disabled { background: #204544; color: #7d9e9b; }
QPushButton#danger { background: #643443; border-color: #94516a; }
QPushButton:checked { background: #126e69; border-color: #58ddc6; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
 background: #0e1929; border: 1px solid #34435c; border-radius: 5px; padding: 6px; selection-background-color: #116a65;
}
QComboBox QAbstractItemView { background: #162234; selection-background-color: #185f5b; }
QListWidget, QTableWidget, QTreeWidget { background: #101c2d; border: 1px solid #25334a; border-radius: 6px; outline: none; alternate-background-color: #17263a; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #223047; }
QListWidget::item:selected, QTableWidget::item:selected { background: #1a4f50; color: #f8ffff; }
QListWidget::item:hover { background: #20334b; }
QHeaderView::section { background: #20314a; border: 0; padding: 7px; }
QTabWidget::pane { border: 1px solid #2a3b51; border-radius: 5px; }
QTabBar::tab { background: #162234; color: #9caec5; padding: 9px 12px; }
QTabBar::tab:selected { color: #64e1ce; border-bottom: 2px solid #64e1ce; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #0d1523; width: 10px; }
QScrollBar::handle:vertical { background: #3a4e69; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QGroupBox { border: 1px solid #30425d; border-radius: 7px; margin-top: 16px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; color: #a6bad2; }
QSplitter::handle { background: #0d1523; }
QStatusBar { color: #a9bad0; background: #101d2f; }
QToolTip { background: #28405b; color: white; border: 1px solid #608099; padding: 6px; }
QMenu { background: #17263b; border: 1px solid #3c526e; }
QMenuBar { background: #101d2f; color: #c9d7e7; }
QMenuBar::item { background: transparent; padding: 5px 12px; }
QMenuBar::item:selected { background: #1a6861; }
QMenu::item { padding: 7px 16px; }
QMenu::item:selected { background: #1a6861; }
"""
