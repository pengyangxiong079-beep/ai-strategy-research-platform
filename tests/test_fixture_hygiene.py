import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOTS = (ROOT / "tests/fixtures", ROOT / "examples/sample_run")
FORBIDDEN = (
    re.compile(r"[A-Za-z]:[\\/]Users[\\/]", re.IGNORECASE),
    re.compile(r"/(?:Users|home)/[^/\s]+/", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(?:authorization|cookie)\s*:\s*[^\s]+"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password)\s*[:=]\s*[^\s,;]+"),
)


def test_versioned_fixtures_are_anonymous_and_secret_free():
    violations = []
    for root in FIXTURE_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN:
                if pattern.search(text):
                    violations.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not violations, "\n".join(violations)


def test_automated_tests_do_not_reference_private_outputs_or_ignored_artifacts():
    forbidden = ("20260806_113125", "20260806_182326", "20260806_203418", "tests/artifacts")
    references = []
    for path in (ROOT / "tests").glob("test_*.py"):
        if path == Path(__file__):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").replace("\\", "/")
        for token in forbidden:
            if token in text:
                references.append(f"{path.name}: {token}")
    assert not references, "\n".join(references)
