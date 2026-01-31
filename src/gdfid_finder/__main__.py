"""Allow running as ``python -m gdfid_finder``."""

from __future__ import annotations

import sys

from gdfid_finder.main import main

sys.exit(main())
