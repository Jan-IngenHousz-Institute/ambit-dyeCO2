"""
main.py — Entry point for the ambit dyeCO2 GUI.

Usage:
    python main.py

Requirements:
    pip install -r requirements.txt
"""

import sys
import os

# Ensure imports resolve correctly when run from any working directory
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ambit dyeCO2 Controller")
    app.setOrganizationName("Ambit")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
