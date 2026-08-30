#!/usr/bin/env python3
"""
Entry point wrapper for PyInstaller binary.
This ensures the vicoa package is properly set up before running the CLI.
"""

import sys

if __name__ == "__main__":
    # When frozen by PyInstaller, sys._MEIPASS contains the extracted bundle directory
    # PyInstaller's bootloader automatically adds it to sys.path, so we don't need to
    # manipulate sys.path here unless there are conflicts

    # Import and run the CLI
    from vicoa.cli import main

    sys.exit(main())
