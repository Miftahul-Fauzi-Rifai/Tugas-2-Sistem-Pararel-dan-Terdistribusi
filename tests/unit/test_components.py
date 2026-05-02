"""Unit tests for distributed system components."""

import pytest
import asyncio
import time
from src.consensus.raft import RaftNode, LogEntry, DeadlockDetector
from src.nodes.lock_manager import DistributedLockManager, LockType
from src.nodes.queue_node import DistributedQueue, ConsistentHashRing
from src.nodes.cache_node import MESICache, CacheState
from src.communication.message_passing import Message, MessageType
from src.communication.failure_detector import FailureDetector


class TestRaft:
    """Test Raft consensus algorithm."""
    
    def test_raft_node_initialization(self):
        """Test Raft node initialization."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        
        assert raft.node_id == 'node1'
        assert raft.peers == ['node2', 'node3']
        assert raft.current_leader is None
        assert raft.raft_state.current_term == 0
    
    def test_become_leader(self):
        """Test node becoming leader."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        
        raft.become_leader()
        assert raft._is_leader()
        assert raft.current_leader == 'node1'
    
    def test_become_follower(self):
        """Test node becoming follower."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        
        raft.become_leader()
        raft.become_follower(1)
        
        assert not raft._is_leader()
        assert raft.raft_state.current_term == 1
    
    @pytest.mark.asyncio
    async def test_append_entry(self):
        """Test appending entry to log."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        command = {'op': 'set', 'key': 'test', 'value': 'value'}
        index = await raft.append_entry(command)
        
        assert index == 0
        assert len(raft.raft_state.log) == 1
        assert raft.raft_state.log[0].command == command


class TestDeadlockDetector:
    """Test deadlock detection."""
    
    def test_deadlock_detection_no_cycle(self):
        """Test with no deadlock."""
        detector = DeadlockDetector()
        
        detector.acquire_lock('node1', 'lock1')
        detector.acquire_lock('node2', 'lock1')
        
        cycle = detector.detect_cycle()
        assert cycle is None
    
    def test_deadlock_detection_with_cycle(self):
        """Test with deadlock cycle."""
        detector = DeadlockDetector()
        
        # Create a cycle: node1 waits for node2, node2 waits for node1
        detector.acquire_lock('node1', 'lock1')  # node1 holds lock1
        detector.acquire_lock('node2', 'lock1')  # node2 waits for lock1
        
        detector.acquire_lock('node2', 'lock2')  # node2 holds lock2
        detector.acquire_lock('node1', 'lock2')  # node1 waits for lock2
        
        cycle = detector.detect_cycle()
        assert cycle is not None


class TestConsistentHashing:
    """Test consistent hashing for queues."""
    
    def test_consistent_hash_ring_creation(self):
        """Test hash ring creation."""
        nodes = ['node1', 'node2', 'node3']
        ring = ConsistentHashRing(nodes, replicas=3)
        
        assert len(ring.ring) == 9  # 3 nodes * 3 replicas
    
    def test_consistent_hash_get_node(self):
        """Test getting node for key."""
        nodes = ['node1', 'node2', 'node3']
        ring = ConsistentHashRing(nodes, replicas=3)
        
        node = ring.get_node('test_key')
        assert node in nodes
    
    def test_consistent_hash_get_nodes_replication(self):
        """Test getting multiple nodes for replication."""
        nodes = ['node1', 'node2', 'node3']
        ring = ConsistentHashRing(nodes, replicas=3)
        
        target_nodes = ring.get_nodes('test_key', count=3)
        assert len(target_nodes) <= 3
        assert all(node in nodes for node in target_nodes)


class TestMESICache:
    """Test MESI cache protocol."""
    
    def test_cache_get_miss(self):
        """Test cache miss."""
        cache = MESICache('node1', cache_size=10)
        
        value = cache.get('nonexistent')
        assert value is None
        assert cache.cache_misses == 1
    
    def test_cache_put_and_get(self):
        """Test putting and getting from cache."""
        cache = MESICache('node1', cache_size=10)
        
        cache.put('key1', 'value1')
        value = cache.get('key1')
        
        assert value == 'value1'
        assert cache.cache_hits == 1
    
    def test_cache_state_transition_to_modified(self):
        """Test state transition to MODIFIED."""
        cache = MESICache('node1', cache_size=10)
        
        state = cache.put('key1', 'value1')
        assert state == CacheState.MODIFIED
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction."""
        cache = MESICache('node1', cache_size=3)
        
        cache.put('key1', 'value1')
        cache.put('key2', 'value2')
        cache.put('key3', 'value3')
        cache.put('key4', 'value4')  # Should evict key1
        
        assert cache.get('key1') is None
        assert cache.get('key4') == 'value4'


class TestFailureDetector:
    """Test failure detection."""
    
    def test_heartbeat_recording(self):
        """Test recording heartbeats."""
        detector = FailureDetector(heartbeat_interval=1.0, threshold=3)
        
        detector.record_heartbeat('node1')
        assert detector.check_node_health('node1')
    
    def test_node_health_check_timeout(self):
        """Test node health timeout."""
        detector = FailureDetector(heartbeat_interval=1.0, threshold=3)
        
        detector.record_heartbeat('node1')
        
        # Check health with future time
        future_time = time.time() + 10.0
        is_healthy = detector.check_node_health('node1', future_time)
        
        assert not is_healthy
    
    def test_network_partition_detection(self):
        """Test network partition detection."""
        detector = FailureDetector()
        
        # 3 total nodes, only 1 healthy = partition
        is_partitioned = detector.is_network_partitioned(1, 3)
        assert is_partitioned
        
        # 3 total nodes, 2 healthy = no partition
        is_partitioned = detector.is_network_partitioned(2, 3)
        assert not is_partitioned


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
