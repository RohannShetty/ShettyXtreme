"""Mock external dependencies before terminal subpackage imports."""
import sys
from unittest.mock import MagicMock

# dhanhq is not installed in test env; mock it so terminal.__init__
# (which imports app.py → dhan.py → dhanhq) doesn't crash at import time.
_dhan_mock = MagicMock()
sys.modules.setdefault("dhanhq", _dhan_mock)
sys.modules.setdefault("dhanhq.dhanhq", MagicMock())
