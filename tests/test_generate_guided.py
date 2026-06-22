import sys
import os
import json
import pytest
from unittest.mock import patch, mock_open

# Add assistant directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assistant"))

from generate import extract_json_block, load_example_patch
from guided import check_gitignore_for_idioms, load_personal_idioms

def test_extract_json_block():
    # Test wrapped in markdown json block
    markdown_json = "```json\n{\n  \"patcher\": {}\n}\n```"
    assert json.loads(extract_json_block(markdown_json)) == {"patcher": {}}

    # Test wrapped in generic markdown block
    generic_markdown = "```\n{\n  \"patcher\": {}\n}\n```"
    assert json.loads(extract_json_block(generic_markdown)) == {"patcher": {}}

    # Test raw JSON
    raw_json = "{\n  \"patcher\": {}\n}"
    assert json.loads(extract_json_block(raw_json)) == {"patcher": {}}

def test_check_gitignore_for_idioms():
    # Test when gitignore contains the target
    mock_gitignore = "# Personal Idioms\ndata/personal_idioms.md\n"
    with patch("builtins.open", mock_open(read_data=mock_gitignore)):
        with patch("os.path.exists", return_value=True):
            assert check_gitignore_for_idioms() is True

    # Test when gitignore doesn't contain target but contains data/
    mock_gitignore_dir = "data/\n"
    with patch("builtins.open", mock_open(read_data=mock_gitignore_dir)):
        with patch("os.path.exists", return_value=True):
            assert check_gitignore_for_idioms() is True

    # Test when gitignore doesn't contain it at all
    mock_gitignore_empty = "*.log\n.venv/\n"
    with patch("builtins.open", mock_open(read_data=mock_gitignore_empty)):
        with patch("os.path.exists", return_value=True):
            assert check_gitignore_for_idioms() is False

def test_load_personal_idioms():
    # Test when file doesn't exist
    with patch("os.path.exists", return_value=False):
        assert load_personal_idioms() == ""

    # Test when file exists and contains data
    mock_idioms_data = "### Lesson 1\nAlways use plugin~ for M4L Audio Effects."
    with patch("builtins.open", mock_open(read_data=mock_idioms_data)):
        with patch("os.path.exists", return_value=True):
            loaded = load_personal_idioms()
            assert "PERSONAL IDIOMS & LESSONS LEARNT" in loaded
            assert "Always use plugin~" in loaded

def test_load_example_patch():
    # Verify that it loads example patches successfully (if files exist on disk)
    max_patch = load_example_patch("max")
    assert max_patch != ""
    assert "patcher" in max_patch

    m4l_patch = load_example_patch("m4l")
    assert m4l_patch != ""
    assert "patcher" in m4l_patch
