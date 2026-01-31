"""Entry point for running as a module: python -m tray_prusa"""

import sys
from .main import main

if __name__ == "__main__":
    sys.exit(main())
