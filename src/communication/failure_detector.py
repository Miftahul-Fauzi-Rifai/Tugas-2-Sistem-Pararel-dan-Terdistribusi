"""Failure detection and network partition detection."""

import time
from typing import Dict, List, Optional
from loguru import logger


class FailureDetector:
    """Detects node failures and network partitions using heartbeat mechanism."""
    
    def __init__(self, heartbeat_interval: float = 1.0, threshold: int = 3):
        """
        Initialize failure detector.
        
        Args:
            heartbeat_interval: Expected interval between heartbeats (seconds)
            threshold: Number of missed heartbeats to declare node dead
        """
        self.heartbeat_interval = heartbeat_interval
        self.threshold = threshold  # Number of missed heartbeats to declare dead
        self.heartbeats: Dict[str, float] = {}
        self.missed_heartbeats: Dict[str, int] = {}
    
    def record_heartbeat(self, node_id: str):
        """
        Record a heartbeat from a node.
        
        Args:
            node_id: ID of the node sending heartbeat
        """
        self.heartbeats[node_id] = time.time()
        self.missed_heartbeats[node_id] = 0
        logger.debug(f"Heartbeat recorded from {node_id}")
    
    def check_node_health(self, node_id: str, current_time: Optional[float] = None) -> bool:
        """
        Check if a node is healthy based on heartbeat activity.
        
        Args:
            node_id: ID of the node to check
            current_time: Current timestamp (for testing)
            
        Returns:
            True if node is healthy, False otherwise
        """
        if current_time is None:
            current_time = time.time()
        
        if node_id not in self.heartbeats:
            return False
        
        time_since_heartbeat = current_time - self.heartbeats[node_id]
        expected_interval = self.heartbeat_interval * self.threshold
        
        is_healthy = time_since_heartbeat <= expected_interval
        
        if not is_healthy:
            logger.warning(
                f"Node {node_id} appears to be down "
                f"(no heartbeat for {time_since_heartbeat:.1f}s)"
            )
        
        return is_healthy
    
    def missed_heartbeat(self, node_id: str):
        """
        Record a missed heartbeat from a node.
        
        Args:
            node_id: ID of the node that missed heartbeat
        """
        if node_id not in self.missed_heartbeats:
            self.missed_heartbeats[node_id] = 0
        self.missed_heartbeats[node_id] += 1
        logger.debug(f"Missed heartbeat from {node_id}: {self.missed_heartbeats[node_id]}")
    
    def get_unhealthy_nodes(self, nodes: List[str], current_time: Optional[float] = None) -> List[str]:
        """
        Get list of unhealthy nodes from a list of node IDs.
        
        Args:
            nodes: List of node IDs to check
            current_time: Current timestamp (for testing)
            
        Returns:
            List of unhealthy node IDs
        """
        unhealthy = [
            node_id for node_id in nodes 
            if not self.check_node_health(node_id, current_time)
        ]
        
        if unhealthy:
            logger.warning(f"Detected unhealthy nodes: {unhealthy}")
        
        return unhealthy
    
    def is_network_partitioned(self, healthy_nodes: int, total_nodes: int) -> bool:
        """
        Detect if a network partition exists.
        
        Network partition is detected when less than majority of nodes are healthy.
        This ensures split-brain prevention through quorum.
        
        Args:
            healthy_nodes: Number of healthy nodes
            total_nodes: Total number of nodes
            
        Returns:
            True if network partition detected, False otherwise
        """
        # Network partition if less than majority nodes are healthy
        majority = (total_nodes // 2) + 1
        partitioned = healthy_nodes < majority
        
        if partitioned:
            logger.error(
                f"Network partition detected! "
                f"Healthy nodes: {healthy_nodes}, Required majority: {majority}"
            )
        
        return partitioned
    
    def get_status(self) -> Dict:
        """
        Get current status of all tracked nodes.
        
        Returns:
            Dictionary with node health information
        """
        return {
            "heartbeats": self.heartbeats.copy(),
            "missed_heartbeats": self.missed_heartbeats.copy()
        }
    
    def reset(self):
        """Reset all failure detection state."""
        self.heartbeats.clear()
        self.missed_heartbeats.clear()
        logger.info("Failure detector state reset")
