import pytest
import logging
import tempfile
import os
from pathlib import Path

from app.logging_config import setup_logging


class TestLoggingConfig:
    def test_setup_logging_returns_config(self):
        """Test that setup_logging returns expected configuration"""
        config = setup_logging(level="INFO")
        
        assert config["level"] == "INFO"
        assert "%(asctime)s" in config["format"]
        assert "%(name)s" in config["format"]
        assert "%(levelname)s" in config["format"]
        assert "%(message)s" in config["format"]
        assert config["handlers"] >= 1

    def test_setup_logging_creates_directory(self):
        """Test that logging setup creates log directory if needed"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "subdir", "test.log")
            
            # Directory doesn't exist initially
            assert not Path(log_file).parent.exists()
            
            setup_logging(log_file=log_file)
            
            # Directory should be created
            assert Path(log_file).parent.exists()

    def test_setup_logging_with_file_creates_file(self):
        """Test that log file is created when specified"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "test.log")
            
            config = setup_logging(level="INFO", log_file=log_file)
            
            assert config["level"] == "INFO"
            assert config["handlers"] == 2  # Console + File
            assert Path(log_file).exists()

    def test_setup_logging_levels(self):
        """Test that different levels are accepted"""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        
        for level in levels:
            config = setup_logging(level=level)
            assert config["level"] == level