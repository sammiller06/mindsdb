import os
from unittest.mock import patch, mock_open
import pytest
from mindsdb.integrations.handlers.langchain_handler.agent_tool_fetcher import AgentToolFetcher
from mindsdb.integrations.handlers.frappe_handler.frappe_handler import FrappeHandler
from cryptography.fernet import Fernet
from langchain.tools import Tool


fake_key = "fuphuFuNho5ALV1ryVUthe858u66mium38-9jh2yBKU="
fake_data = Fernet(fake_key).encrypt(b"fake domain\nfake token")


@pytest.fixture
def tool_fetcher():
    return AgentToolFetcher(fake_key)


@pytest.fixture
def fake_os_path_exists():
    with patch("os.path.exists") as mock_exists:
        yield mock_exists


@pytest.fixture
def fake_open():
    with patch("builtins.open", mock_open(read_data=fake_data)) as mock_file:
        yield mock_file


def test_get_token_path_success(tool_fetcher, fake_os_path_exists):
    """
    Test that get_token_path returns the expected path when the file exists
    """
    fake_os_path_exists.return_value = True
    base_dir = "/fake/base/dir"
    username = "johndoe"
    token_file = "token.txt"
    expected_path = os.path.join(base_dir, username, token_file)
    assert tool_fetcher.get_token_path(base_dir, username, token_file) == expected_path


def test_get_token_path_failure(tool_fetcher, fake_os_path_exists):
    """
    Test that get_token_path raises an AssertionError when the file does not exist
    """
    fake_os_path_exists.return_value = False
    with pytest.raises(AssertionError):
        tool_fetcher.get_token_path("/fake/base/dir", "johndoe", "token.txt")


def test_get_frappe_handler(tool_fetcher, fake_os_path_exists, fake_open):
    """
    Test that get_frappe_handler returns a FrappeHandler instance when the token files exists
    """
    fake_os_path_exists.return_value = True
    handler = tool_fetcher.get_frappe_handler("/fake/base/dir", "johndoe")
    assert isinstance(handler, FrappeHandler)


def test_get_tools_for_agent_unknown(tool_fetcher):
    """
    Test that get_tools_for_agent returns an empty list when the agent name is unknown
    """
    tools = tool_fetcher.get_tools_for_agent("unknown", "/fake/base/dir", "johndoe")
    assert tools == []


def test_get_tools_for_agent_frappe(tool_fetcher, fake_os_path_exists, fake_open):
    """
    Test that get_tools_for_agent returns the expected tools when the agent name is frappe
    """
    tools = tool_fetcher.get_tools_for_agent("frappe", "/fake/base/dir", "johndoe")
    assert len(tools)
    for tool in tools:
        assert isinstance(tool, Tool)
