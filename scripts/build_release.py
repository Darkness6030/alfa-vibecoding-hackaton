"""Build a minimal runtime-source ZIP; refuse secrets, links and overwrites."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_FILES = (
    "config/policies.json",
    "config/nginx.conf",
    "docker-compose.tls.yml",
    "Dockerfile",
    "docker-compose.yml",
    "requirements.txt",
    ".dockerignore",
    ".env.example",
    "scripts/generate_demo_secrets.py",
)


def collect(root: Path) -> list[Path]:
    app = root / "app"
    if app.is_symlink() or not app.is_dir():
        raise ValueError("app must be a real directory")
    files = []
    for path in app.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"refusing symlink: {path.relative_to(root)}")
        if (
            path.is_file()
            and path.suffix in {".py", ".html"}
            and "__pycache__" not in path.parts
        ):
            files.append(path)
    for name in RUNTIME_FILES:
        path = root / name
        if any(
            parent.is_symlink()
            for parent in (path, *path.parents)
            if parent != root.parent
        ):
            raise ValueError(f"refusing symlink: {name}")
        if not path.is_file():
            raise FileNotFoundError(name)
        files.append(path)
    return sorted(files)


def build(root: Path, output: Path) -> dict:
    files = collect(root)
    content = {str(p.relative_to(root)): p.read_bytes() for p in files}
    if any(len(data) > 2_000_000 for data in content.values()):
        raise ValueError("unexpected large runtime source")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in content.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("corrupt archive")
    return {
        "archive": str(output),
        "files": len(files),
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", default="0.4.4")
    args = parser.parse_args()
    if not args.version or any(
        c not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-_"
        for c in args.version
    ):
        parser.error("invalid version")
    result = build(ROOT, ROOT / "dist" / f"alfagen-pii-guard-{args.version}.zip")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
