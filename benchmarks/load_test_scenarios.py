"""Performance benchmarks for distributed system."""

import time
import asyncio
from typing import List, Dict, Any
from src.consensus.raft import RaftNode, LogEntry
from src.nodes.lock_manager import DistributedLockManager, LockType
from src.nodes.queue_node import DistributedQueue
from src.nodes.cache_node import MESICache, CacheCoherence
import statistics


class BenchmarkRunner:
    """Run performance benchmarks."""
    
    def __init__(self, warmup_iterations: int = 100, iterations: int = 1000):
        self.warmup_iterations = warmup_iterations
        self.iterations = iterations
        self.results = {}
    
    def measure_time(self, func, *args, **kwargs) -> float:
        """Measure execution time of a function."""
        start = time.time()
        func(*args, **kwargs)
        return time.time() - start
    
    async def measure_async_time(self, func, *args, **kwargs) -> float:
        """Measure execution time of async function."""
        start = time.time()
        await func(*args, **kwargs)
        return time.time() - start
    
    def run_benchmark(self, name: str, func, *args, **kwargs) -> Dict[str, Any]:
        """Run a benchmark and return statistics."""
        # Warmup
        for _ in range(self.warmup_iterations):
            self.measure_time(func, *args, **kwargs)
        
        # Actual benchmark
        times = []
        for _ in range(self.iterations):
            time_taken = self.measure_time(func, *args, **kwargs)
            times.append(time_taken)
        
        # Calculate statistics
        result = {
            'name': name,
            'iterations': self.iterations,
            'min': min(times),
            'max': max(times),
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0,
            'total': sum(times),
            'throughput': self.iterations / sum(times),  # ops/sec
        }
        
        self.results[name] = result
        return result
    
    async def run_async_benchmark(
        self,
        name: str,
        func,
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """Run async benchmark."""
        # Warmup
        for _ in range(self.warmup_iterations):
            await self.measure_async_time(func, *args, **kwargs)
        
        # Actual benchmark
        times = []
        for _ in range(self.iterations):
            time_taken = await self.measure_async_time(func, *args, **kwargs)
            times.append(time_taken)
        
        # Calculate statistics
        result = {
            'name': name,
            'iterations': self.iterations,
            'min': min(times),
            'max': max(times),
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0,
            'total': sum(times),
            'throughput': self.iterations / sum(times),
        }
        
        self.results[name] = result
        return result
    
    def print_results(self):
        """Print benchmark results."""
        print("\n" + "="*80)
        print("PERFORMANCE BENCHMARK RESULTS")
        print("="*80)
        
        for name, result in self.results.items():
            print(f"\n{name}:")
            print(f"  Iterations:  {result['iterations']}")
            print(f"  Min:         {result['min']*1000:.4f} ms")
            print(f"  Max:         {result['max']*1000:.4f} ms")
            print(f"  Mean:        {result['mean']*1000:.4f} ms")
            print(f"  Median:      {result['median']*1000:.4f} ms")
            print(f"  Stdev:       {result['stdev']*1000:.4f} ms")
            print(f"  Throughput:  {result['throughput']:.2f} ops/sec")


class RaftBenchmark:
    """Raft consensus benchmarks."""
    
    @staticmethod
    def append_entry_to_log():
        """Benchmark appending entries to Raft log."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        
        async def append():
            command = {'op': 'set', 'key': 'test', 'value': 'value'}
            await raft.append_entry(command)
        
        return append


class LockManagerBenchmark:
    """Lock manager benchmarks."""
    
    @staticmethod
    def lock_acquisition():
        """Benchmark lock acquisition."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        lock_mgr = DistributedLockManager(raft, 'node1')
        
        counter = [0]
        
        async def acquire():
            counter[0] += 1
            lock_id = f'lock_{counter[0]}'
            await lock_mgr.acquire_lock(lock_id, 'node1', LockType.EXCLUSIVE, timeout=1)
            await lock_mgr.release_lock(lock_id, 'node1')
        
        return acquire


class QueueBenchmark:
    """Queue benchmarks."""
    
    @staticmethod
    def enqueue_dequeue():
        """Benchmark enqueue/dequeue."""
        nodes = ['node1', 'node2', 'node3']
        raft = RaftNode('node1', nodes)
        raft.become_leader()
        queue = DistributedQueue(raft, 'node1', nodes)
        
        counter = [0]
        
        async def enqueue_dequeue():
            counter[0] += 1
            msg_id = f'msg_{counter[0]}'
            await queue.enqueue('test_queue', f'message_{counter[0]}', 'producer')
            await queue.dequeue('test_queue', 'consumer')
        
        return enqueue_dequeue


class CacheBenchmark:
    """Cache benchmarks."""
    
    @staticmethod
    def cache_operations():
        """Benchmark cache get/put."""
        cache = MESICache('node1', cache_size=10000)
        counter = [0]
        
        def operations():
            counter[0] += 1
            key = f'key_{counter[0] % 1000}'
            value = f'value_{counter[0]}'
            cache.put(key, value)
            cache.get(key)
        
        return operations


async def run_all_benchmarks():
    """Run all benchmarks."""
    runner = BenchmarkRunner(warmup_iterations=100, iterations=1000)
    
    print("Running Benchmarks...")
    print("-" * 80)
    
    # Cache benchmarks (synchronous)
    print("\n1. Running Cache Benchmarks...")
    cache_bench = CacheBenchmark.cache_operations()
    result = runner.run_benchmark("Cache Get/Put Operations", cache_bench)
    print(f"   Throughput: {result['throughput']:.2f} ops/sec")
    
    # Raft benchmarks (async)
    print("\n2. Running Raft Benchmarks...")
    raft_bench = RaftBenchmark.append_entry_to_log()
    result = await runner.run_async_benchmark("Raft Log Append", raft_bench)
    print(f"   Throughput: {result['throughput']:.2f} ops/sec")
    
    # Lock manager benchmarks (async)
    print("\n3. Running Lock Manager Benchmarks...")
    lock_bench = LockManagerBenchmark.lock_acquisition()
    result = await runner.run_async_benchmark(
        "Lock Acquisition/Release",
        lock_bench
    )
    print(f"   Throughput: {result['throughput']:.2f} ops/sec")
    
    # Queue benchmarks (async)
    print("\n4. Running Queue Benchmarks...")
    queue_bench = QueueBenchmark.enqueue_dequeue()
    result = await runner.run_async_benchmark(
        "Queue Enqueue/Dequeue",
        queue_bench
    )
    print(f"   Throughput: {result['throughput']:.2f} ops/sec")
    
    runner.print_results()


if __name__ == '__main__':
    asyncio.run(run_all_benchmarks())
