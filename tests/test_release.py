"""Release packaging must stay source-only and preserve previous artifacts."""

import zipfile
import pytest
from scripts.build_release import build, collect, RUNTIME_FILES


@pytest.fixture
def source(tmp_path):
    for name in ("app/main.py", *RUNTIME_FILES):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic fixture\n")
    return tmp_path


def test_archive_excludes_extra_files_and_is_reproducible(source):
    for name in (".env", "dump.bin", "notes.md"):
        (source / "app" / name).write_text("synthetic non-runtime content")
    first, second = source / "first.zip", source / "second.zip"
    build(source, first)
    build(source, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {"app/main.py", *RUNTIME_FILES}
    with pytest.raises(FileExistsError):
        build(source, first)


def test_archive_rejects_file_symlink(source):
    (source / "app" / "linked.py").symlink_to(source / "app" / "main.py")
    with pytest.raises(ValueError, match="symlink"):
        collect(source)


def test_archive_rejects_root_directory_symlink(source):
    (source / "app").rename(source / "real_app")
    (source / "app").symlink_to(source / "real_app", target_is_directory=True)
    with pytest.raises(ValueError):
        collect(source)


def test_archive_rejects_configuration_parent_symlink(source):
    (source / "config").rename(source / "real_config")
    (source / "config").symlink_to(source / "real_config", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        collect(source)
