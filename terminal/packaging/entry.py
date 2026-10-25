"""Entry script for the PyInstaller bundle.

PyInstaller needs a real file to analyse, so the console script from
``pyproject.toml`` gets a tiny wrapper of its own.
"""

from lector_tui.__main__ import main

if __name__ == "__main__":
    main()
