from __future__ import annotations

import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from clipanywhere.client import main


if __name__ == "__main__":
    main()

