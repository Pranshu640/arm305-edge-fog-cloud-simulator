"""Create the single submission archive without local caches or environments."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["app.py", "cli.py", "requirements.txt", "README.md", "docs/ARM305_Project_Report.pdf",
            "docs/ARM305_Presentation.pptx", "docs/architecture.svg", "results/summary.csv",
            "results/comparison.png", "results/experiments.json", "evidence/test-results.txt",
            "evidence/browser-check.json"]


def main():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit(f"Missing deliverables: {missing}")
    destination = ROOT / "output" / "ARM305_Submission.zip"
    destination.parent.mkdir(exist_ok=True)
    files = [ROOT / f for f in ["app.py", "cli.py", "requirements.txt", "requirements-lock.txt", "README.md"]]
    for folder in ["simulator", "tests", "docs", "results", "evidence", "tools", ".streamlit"]:
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(set(files)):
            archive.write(file, str(Path("ARM305_Continuum") / file.relative_to(ROOT)))
    with zipfile.ZipFile(destination) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"Archive integrity check failed: {bad}")
    print(f"Created {destination} ({destination.stat().st_size:,} bytes; {len(set(files))} files)")


if __name__ == "__main__":
    main()
