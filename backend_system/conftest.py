"""Pytest bootstrap: make `backend_system` (not the repo root) win `import shop`.

`tests/` carries `__init__.py`, so pytest inserts the first non-package
parent (`De_data_test/`) into `sys.path` — where an unrelated outer `shop/`
folder can shadow this package. Pinning this directory first keeps imports
unambiguous no matter what sits next to it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
