#!/usr/bin/env python3
"""
Example API calls for Distributed Synchronization System.
This script demonstrates all major API endpoints.
"""

import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8001"
HEADERS = {"Content-Type": "application/json"}


class DistributedSystemClient:
    """Client for interacting with distributed system."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.headers = HEADERS
    
    def health_check(self) -> Dict[str, Any]:
        """Check node health."""
        response = requests.get(f"{self.base_url}/health", headers=self.headers)
        return response.json()
    
    def get_status(self) -> Dict[str, Any]:
        """Get node status."""
        response = requests.get(f"{self.base_url}/status", headers=self.headers)
        return response.json()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get system metrics."""
        response = requests.get(f"{self.base_url}/metrics", headers=self.headers)
        return response.json()
    
    # Lock Management
    def acquire_lock(
        self,
        lock_id: str,
        requester_id: str,
        lock_type: str = "exclusive",
        ttl: int = None
    ) -> Dict[str, Any]:
        """Acquire a lock."""
        data = {
            "lock_id": lock_id,
            "requester_id": requester_id,
            "lock_type": lock_type,
        }
        if ttl:
            data["ttl"] = ttl
        
        response = requests.post(
            f"{self.base_url}/locks/acquire",
            json=data,
            headers=self.headers
        )
        return response.json()
    
    def release_lock(self, lock_id: str, owner_id: str) -> Dict[str, Any]:
        """Release a lock."""
        data = {
            "lock_id": lock_id,
            "owner_id": owner_id
        }
        response = requests.post(
            f"{self.base_url}/locks/release",
            json=data,
            headers=self.headers
        )
        return response.json()
    
    def get_locks(self) -> Dict[str, Any]:
        """Get all locks."""
        response = requests.get(f"{self.base_url}/locks", headers=self.headers)
        return response.json()
    
    def check_deadlock(self) -> Dict[str, Any]:
        """Check for deadlocks."""
        response = requests.get(
            f"{self.base_url}/locks/deadlock",
            headers=self.headers
        )
        return response.json()
    
    # Queue Operations
    def enqueue_message(
        self,
        queue_name: str,
        content: Dict[str, Any],
        producer_id: str
    ) -> Dict[str, Any]:
        """Enqueue a message."""
        data = {
            "queue_name": queue_name,
            "content": content,
            "producer_id": producer_id
        }
        response = requests.post(
            f"{self.base_url}/queue/enqueue",
            json=data,
            headers=self.headers
        )
        return response.json()
    
    def dequeue_message(
        self,
        queue_name: str,
        consumer_id: str
    ) -> Dict[str, Any]:
        """Dequeue a message."""
        data = {
            "queue_name": queue_name,
            "consumer_id": consumer_id
        }
        response = requests.post(
            f"{self.base_url}/queue/dequeue",
            json=data,
            headers=self.headers
        )
        return response.json()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status."""
        response = requests.get(
            f"{self.base_url}/queue/status",
            headers=self.headers
        )
        return response.json()
    
    # Cache Operations
    def cache_get(self, key: str) -> Dict[str, Any]:
        """Get value from cache."""
        response = requests.get(
            f"{self.base_url}/cache/{key}",
            headers=self.headers
        )
        return response.json()
    
    def cache_put(self, key: str, value: str) -> Dict[str, Any]:
        """Put value in cache."""
        data = {"value": value}
        response = requests.post(
            f"{self.base_url}/cache/{key}",
            json=data,
            headers=self.headers
        )
        return response.json()
    
    def cache_invalidate(self, key: str) -> Dict[str, Any]:
        """Invalidate cache entry."""
        response = requests.delete(
            f"{self.base_url}/cache/{key}",
            headers=self.headers
        )
        return response.json()
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache status."""
        response = requests.get(
            f"{self.base_url}/cache",
            headers=self.headers
        )
        return response.json()


def print_result(title: str, result: Dict[str, Any], indent: int = 0):
    """Pretty print result."""
    prefix = "  " * indent
    print(f"\n{prefix}► {title}")
    print(f"{prefix}{json.dumps(result, indent=2)}")


def demo_health_checks(client: DistributedSystemClient):
    """Demonstrate health checking."""
    print("\n" + "="*60)
    print("HEALTH CHECK DEMO")
    print("="*60)
    
    result = client.health_check()
    print_result("Health Check Result", result)
    
    result = client.get_status()
    print_result("Node Status", result)
    
    result = client.get_metrics()
    print_result("System Metrics", result, indent=1)


