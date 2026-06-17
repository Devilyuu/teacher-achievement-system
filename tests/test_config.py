import importlib

from app import config


def test_config_reads_data_dir_and_secret_key_from_environment(monkeypatch, tmp_path):
    custom_data_dir = tmp_path / "teacher-achievement-data"
    monkeypatch.setenv("TEACHER_ACHIEVEMENT_DATA_DIR", str(custom_data_dir))
    monkeypatch.setenv("TEACHER_ACHIEVEMENT_SECRET_KEY", "deployment-secret")

    reloaded = importlib.reload(config)

    try:
        assert reloaded.DATA_DIR == custom_data_dir
        assert reloaded.DATABASE_PATH == custom_data_dir / "database" / "app.sqlite3"
        assert reloaded.UPLOAD_DIR == custom_data_dir / "uploads"
        assert reloaded.EXPORT_DIR == custom_data_dir / "exports"
        assert reloaded.USER_IMPORT_DIR == custom_data_dir / "imports" / "users"
        assert reloaded.SECRET_KEY == "deployment-secret"
    finally:
        monkeypatch.delenv("TEACHER_ACHIEVEMENT_DATA_DIR", raising=False)
        monkeypatch.delenv("TEACHER_ACHIEVEMENT_SECRET_KEY", raising=False)
        importlib.reload(config)
