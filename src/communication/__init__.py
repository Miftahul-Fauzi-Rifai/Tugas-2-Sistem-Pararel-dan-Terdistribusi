"""Communication module for distributed synchronization system."""

from .message_passing import Message, MessageType, MessageHandler
from .failure_detector import FailureDetector

__all__ = [
    'Message',
    'MessageType',
    'MessageHandler',
    'FailureDetector',
]
