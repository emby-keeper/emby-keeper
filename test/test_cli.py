import os
from pathlib import Path
from typer.testing import CliRunner

import tomli as tomllib
from tomlkit import dump
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

def test_check_config(in_temp_dir: Path):
    config = {'telegram': {k: 'Test' for k in ('api_id', 'api_hash', 'phone')}}
    with open('config.toml', 'wb') as f:
        dump(config, f)
    result = runner.invoke(app)
    assert result.exit_code == 251
    assert '配置文件错误' in result.stderr

def test_create_config(in_temp_dir: Path):
    result = runner.invoke(app)
    assert result.exit_code == 250
    assert '生成' in result.stderr
    assert Path("config.toml").exists()
    with open("config.toml", 'rb') as f:
        config = tomllib.load(f)
    assert check_config(config)
    
def test_fail():
    result = runner.invoke(app, ['nonexisting.toml'])
    assert result.exit_code == 1
    assert '关键错误' in result.stderr
