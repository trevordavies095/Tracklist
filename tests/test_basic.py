"""
Basic test to verify testing is working.
This test doesn't import pytest or any app modules.
"""


def test_basic_math():
    """Test that basic math works."""
    assert 2 + 2 == 4


def test_string_operations():
    """Test string operations."""
    text = "hello"
    assert text.upper() == "HELLO"
    assert len(text) == 5


def test_multiplication():
    """Test multiplication."""
    assert 3 * 4 == 12
    assert 5 * 5 == 25


def test_boolean_logic():
    """Test boolean operations."""
    assert True and True
    assert not (True and False)
    assert True or False