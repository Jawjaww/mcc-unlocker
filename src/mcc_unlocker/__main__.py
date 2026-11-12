"""Desktop entry point; no command line needed for the packaged app."""

import sys

from mcc_unlocker.cli import main


if __name__ == "__main__":
    if len(sys.argv) == 1:
        from mcc_unlocker.ui.launcher_app import main as launcher_main

        raise SystemExit(launcher_main(sys.argv))
    raise SystemExit(main())
