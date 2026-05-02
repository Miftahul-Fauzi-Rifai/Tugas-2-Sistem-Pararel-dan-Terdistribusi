# Deployment Guide

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Docker Deployment](#docker-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)
7. [Performance Tuning](#performance-tuning)

## Prerequisites

### System Requirements

- Python 3.8+
- Docker 20.10+ (for containerized deployment)
- Docker Compose 1.29+ (for multi-node local deployment)
- 4GB RAM minimum (8GB recommended)
- 2 CPU cores minimum

### Software Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv python3.11-dev
sudo apt-get install docker.io docker-compose
sudo usermod -aG docker $USER

# macOS with Homebrew
brew install python@3.11 docker docker-compose

# Windows
# Download from python.org and docker.com
```

## Local Development

### Installation

```bash
# 1. Clone repository
git clone <repository-url>
cd distributed-sync-system

# 2. Create virtual environment
python3.11 -m venv venv

# 3. Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create log directory
mkdir -p logs
```

### Running 3-Node Cluster Locally

#### Terminal 1 - Node 1

```bash
export NODE_ID=node1
export NODE_PORT=8001
export PEERS=http://127.0.0.1:8002,http://127.0.0.1:8003
export REDIS_HOST=localhost
python -m src.nodes
```

#### Terminal 2 - Node 2

```bash
export NODE_ID=node2
export NODE_PORT=8002
export PEERS=http://127.0.0.1:8001,http://127.0.0.1:8003
export REDIS_HOST=localhost
python -m src.nodes
```

#### Terminal 3 - Node 3

```bash
export NODE_ID=node3
export NODE_PORT=8003
export PEERS=http://127.0.0.1:8001,http://127.0.0.1:8002
export REDIS_HOST=localhost
python -m src.nodes
```

### Testing Nodes

```bash
# Health check
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Get metrics
curl http://localhost:8001/metrics

# Test lock acquisition
curl -X POST http://localhost:8001/locks/acquire \
  -H "Content-Type: application/json" \
  -d '{
    "lock_id": "test_lock",
    "requester_id": "node1",
    "lock_type": "exclusive"
  }'
```

## Docker Deployment

### Quick Start

```bash
# Navigate to project root
cd distributed-sync-system

# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Check service status
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop services
docker-compose -f docker/docker-compose.yml down
```

### Custom Configuration

Create `.env` file at project root:

```env
# Node 1 Configuration
NODE1_ID=node1
NODE1_PORT=8001

# Node 2 Configuration
NODE2_ID=node2
NODE2_PORT=8002

# Node 3 Configuration
NODE3_ID=node3
NODE3_PORT=8003

# Redis Configuration
REDIS_PORT=6379

# Logging
LOG_LEVEL=INFO
```

Update `docker-compose.yml` to use custom `.env`:

```yaml
env_file:
  - .env
```

### Building Custom Images

```bash
# Build image
docker build -t my-distributed-sync:1.0.0 \
  -f docker/Dockerfile.node .

# Tag for registry
docker tag my-distributed-sync:1.0.0 \
  your-registry/distributed-sync:1.0.0

# Push to registry
docker push your-registry/distributed-sync:1.0.0
```

### Multi-Node Docker Deployment

```bash
# Create custom network
docker network create distributed-network

# Run node 1
docker run -d \
  --name node1 \
  --network distributed-network \
  -p 8001:8001 \
  -e NODE_ID=node1 \
  -e NODE_PORT=8001 \
  -e PEERS=http://node2:8002,http://node3:8003 \
  my-distributed-sync:1.0.0

# Run node 2
docker run -d \
  --name node2 \
  --network distributed-network \
  -p 8002:8002 \
  -e NODE_ID=node2 \
  -e NODE_PORT=8002 \
  -e PEERS=http://node1:8001,http://node3:8003 \
  my-distributed-sync:1.0.0

# Run node 3
docker run -d \
  --name node3 \
  --network distributed-network \
  -p 8003:8003 \
  -e NODE_ID=node3 \
  -e NODE_PORT=8003 \
  -e PEERS=http://node1:8001,http://node2:8002 \
  my-distributed-sync:1.0.0

# Verify
docker ps
curl http://localhost:8001/health
```

## Kubernetes Deployment

### Deployment Manifests

Create `kubernetes/deployment.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: distributed-sync-config
data:
  LOG_LEVEL: "INFO"
  ENABLE_METRICS: "true"

---
apiVersion: v1
kind: Service
metadata:
  name: distributed-sync
spec:
  type: ClusterIP
  selector:
    app: distributed-sync
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8001

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: distributed-sync
spec:
  serviceName: distributed-sync
  replicas: 3
  selector:
    matchLabels:
      app: distributed-sync
  template:
    metadata:
      labels:
        app: distributed-sync
    spec:
      containers:
      - name: node
        image: your-registry/distributed-sync:1.0.0
        ports:
        - containerPort: 8001
        env:
        - name: NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: NODE_PORT
          value: "8001"
        - name: PEERS
          value: "http://distributed-sync-0:8001,http://distributed-sync-1:8001,http://distributed-sync-2:8001"
        envFrom:
        - configMapRef:
            name: distributed-sync-config
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        volumeMounts:
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: logs
        emptyDir: {}
```

### Deploy to Kubernetes

```bash
# Apply manifests
kubectl apply -f kubernetes/deployment.yaml

# Check deployment
kubectl get statefulsets
kubectl get pods
kubectl get services

# View logs
kubectl logs distributed-sync-0
kubectl logs -f distributed-sync-1

# Port forward for testing
kubectl port-forward service/distributed-sync 8001:8001

# Test
curl http://localhost:8001/health
```

## Monitoring

### Enable Prometheus Metrics

The system exposes Prometheus metrics at `/metrics` endpoint.

Create `monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'distributed-sync'
    static_configs:
      - targets: ['localhost:8001', 'localhost:8002', 'localhost:8003']
```

Run Prometheus:

```bash
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

### Grafana Dashboard

1. Access Grafana: http://localhost:3000
2. Add Prometheus data source: http://prometheus:9090
3. Import dashboard from `monitoring/grafana-dashboard.json`

### Log Aggregation

Logs are written to `logs/node.log` by default.

For production, consider:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- CloudWatch (AWS)

## Troubleshooting

### Common Issues

#### Issue: Nodes cannot communicate

**Symptoms:**
- Nodes stuck in CANDIDATE state
- No leader elected
- Timeouts in API requests

**Solutions:**
```bash
# Check network connectivity
ping 127.0.0.1:8002
netstat -tuln | grep 8001

# Verify firewall
sudo ufw allow 8001:8003/tcp

# Check logs
tail -f logs/node.log | grep "Error\|error"
```

#### Issue: High latency in lock acquisition

**Symptoms:**
- Lock acquire responses take > 1 second
- Queue operations slow

**Solutions:**
```bash
# Check system load
top -n 1 | head -15

# Monitor network
iftop

# Increase timeout values in .env
SYNC_TIMEOUT=10.0

# Restart nodes
docker-compose restart
```

#### Issue: Memory usage growing

**Symptoms:**
- Container using >1GB memory
- OOMKilled pods

**Solutions:**
```bash
# Reduce cache size
CACHE_MAX_SIZE=5000

# Enable cache eviction
# (LRU is enabled by default)

# Monitor memory
docker stats
```

## Performance Tuning

### Cache Optimization

```env
# Adjust cache size based on available RAM
CACHE_MAX_SIZE=10000        # Default: 1000
LRU_CACHE_SIZE=5000         # Default: 500

# For high-traffic scenarios
BATCH_SIZE=500              # Default: 100
MAX_CONNECTIONS=5000        # Default: 1000
```

### Consensus Tuning

```env
# Adjust timeouts for different network conditions
# Fast network (LAN)
HEARTBEAT_INTERVAL=0.5
ELECTION_TIMEOUT_MIN=1
ELECTION_TIMEOUT_MAX=2

# Slow network (WAN)
HEARTBEAT_INTERVAL=2.0
ELECTION_TIMEOUT_MIN=5
ELECTION_TIMEOUT_MAX=10
```

### Queue Optimization

```env
# For high-throughput queue scenarios
QUEUE_SIZE=50000            # Default: 10000
ENABLE_PERSISTENCE=true     # Ensure persistence
```

### Resource Allocation

For Docker:

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

For Kubernetes: Adjust based on expected load

```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "1000m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

## Production Checklist

- [ ] Enable TLS/mTLS for inter-node communication
- [ ] Configure authentication and authorization
- [ ] Enable audit logging
- [ ] Set up monitoring and alerting
- [ ] Configure backup and recovery procedures
- [ ] Test failover scenarios
- [ ] Document runbooks and procedures
- [ ] Set up proper log retention policies
- [ ] Configure rate limiting
- [ ] Enable health checks and auto-recovery

## Support

For issues and questions:
1. Check logs: `logs/node.log`
2. Review API docs: `docs/api_spec.yaml`
3. Check architecture: `docs/architecture.md`
4. Run tests: `pytest tests/ -v`

---

Last Updated: May 2, 2026
