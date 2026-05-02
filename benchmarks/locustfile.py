from locust import HttpUser, task, between
import random

class DistributedSystemUser(HttpUser):
    # Simulasi jeda antar request user (1 sampai 3 detik)
    wait_time = between(1, 3)

    # --- BAGIAN 1: LOCK MANAGER ---

    @task(2)
    def acquire_lock(self):
        """Simulasi Acquire Lock (Baris 1 di Dashboard)"""
        # Memperkecil jangkauan angka agar terjadi kompetisi lock antar user
        lock_id = f"resource_{random.randint(1, 5)}" 
        payload = {
            "lock_id": lock_id,
            "requester_id": "locust_worker",
            "lock_type": "exclusive",
            "ttl": 10
        }
        # Menggunakan parameter 'name' agar tampilan di dashboard rapi
        self.client.post("/locks/acquire", json=payload, name="/locks/acquire")

    @task(1)
    def release_lock(self):
        """Simulasi Release Lock (Baris 2 di Dashboard)"""
        payload = {
            "lock_id": f"resource_{random.randint(1, 5)}",
            "owner_id": "locust_worker"
        }
        self.client.post("/locks/release", json=payload, name="/locks/release")

    # --- BAGIAN 2: DISTRIBUTED QUEUE ---

    @task(2)
    def push_to_queue(self):
        """Simulasi Enqueue Pesan (Baris 3 di Dashboard)"""
        payload = {
            "queue_name": "task_queue",
            "content": f"Data_{random.randint(100, 999)}",
            "producer_id": "locust_producer"
        }
        self.client.post("/queue/enqueue", json=payload, name="/queue/push")

    @task(1)
    def pull_from_queue(self):
        """Simulasi Dequeue Pesan (Baris 4 di Dashboard)"""
        payload = {
            "queue_name": "task_queue",
            "consumer_id": "locust_consumer"
        }
        self.client.post("/queue/dequeue", json=payload, name="/queue/pull")