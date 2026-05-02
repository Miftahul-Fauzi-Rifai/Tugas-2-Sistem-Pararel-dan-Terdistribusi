"""Main entry point for running a distributed node."""

import asyncio
import sys
import logging
from loguru import logger
from aiohttp import web

from src.utils.config import get_config
from src.nodes.base_node import BaseNode
from src.communication.message_passing import Message, MessageType
from src.consensus.raft import RaftNode
from src.nodes.lock_manager import DistributedLockManager
from src.nodes.queue_node import DistributedQueue
from src.nodes.cache_node import MESICache


# Configure logging
def setup_logging(config):
    """Setup logging configuration."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=config.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
    )
    
    if config.log_file:
        logger.add(
            config.log_file,
            level=config.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB"
        )


class DistributedSyncNode(BaseNode):
    """Distributed synchronization node with lock manager, queue, and cache."""
    
    def __init__(self, config=None):
        super().__init__(config)
        
        # Initialize Raft node
        self.raft_node = RaftNode(
            node_id=self.node_id,
            all_nodes=[self.node_id] + self.config.peers,
            election_timeout_min=self.config.election_timeout_min,
            election_timeout_max=self.config.election_timeout_max,
            heartbeat_interval=self.config.heartbeat_interval,
        )
        
        self.raft_node.attach_transport(self.message_handler)
        
        # Initialize components
        self.lock_manager = DistributedLockManager(self.raft_node, self.node_id)
        self.queue = DistributedQueue(
            self.raft_node,
            self.node_id,
            [self.node_id] + self.config.peers,
            enable_persistence=True,
            replication_factor=3
        )
        self.cache = MESICache(
            self.node_id,
            self.config.lru_cache_size,
            [self.node_id] + self.config.peers
        )
        
        # Setup additional routes
        self._setup_component_routes()
        
        self.message_handler.register_handler(MessageType.VOTE_REQUEST, self._handle_vote_request)
        self.message_handler.register_handler(MessageType.HEARTBEAT, self._handle_raft_heartbeat)

    async def _handle_vote_request(self, message: Message):
        """Menerima dan memproses permintaan voting dari Kandidat lain"""
        term, granted = await self.raft_node.request_vote(
            candidate_id=message.data.get('candidate_id'),
            term=message.term,
            last_log_index=message.data.get('last_log_index', 0),
            last_log_term=message.data.get('last_log_term', 0)
        )
        return {"term": term, "vote_granted": granted}

    async def _handle_raft_heartbeat(self, message: Message):
        """Menerima heartbeat dari Leader agar node ini tidak memicu pemilu"""
        self.failure_detector.record_heartbeat(message.sender_id)
        
        self.raft_node.receive_heartbeat(
            leader_id=message.sender_id,
            term=message.term
        )
        self.current_term = self.raft_node.current_term
        return {"status": "ok", "term": self.raft_node.current_term}


    def _start_background_tasks(self):
        """Override untuk menjalankan task otomatis Raft bersama task bawaan"""
        super()._start_background_tasks()
        
        if hasattr(self.raft_node, 'run'):
            raft_task = asyncio.create_task(self.raft_node.run())
            self.running_tasks.append(raft_task)
            logger.info("🤖 Mode Otomatis Raft (Leader Election) BERHASIL diaktifkan!")
        else:
            logger.error("RaftNode tidak memiliki fungsi 'run'. Pastikan kerangka raft.py sudah lengkap.")

    def _setup_component_routes(self):
        """Setup routes for components."""
        from aiohttp import web
        
        # Lock manager routes
        self.app.router.add_post('/locks/acquire', self._acquire_lock_endpoint)
        self.app.router.add_post('/locks/release', self._release_lock_endpoint)
        self.app.router.add_get('/locks', self._get_locks_endpoint)
        self.app.router.add_get('/locks/deadlock', self._check_deadlock_endpoint)
        
        # Queue routes
        self.app.router.add_post('/queue/enqueue', self._enqueue_endpoint)
        self.app.router.add_post('/queue/dequeue', self._dequeue_endpoint)
        self.app.router.add_get('/queue/status', self._queue_status_endpoint)
        
        # Cache routes
        self.app.router.add_get('/cache/{key}', self._cache_get_endpoint)
        self.app.router.add_post('/cache/{key}', self._cache_set_endpoint)
        self.app.router.add_delete('/cache/{key}', self._cache_invalidate_endpoint)
        self.app.router.add_get('/cache', self._cache_status_endpoint)
        
        # Endpoint untuk Demo
        self.app.router.add_post('/force-leader', self._force_leader_endpoint)
            
    async def _get_status(self, request: web.Request) -> web.Response:
        """Safe Override status endpoint"""
        try:
            r_state = getattr(self.raft_node, 'state', self.state)
            if hasattr(r_state, 'value'):
                r_state = r_state.value
                
            r_term = getattr(self.raft_node, 'current_term', getattr(self, 'current_term', 0))
            r_vote = getattr(self.raft_node, 'voted_for', getattr(self, 'voted_for', None))
            
            return web.json_response({
                "node_id": self.node_id,
                "state": str(r_state).lower(),
                "term": r_term,
                "voted_for": r_vote,
                "is_running": self.is_running,
            })
        except Exception as e:
            logger.error(f"Error di _get_status: {e}")
            return web.json_response({"error": "Internal Server Error", "detail": str(e)}, status=200)
        
    async def _force_leader_endpoint(self, request: web.Request) -> web.Response:
        try:
            if hasattr(self.raft_node, 'state'):
                self.raft_node.state = 'leader'
            self.state = 'leader'
            
            if hasattr(self.raft_node, 'current_term'):
                self.raft_node.current_term += 1
            self.current_term += 1
            
            return web.json_response({
                "status": "success", 
                "message": f"Node {self.node_id} dipaksa menjadi LEADER",
                "term": getattr(self.raft_node, 'current_term', self.current_term)
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=200)

    # =========================================================================
    # FIX: BARIS INI YANG DIUBAH! (Menghapus .value karena input dari json)
    # =========================================================================
    async def _acquire_lock_endpoint(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            success, error = await self.lock_manager.acquire_lock(
                data.get('lock_id'), 
                data.get('requester_id'), 
                data.get('lock_type', 'exclusive'), # Tidak pakai .value
                data.get('ttl')
            )
            return web.json_response({'success': success, 'lock_id': data.get('lock_id'), 'error': error})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)
    
    async def _release_lock_endpoint(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            success, error = await self.lock_manager.release_lock(data.get('lock_id'), data.get('owner_id'))
            return web.json_response({'success': success, 'lock_id': data.get('lock_id'), 'error': error})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)
    
    async def _get_locks_endpoint(self, request: web.Request) -> web.Response:
        return web.json_response(self.lock_manager.get_metrics())
    
    async def _check_deadlock_endpoint(self, request: web.Request) -> web.Response:
        return web.json_response(await self.lock_manager.check_deadlock())
    
    async def _enqueue_endpoint(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            success, message_id = await self.queue.enqueue(
                data.get('queue_name'), data.get('content'), data.get('producer_id')
            )
            return web.json_response({'success': success, 'message_id': message_id})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)
    
    async def _dequeue_endpoint(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            message = await self.queue.dequeue(data.get('queue_name'), data.get('consumer_id'))
            if message:
                return web.json_response({'message_id': message.message_id, 'content': str(message.content), 'producer_id': message.producer_id})
            return web.json_response({'error': 'No message available'}, status=404)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)
    
    async def _queue_status_endpoint(self, request: web.Request) -> web.Response:
        return web.json_response(self.queue.get_metrics())
    
    async def _cache_get_endpoint(self, request: web.Request) -> web.Response:
        key = request.match_info['key']
        value = self.cache.get(key)
        if value is not None:
            return web.json_response({'key': key, 'value': str(value), 'found': True})
        return web.json_response({'key': key, 'found': False}, status=404)
    
    async def _cache_set_endpoint(self, request: web.Request) -> web.Response:
        try:
            key = request.match_info['key']
            data = await request.json()
            state = self.cache.put(key, data.get('value'))
            return web.json_response({'key': key, 'state': state.value if hasattr(state, 'value') else state})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)
    
    async def _cache_invalidate_endpoint(self, request: web.Request) -> web.Response:
        key = request.match_info['key']
        success = self.cache.invalidate(key, self.node_id)
        return web.json_response({'key': key, 'invalidated': success})
    
    async def _cache_status_endpoint(self, request: web.Request) -> web.Response:
        return web.json_response(self.cache.get_metrics())

    async def run(self):
        """Implementasi wajib dari metode abstrak BaseNode."""
        try:
            await self.start()
            logger.info(f"Node {self.node_id} started successfully")
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Diterima Keyboard Interrupt. Mematikan node...")
        except Exception as e:
            logger.error(f"Error fatal saat menjalankan node: {e}")
        finally:
            await self.stop()


async def main():
    """Main entry point."""
    config = get_config()
    setup_logging(config)
    
    logger.info(f"Starting Distributed Synchronization Node")
    logger.info(f"Configuration: {config}")
    
    node = DistributedSyncNode(config)
    await node.run()


if __name__ == "__main__":
    asyncio.run(main())