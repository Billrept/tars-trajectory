SOLVER_VERSION = "1.0.0"
MODEL_VERSION = "patched_conic_approx_v1"
import hashlib
from pathlib import Path
_root=Path(__file__).parent
SOLVER_DIGEST=hashlib.sha256(b''.join(str(p.relative_to(_root)).encode()+p.read_bytes() for p in sorted(_root.rglob('*.py')) if p.name!='__init__.py')).hexdigest()
