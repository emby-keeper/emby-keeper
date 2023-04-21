import os
from pathlib import Path
from typer.testing import CliRunner

import tomli as tomllib
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
    assert '生成' in result.stderr
    assert result.exit_code != 0
    with open("config.toml", 'rb') as f:
        config = tomllib.load(f)
    assert check_config(config)
    
def test_fail():
    result = runner.invoke(app, ['nonexisting.toml'])
    assert '关键错误' in result.stderr
    assert result.exit_code != 0