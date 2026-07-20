from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path


def zip_paths(paths: list[Path]) -> tuple[str, bytes]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    zip_name = f"clipboard-files-{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                if path.is_dir():
                    zf.writestr(f"{path.name}/", "")
                    for child in path.rglob("*"):
                        archive_name = Path(path.name) / child.relative_to(path)
                        if child.is_dir():
                            zf.writestr(str(archive_name).replace("\\", "/") + "/", "")
                        if child.is_file():
                            zf.write(child, arcname=str(archive_name))
                elif path.is_file():
                    zf.write(path, arcname=path.name)
        return zip_name, zip_path.read_bytes()


def extract_zip_to_downloads(zip_bytes: bytes, download_dir: Path) -> list[Path]:
    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / time.strftime("clipboard-files-%Y%m%d-%H%M%S")
    target.mkdir()
    zip_path = target / "clipboard-files.zip"
    zip_path.write_bytes(zip_bytes)
    top_level_names: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        target_root = target.resolve()
        for member in zf.infolist():
            member_target = (target / member.filename).resolve()
            if target_root not in (member_target, *member_target.parents):
                raise ValueError(f"unsafe zip member path: {member.filename}")
            top_level = Path(member.filename).parts[0] if Path(member.filename).parts else ""
            if top_level:
                top_level_names.add(top_level)
        zf.extractall(target)
    zip_path.unlink(missing_ok=True)
    extracted_paths = [target / name for name in sorted(top_level_names)]
    return [path for path in extracted_paths if path.exists()] or [target]