def demo_lock_management(client: DistributedSystemClient):
    """Demonstrate lock management."""
    print("\n" + "="*60)
    print("LOCK MANAGEMENT DEMO")
    print("="*60)
    
    # Acquire exclusive lock
    print("\n1. Acquiring exclusive lock...")
    result = client.acquire_lock("database_connection", "client1", "exclusive")
    print_result("Acquire Lock Result", result)
    
    # Try to acquire same lock (should fail)
    print("\n2. Attempting to acquire same lock (should timeout/fail)...")
    result = client.acquire_lock("database_connection", "client2", "exclusive", timeout=1)
    print_result("Second Acquire Attempt", result)
    
    # Get all locks
    print("\n3. Viewing all active locks...")
    result = client.get_locks()
    print_result("Active Locks", result)
    
    # Check for deadlocks
    print("\n4. Checking for deadlocks...")
    result = client.check_deadlock()
    print_result("Deadlock Check", result)
    
    # Release lock
    print("\n5. Releasing lock...")
    result = client.release_lock("database_connection", "client1")
    print_result("Release Lock Result", result)
    
    # Shared locks demo
    print("\n6. Acquiring shared locks (should be compatible)...")
    result1 = client.acquire_lock("config_file", "reader1", "shared")
    print_result("Reader 1 Shared Lock", result1)
    
    result2 = client.acquire_lock("config_file", "reader2", "shared")
    print_result("Reader 2 Shared Lock", result2)
    
    # Cleanup
    client.release_lock("config_file", "reader1")
    client.release_lock("config_file", "reader2")


def demo_queue_operations(client: DistributedSystemClient):
    """Demonstrate queue operations."""
    print("\n" + "="*60)
    print("QUEUE OPERATIONS DEMO")
    print("="*60)
    
    # Enqueue messages
    print("\n1. Enqueueing messages...")
    for i in range(3):
        result = client.enqueue_message(
            "task_queue",
            {"task_id": i, "task_name": f"Task_{i}", "priority": "high"},
            "producer1"
        )
        print_result(f"Enqueue Message {i+1}", result)
        time.sleep(0.1)
    
    # Get queue status
    print("\n2. Queue status after enqueuing...")
    result = client.get_queue_status()
    print_result("Queue Status", result)
    
    # Dequeue messages
    print("\n3. Dequeueing messages...")
    for i in range(3):
        result = client.dequeue_message("task_queue", f"consumer{i % 2 + 1}")
        print_result(f"Dequeue Message {i+1}", result)
        time.sleep(0.1)
    
    # Queue status after dequeue
    print("\n4. Queue status after dequeuing...")
    result = client.get_queue_status()
    print_result("Queue Status", result)


def demo_cache_operations(client: DistributedSystemClient):
    """Demonstrate cache operations."""
    print("\n" + "="*60)
    print("CACHE OPERATIONS DEMO")
    print("="*60)
    
    # Put values in cache
    print("\n1. Putting values in cache...")
    keys = ["user_123", "session_456", "config_cache"]
    for key in keys:
        result = client.cache_put(key, f"value_for_{key}")
        print_result(f"Cache Put: {key}", result)
        time.sleep(0.1)
    
    # Get cache status
    print("\n2. Cache status after puts...")
    result = client.get_cache_status()
    print_result("Cache Status", result)
    
    # Get values from cache
    print("\n3. Getting values from cache...")
    for key in keys:
        result = client.cache_get(key)
        print_result(f"Cache Get: {key}", result)
        time.sleep(0.1)
    
    # Cache hits should increase
    print("\n4. Cache status after gets (should show more hits)...")
    result = client.get_cache_status()
    print_result("Cache Status", result)
    
    # Invalidate cache entries
    print("\n5. Invalidating cache entries...")
    result = client.cache_invalidate("user_123")
    print_result("Invalidate: user_123", result)


def demo_stress_test(client: DistributedSystemClient):
    """Demonstrate stress testing."""
    print("\n" + "="*60)
    print("STRESS TEST DEMO")
    print("="*60)
    
    # Concurrent locks
    print("\n1. Rapid lock acquisitions...")
    start_time = time.time()
    for i in range(10):
        client.acquire_lock(f"lock_{i}", f"client_{i % 3}", "exclusive")
    elapsed = time.time() - start_time
    print(f"   Acquired 10 locks in {elapsed:.2f} seconds")
    
    # Concurrent queue operations
    print("\n2. Rapid queue operations...")
    start_time = time.time()
    for i in range(20):
        client.enqueue_message(
            f"queue_{i % 3}",
            {"data": f"message_{i}"},
            "producer"
        )
    elapsed = time.time() - start_time
    print(f"   Enqueued 20 messages in {elapsed:.2f} seconds")
    
    # Concurrent cache operations
    print("\n3. Rapid cache operations...")
    start_time = time.time()
    for i in range(50):
        client.cache_put(f"key_{i}", f"value_{i}")
    elapsed = time.time() - start_time
    print(f"   Cached 50 entries in {elapsed:.2f} seconds")
    
    # Final metrics
    print("\n4. Final metrics...")
    result = client.get_metrics()
    print_result("System Metrics", result)


def main():
    """Run all demos."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║   Distributed Synchronization System - API Examples       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Create client
    client = DistributedSystemClient()
    
    try:
        # Run demos
        demo_health_checks(client)
        demo_lock_management(client)
        demo_queue_operations(client)
        demo_cache_operations(client)
        demo_stress_test(client)
        
        print("\n" + "="*60)
        print("DEMO COMPLETED SUCCESSFULLY")
        print("="*60 + "\n")
        
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Could not connect to the distributed system")
        print("  Make sure nodes are running:")
        print("    export NODE_ID=node1 NODE_PORT=8001 && python -m src.nodes")
        print("  Or use Docker Compose:")
        print("    docker-compose -f docker/docker-compose.yml up -d")


if __name__ == "__main__":
    main()
