"""Message passing and communication protocols."""

import json
import asyncio
from dataclasses import dataclass, asdict
from typing import Any, Dict, Callable, Optional, List
from enum import Enum
import aiohttp
from loguru import logger
import time

from .failure_detector import FailureDetector


class MessageType(str, Enum):
    """Message types in the system."""
    HEARTBEAT = "heartbeat"
    VOTE_REQUEST = "vote_request"
    VOTE_RESPONSE = "vote_response"
    APPEND_ENTRIES = "append_entries"
    APPEND_RESPONSE = "append_response"
    LOCK_REQUEST = "lock_request"
    LOCK_GRANT = "lock_grant"
    LOCK_RELEASE = "lock_release"
    QUEUE_ENQUEUE = "queue_enqueue"
    QUEUE_DEQUEUE = "queue_dequeue"
    CACHE_GET = "cache_get"
    CACHE_SET = "cache_set"
    CACHE_INVALIDATE = "cache_invalidate"
    DEADLOCK_DETECTION = "deadlock_detection"


@dataclass
class Message:
    """Base message structure."""
    message_type: str
    sender_id: str
    receiver_id: str
    term: int = 0
    data: Dict[str, Any] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create from dictionary."""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


class MessageHandler:
    """Handles message sending and receiving."""
    
    def __init__(self, node_id: str, timeout: float = 5.0):
        self.node_id = node_id
        self.timeout = timeout
        self.handlers: Dict[str, Callable] = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize the message handler."""
        self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the message handler."""
        if self.session:
            await self.session.close()
    
    def register_handler(self, message_type: str, handler: Callable):
        """Register a message handler."""
        self.handlers[message_type] = handler
    
    async def send_message(self, target_url: str, message: Message) -> Optional[Dict]:
        """Send a message to a target node."""
        if not self.session:
            await self.initialize()
        
        try:
            async with self.session.post(
                f"{target_url}/messages",
                json=message.to_dict(),
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    logger.debug(f"Message sent to {target_url}: {message.message_type}")
                    return await response.json()
                else:
                    logger.warning(f"Failed to send message to {target_url}: {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Message send timeout to {target_url}")
            return None
        except Exception as e:
            logger.error(f"Error sending message to {target_url}: {e}")
            return None
    
    async def broadcast_message(
        self, 
        targets: List[str], 
        message: Message
    ) -> Dict[str, Optional[Dict]]:
        """Broadcast a message to multiple targets."""
        tasks = [self.send_message(target, message) for target in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            target: result if not isinstance(result, Exception) else None
            for target, result in zip(targets, results)
        }
    
    async def handle_message(self, message: Message) -> Optional[Dict]:
        """Handle an incoming message."""
        if message.message_type in self.handlers:
            handler = self.handlers[message.message_type]
            try:
                result = await handler(message)
                return result
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                return {"error": str(e)}
        else:
            logger.warning(f"No handler for message type: {message.message_type}")
            return None
