"""Enable ``python -m nova`` (used by the CLI and the GitHub Action)."""

from .main import main

if __name__ == "__main__":
    main()
