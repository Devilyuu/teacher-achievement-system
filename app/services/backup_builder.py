import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile


def build_system_backup(
    database_path: Path,
    upload_dir: Path,
    export_dir: Path,
) -> Path:
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise FileNotFoundError(database_path)

    backup_dir = export_dir / "backups" / uuid4().hex
    backup_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = backup_dir / "app.sqlite3"
    _create_sqlite_snapshot(database_path, snapshot_path)

    material_files = _material_files(upload_dir)
    generated_at = datetime.now().astimezone()
    backup_path = backup_dir / (
        f"teacher_achievement_backup_{generated_at:%Y%m%d_%H%M%S}.zip"
    )
    manifest = {
        "generated_at": generated_at.isoformat(),
        "database_file": "database/app.sqlite3",
        "material_file_count": len(material_files),
        "material_total_bytes": sum(path.stat().st_size for path in material_files),
    }

    with ZipFile(backup_path, "w", ZIP_DEFLATED) as archive:
        archive.write(snapshot_path, "database/app.sqlite3")
        upload_root = upload_dir.resolve()
        for material_path in material_files:
            relative_path = material_path.relative_to(upload_root)
            archive.write(material_path, (Path("uploads") / relative_path).as_posix())
        archive.writestr(
            "backup_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    return backup_path


def _create_sqlite_snapshot(source_path: Path, target_path: Path) -> None:
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _material_files(upload_dir: Path) -> list[Path]:
    if not upload_dir.exists():
        return []
    upload_root = upload_dir.resolve()
    files = []
    for path in upload_root.rglob("*"):
        resolved = path.resolve()
        if resolved.is_file() and resolved.is_relative_to(upload_root):
            files.append(resolved)
    return sorted(files)
