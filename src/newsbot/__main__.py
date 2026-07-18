"""Enable ``python -m newsbot`` to run the CLI.

Delegates to :func:`newsbot.main.main` so the module-execution form and the
``newsbot`` console script share one implementation.
"""

from __future__ import annotations

import sys

from newsbot.main import main

if __name__ == "__main__":
    sys.exit(main())
