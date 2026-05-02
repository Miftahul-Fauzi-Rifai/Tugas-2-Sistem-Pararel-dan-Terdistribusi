"""Cache Coherence with MESI Protocol."""

import time
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from collections import OrderedDict
from loguru import logger


class CacheState(str, Enum):
    """MESI cache states."""
    MODIFIED = "modified"      # M - Modified (dirty, different from memory)
    EXCLUSIVE = "exclusive"    # E - Exclusive (clean, only copy)
    SHARED = "shared"          # S - Shared (clean, multiple copies)
    INVALID = "invalid"        # I - Invalid (not present)


class CacheLineState:
    """State of a cache line."""
    
    def __init__(self, key: str, value: Any = None):
        self.key = key
        self.value = value
        self.state = CacheState.INVALID
        self.owner_node = None
        self.shared_by: List[str] = []  # Nodes that have this in shared state
        self.timestamp = time.time()
        self.access_count = 0  # For LRU
    
    def __repr__(self):
        return f"CacheLineState({self.key}, {self.state}, owner={self.owner_node})"


class MESICache:
    """MESI Protocol cache implementation."""
    
    def __init__(self, node_id: str, cache_size: int = 1000, all_nodes: List[str] = None):
        self.node_id = node_id
        self.cache_size = cache_size
        self.all_nodes = all_nodes or [node_id]
        
        # Cache storage (using OrderedDict for LRU)
        self.cache: OrderedDict[str, CacheLineState] = OrderedDict()
        
        # Invalidation tracking
        self.pending_invalidations: Dict[str, List[str]] = {}
        
        # Metrics
        self.cache_hits = 0
        self.cache_misses = 0
        self.invalidations_sent = 0
        self.invalidations_received = 0
        self.state_transitions = 0
    
    def _evict_lru(self):
        """Evict least recently used cache line."""
        if len(self.cache) >= self.cache_size:
            # Remove least recently used
            lru_key, lru_line = next(iter(self.cache.items()))
            del self.cache[lru_key]
            logger.debug(f"Node {self.node_id}: Evicted {lru_key} (LRU)")
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache (READ)."""
        if key not in self.cache:
            self.cache_misses += 1
            return None
        
        line = self.cache[key]
        
        # Update LRU - move to end
        self.cache.move_to_end(key)
        line.access_count += 1
        
        if line.state == CacheState.INVALID:
            self.cache_misses += 1
            return None
        
        self.cache_hits += 1
        logger.debug(
            f"Node {self.node_id}: Cache HIT for {key} "
            f"(state={line.state}, value={line.value})"
        )
        
        return line.value
    
    def put(self, key: str, value: Any, from_node: str = None) -> CacheState:
        """Put a value in cache (WRITE)."""
        
        # Evict if cache is full
        self._evict_lru()
        
        if key in self.cache:
            line = self.cache[key]
            old_state = line.state
        else:
            line = CacheLineState(key, value)
            self.cache[key] = line
            old_state = CacheState.INVALID
        
        # Transition state based on MESI protocol
        if from_node == self.node_id or from_node is None:
            # Local write - transition to MODIFIED
            new_state = CacheState.MODIFIED
            line.owner_node = self.node_id
            line.shared_by = []
            
            # Invalidate copies at other nodes
            if old_state != CacheState.INVALID:
                self._invalidate_others(key)
        else:
            # Remote write - transition to SHARED or stay INVALID
            new_state = CacheState.SHARED
            if from_node not in line.shared_by:
                line.shared_by.append(from_node)
        
        line.state = new_state
        line.value = value
        line.timestamp = time.time()
        
        # Move to end for LRU
        self.cache.move_to_end(key)
        
        self.state_transitions += 1
        logger.debug(
            f"Node {self.node_id}: State transition {old_state} -> {new_state} "
            f"for {key}"
        )
        
        return new_state
    
    def _invalidate_others(self, key: str):
        """Send invalidation to other nodes."""
        self.pending_invalidations[key] = [
            node for node in self.all_nodes if node != self.node_id
        ]
        self.invalidations_sent += 1
        
        logger.debug(
            f"Node {self.node_id}: Invalidating {key} at "
            f"{len(self.pending_invalidations[key])} nodes"
        )
    
    def invalidate(self, key: str, from_node: str) -> bool:
        """Handle invalidation from another node."""
        if key not in self.cache:
            return True
        
        line = self.cache[key]
        
        # Can only invalidate if in SHARED or EXCLUSIVE state
        if line.state == CacheState.MODIFIED:
            logger.warning(
                f"Node {self.node_id}: Cannot invalidate MODIFIED {key} from {from_node}"
            )
            return False
        
        if line.state in [CacheState.SHARED, CacheState.EXCLUSIVE]:
            line.state = CacheState.INVALID
            line.value = None
            line.owner_node = None
            
            self.invalidations_received += 1
            logger.debug(f"Node {self.node_id}: Invalidated {key}")
            
            return True
        
        return False
    
    def update_shared_state(self, key: str, shared_by: List[str]):
        """Update which nodes have this line in shared state."""
        if key in self.cache:
            self.cache[key].shared_by = shared_by
    
    def transition_to_exclusive(self, key: str) -> bool:
        """Transition from SHARED to EXCLUSIVE."""
        if key not in self.cache:
            return False
        
        line = self.cache[key]
        if line.state == CacheState.SHARED:
            line.state = CacheState.EXCLUSIVE
            self.state_transitions += 1
            logger.debug(f"Node {self.node_id}: {key} transitioned to EXCLUSIVE")
            return True
        
        return False
    
    def transition_to_modified(self, key: str) -> bool:
        """Transition from EXCLUSIVE to MODIFIED."""
        if key not in self.cache:
            return False
        
        line = self.cache[key]
        if line.state == CacheState.EXCLUSIVE:
            line.state = CacheState.MODIFIED
            line.owner_node = self.node_id
            line.shared_by = []
            self.state_transitions += 1
            logger.debug(f"Node {self.node_id}: {key} transitioned to MODIFIED")
            return True
        
        return False
    
    def get_cache_line(self, key: str) -> Optional[CacheLineState]:
        """Get cache line information."""
        return self.cache.get(key)
    
    def get_all_cache_lines(self) -> Dict[str, Dict[str, Any]]:
        """Get all cache lines."""
        return {
            key: {
                'state': line.state.value,
                'value': str(line.value),
                'owner_node': line.owner_node,
                'shared_by': line.shared_by,
                'access_count': line.access_count,
                'timestamp': line.timestamp
            }
            for key, line in self.cache.items()
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        total_accesses = self.cache_hits + self.cache_misses
        hit_rate = (
            self.cache_hits / total_accesses
            if total_accesses > 0 else 0
        )
        
        return {
            'node_id': self.node_id,
            'cache_size': len(self.cache),
            'max_cache_size': self.cache_size,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': hit_rate,
            'invalidations_sent': self.invalidations_sent,
            'invalidations_received': self.invalidations_received,
            'state_transitions': self.state_transitions,
            'cache_lines': self.get_all_cache_lines(),
        }
    
    def reset_metrics(self):
        """Reset metrics."""
        self.cache_hits = 0
        self.cache_misses = 0
        self.invalidations_sent = 0
        self.invalidations_received = 0
        self.state_transitions = 0


class CacheCoherence:
    """Manages cache coherence across nodes."""
    
    def __init__(self, all_nodes: List[str]):
        self.all_nodes = all_nodes
        self.caches: Dict[str, MESICache] = {}
        
        # Initialize caches for all nodes
        for node_id in all_nodes:
            self.caches[node_id] = MESICache(node_id, cache_size=1000, all_nodes=all_nodes)
    
    def broadcast_invalidation(self, key: str, from_node: str):
        """Broadcast cache invalidation."""
        for node_id, cache in self.caches.items():
            if node_id != from_node:
                cache.invalidate(key, from_node)
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system-wide cache metrics."""
        return {
            node_id: cache.get_metrics()
            for node_id, cache in self.caches.items()
        }
    
    def get_cache_coherence_status(self) -> Dict[str, Any]:
        """Get overall cache coherence status."""
        total_hits = sum(cache.cache_hits for cache in self.caches.values())
        total_misses = sum(cache.cache_misses for cache in self.caches.values())
        total_accesses = total_hits + total_misses
        
        return {
            'total_accesses': total_accesses,
            'total_hits': total_hits,
            'total_misses': total_misses,
            'overall_hit_rate': total_hits / total_accesses if total_accesses > 0 else 0,
            'total_invalidations': sum(cache.invalidations_sent for cache in self.caches.values()),
            'total_state_transitions': sum(cache.state_transitions for cache in self.caches.values()),
        }
