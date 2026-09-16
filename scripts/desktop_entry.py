"""PyInstaller entry point; keep the package imports absolute."""

from slitlamp.app import main

if __name__ == "__main__":
    raise SystemExit(main())
