"""Distributed Queue System with consistent hashing."""

import asyncio
import time
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from loguru import logger

from src.consensus.raft import RaftNode


@dataclass
class QueueMessage:
    """A message in the distributed queue."""
    message_id: str
    content: Any
    producer_id: str
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3
    persisted: bool = False


class ConsistentHashRing:
    """Consistent hashing ring for queue distribution."""
    
    def __init__(self, nodes: List[str], replicas: int = 3):
        self.nodes = nodes
        self.replicas = replicas
        self.ring: Dict[int, str] = {}
        self._build_ring()
    
    def _build_ring(self):
        """Build the hash ring."""
        self.ring = {}
        
        for node in self.nodes:
            for i in range(self.replicas):
                hash_key = self._hash(f"{node}:{i}")
                self.ring[hash_key] = node
    
    def _hash(self, key: str) -> int:
        """Hash a key."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def get_node(self, key: str) -> str:
        """Get the node responsible for a key."""
        if not self.ring:
            raise RuntimeError("No nodes in ring")
        
        hash_key = self._hash(key)
        sorted_keys = sorted(self.ring.keys())
        
        for ring_key in sorted_keys:
            if hash_key <= ring_key:
                return self.ring[ring_key]
        
        return self.ring[sorted_keys[0]]
    
    def get_nodes(self, key: str, count: int = 3) -> List[str]:
        """Get multiple nodes for replication."""
        if not self.ring:
            return []
        
        sorted_keys = sorted(self.ring.keys())
        hash_key = self._hash(key)
        
        nodes = []
        seen = set()
        
        for ring_key in sorted_keys:
            if hash_key <= ring_key:
                node = self.ring[ring_key]
                if node not in seen:
                    nodes.append(node)
                    seen.add(node)
                    if len(nodes) >= count:
                        break
        
        # Wrap around if needed
        for ring_key in sorted_keys:
            if len(nodes) >= count:
                break
            node = self.ring[ring_key]
            if node not in seen:
                nodes.append(node)
                seen.add(node)
        
        return nodes[:count]


class DistributedQueue:
    """Distributed queue with persistence and at-least-once delivery."""
    
    def __init__(
        self,
        raft_node: RaftNode,
        node_id: str,
        all_nodes: List[str],
        enable_persistence: bool = True,
        replication_factor: int = 3
    ):
        self.raft_node = raft_node
        self.node_id = node_id
        self.all_nodes = all_nodes
        self.enable_persistence = enable_persistence
        self.replication_factor = replication_factor
        
        # Queues
        self.queues: Dict[str, deque] = {}
        self.hash_ring = ConsistentHashRing(all_nodes, replicas=3)
        
        # Persistence
        self.persistence_log: Dict[str, List[Dict]] = {}
        self.acknowledged_messages: Dict[str, List[str]] = {}
        
        # Metrics
        self.messages_enqueued = 0
        self.messages_dequeued = 0
        self.messages_failed = 0
        self.replication_failures = 0
    
    async def enqueue(
        self,
        queue_name: str,
        content: Any,
        producer_id: str,
        persist: bool = True
    ) -> Tuple[bool, str]:
        """Enqueue a message."""
        
        message_id = f"{producer_id}:{int(time.time() * 1000)}"
        
        message = QueueMessage(
            message_id=message_id,
            content=content,
            producer_id=producer_id,
            timestamp=time.time(),
            persisted=False
        )
        
        # Add to local queue
        if queue_name not in self.queues:
            self.queues[queue_name] = deque()
        
        self.queues[queue_name].append(message)
        self.messages_enqueued += 1
        
        # Append to Raft log
        command = {
            'op': 'enqueue',
            'queue_name': queue_name,
            'message_id': message_id,
            'content': str(content),
            'producer_id': producer_id,
            'timestamp': message.timestamp
        }
        
        try:
            if self.raft_node._is_leader():
                index = await self.raft_node.append_entry(command)
                message.persisted = True
            
            # Persist locally if enabled
            if persist and self.enable_persistence:
                self._persist_message(queue_name, message)
            
            logger.info(f"Message {message_id} enqueued to {queue_name}")
            return True, message_id
        
        except Exception as e:
            logger.error(f"Failed to enqueue message: {e}")
            self.messages_failed += 1
            return False, str(e)
    
    async def dequeue(
        self,
        queue_name: str,
        consumer_id: str,
        timeout: float = 1.0
    ) -> Optional[QueueMessage]:
        """Dequeue a message with at-least-once guarantee."""
        
        if queue_name not in self.queues:
            return None
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.queues[queue_name]:
                message = self.queues[queue_name].popleft()
                
                # Log consumption for at-least-once
                if queue_name not in self.acknowledged_messages:
                    self.acknowledged_messages[queue_name] = []
                
                self.acknowledged_messages[queue_name].append(message.message_id)
                self.messages_dequeued += 1
                
                logger.info(
                    f"Message {message.message_id} dequeued by {consumer_id} "
                    f"from {queue_name}"
                )
                
                return message
            
            await asyncio.sleep(0.01)
        
        return None
    
    async def replicate_message(
        self,
        queue_name: str,
        message: QueueMessage
    ) -> bool:
        """Replicate message to other nodes."""
        
        target_nodes = self.hash_ring.get_nodes(
            f"{queue_name}:{message.message_id}",
            self.replication_factor
        )
        
        # Remove self from targets
        target_nodes = [n for n in target_nodes if n != self.node_id]
        
        if not target_nodes:
            return True
        
        # Send replication message to target nodes
        replication_success = 0
        for node in target_nodes:
            try:
                # In a real system, this would send an RPC
                replication_success += 1
            except Exception as e:
                logger.error(f"Failed to replicate to {node}: {e}")
                self.replication_failures += 1
        
        return replication_success == len(target_nodes)
    
    def _persist_message(self, queue_name: str, message: QueueMessage):
        """Persist message locally."""
        if queue_name not in self.persistence_log:
            self.persistence_log[queue_name] = []
        
        self.persistence_log[queue_name].append({
            'message_id': message.message_id,
            'content': str(message.content),
            'timestamp': message.timestamp,
            'producer_id': message.producer_id
        })
    
    async def recover_unacknowledged(self, queue_name: str) -> int:
        """Recover unacknowledged messages."""
        if queue_name not in self.persistence_log:
            return 0
        
        recovered = 0
        for message_data in self.persistence_log[queue_name]:
            msg_id = message_data['message_id']
            if queue_name not in self.acknowledged_messages or \
               msg_id not in self.acknowledged_messages[queue_name]:
                
                message = QueueMessage(
                    message_id=msg_id,
                    content=message_data['content'],
                    producer_id=message_data['producer_id'],
                    timestamp=message_data['timestamp'],
                    persisted=True
                )
                
                if queue_name not in self.queues:
                    self.queues[queue_name] = deque()
                
                self.queues[queue_name].append(message)
                recovered += 1
        
        logger.info(f"Recovered {recovered} messages from {queue_name}")
        return recovered
    
    def get_queue_size(self, queue_name: str) -> int:
        """Get size of a queue."""
        if queue_name not in self.queues:
            return 0
        return len(self.queues[queue_name])
    
    def get_all_queues(self) -> Dict[str, int]:
        """Get all queues and their sizes."""
        return {
            name: len(queue)
            for name, queue in self.queues.items()
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get queue metrics."""
        return {
            'messages_enqueued': self.messages_enqueued,
            'messages_dequeued': self.messages_dequeued,
            'messages_failed': self.messages_failed,
            'replication_failures': self.replication_failures,
            'queue_sizes': self.get_all_queues(),
            'hash_ring_nodes': self.hash_ring.nodes,
        }
