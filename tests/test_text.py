"""Public text rules: no em or en dashes anywhere a judge reads (README, Devpost draft, UI strings, examples)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = [ROOT / "README.md", ROOT / "docs" / "DEVPOST.md", ROOT / "server" / "examples.py"] + sorted((ROOT / "web" / "src").glob("*.tsx"))


def test_no_em_or_en_dashes():
    bad = []
    for f in FILES:
        if f.exists():
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if "—" in line or "–" in line:
                    bad.append(f"{f.relative_to(ROOT)}:{n}")
    assert not bad, "em/en dashes found: " + ", ".join(bad)
