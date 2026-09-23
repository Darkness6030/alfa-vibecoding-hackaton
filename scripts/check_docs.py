"""Check local Markdown links in the repository documentation."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent


def main():
    errors = []
    files = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    for path in files:
        if not path.exists():
            continue
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith(("#", "app:", "mailto:")):
                continue
            destination = unquote(target.split("#")[0].strip("<>"))
            if destination and not (path.parent / destination).exists():
                errors.append(f"{path.relative_to(ROOT)}: {target}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"{len(files)} Markdown files: local links OK")


if __name__ == "__main__":
    main()
