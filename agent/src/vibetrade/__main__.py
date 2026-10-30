"""Executable package entrypoint for python -m vibetrade."""

import sys
from src.vibetrade.cli import main

if __name__ == "__main__":
    sys.exit(main())
