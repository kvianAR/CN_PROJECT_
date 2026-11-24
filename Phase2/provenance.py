"""Content fingerprints for Phase 2 helpers and tests, excluding generated runtime files."""
import hashlib
from pathlib import Path


def fingerprint_sources(root):
    root = Path(root)
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / 'Phase2').rglob('*.py'))
            if not any(part in {'runtime', 'certs', '__pycache__'}
                       for part in path.relative_to(root / 'Phase2').parts)}
