"""Configuration management for distributed system."""

import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


class NodeConfig:
    """Node configuration settings."""

    def __init__(self):
        self.node_id: str = os.getenv("NODE_ID", "node1")
        self.host: str = os.getenv("NODE_HOST", "127.0.0.1")
        self.port: int = int(os.getenv("NODE_PORT", 8001))
        self.peers: List[str] = self._parse_peers(os.getenv("PEERS", ""))
        
        # Redis configuration
        self.redis_host: str = os.getenv("REDIS_HOST", "localhost")
        self.redis_port: int = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db: int = int(os.getenv("REDIS_DB", 0))
        
        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_file: str = os.getenv("LOG_FILE", "logs/node.log")
        
        # Timeouts
        self.heartbeat_interval: float = float(os.getenv("HEARTBEAT_INTERVAL", 1.0))
        self.election_timeout_min: float = float(os.getenv("ELECTION_TIMEOUT_MIN", 2))
        self.election_timeout_max: float = float(os.getenv("ELECTION_TIMEOUT_MAX", 4))
        self.sync_timeout: float = float(os.getenv("SYNC_TIMEOUT", 5.0))
        
        # Performance tuning
        self.batch_size: int = int(os.getenv("BATCH_SIZE", 100))
        self.max_connections: int = int(os.getenv("MAX_CONNECTIONS", 1000))
        self.queue_size: int = int(os.getenv("QUEUE_SIZE", 10000))
        self.cache_max_size: int = int(os.getenv("CACHE_MAX_SIZE", 1000))
        self.lru_cache_size: int = int(os.getenv("LRU_CACHE_SIZE", 500))
        
        # Feature flags
        self.enable_metrics: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"
        self.enable_deadlock_detection: bool = os.getenv("ENABLE_DEADLOCK_DETECTION", "true").lower() == "true"
        self.debug_mode: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"

    @staticmethod
    def _parse_peers(peers_str: str) -> List[str]:
        """Parse peers from comma-separated string."""
        if not peers_str:
            return []
        return [p.strip() for p in peers_str.split(",") if p.strip()]

    @property
    def base_url(self) -> str:
        """Get base URL for this node."""
        return f"http://{self.host}:{self.port}"

    def __repr__(self) -> str:
        return (
            f"NodeConfig(id={self.node_id}, host={self.host}, port={self.port}, "
            f"peers={len(self.peers)}, redis={self.redis_host}:{self.redis_port})"
        )


def get_config() -> NodeConfig:
    """Get global node configuration."""
    return NodeConfig()
