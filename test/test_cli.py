import os
from pathlib import Path
from typer.testing import CliRunner

import tomli as tomllib
import tomlkit
import pytest

import embykeeper
from embykeeper.cli import app
from embykeeper.settings import check_config

runner = CliRunner(mix_stderr=False)


@pytest.fixture()
def in_temp_dir(tmp_path: Path):
    current = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(current)


@pytest.fixture()
def generated_config(in_temp_dir: Path):
    runner.invoke(app)


def test_version():
    result = runner.invoke(app, ["--version"])
    assert embykeeper.__version__ in result.stdout
    assert result.exit_code == 0


def test_create_config(in_temp_dir: Path):
    result = runner.invoke(app)
    print(result.stderr)
    assert "生成" in result.stderr
    assert result.exit_code == 250
    assert Path("config.toml").exists()
    with open("config.toml", "rb") as f:
        config = tomllib.load(f)
    assert not check_config(config)


def test_create_config_empty(in_temp_dir: Path):
    config_file = Path("config.toml")
    config_file.touch()
    result = runner.invoke(app, [str(config_file)])
    print(result.stderr)
    assert "生成" in result.stderr
    assert result.exit_code == 250
    with open("config.toml", "rb") as f:
        config = tomllib.load(f)
    assert config

    config_file.unlink()
    config_file.touch()
    result = runner.invoke(app)
    print(result.stderr)
    assert "生成" in result.stderr
    assert result.exit_code == 250
    with open("config.toml", "rb") as f:
        config = tomllib.load(f)
    assert config

    config_file = Path("empty.toml")
    config_file.touch()
    result = runner.invoke(app, [str(config_file), "--once"])
    assert "生成" not in result.stderr
    assert result.exit_code == 0


def test_nonexist_config(in_temp_dir: Path):
    for fn in ("config.toml", "nonexisting.toml"):
        result = runner.invoke(app, [fn])
        print(result.stderr)
        assert "不存在" in result.stderr
        assert result.exit_code == 251


def test_check_config(in_temp_dir: Path):
    with open("config.toml", "w+") as f:
        f.write("notifier: true")
    result = runner.invoke(app)
    print(result.stderr)
    assert "配置文件错误" in result.stderr
    assert result.exit_code == 252

    config = {"telegram": {k: "Test" for k in ("api_id", "api_hash", "phone")}}
    with open("config.toml", "w+") as f:
        tomlkit.dump(config, f)
    result = runner.invoke(app)
    print(result.stderr)
    assert "配置文件错误" in result.stderr
    assert result.exit_code == 253
