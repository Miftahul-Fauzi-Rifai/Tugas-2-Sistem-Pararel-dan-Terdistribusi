"""Base node implementation for distributed system."""

import asyncio
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from enum import Enum
import aiohttp
from aiohttp import web
import logging
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from src.utils.config import NodeConfig, get_config
from src.utils.metrics import SystemMetrics
from src.communication.message_passing import Message, MessageHandler, MessageType
from src.communication.failure_detector import FailureDetector


class NodeState(str, Enum):
    """Node states in Raft consensus."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class BaseNode(ABC):
    """Base node for distributed system."""
    
    def __init__(self, config: Optional[NodeConfig] = None):
        self.config = config or get_config()
        self.node_id = self.config.node_id
        self.state = NodeState.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        
        # Components
        self.message_handler = MessageHandler(self.node_id)
        self.metrics = SystemMetrics(self.node_id, self.config.enable_metrics)
        self.failure_detector = FailureDetector(
            heartbeat_interval=self.config.heartbeat_interval,
            threshold=3
        )
        
        # Web server
        self.app = web.Application()
        self.runner = None
        self.site = None
        
        # Tasks
        self.running_tasks: List[asyncio.Task] = []
        self.is_running = False
        
        # Setup routes
        self._setup_routes()
        
        logger.info(f"Node {self.node_id} initialized at {self.config.base_url}")
    
    def _setup_routes(self):
        """Setup web server routes."""
        self.app.router.add_post('/messages', self._handle_message_endpoint)
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_get('/metrics', self._get_metrics)
        self.app.router.add_get('/status', self._get_status)
        
        # Register message handlers
        self.message_handler.register_handler(MessageType.HEARTBEAT, self._handle_heartbeat)
    
    async def _handle_message_endpoint(self, request: web.Request) -> web.Response:
        """Handle incoming message endpoint."""
        try:
            data = await request.json()
            message = Message.from_dict(data)
            
            logger.debug(f"Received message from {message.sender_id}: {message.message_type}")
            
            result = await self.message_handler.handle_message(message)
            self.metrics.record_message_received()
            
            return web.json_response(result or {"status": "ok"})
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return web.json_response({"error": str(e)}, status=400)
    
    async def _health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "node_id": self.node_id,
            "state": self.state.value,
            "term": self.current_term,
        })
    
    async def _get_metrics(self, request: web.Request) -> web.Response:
        """Get metrics endpoint."""
        return web.json_response(self.metrics.get_summary())
    
    async def _get_status(self, request: web.Request) -> web.Response:
        """Get node status endpoint."""
        return web.json_response({
            "node_id": self.node_id,
            "state": self.state.value,
            "term": self.current_term,
            "voted_for": self.voted_for,
            "is_running": self.is_running,
        })
    
    async def _handle_heartbeat(self, message: Message) -> Dict[str, Any]:
        """Handle heartbeat message."""
        logger.debug(f"Received heartbeat from {message.sender_id}")
        self.failure_detector.record_heartbeat(message.sender_id)
        
        # Update term if necessary
        if message.term > self.current_term:
            self.current_term = message.term
            self.state = NodeState.FOLLOWER
            self.voted_for = None
        
        return {"status": "ok", "term": self.current_term}
    
    async def start(self):
        """Start the node."""
        logger.info(f"Starting node {self.node_id}...")
        
        # Initialize message handler
        await self.message_handler.initialize()
        
        # Start web server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.config.host, self.config.port)
        await self.site.start()
        
        logger.info(f"Node {self.node_id} listening on {self.config.base_url}")
        
        self.is_running = True
        
        # Start background tasks
        self._start_background_tasks()
    
    def _start_background_tasks(self):
        """Start background tasks."""
        task = asyncio.create_task(self._heartbeat_loop())
        self.running_tasks.append(task)
        
        task = asyncio.create_task(self._health_check_loop())
        self.running_tasks.append(task)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        try:
            while self.is_running:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                # Send heartbeats to all peers
                message = Message(
                    message_type=MessageType.HEARTBEAT,
                    sender_id=self.node_id,
                    receiver_id="broadcast",
                    term=self.current_term,
                )
                
                results = await self.message_handler.broadcast_message(
                    self.config.peers,
                    message
                )
                
                self.metrics.record_message_sent()
        except asyncio.CancelledError:
            logger.debug(f"Heartbeat loop cancelled for {self.node_id}")
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {e}")
    
    async def _health_check_loop(self):
        """Monitor health of peer nodes."""
        try:
            while self.is_running:
                await asyncio.sleep(self.config.heartbeat_interval * 2)
                
                unhealthy_nodes = self.failure_detector.get_unhealthy_nodes(
                    self.config.peers
                )
                
                if unhealthy_nodes:
                    logger.warning(f"Unhealthy nodes detected: {unhealthy_nodes}")
                    
                    # Check for network partition
                    healthy_count = len(self.config.peers) - len(unhealthy_nodes)
                    total_count = len(self.config.peers) + 1  # Including self
                    
                    if self.failure_detector.is_network_partitioned(healthy_count, total_count):
                        logger.error("Network partition detected!")
        except asyncio.CancelledError:
            logger.debug(f"Health check loop cancelled for {self.node_id}")
        except Exception as e:
            logger.error(f"Error in health check loop: {e}")
    
    async def stop(self):
        """Stop the node."""
        logger.info(f"Stopping node {self.node_id}...")
        
        self.is_running = False
        
        # Cancel all tasks
        for task in self.running_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close message handler
        await self.message_handler.close()
        
        # Stop web server
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        logger.info(f"Node {self.node_id} stopped")
    
    @abstractmethod
    async def run(self):
        """Run the node (to be implemented by subclasses)."""
        pass


async def create_node(node_config: Optional[NodeConfig] = None) -> BaseNode:
    """Factory function to create a node."""
    from src.nodes.base_node import BaseNode as BaseNodeImpl
    node = BaseNodeImpl(node_config)
    return node
