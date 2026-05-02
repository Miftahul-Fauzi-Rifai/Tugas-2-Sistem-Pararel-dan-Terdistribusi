"""Raft Consensus Algorithm implementation."""

import asyncio
import random
import time
from typing import Callable, Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

from src.communication.message_passing import Message, MessageHandler, MessageType


@dataclass
class LogEntry:
    """A log entry in Raft."""
    term: int
    index: int
    command: Dict[str, Any]
    committed: bool = False


@dataclass
class RaftState:
    """Persistent state on all servers."""
    current_term: int = 0
    voted_for: Optional[str] = None
    log: List[LogEntry] = field(default_factory=list)


@dataclass
class VolatileState:
    """Volatile state on all servers."""
    commit_index: int = 0
    last_applied: int = 0


@dataclass
class LeaderState:
    """Volatile state on leaders."""
    next_index: Dict[str, int] = field(default_factory=dict)
    match_index: Dict[str, int] = field(default_factory=dict)


class RaftNode:
    """Raft consensus node."""
    
    def __init__(
        self,
        node_id: str,
        all_nodes: List[str],
        election_timeout_min: float = 2.0,
        election_timeout_max: float = 4.0,
        heartbeat_interval: float = 1.0,
    ):
        self.node_id = node_id
        self.all_nodes = all_nodes
        self.peers = [n for n in all_nodes if n != node_id]
        
        # Timeouts
        self.election_timeout_min = election_timeout_min
        self.election_timeout_max = election_timeout_max
        self.heartbeat_interval = heartbeat_interval
        self._update_election_timeout()

        # Transport and runtime state
        self.message_handler: Optional[MessageHandler] = None
        self.state_change_callback: Optional[Callable[["RaftNode"], None]] = None
        self._election_lock = asyncio.Lock()
        self._running = False
        self._last_leader_heartbeat = time.monotonic()
        
        # Internal State
        self.state = "follower" 
        self.raft_state = RaftState()
        self.volatile_state = VolatileState()
        self.leader_state = LeaderState()
        self.current_leader = None
        
        # State machine
        self.state_machine: Dict[str, Any] = {}
        
        # Deadlock detection
        self.deadlock_detector = DeadlockDetector()

    def _is_leader(self) -> bool:
        """Helper to check if current node is leader."""
        return self.state == "leader"

    @property
    def current_term(self):
        return self.raft_state.current_term
        
    @current_term.setter
    def current_term(self, value):
        self.raft_state.current_term = value

    @property
    def voted_for(self):
        return self.raft_state.voted_for
        
    @voted_for.setter
    def voted_for(self, value):
        self.raft_state.voted_for = value

    def attach_transport(self, message_handler: MessageHandler):
        self.message_handler = message_handler

    def _majority_count(self) -> int:
        return (len(self.all_nodes) // 2) + 1

    def _notify_state_change(self):
        if self.state_change_callback:
            try:
                self.state_change_callback(self)
            except Exception as exc:
                logger.debug(f"State change callback failed for {self.node_id}: {exc}")

    def receive_heartbeat(self, leader_id: str, term: int):
        if term >= self.raft_state.current_term:
            if term > self.raft_state.current_term:
                self.raft_state.current_term = term
                self.raft_state.voted_for = None
            
            self.current_leader = leader_id
            self.state = "follower"
            self._last_leader_heartbeat = time.monotonic()
            self._notify_state_change()

    async def _broadcast_heartbeat(self):
        if not self.message_handler or not self.peers:
            return

        heartbeat = Message(
            message_type=MessageType.HEARTBEAT,
            sender_id=self.node_id,
            receiver_id="broadcast",
            term=self.raft_state.current_term,
            data={"leader_id": self.node_id},
        )
        await self.message_handler.broadcast_message(self.peers, heartbeat)

    async def _start_election(self):
        async with self._election_lock:
            if self.state == "leader":
                return

            logger.info(f"Node {self.node_id}: Starting election for term {self.raft_state.current_term + 1}")
            
            self.state = "candidate"
            self.raft_state.current_term += 1
            self.raft_state.voted_for = self.node_id
            self.current_leader = None
            self._update_election_timeout()
            self._notify_state_change()

            if not self.message_handler or not self.peers:
                self.become_leader()
                return

            vote_request = Message(
                message_type=MessageType.VOTE_REQUEST,
                sender_id=self.node_id,
                receiver_id="broadcast",
                term=self.raft_state.current_term,
                data={
                    "candidate_id": self.node_id,
                    "last_log_index": len(self.raft_state.log) - 1,
                    "last_log_term": self._get_last_log_term(),
                },
            )

            votes = 1
            results = await self.message_handler.broadcast_message(self.peers, vote_request)

            for peer_response in results.values():
                if not peer_response: 
                    continue
                
                response_term = peer_response.get("term", self.raft_state.current_term)
                if response_term > self.raft_state.current_term:
                    self.become_follower(response_term)
                    return

                if peer_response.get("vote_granted"):
                    votes += 1

            if votes >= self._majority_count() and self.state == "candidate":
                self.become_leader()
            else:
                self.become_follower(self.raft_state.current_term)
    
    def _update_election_timeout(self):
        self.election_timeout = random.uniform(self.election_timeout_min, self.election_timeout_max)

    async def run(self):
        self._running = True
        self._last_leader_heartbeat = time.monotonic()
        logger.info(f"Node {self.node_id}: Raft loop started")

        try:
            while self._running:
                await asyncio.sleep(0.1) 

                if self.state == "leader":
                    await self._broadcast_heartbeat()
                    await asyncio.sleep(self.heartbeat_interval)
                    continue

                if time.monotonic() - self._last_leader_heartbeat >= self.election_timeout:
                    await self._start_election()
                    
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Raft loop error: {exc}")

    async def append_entry(self, command: Dict[str, Any]) -> int:
        if not self._is_leader():
            raise RuntimeError("Only leader can append entries")
        
        entry = LogEntry(term=self.raft_state.current_term, index=len(self.raft_state.log), command=command)
        self.raft_state.log.append(entry)
        return entry.index
    
    async def request_vote(self, candidate_id: str, term: int, last_log_index: int, last_log_term: int) -> Tuple[int, bool]:
        if term > self.raft_state.current_term:
            self.become_follower(term)
        
        if term < self.raft_state.current_term:
            return self.raft_state.current_term, False
        
        local_term = self._get_last_log_term()
        local_index = len(self.raft_state.log) - 1
        up_to_date = (last_log_term > local_term or (last_log_term == local_term and last_log_index >= local_index))

        if (self.raft_state.voted_for is None or self.raft_state.voted_for == candidate_id) and up_to_date:
            self.raft_state.voted_for = candidate_id
            self._last_leader_heartbeat = time.monotonic()
            return term, True
        
        return self.raft_state.current_term, False

    async def append_entries(self, leader_id: str, term: int, prev_log_index: int, prev_log_term: int, entries: List[LogEntry], leader_commit: int) -> Tuple[int, bool]:
        if term > self.raft_state.current_term:
            self.become_follower(term)
        
        if term < self.raft_state.current_term:
            return self.raft_state.current_term, False
        
        self._last_leader_heartbeat = time.monotonic()
        self.current_leader = leader_id
        
        if prev_log_index >= 0:
            if prev_log_index >= len(self.raft_state.log) or self.raft_state.log[prev_log_index].term != prev_log_term:
                return self.raft_state.current_term, False
        
        for entry in entries:
            if entry.index >= len(self.raft_state.log):
                self.raft_state.log.append(entry)
            elif self.raft_state.log[entry.index].term != entry.term:
                self.raft_state.log[entry.index] = entry
        
        if leader_commit > self.volatile_state.commit_index:
            self.volatile_state.commit_index = min(leader_commit, len(self.raft_state.log) - 1)
            self._apply_committed_entries()
        
        return self.raft_state.current_term, True
    
    def _apply_committed_entries(self):
        while self.volatile_state.last_applied < self.volatile_state.commit_index:
            self.volatile_state.last_applied += 1
            entry = self.raft_state.log[self.volatile_state.last_applied]
            logger.debug(f"Node {self.node_id}: Applied entry {entry.index}")
    
    def _get_last_log_term(self) -> int:
        return self.raft_state.log[-1].term if self.raft_state.log else 0
    
    def become_leader(self):
        self.current_leader = self.node_id
        self.state = "leader"
        self._last_leader_heartbeat = time.monotonic()
        logger.info(f"🏆 Node {self.node_id} RESMI MENJADI LEADER!")
        self._notify_state_change()
    
    def become_follower(self, term: int):
        self.raft_state.current_term = term
        self.raft_state.voted_for = None
        self.state = "follower"
        self._last_leader_heartbeat = time.monotonic()
        self._notify_state_change()


class DeadlockDetector:
    def __init__(self):
        self.wait_for_graph: Dict[str, List[str]] = {}
        self.lock_holders: Dict[str, str] = {}
        self.lock_waiters: Dict[str, List[str]] = {}
    
    def acquire_lock(self, node_id: str, lock_id: str):
        if lock_id not in self.lock_holders:
            self.lock_holders[lock_id] = node_id
        else:
            if lock_id not in self.lock_waiters: 
                self.lock_waiters[lock_id] = []
            self.lock_waiters[lock_id].append(node_id)
            if node_id not in self.wait_for_graph: 
                self.wait_for_graph[node_id] = []
            self.wait_for_graph[node_id].append(self.lock_holders[lock_id])

    def release_lock(self, lock_id: str):
        if lock_id in self.lock_holders: 
            del self.lock_holders[lock_id]
        if lock_id in self.lock_waiters: 
            del self.lock_waiters[lock_id]

    def detect_cycle(self) -> Optional[List[str]]:
        visited, rec_stack = set(), set()
        
        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            if node in self.wait_for_graph:
                for neighbor in self.wait_for_graph[node]:
                    if neighbor not in visited:
                        cycle = dfs(neighbor, path[:])
                        if cycle: return cycle
                    elif neighbor in rec_stack:
                        return path[path.index(neighbor):] + [neighbor]
            rec_stack.remove(node)
            return None
            
        for node in self.wait_for_graph:
            if node not in visited:
                cycle = dfs(node, [])
                if cycle: return cycle
        return None