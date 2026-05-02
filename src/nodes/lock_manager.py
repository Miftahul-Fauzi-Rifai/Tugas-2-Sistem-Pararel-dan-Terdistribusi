"""Distributed Lock Manager using Raft consensus."""

import asyncio
import time
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from loguru import logger

from src.consensus.raft import RaftNode
from src.communication.message_passing import Message, MessageType


class LockType(str, Enum):
    """Lock types."""
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


@dataclass
class LockInfo:
    """Information about a lock."""
    lock_id: str
    owner: str
    lock_type: LockType
    acquired_at: float
    ttl: Optional[float] = None  # Time to live
    
    def is_expired(self) -> bool:
        """Check if lock is expired."""
        if self.ttl is None:
            return False
        return time.time() - self.acquired_at > self.ttl


class DistributedLockManager:
    """Manages distributed locks using Raft consensus."""
    
    def __init__(self, raft_node: RaftNode, node_id: str):
        self.raft_node = raft_node
        self.node_id = node_id
        
        # Lock storage
        self.locks: Dict[str, LockInfo] = {}
        self.lock_queue: Dict[str, List[Tuple[str, LockType]]] = {}
        self.node_locks: Dict[str, List[str]] = {}  # Track locks per node
        
        # Metrics
        self.lock_acquisitions = 0
        self.lock_rejections = 0
        self.deadlock_detections = 0
    
    async def acquire_lock(
        self,
        lock_id: str,
        requester_id: str,
        lock_type: LockType = LockType.EXCLUSIVE,
        ttl: Optional[float] = None,
        timeout: float = 5.0,
    ) -> Tuple[bool, Optional[str]]:
        """Acquire a distributed lock."""
        
        # --- PERBAIKAN: Konversi string dari HTTP Request menjadi Enum ---
        if not isinstance(lock_type, LockType):
            lock_type = LockType(lock_type)
        # -----------------------------------------------------------------
        
        if not self.raft_node._is_leader():
            return False, "Not the leader"
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if lock is available
            if lock_id not in self.locks:
                # Lock is free - acquire it
                lock_info = LockInfo(
                    lock_id=lock_id,
                    owner=requester_id,
                    lock_type=lock_type,
                    acquired_at=time.time(),
                    ttl=ttl
                )
                
                # Append to Raft log
                command = {
                    'op': 'acquire_lock',
                    'lock_id': lock_id,
                    'owner': requester_id,
                    'lock_type': lock_type.value,
                    'ttl': ttl,
                    'timestamp': time.time()
                }
                
                try:
                    index = await self.raft_node.append_entry(command)
                    self.locks[lock_id] = lock_info
                    
                    if requester_id not in self.node_locks:
                        self.node_locks[requester_id] = []
                    self.node_locks[requester_id].append(lock_id)
                    
                    self.lock_acquisitions += 1
                    logger.info(f"Lock {lock_id} acquired by {requester_id}")
                    
                    return True, None
                except Exception as e:
                    logger.error(f"Failed to append lock entry: {e}")
                    return False, str(e)
            
            else:
                current_lock = self.locks[lock_id]
                
                # Check if it's expired
                if current_lock.is_expired():
                    # Expired lock - release it
                    await self.release_lock(current_lock.lock_id, current_lock.owner)
                    continue
                
                # Check compatibility
                if lock_type == LockType.SHARED and current_lock.lock_type == LockType.SHARED:
                    # Both shared - can grant
                    lock_info = LockInfo(
                        lock_id=lock_id,
                        owner=requester_id,
                        lock_type=lock_type,
                        acquired_at=time.time(),
                        ttl=ttl
                    )
                    self.locks[lock_id] = lock_info
                    self.lock_acquisitions += 1
                    logger.info(f"Shared lock {lock_id} acquired by {requester_id}")
                    return True, None
                
                # Incompatible - add to queue
                if lock_id not in self.lock_queue:
                    self.lock_queue[lock_id] = []
                
                self.lock_queue[lock_id].append((requester_id, lock_type))
                
                # Wait a bit before retrying
                await asyncio.sleep(0.1)
        
        self.lock_rejections += 1
        logger.warning(f"Failed to acquire lock {lock_id} for {requester_id} (timeout)")
        return False, "Timeout"
    
    async def release_lock(
        self,
        lock_id: str,
        owner_id: str
    ) -> Tuple[bool, Optional[str]]:
        """Release a distributed lock."""
        
        if not self.raft_node._is_leader():
            return False, "Not the leader"
        
        if lock_id not in self.locks:
            return False, "Lock not found"
        
        lock_info = self.locks[lock_id]
        if lock_info.owner != owner_id:
            return False, "Not the lock owner"
        
        # Append to Raft log
        command = {
            'op': 'release_lock',
            'lock_id': lock_id,
            'owner': owner_id,
            'timestamp': time.time()
        }
        
        try:
            index = await self.raft_node.append_entry(command)
            del self.locks[lock_id]
            
            if owner_id in self.node_locks:
                self.node_locks[owner_id].remove(lock_id)
            
            logger.info(f"Lock {lock_id} released by {owner_id}")
            
            # Try to grant lock to waiting nodes
            if lock_id in self.lock_queue and self.lock_queue[lock_id]:
                waiter, waiter_type = self.lock_queue[lock_id].pop(0)
                # Process waiter asynchronously
                asyncio.create_task(
                    self.acquire_lock(lock_id, waiter, waiter_type)
                )
            
            return True, None
        except Exception as e:
            logger.error(f"Failed to append lock release: {e}")
            return False, str(e)
    
    async def check_deadlock(self) -> Dict:
        """Check for deadlocks."""
        info = self.raft_node.deadlock_detector.get_deadlock_info()
        
        if info['has_deadlock']:
            self.deadlock_detections += 1
            logger.error(f"Deadlock detected: {info['cycle']}")
        
        return info
    
    def get_lock_status(self, lock_id: str) -> Optional[Dict]:
        """Get status of a lock."""
        if lock_id not in self.locks:
            return None
        
        lock_info = self.locks[lock_id]
        return {
            'lock_id': lock_info.lock_id,
            'owner': lock_info.owner,
            'lock_type': lock_info.lock_type.value,
            'acquired_at': lock_info.acquired_at,
            'ttl': lock_info.ttl,
            'is_expired': lock_info.is_expired(),
        }
    
    def get_all_locks(self) -> Dict[str, Dict]:
        """Get all locks."""
        return {
            lock_id: self.get_lock_status(lock_id)
            for lock_id in self.locks
        }
    
    def get_node_locks(self, node_id: str) -> List[str]:
        """Get all locks owned by a node."""
        return self.node_locks.get(node_id, [])
    
    async def cleanup_expired_locks(self):
        """Remove expired locks."""
        expired = [
            lock_id for lock_id, lock_info in self.locks.items()
            if lock_info.is_expired()
        ]
        
        for lock_id in expired:
            await self.release_lock(lock_id, self.locks[lock_id].owner)
    
    def get_metrics(self) -> Dict:
        """Get lock manager metrics."""
        return {
            'total_locks': len(self.locks),
            'lock_acquisitions': self.lock_acquisitions,
            'lock_rejections': self.lock_rejections,
            'deadlock_detections': self.deadlock_detections,
            'active_locks': self.get_all_locks(),
            'pending_requests': {
                lock_id: len(waiters)
                for lock_id, waiters in self.lock_queue.items()
            }
        }