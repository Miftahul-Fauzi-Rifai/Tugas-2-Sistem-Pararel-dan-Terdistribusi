"""Metrics collection and reporting."""

from typing import Dict, Any
from datetime import datetime
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import time


class SystemMetrics:
    """Collect and report system metrics."""

    def __init__(self, node_id: str, enable_prometheus: bool = True):
        self.node_id = node_id
        self.enable_prometheus = enable_prometheus
        
        if enable_prometheus:
            self.registry = CollectorRegistry()
        
        # Counters
        self.messages_sent = Counter(
            'messages_sent_total',
            'Total messages sent',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        self.messages_received = Counter(
            'messages_received_total',
            'Total messages received',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        self.locks_acquired = Counter(
            'locks_acquired_total',
            'Total locks acquired',
            ['node_id', 'lock_type'],
            registry=self.registry if enable_prometheus else None
        )
        self.queue_items_processed = Counter(
            'queue_items_processed_total',
            'Total queue items processed',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        
        # Histograms
        self.message_latency = Histogram(
            'message_latency_seconds',
            'Message latency in seconds',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        self.lock_acquisition_time = Histogram(
            'lock_acquisition_seconds',
            'Lock acquisition time in seconds',
            ['node_id', 'lock_type'],
            registry=self.registry if enable_prometheus else None
        )
        self.queue_processing_time = Histogram(
            'queue_processing_seconds',
            'Queue item processing time in seconds',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        
        # Gauges
        self.active_connections = Gauge(
            'active_connections',
            'Number of active connections',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        self.queue_size = Gauge(
            'queue_size',
            'Current queue size',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        self.cache_size = Gauge(
            'cache_size',
            'Current cache size',
            ['node_id'],
            registry=self.registry if enable_prometheus else None
        )
        
        # Local metrics
        self.local_metrics: Dict[str, Any] = {
            'messages_sent': 0,
            'messages_received': 0,
            'locks_acquired': {},
            'queue_items_processed': 0,
            'total_latency': 0.0,
            'latency_count': 0,
        }

    def record_message_sent(self):
        """Record a message sent."""
        self.local_metrics['messages_sent'] += 1
        if self.enable_prometheus:
            self.messages_sent.labels(node_id=self.node_id).inc()

    def record_message_received(self):
        """Record a message received."""
        self.local_metrics['messages_received'] += 1
        if self.enable_prometheus:
            self.messages_received.labels(node_id=self.node_id).inc()

    def record_message_latency(self, latency: float):
        """Record message latency."""
        self.local_metrics['total_latency'] += latency
        self.local_metrics['latency_count'] += 1
        if self.enable_prometheus:
            self.message_latency.labels(node_id=self.node_id).observe(latency)

    def record_lock_acquired(self, lock_type: str):
        """Record lock acquisition."""
        self.local_metrics['locks_acquired'][lock_type] = (
            self.local_metrics['locks_acquired'].get(lock_type, 0) + 1
        )
        if self.enable_prometheus:
            self.locks_acquired.labels(node_id=self.node_id, lock_type=lock_type).inc()

    def record_lock_acquisition_time(self, lock_type: str, time_seconds: float):
        """Record lock acquisition time."""
        if self.enable_prometheus:
            self.lock_acquisition_time.labels(
                node_id=self.node_id, lock_type=lock_type
            ).observe(time_seconds)

    def record_queue_item_processed(self):
        """Record queue item processed."""
        self.local_metrics['queue_items_processed'] += 1
        if self.enable_prometheus:
            self.queue_items_processed.labels(node_id=self.node_id).inc()

    def record_queue_processing_time(self, time_seconds: float):
        """Record queue processing time."""
        if self.enable_prometheus:
            self.queue_processing_time.labels(node_id=self.node_id).observe(time_seconds)

    def set_active_connections(self, count: int):
        """Set active connection count."""
        if self.enable_prometheus:
            self.active_connections.labels(node_id=self.node_id).set(count)

    def set_queue_size(self, size: int):
        """Set queue size."""
        if self.enable_prometheus:
            self.queue_size.labels(node_id=self.node_id).set(size)

    def set_cache_size(self, size: int):
        """Set cache size."""
        if self.enable_prometheus:
            self.cache_size.labels(node_id=self.node_id).set(size)

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        avg_latency = (
            self.local_metrics['total_latency'] / self.local_metrics['latency_count']
            if self.local_metrics['latency_count'] > 0
            else 0
        )
        
        return {
            'timestamp': datetime.now().isoformat(),
            'node_id': self.node_id,
            'messages_sent': self.local_metrics['messages_sent'],
            'messages_received': self.local_metrics['messages_received'],
            'locks_acquired': self.local_metrics['locks_acquired'],
            'queue_items_processed': self.local_metrics['queue_items_processed'],
            'average_latency_ms': avg_latency * 1000,
        }

    def reset(self):
        """Reset local metrics."""
        self.local_metrics = {
            'messages_sent': 0,
            'messages_received': 0,
            'locks_acquired': {},
            'queue_items_processed': 0,
            'total_latency': 0.0,
            'latency_count': 0,
        }
