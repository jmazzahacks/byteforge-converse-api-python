"""
Python client for the ByteforgeConverse backend API.
"""

from .client import ConverseClient, ConverseAPIError

__version__ = "0.2.0"

__all__ = ["ConverseClient", "ConverseAPIError"]
