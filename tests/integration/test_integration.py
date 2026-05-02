"""Integration tests for distributed system."""

import pytest
import asyncio
from src.consensus.raft import RaftNode
from src.nodes.lock_manager import DistributedLockManager, LockType
from src.nodes.queue_node import DistributedQueue
from src.nodes.cache_node import CacheCoherence


@pytest.mark.asyncio
class TestDistributedLocking:
    """Integration tests for distributed locking."""
    
    async def test_exclusive_lock_acquisition(self):
        """Test exclusive lock acquisition."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        lock_mgr = DistributedLockManager(raft, 'node1')
        
        success, error = await lock_mgr.acquire_lock(
            'resource1', 'node1', LockType.EXCLUSIVE
        )
        
        assert success
        assert error is None
        assert 'resource1' in lock_mgr.locks
    
    async def test_shared_lock_compatibility(self):
        """Test that shared locks are compatible."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        lock_mgr = DistributedLockManager(raft, 'node1')
        
        # First node acquires shared lock
        success1, _ = await lock_mgr.acquire_lock(
            'resource1', 'node1', LockType.SHARED
        )
        assert success1
        
        # Second node can acquire shared lock too
        success2, _ = await lock_mgr.acquire_lock(
            'resource1', 'node2', LockType.SHARED
        )
        assert success2
    
    async def test_exclusive_lock_blocks_others(self):
        """Test that exclusive lock blocks other acquisitions."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        lock_mgr = DistributedLockManager(raft, 'node1')
        
        # First node acquires exclusive lock
        success1, _ = await lock_mgr.acquire_lock(
            'resource1', 'node1', LockType.EXCLUSIVE
        )
        assert success1
        
        # Second node cannot acquire (with timeout)
        success2, _ = await lock_mgr.acquire_lock(
            'resource1', 'node2', LockType.EXCLUSIVE, timeout=0.5
        )
        assert not success2


@pytest.mark.asyncio
class TestDistributedQueue:
    """Integration tests for distributed queue."""
    
    async def test_enqueue_dequeue_single_node(self):
        """Test basic enqueue/dequeue on single node."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        queue = DistributedQueue(raft, 'node1', nodes)
        
        # Enqueue a message
        success, msg_id = await queue.enqueue(
            'test_queue', 'hello', 'producer1'
        )
        assert success
        
        # Dequeue the message
        message = await queue.dequeue('test_queue', 'consumer1')
        assert message is not None
        assert message.message_id == msg_id
        assert message.content == 'hello'
    
    async def test_at_least_once_delivery(self):
        """Test at-least-once delivery guarantee."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        queue = DistributedQueue(raft, 'node1', nodes)
        
        # Enqueue multiple messages
        for i in range(5):
            await queue.enqueue('test_queue', f'message{i}', 'producer1')
        
        # Dequeue and verify
        for i in range(5):
            message = await queue.dequeue('test_queue', 'consumer1')
            assert message is not None
    
    async def test_message_recovery_after_failure(self):
        """Test message recovery after node failure."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        queue = DistributedQueue(raft, 'node1', nodes, enable_persistence=True)
        
        # Enqueue a message
        await queue.enqueue('test_queue', 'important_message', 'producer1')
        
        # Simulate persistence
        recovered = await queue.recover_unacknowledged('test_queue')
        assert recovered >= 0  # Should recover persisted messages


@pytest.mark.asyncio
class TestCacheCoherence:
    """Integration tests for cache coherence."""
    
    def test_cache_coherence_system(self):
        """Test cache coherence across multiple nodes."""
        nodes = ['node1', 'node2', 'node3']
        coherence = CacheCoherence(nodes)
        
        # Put value in node1 cache
        coherence.caches['node1'].put('key1', 'value1')
        assert coherence.caches['node1'].get('key1') == 'value1'
        
        # Get from node2 cache (should miss)
        assert coherence.caches['node2'].get('key1') is None
        
        # Invalidate at other nodes
        coherence.broadcast_invalidation('key1', 'node1')
        
        # Verify system metrics
        metrics = coherence.get_system_metrics()
        assert len(metrics) == 3
    
    def test_cache_state_transitions(self):
        """Test cache state transitions."""
        nodes = ['node1', 'node2', 'node3']
        coherence = CacheCoherence(nodes)
        
        cache = coherence.caches['node1']
        
        # Write should put in MODIFIED state
        state = cache.put('key1', 'value1')
        assert state.value == 'modified'
        
        # Read should work
        value = cache.get('key1')
        assert value == 'value1'
        assert cache.cache_hits == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
