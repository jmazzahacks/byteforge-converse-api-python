"""
Python client for the ByteforgeConverse backend API.
"""

from .client import ConverseClient, ConverseAPIError

__version__ = "0.0.2"

__all__ = ["ConverseClient", "ConverseAPIError"]
