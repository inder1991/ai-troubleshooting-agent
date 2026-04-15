# Cluster Diagnostic Demo Mock Data — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace cluster diagnostic fixture files and add realistic delays to MockClusterClient + LangGraph nodes so the demo simulates a dramatic multi-domain OpenShift production incident over 60-90 seconds.

**Architecture:** Update 4 JSON fixture files with "Monday Morning Outage" scenario data, add `asyncio.sleep` delays to MockClusterClient methods, and add inter-stage event emissions with delays in the LangGraph pipeline nodes. The MockClusterClient already loads these fixtures — no structural changes needed.

**Tech Stack:** Python, JSON fixtures, asyncio, LangGraph

---

### Task 1: Replace `cluster_ctrl_plane_mock.json`

**Files:**
- Modify: `backend/src/agents/fixtures/cluster_ctrl_plane_mock.json`

**Step 1: Replace the fixture file**

Replace the entire file with this content. The scenario: MachineConfigPool `worker` stuck Degraded after a bad kernel parameter update Friday night. 2 of 5 ClusterOperators degraded (ingress, monitoring). Etcd showing leader election churn from resource pressure. API server p99 latency spiked to 4200ms. Webhook timeout warnings.

```json
{
  "api_health": {
    "status": "degraded",
    "latency_ms": 4200,
    "error_rate_pct": 8.3,
    "audit_log_backlog": 12400
  },
  "cluster_operators": [
    {
      "name": "ingress",
      "available": true,
      "degraded": true,
      "progressing": false,
      "message": "IngressController \"default\" degraded: 1 of 3 router pods are unavailable (pod router-default-7b9f4-kx2m1 evicted from worker-3.prod-east.internal due to DiskPressure)"
    },
    {
      "name": "monitoring",
      "available": true,
      "degraded": true,
      "progressing": false,
      "message": "Prometheus adapter pod CrashLoopBackOff — prometheus-adapter-6d8c4-zmq9 on worker-3 evicted, replacement pending scheduling"
    },
    {
      "name": "dns",
      "available": true,
      "degraded": false,
      "progressing": false,
      "message": ""
    },
    {
      "name": "authentication",
      "available": true,
      "degraded": false,
      "progressing": false,
      "message": ""
    },
    {
      "name": "machine-config",
      "available": true,
      "degraded": true,
      "progressing": true,
      "message": "MachineConfigPool worker: 2 nodes are reporting Degraded — rendered-worker-9f8a2b failed to apply 99-worker-kernel-params (kernel.pid_max=131072): error writing sysctl: permission denied"
    }
  ],
  "etcd_members": [
    {
      "name": "etcd-master-1.prod-east.internal",
      "status": "healthy",
      "db_size_mb": 387,
      "leader": false,
      "leader_changes_last_hour": 4,
      "raft_term": 892,
      "applied_index_lag": 12
    },
    {
      "name": "etcd-master-2.prod-east.internal",
      "status": "healthy",
      "db_size_mb": 391,
      "leader": true,
      "leader_changes_last_hour": 4,
      "raft_term": 892,
      "applied_index_lag": 0
    },
    {
      "name": "etcd-master-3.prod-east.internal",
      "status": "slow",
      "db_size_mb": 394,
      "leader": false,
      "leader_changes_last_hour": 4,
      "raft_term": 892,
      "applied_index_lag": 45,
      "warning": "apply duration exceeded 100ms threshold (avg 187ms over last 15m)"
    }
  ],
  "api_audit_logs": [
    {
      "timestamp": "2026-04-06T06:12:00Z",
      "verb": "delete",
      "resource": "pods",
      "namespace": "ecommerce-prod",
      "user": "system:node:worker-3.prod-east.internal",
      "reason": "eviction",
      "count": 12
    },
    {
      "timestamp": "2026-04-06T06:14:22Z",
      "verb": "create",
      "resource": "events",
      "namespace": "openshift-machine-config-operator",
      "user": "system:serviceaccount:openshift-machine-config-operator:machine-config-daemon",
      "reason": "MachineConfigDaemon failed to apply config rendered-worker-9f8a2b"
    },
    {
      "timestamp": "2026-04-06T06:15:01Z",
      "verb": "update",
      "resource": "nodes/status",
      "namespace": "",
      "user": "system:node:worker-3.prod-east.internal",
      "reason": "NodeCondition DiskPressure changed to True"
    },
    {
      "timestamp": "2026-04-06T07:45:30Z",
      "verb": "delete",
      "resource": "pods",
      "namespace": "openshift-monitoring",
      "user": "system:node:worker-3.prod-east.internal",
      "reason": "eviction"
    }
  ],
  "webhooks": [
    {
      "name": "validator.openshift.io",
      "type": "ValidatingWebhookConfiguration",
      "timeout_seconds": 10,
      "failure_policy": "Fail",
      "rules_count": 3,
      "warning": "3 timeout events in last hour — pod creation delayed by webhook latency"
    }
  ],
  "cluster_version": {
    "version": "4.14.12",
    "desired": "4.14.12",
    "channel": "stable-4.14",
    "conditions": [
      {"type": "Available", "status": "True", "message": "Done applying 4.14.12"},
      {"type": "Progressing", "status": "False", "message": ""},
      {"type": "Failing", "status": "False", "message": ""}
    ]
  }
}
```

**Step 2: Verify JSON is valid**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m json.tool backend/src/agents/fixtures/cluster_ctrl_plane_mock.json > /dev/null`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add backend/src/agents/fixtures/cluster_ctrl_plane_mock.json
git commit -m "feat(demo): replace ctrl_plane fixture with Monday Morning Outage scenario"
```

---

### Task 2: Replace `cluster_node_mock.json`

**Files:**
- Modify: `backend/src/agents/fixtures/cluster_node_mock.json`

**Step 1: Replace the fixture file**

The scenario: 6 nodes (3 control-plane, 2 healthy workers, 1 NotReady worker with DiskPressure at 93%). 12 pods evicted from worker-3. Deployment `order-service` stuck rollout (2/4 ready). DaemonSet `fluentd` has 1 unavailable. Warning events for eviction, failed scheduling, failed mount, liveness/readiness probe failures. Resource quota exceeded. Prometheus metrics showing node pressure.

```json
{
  "nodes": [
    {
      "name": "master-1.prod-east.internal",
      "status": "Ready",
      "roles": ["control-plane", "master"],
      "cpu_pct": 42,
      "memory_pct": 58,
      "disk_pct": 44,
      "kernel_version": "5.14.0-284.30.1.el9_2.x86_64",
      "container_runtime": "cri-o://1.27.1",
      "kubelet_version": "v1.27.8+4fab27b",
      "conditions": ["Ready"]
    },
    {
      "name": "master-2.prod-east.internal",
      "status": "Ready",
      "roles": ["control-plane", "master"],
      "cpu_pct": 38,
      "memory_pct": 54,
      "disk_pct": 41,
      "kernel_version": "5.14.0-284.30.1.el9_2.x86_64",
      "container_runtime": "cri-o://1.27.1",
      "kubelet_version": "v1.27.8+4fab27b",
      "conditions": ["Ready"]
    },
    {
      "name": "master-3.prod-east.internal",
      "status": "Ready",
      "roles": ["control-plane", "master"],
      "cpu_pct": 45,
      "memory_pct": 61,
      "disk_pct": 43,
      "kernel_version": "5.14.0-284.30.1.el9_2.x86_64",
      "container_runtime": "cri-o://1.27.1",
      "kubelet_version": "v1.27.8+4fab27b",
      "conditions": ["Ready"]
    },
    {
      "name": "worker-1.prod-east.internal",
      "status": "Ready",
      "roles": ["worker"],
      "cpu_pct": 71,
      "memory_pct": 74,
      "disk_pct": 52,
      "kernel_version": "5.14.0-284.30.1.el9_2.x86_64",
      "container_runtime": "cri-o://1.27.1",
      "kubelet_version": "v1.27.8+4fab27b",
      "conditions": ["Ready"]
    },
    {
      "name": "worker-2.prod-east.internal",
      "status": "Ready",
      "roles": ["worker"],
      "cpu_pct": 68,
      "memory_pct": 69,
      "disk_pct": 48,
      "kernel_version": "5.14.0-284.30.1.el9_2.x86_64",
      "container_runtime": "cri-o://1.27.1",
      "kubelet_version": "v1.27.8+4fab27b",
      "conditions": ["Ready"]
    },
    {
      "name": "worker-3.prod-east.internal",
      "status": "NotReady,DiskPressure",
      "roles": ["worker"],
      "cpu_pct": 89,
      "memory_pct": 82,
      "disk_pct": 93,
      "kernel_version": "5.14.0-284.30.1.el9_2.x86_64",
      "container_runtime": "cri-o://1.27.1",
      "kubelet_version": "v1.27.8+4fab27b",
      "conditions": ["DiskPressure", "NotReady"],
      "taints": ["node.kubernetes.io/not-ready", "node.kubernetes.io/disk-pressure"]
    }
  ],
  "events": [
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/order-service-5c7d8-r4k2m",
      "message": "The node had condition: [DiskPressure]. Pod order-service-5c7d8-r4k2m evicted.",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:01Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/order-service-5c7d8-t8n5p",
      "message": "The node had condition: [DiskPressure]. Pod order-service-5c7d8-t8n5p evicted.",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:02Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/catalog-service-8a3f1-j7h2v",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:04Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/payment-gateway-2d9e6-w3x8z",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:05Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/fluentd-logging-mk4r2",
      "message": "The node had condition: [DiskPressure]. DaemonSet pod evicted.",
      "node": "worker-3.prod-east.internal",
      "namespace": "kube-system",
      "timestamp": "2026-04-06T06:12:06Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/node-exporter-qr7z9",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "monitoring",
      "timestamp": "2026-04-06T06:12:07Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/prometheus-adapter-6d8c4-zmq9",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "openshift-monitoring",
      "timestamp": "2026-04-06T06:12:08Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/router-default-7b9f4-kx2m1",
      "message": "The node had condition: [DiskPressure]. Ingress controller pod evicted.",
      "node": "worker-3.prod-east.internal",
      "namespace": "openshift-ingress",
      "timestamp": "2026-04-06T06:12:09Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/coredns-worker3-8f4a2",
      "message": "The node had condition: [DiskPressure]. CoreDNS pod evicted.",
      "node": "worker-3.prod-east.internal",
      "namespace": "openshift-dns",
      "timestamp": "2026-04-06T06:12:10Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/search-indexer-4b6c9-p2q1r",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:12Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/recommendation-engine-7e2d3-s5t4u",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:13Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "Evicted",
      "object": "pod/notification-service-1a8b5-v6w3x",
      "message": "The node had condition: [DiskPressure].",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:14Z",
      "count": 1
    },
    {
      "type": "Warning",
      "reason": "FailedScheduling",
      "object": "pod/order-service-5c7d8-new1",
      "message": "0/6 nodes are available: 1 node(s) had disk pressure, 3 node(s) had untolerated taint {node-role.kubernetes.io/master: }, 2 node(s) didn't have free ports for the requested pod ports.",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:14:30Z",
      "count": 4
    },
    {
      "type": "Warning",
      "reason": "FailedMount",
      "object": "pod/order-service-5c7d8-new2",
      "message": "Unable to attach or mount volumes: unmounted volumes=[order-data], unattached volumes=[order-data kube-api-access-7x2r4]: timed out waiting for the condition",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:18:45Z",
      "count": 2
    },
    {
      "type": "Warning",
      "reason": "Unhealthy",
      "object": "pod/catalog-service-8a3f1-rescheduled",
      "message": "Readiness probe failed: HTTP probe failed with statuscode: 503",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:22:10Z",
      "count": 8
    },
    {
      "type": "Warning",
      "reason": "Unhealthy",
      "object": "pod/payment-gateway-2d9e6-rescheduled",
      "message": "Liveness probe failed: connection refused (dial tcp 10.128.4.72:8080: connect: connection refused)",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:25:33Z",
      "count": 5
    },
    {
      "type": "Warning",
      "reason": "BackOff",
      "object": "pod/payment-gateway-2d9e6-rescheduled",
      "message": "Back-off restarting failed container payment-gateway in pod payment-gateway-2d9e6-rescheduled_ecommerce-prod",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:30:15Z",
      "count": 3
    },
    {
      "type": "Warning",
      "reason": "ExceededGracePeriod",
      "object": "pod/search-indexer-4b6c9-p2q1r",
      "message": "Container runtime did not kill the pod within specified grace period.",
      "node": "worker-3.prod-east.internal",
      "namespace": "ecommerce-prod",
      "timestamp": "2026-04-06T06:12:42Z",
      "count": 1
    },
    {
      "type": "Normal",
      "reason": "NodeNotReady",
      "object": "node/worker-3.prod-east.internal",
      "message": "Node worker-3.prod-east.internal status is now: NodeNotReady",
      "timestamp": "2026-04-06T06:35:00Z",
      "count": 1
    }
  ],
  "top_pods": [
    {
      "namespace": "ecommerce-prod",
      "name": "order-service-5c7d8-a1b2c",
      "status": "Running",
      "cpu_m": 280,
      "memory_mi": 512,
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "order-service-5c7d8-d3e4f",
      "status": "Running",
      "cpu_m": 310,
      "memory_mi": 540,
      "node": "worker-2.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "order-service-5c7d8-new1",
      "status": "Pending",
      "cpu_m": 0,
      "memory_mi": 0,
      "node": "",
      "restarts": 0,
      "ready": false,
      "reason": "FailedScheduling"
    },
    {
      "namespace": "ecommerce-prod",
      "name": "order-service-5c7d8-new2",
      "status": "ContainerCreating",
      "cpu_m": 0,
      "memory_mi": 0,
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": false,
      "reason": "FailedMount"
    },
    {
      "namespace": "ecommerce-prod",
      "name": "catalog-service-8a3f1-h5g6i",
      "status": "Running",
      "cpu_m": 190,
      "memory_mi": 384,
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "catalog-service-8a3f1-rescheduled",
      "status": "Running",
      "cpu_m": 95,
      "memory_mi": 256,
      "node": "worker-2.prod-east.internal",
      "restarts": 2,
      "ready": false,
      "reason": "ReadinessProbe failed"
    },
    {
      "namespace": "ecommerce-prod",
      "name": "payment-gateway-2d9e6-k7l8m",
      "status": "Running",
      "cpu_m": 150,
      "memory_mi": 320,
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "payment-gateway-2d9e6-rescheduled",
      "status": "CrashLoopBackOff",
      "cpu_m": 0,
      "memory_mi": 0,
      "node": "worker-2.prod-east.internal",
      "restarts": 7,
      "ready": false,
      "reason": "CrashLoopBackOff"
    },
    {
      "namespace": "ecommerce-prod",
      "name": "cart-service-3f9a2-n9o1p",
      "status": "Running",
      "cpu_m": 120,
      "memory_mi": 256,
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "user-auth-service-6b4e8-q2r3s",
      "status": "Running",
      "cpu_m": 85,
      "memory_mi": 192,
      "node": "worker-2.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "search-indexer-4b6c9-rescheduled",
      "status": "Running",
      "cpu_m": 340,
      "memory_mi": 1024,
      "node": "worker-1.prod-east.internal",
      "restarts": 1,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "notification-service-1a8b5-rescheduled",
      "status": "Running",
      "cpu_m": 60,
      "memory_mi": 128,
      "node": "worker-2.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "recommendation-engine-7e2d3-rescheduled",
      "status": "Running",
      "cpu_m": 420,
      "memory_mi": 1536,
      "node": "worker-1.prod-east.internal",
      "restarts": 1,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "api-gateway-9c1d7-t4u5v",
      "status": "Running",
      "cpu_m": 200,
      "memory_mi": 384,
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "api-gateway-9c1d7-w6x7y",
      "status": "Running",
      "cpu_m": 210,
      "memory_mi": 400,
      "node": "worker-2.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "namespace": "ecommerce-prod",
      "name": "api-gateway-9c1d7-z8a9b",
      "status": "Running",
      "cpu_m": 195,
      "memory_mi": 370,
      "node": "worker-2.prod-east.internal",
      "restarts": 0,
      "ready": true
    }
  ],
  "resource_quotas": [
    {
      "namespace": "ecommerce-prod",
      "name": "compute-quota",
      "hard": {"requests.cpu": "16", "requests.memory": "32Gi", "limits.cpu": "32", "limits.memory": "64Gi"},
      "used": {"requests.cpu": "15200m", "requests.memory": "30Gi", "limits.cpu": "28800m", "limits.memory": "58Gi"},
      "exceeded": false,
      "near_limit": true,
      "usage_pct": {"requests.cpu": 95, "requests.memory": 93.75, "limits.cpu": 90, "limits.memory": 90.6}
    }
  ],
  "prometheus_metrics": {
    "node_disk_usage": [
      {"node": "worker-3.prod-east.internal", "filesystem": "/dev/sda1", "usage_pct": 93.2, "available_gi": 4.8},
      {"node": "worker-1.prod-east.internal", "filesystem": "/dev/sda1", "usage_pct": 52.1, "available_gi": 33.6},
      {"node": "worker-2.prod-east.internal", "filesystem": "/dev/sda1", "usage_pct": 48.4, "available_gi": 36.1}
    ],
    "container_restarts_15m": [
      {"pod": "payment-gateway-2d9e6-rescheduled", "namespace": "ecommerce-prod", "restarts": 4},
      {"pod": "catalog-service-8a3f1-rescheduled", "namespace": "ecommerce-prod", "restarts": 2}
    ],
    "kubelet_runtime_errors": [
      {"node": "worker-3.prod-east.internal", "errors_per_min": 14.2, "type": "container_log_write_failed"}
    ]
  }
}
```

**Step 2: Verify JSON is valid**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m json.tool backend/src/agents/fixtures/cluster_node_mock.json > /dev/null`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add backend/src/agents/fixtures/cluster_node_mock.json
git commit -m "feat(demo): replace node fixture with Monday Morning Outage — NotReady worker, 12 evictions"
```

---

### Task 3: Replace `cluster_network_mock.json`

**Files:**
- Modify: `backend/src/agents/fixtures/cluster_network_mock.json`

**Step 1: Replace the fixture file**

The scenario: Ingress controller degraded (1/3 available). CoreDNS pod evicted from worker-3, DNS resolution failures at 40%. Payment-gateway service has 0 ready endpoints. 3 routes returning 503. NetworkPolicy blocking cross-namespace traffic to monitoring namespace.

```json
{
  "dns_pods": [
    {
      "name": "dns-default-g8h9i",
      "status": "Running",
      "node": "worker-1.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "name": "dns-default-j1k2l",
      "status": "Running",
      "node": "worker-2.prod-east.internal",
      "restarts": 0,
      "ready": true
    },
    {
      "name": "dns-default-worker3-evicted",
      "status": "Evicted",
      "node": "worker-3.prod-east.internal",
      "restarts": 0,
      "ready": false
    },
    {
      "name": "dns-default-pending-reschedule",
      "status": "Pending",
      "node": "",
      "restarts": 0,
      "ready": false
    }
  ],
  "ingress_controllers": [
    {
      "name": "default",
      "namespace": "openshift-ingress",
      "replicas": 3,
      "available": 1,
      "unavailable": 2,
      "status": "Degraded",
      "message": "2 router pods unavailable — router-default-7b9f4-kx2m1 evicted from worker-3 (DiskPressure), router-default-7b9f4-m3n4o CrashLoopBackOff on worker-2"
    }
  ],
  "routes": [
    {
      "name": "ecommerce-storefront",
      "namespace": "ecommerce-prod",
      "host": "shop.prodeast.example.com",
      "status": "Admitted",
      "backend_service": "api-gateway",
      "tls_termination": "edge",
      "http_status": 200
    },
    {
      "name": "order-api",
      "namespace": "ecommerce-prod",
      "host": "orders-api.prodeast.example.com",
      "status": "Admitted",
      "backend_service": "order-service",
      "tls_termination": "edge",
      "http_status": 503,
      "error": "No healthy upstream — order-service only 2/4 pods ready"
    },
    {
      "name": "payment-webhook",
      "namespace": "ecommerce-prod",
      "host": "pay.prodeast.example.com",
      "status": "Admitted",
      "backend_service": "payment-gateway",
      "tls_termination": "reencrypt",
      "http_status": 503,
      "error": "All backend pods in CrashLoopBackOff or evicted"
    },
    {
      "name": "grafana-dashboard",
      "namespace": "monitoring",
      "host": "grafana.prodeast.example.com",
      "status": "Admitted",
      "backend_service": "grafana",
      "tls_termination": "edge",
      "http_status": 503,
      "error": "NetworkPolicy deny-monitoring-ingress blocking ingress traffic"
    }
  ],
  "network_policies": [
    {
      "name": "default-deny-ecommerce",
      "namespace": "ecommerce-prod",
      "pod_selector": {},
      "policy_types": ["Ingress", "Egress"],
      "ingress_rules_count": 3,
      "egress_rules_count": 2,
      "has_empty_ingress": false,
      "has_empty_egress": false
    },
    {
      "name": "deny-monitoring-ingress",
      "namespace": "monitoring",
      "pod_selector": {},
      "policy_types": ["Ingress"],
      "ingress_rules_count": 0,
      "egress_rules_count": 0,
      "has_empty_ingress": true,
      "has_empty_egress": false,
      "warning": "Blocks ALL ingress to monitoring namespace — prevents cross-namespace scraping and dashboard access"
    },
    {
      "name": "allow-dns-egress",
      "namespace": "ecommerce-prod",
      "pod_selector": {},
      "policy_types": ["Egress"],
      "ingress_rules_count": 0,
      "egress_rules_count": 1,
      "has_empty_ingress": false,
      "has_empty_egress": false
    }
  ],
  "services_with_issues": [
    {
      "name": "payment-gateway",
      "namespace": "ecommerce-prod",
      "type": "ClusterIP",
      "ready_endpoints": 0,
      "total_endpoints": 2,
      "warning": "Service has 0 ready endpoints — all backend pods are CrashLoopBackOff or evicted"
    },
    {
      "name": "order-service",
      "namespace": "ecommerce-prod",
      "type": "ClusterIP",
      "ready_endpoints": 2,
      "total_endpoints": 4,
      "warning": "Service has only 2 of 4 endpoints ready — 2 pods evicted from worker-3"
    }
  ],
  "dns_metrics": {
    "resolution_failures_pct": 38.7,
    "avg_latency_ms": 1850,
    "queries_per_sec": 2400,
    "servfail_domains": [
      "payment-gateway.ecommerce-prod.svc.cluster.local",
      "order-service.ecommerce-prod.svc.cluster.local",
      "prometheus-k8s.openshift-monitoring.svc.cluster.local"
    ]
  },
  "ingress_metrics": {
    "5xx_rate_pct": 23.4,
    "request_rate": 4200,
    "p99_latency_ms": 12800,
    "error_breakdown": {
      "503": 18.1,
      "502": 3.8,
      "504": 1.5
    }
  },
  "logs": [
    {
      "timestamp": "2026-04-06T06:15:22Z",
      "source": "coredns",
      "message": "SERVFAIL for payment-gateway.ecommerce-prod.svc.cluster.local IN A: read udp 10.128.0.12:53: i/o timeout",
      "severity": "error"
    },
    {
      "timestamp": "2026-04-06T06:15:24Z",
      "source": "coredns",
      "message": "SERVFAIL for order-service.ecommerce-prod.svc.cluster.local IN A: context deadline exceeded",
      "severity": "error"
    },
    {
      "timestamp": "2026-04-06T06:18:01Z",
      "source": "haproxy-router",
      "message": "[WARNING] 096/061801 (1) : Server ecommerce-prod_payment-gateway/pod:payment-gateway-2d9e6-rescheduled:8080 is DOWN, reason: Layer4 connection problem, info: Connection refused",
      "severity": "warning"
    },
    {
      "timestamp": "2026-04-06T06:18:03Z",
      "source": "haproxy-router",
      "message": "[ALERT] 096/061803 (1) : backend ecommerce-prod_payment-gateway has no server available!",
      "severity": "critical"
    },
    {
      "timestamp": "2026-04-06T06:22:15Z",
      "source": "haproxy-router",
      "message": "[WARNING] 096/062215 (1) : Server ecommerce-prod_order-service/pod:order-service-5c7d8-new1 is DOWN, reason: Layer4 timeout",
      "severity": "warning"
    },
    {
      "timestamp": "2026-04-06T07:45:00Z",
      "source": "network-policy-controller",
      "message": "NetworkPolicy deny-monitoring-ingress in namespace monitoring: blocking all ingress traffic including Prometheus scrape targets",
      "severity": "warning"
    }
  ]
}
```

**Step 2: Verify JSON is valid**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m json.tool backend/src/agents/fixtures/cluster_network_mock.json > /dev/null`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add backend/src/agents/fixtures/cluster_network_mock.json
git commit -m "feat(demo): replace network fixture — degraded ingress, DNS failures, 503 routes"
```

---

### Task 4: Replace `cluster_storage_mock.json`

**Files:**
- Modify: `backend/src/agents/fixtures/cluster_storage_mock.json`

**Step 1: Replace the fixture file**

The scenario: PVC `data-postgres-0` at 94% capacity in `ecommerce-prod`. CSI driver `ebs.csi.aws.com` reporting attach/detach timeouts on the NotReady node. 2 PVCs stuck in `Pending` state (one due to no matching storage class, one due to volume already attached to NotReady node).

```json
{
  "storage_classes": [
    {
      "name": "gp3-csi",
      "provisioner": "ebs.csi.aws.com",
      "default": true,
      "reclaim_policy": "Delete",
      "volume_binding_mode": "WaitForFirstConsumer",
      "allow_volume_expansion": true,
      "parameters": {
        "type": "gp3",
        "iops": "3000",
        "throughput": "125"
      }
    },
    {
      "name": "gp2-legacy",
      "provisioner": "kubernetes.io/aws-ebs",
      "default": false,
      "reclaim_policy": "Delete",
      "volume_binding_mode": "Immediate",
      "allow_volume_expansion": false,
      "parameters": {
        "type": "gp2"
      }
    },
    {
      "name": "io2-high-perf",
      "provisioner": "ebs.csi.aws.com",
      "default": false,
      "reclaim_policy": "Retain",
      "volume_binding_mode": "WaitForFirstConsumer",
      "allow_volume_expansion": true,
      "parameters": {
        "type": "io2",
        "iops": "16000"
      }
    }
  ],
  "pvcs": [
    {
      "name": "data-postgres-0",
      "namespace": "ecommerce-prod",
      "status": "Bound",
      "capacity": "100Gi",
      "used_pct": 94,
      "storage_class": "gp3-csi",
      "volume_name": "pvc-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "access_modes": ["ReadWriteOnce"],
      "node": "worker-1.prod-east.internal",
      "warning": "Volume usage at 94% — approaching capacity limit. Postgres WAL accumulation detected."
    },
    {
      "name": "data-postgres-1",
      "namespace": "ecommerce-prod",
      "status": "Bound",
      "capacity": "100Gi",
      "used_pct": 62,
      "storage_class": "gp3-csi",
      "volume_name": "pvc-b2c3d4e5-f6a7-8901-bcde-f23456789012",
      "access_modes": ["ReadWriteOnce"],
      "node": "worker-2.prod-east.internal"
    },
    {
      "name": "data-redis-0",
      "namespace": "ecommerce-prod",
      "status": "Bound",
      "capacity": "20Gi",
      "used_pct": 41,
      "storage_class": "gp3-csi",
      "volume_name": "pvc-c3d4e5f6-a7b8-9012-cdef-345678901234",
      "access_modes": ["ReadWriteOnce"],
      "node": "worker-2.prod-east.internal"
    },
    {
      "name": "search-data-0",
      "namespace": "ecommerce-prod",
      "status": "Pending",
      "capacity": "",
      "used_pct": 0,
      "storage_class": "io2-high-perf-NOT-FOUND",
      "volume_name": "",
      "access_modes": ["ReadWriteOnce"],
      "warning": "StorageClass io2-high-perf-NOT-FOUND does not exist — PVC stuck in Pending",
      "events": [
        {
          "type": "Warning",
          "reason": "ProvisioningFailed",
          "message": "storageclass.storage.k8s.io \"io2-high-perf-NOT-FOUND\" not found",
          "timestamp": "2026-04-06T06:30:00Z",
          "count": 12
        }
      ]
    },
    {
      "name": "order-data-volume",
      "namespace": "ecommerce-prod",
      "status": "Pending",
      "capacity": "50Gi",
      "used_pct": 0,
      "storage_class": "gp3-csi",
      "volume_name": "pvc-d4e5f6a7-b8c9-0123-defa-456789012345",
      "access_modes": ["ReadWriteOnce"],
      "warning": "Volume previously attached to worker-3 (NotReady) — CSI detach timeout, cannot reattach to new node",
      "events": [
        {
          "type": "Warning",
          "reason": "FailedAttachVolume",
          "message": "Multi-Attach error for volume \"pvc-d4e5f6a7-b8c9-0123-defa-456789012345\": volume is already exclusively attached to node worker-3.prod-east.internal and cannot be attached to node worker-1.prod-east.internal",
          "timestamp": "2026-04-06T06:20:00Z",
          "count": 8
        }
      ]
    },
    {
      "name": "monitoring-prometheus-data",
      "namespace": "monitoring",
      "status": "Bound",
      "capacity": "200Gi",
      "used_pct": 45,
      "storage_class": "gp3-csi",
      "volume_name": "pvc-e5f6a7b8-c9d0-1234-efab-567890123456",
      "access_modes": ["ReadWriteOnce"],
      "node": "worker-1.prod-east.internal"
    }
  ],
  "csi_driver_pods": [
    {
      "name": "ebs-csi-controller-0",
      "namespace": "openshift-cluster-csi-drivers",
      "status": "Running",
      "restarts": 0,
      "ready": true
    },
    {
      "name": "ebs-csi-controller-1",
      "namespace": "openshift-cluster-csi-drivers",
      "status": "Running",
      "restarts": 0,
      "ready": true
    },
    {
      "name": "ebs-csi-node-worker1",
      "namespace": "openshift-cluster-csi-drivers",
      "status": "Running",
      "restarts": 0,
      "ready": true
    },
    {
      "name": "ebs-csi-node-worker2",
      "namespace": "openshift-cluster-csi-drivers",
      "status": "Running",
      "restarts": 0,
      "ready": true
    },
    {
      "name": "ebs-csi-node-worker3",
      "namespace": "openshift-cluster-csi-drivers",
      "status": "NotReady",
      "restarts": 3,
      "ready": false,
      "warning": "CSI node plugin on worker-3 not responding — volume operations will fail"
    }
  ],
  "volume_metrics": {
    "iops_throttled_pct": 12.4,
    "attach_latency_ms": 8500,
    "detach_timeout_count": 3,
    "pending_attach_operations": 2,
    "warning": "Elevated attach latency (8.5s vs normal 120ms) — CSI controller struggling with NotReady node detach"
  }
}
```

**Step 2: Verify JSON is valid**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m json.tool backend/src/agents/fixtures/cluster_storage_mock.json > /dev/null`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add backend/src/agents/fixtures/cluster_storage_mock.json
git commit -m "feat(demo): replace storage fixture — PVC near-full, CSI timeouts, stuck volumes"
```

---

### Task 5: Update MockClusterClient with new scenario data and delays

**Files:**
- Modify: `backend/src/agents/cluster_client/mock_client.py`

**Step 1: Add asyncio import and delay helper**

At the top of the file, after the existing imports, add:

```python
import asyncio

# Realistic demo delays to simulate K8s API latency
_DEMO_DELAYS = {
    "detect_platform": 0.5,
    "list_namespaces": 0.8,
    "list_nodes": 2.0,
    "list_pods": 2.5,
    "list_events": 1.5,
    "list_pvcs": 1.0,
    "get_api_health": 1.0,
    "query_prometheus": 1.5,
    "query_logs": 1.0,
    "list_deployments": 1.2,
    "list_statefulsets": 0.8,
    "list_daemonsets": 0.8,
    "list_services": 1.0,
    "list_endpoints": 0.8,
    "list_pdbs": 0.5,
    "list_network_policies": 0.5,
    "list_hpas": 0.5,
    "get_cluster_operators": 1.5,
    "get_machine_config_pools": 1.0,
    "get_cluster_version": 0.5,
    "list_machines": 0.8,
    "list_subscriptions": 0.5,
    "list_csvs": 0.5,
    "get_routes": 0.8,
    "list_roles": 0.5,
    "list_role_bindings": 0.5,
    "list_cluster_roles": 0.5,
    "list_service_accounts": 0.5,
    "list_jobs": 0.5,
    "list_cronjobs": 0.5,
    "list_tls_secrets": 0.5,
    "get_security_context_constraints": 0.5,
    "get_proxy_config": 0.3,
    "list_install_plans": 0.3,
    "get_build_configs": 0.5,
    "get_image_streams": 0.5,
    "get_machine_sets": 0.5,
    "list_vpas": 0.3,
}

async def _demo_delay(method_name: str) -> None:
    """Add realistic delay for demo mode."""
    delay = _DEMO_DELAYS.get(method_name, 0.5)
    if delay > 0:
        await asyncio.sleep(delay)
```

**Step 2: Add delay call to every async method in MockClusterClient**

Add `await _demo_delay("method_name")` as the first line inside every `async def` method in MockClusterClient. For example:

```python
async def detect_platform(self) -> dict[str, str]:
    await _demo_delay("detect_platform")
    return {"platform": self._platform, "version": "4.14.12" if self._platform == "openshift" else "1.28.3"}
```

Do this for ALL async methods in the class. Also update the platform version from `"4.14.2"` to `"4.14.12"` to match the new fixture data.

**Step 3: Update list_pods to use fixture data instead of hardcoded injection**

The existing `list_pods` injects a hardcoded CrashLoopBackOff pod. Remove that injection — the new fixture `cluster_node_mock.json` already has CrashLoopBackOff and Pending pods in `top_pods`.

```python
async def list_pods(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_pods")
    data = _load_fixture("cluster_node_mock.json")
    pods = data.get("top_pods", [])
    if namespace:
        pods = [p for p in pods if p.get("namespace") == namespace]
    return QueryResult(data=pods, total_available=len(pods), returned=len(pods))
```

**Step 4: Update list_events to use fixture data instead of hardcoded injection**

Remove the injected FailedScheduling event — the new fixture already has comprehensive events.

```python
async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
    await _demo_delay("list_events")
    data = _load_fixture("cluster_node_mock.json")
    events = data.get("events", [])
    if namespace:
        events = [e for e in events if e.get("namespace") == namespace]
    cap = OBJECT_CAPS["events"]
    truncated = len(events) > cap
    returned = events[:cap]
    return QueryResult(data=returned, total_available=len(events), returned=len(returned), truncated=truncated)
```

**Step 5: Update list_namespaces to match the new scenario**

```python
async def list_namespaces(self) -> QueryResult:
    await _demo_delay("list_namespaces")
    ns = ["default", "kube-system", "openshift-dns", "openshift-ingress",
          "openshift-monitoring", "openshift-machine-config-operator",
          "openshift-cluster-csi-drivers", "openshift-operators",
          "openshift-operators-redhat", "ecommerce-prod", "ecommerce-staging",
          "monitoring", "logging"]
    return QueryResult(data=ns, total_available=len(ns), returned=len(ns))
```

**Step 6: Update inline data methods to match the new scenario**

Update `list_deployments` to include the ecommerce-prod services:

```python
async def list_deployments(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_deployments")
    deployments = [
        {
            "name": "api-gateway",
            "namespace": "ecommerce-prod",
            "replicas_desired": 3,
            "replicas_ready": 3,
            "replicas_available": 3,
            "replicas_updated": 3,
            "strategy": "RollingUpdate",
            "conditions": {
                "Available": {"status": "True", "reason": "MinimumReplicasAvailable", "message": "Deployment has minimum availability."},
                "Progressing": {"status": "True", "reason": "NewReplicaSetAvailable", "message": "ReplicaSet has successfully progressed."},
            },
            "stuck_rollout": False,
            "age": "2026-02-01T10:00:00+00:00",
        },
        {
            "name": "order-service",
            "namespace": "ecommerce-prod",
            "replicas_desired": 4,
            "replicas_ready": 2,
            "replicas_available": 2,
            "replicas_updated": 4,
            "strategy": "RollingUpdate",
            "conditions": {
                "Available": {"status": "False", "reason": "MinimumReplicasUnavailable", "message": "Deployment does not have minimum availability."},
                "Progressing": {"status": "False", "reason": "ProgressDeadlineExceeded", "message": "ReplicaSet \"order-service-5c7d8\" has timed out progressing."},
            },
            "stuck_rollout": True,
            "age": "2026-03-15T08:30:00+00:00",
        },
        {
            "name": "catalog-service",
            "namespace": "ecommerce-prod",
            "replicas_desired": 2,
            "replicas_ready": 1,
            "replicas_available": 1,
            "replicas_updated": 2,
            "strategy": "RollingUpdate",
            "conditions": {
                "Available": {"status": "False", "reason": "MinimumReplicasUnavailable", "message": "Deployment does not have minimum availability."},
                "Progressing": {"status": "True", "reason": "ReplicaSetUpdated", "message": "ReplicaSet is progressing."},
            },
            "stuck_rollout": False,
            "age": "2026-02-20T14:00:00+00:00",
        },
        {
            "name": "payment-gateway",
            "namespace": "ecommerce-prod",
            "replicas_desired": 2,
            "replicas_ready": 0,
            "replicas_available": 0,
            "replicas_updated": 2,
            "strategy": "RollingUpdate",
            "conditions": {
                "Available": {"status": "False", "reason": "MinimumReplicasUnavailable", "message": "Deployment does not have minimum availability."},
                "Progressing": {"status": "False", "reason": "ProgressDeadlineExceeded", "message": "ReplicaSet has timed out progressing."},
            },
            "stuck_rollout": True,
            "age": "2026-03-10T09:00:00+00:00",
        },
        {
            "name": "cart-service",
            "namespace": "ecommerce-prod",
            "replicas_desired": 2,
            "replicas_ready": 2,
            "replicas_available": 2,
            "replicas_updated": 2,
            "strategy": "RollingUpdate",
            "conditions": {
                "Available": {"status": "True", "reason": "MinimumReplicasAvailable", "message": "Deployment has minimum availability."},
                "Progressing": {"status": "True", "reason": "NewReplicaSetAvailable", "message": "ReplicaSet has successfully progressed."},
            },
            "stuck_rollout": False,
            "age": "2026-01-20T14:00:00+00:00",
        },
        {
            "name": "user-auth-service",
            "namespace": "ecommerce-prod",
            "replicas_desired": 2,
            "replicas_ready": 2,
            "replicas_available": 2,
            "replicas_updated": 2,
            "strategy": "RollingUpdate",
            "conditions": {
                "Available": {"status": "True", "reason": "MinimumReplicasAvailable", "message": "Deployment has minimum availability."},
                "Progressing": {"status": "True", "reason": "NewReplicaSetAvailable", "message": "ReplicaSet has successfully progressed."},
            },
            "stuck_rollout": False,
            "age": "2026-01-15T10:00:00+00:00",
        },
    ]
    if namespace:
        deployments = [d for d in deployments if d["namespace"] == namespace]
    return QueryResult(data=deployments, total_available=len(deployments), returned=len(deployments))
```

Update `list_daemonsets`:

```python
async def list_daemonsets(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_daemonsets")
    daemonsets = [
        {
            "name": "fluentd-logging",
            "namespace": "kube-system",
            "desired_number_scheduled": 5,
            "number_ready": 4,
            "number_unavailable": 1,
            "number_misscheduled": 0,
            "updated_number_scheduled": 5,
            "age": "2026-01-05T10:00:00+00:00",
        },
        {
            "name": "node-exporter",
            "namespace": "monitoring",
            "desired_number_scheduled": 5,
            "number_ready": 4,
            "number_unavailable": 1,
            "number_misscheduled": 0,
            "updated_number_scheduled": 5,
            "age": "2026-01-05T10:00:00+00:00",
        },
        {
            "name": "calico-node",
            "namespace": "kube-system",
            "desired_number_scheduled": 5,
            "number_ready": 5,
            "number_unavailable": 0,
            "number_misscheduled": 0,
            "updated_number_scheduled": 5,
            "age": "2026-01-01T00:00:00+00:00",
        },
    ]
    if namespace:
        daemonsets = [d for d in daemonsets if d["namespace"] == namespace]
    return QueryResult(data=daemonsets, total_available=len(daemonsets), returned=len(daemonsets))
```

Update `list_services` to match the ecommerce scenario:

```python
async def list_services(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_services")
    services = [
        {
            "name": "api-gateway",
            "namespace": "ecommerce-prod",
            "type": "ClusterIP",
            "cluster_ip": "10.96.45.12",
            "ports": [{"port": 80, "target_port": "8080", "protocol": "TCP", "name": "http"}],
            "selector": {"app": "api-gateway"},
            "external_ip": "",
        },
        {
            "name": "order-service",
            "namespace": "ecommerce-prod",
            "type": "ClusterIP",
            "cluster_ip": "10.96.78.34",
            "ports": [{"port": 8080, "target_port": "8080", "protocol": "TCP", "name": "http"}],
            "selector": {"app": "order-service"},
            "external_ip": "",
        },
        {
            "name": "payment-gateway",
            "namespace": "ecommerce-prod",
            "type": "ClusterIP",
            "cluster_ip": "10.96.102.56",
            "ports": [{"port": 8443, "target_port": "8443", "protocol": "TCP", "name": "https"}],
            "selector": {"app": "payment-gateway"},
            "external_ip": "",
        },
        {
            "name": "catalog-service",
            "namespace": "ecommerce-prod",
            "type": "ClusterIP",
            "cluster_ip": "10.96.55.78",
            "ports": [{"port": 8080, "target_port": "8080", "protocol": "TCP", "name": "http"}],
            "selector": {"app": "catalog-service"},
            "external_ip": "",
        },
        {
            "name": "public-lb",
            "namespace": "ecommerce-prod",
            "type": "LoadBalancer",
            "cluster_ip": "10.96.200.1",
            "ports": [{"port": 443, "target_port": "8443", "protocol": "TCP", "name": "https"}],
            "selector": {"app": "api-gateway"},
            "external_ip": "52.23.178.92",
        },
    ]
    if namespace:
        services = [s for s in services if s["namespace"] == namespace]
    return QueryResult(data=services, total_available=len(services), returned=len(services))
```

Update `list_endpoints`:

```python
async def list_endpoints(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_endpoints")
    endpoints = [
        {
            "name": "api-gateway",
            "namespace": "ecommerce-prod",
            "subsets": [{"addresses_count": 3, "not_ready_addresses_count": 0, "ports": [{"port": 8080, "protocol": "TCP", "name": "http"}]}],
            "total_ready_addresses": 3,
            "total_not_ready_addresses": 0,
        },
        {
            "name": "order-service",
            "namespace": "ecommerce-prod",
            "subsets": [{"addresses_count": 2, "not_ready_addresses_count": 2, "ports": [{"port": 8080, "protocol": "TCP", "name": "http"}]}],
            "total_ready_addresses": 2,
            "total_not_ready_addresses": 2,
        },
        {
            "name": "payment-gateway",
            "namespace": "ecommerce-prod",
            "subsets": [{"addresses_count": 0, "not_ready_addresses_count": 2, "ports": [{"port": 8443, "protocol": "TCP", "name": "https"}]}],
            "total_ready_addresses": 0,
            "total_not_ready_addresses": 2,
        },
        {
            "name": "catalog-service",
            "namespace": "ecommerce-prod",
            "subsets": [{"addresses_count": 1, "not_ready_addresses_count": 1, "ports": [{"port": 8080, "protocol": "TCP", "name": "http"}]}],
            "total_ready_addresses": 1,
            "total_not_ready_addresses": 1,
        },
    ]
    if namespace:
        endpoints = [e for e in endpoints if e["namespace"] == namespace]
    return QueryResult(data=endpoints, total_available=len(endpoints), returned=len(endpoints))
```

Update `get_routes` to return the routes from the network fixture:

```python
async def get_routes(self, namespace: str = "") -> QueryResult:
    await _demo_delay("get_routes")
    if self._platform != "openshift":
        return QueryResult()
    data = _load_fixture("cluster_network_mock.json")
    routes = data.get("routes", [])
    if namespace:
        routes = [r for r in routes if r.get("namespace") == namespace]
    return QueryResult(data=routes, total_available=len(routes), returned=len(routes))
```

Update `get_machine_config_pools` to reference fixture:

```python
async def get_machine_config_pools(self) -> QueryResult:
    await _demo_delay("get_machine_config_pools")
    if self._platform != "openshift":
        return QueryResult()
    pools = [
        {
            "name": "master",
            "degraded": False,
            "updating": False,
            "machine_count": 3,
            "ready_count": 3,
            "updated_count": 3,
            "unavailable_count": 0,
        },
        {
            "name": "worker",
            "degraded": True,
            "updating": True,
            "machine_count": 3,
            "ready_count": 2,
            "updated_count": 2,
            "unavailable_count": 1,
            "message": "Node worker-3.prod-east.internal is reporting Degraded — rendered-worker-9f8a2b failed to apply 99-worker-kernel-params",
        },
    ]
    return QueryResult(data=pools, total_available=len(pools), returned=len(pools))
```

Update `list_machines`:

```python
async def list_machines(self) -> QueryResult:
    await _demo_delay("list_machines")
    if self._platform != "openshift":
        return QueryResult()
    machines = [
        {
            "name": "prod-east-master-0",
            "phase": "Running",
            "provider_id": "aws:///us-east-1a/i-0a1b2c3d4e5f60001",
            "node_ref": "master-1.prod-east.internal",
            "conditions": [],
            "creation_timestamp": "2026-01-10T08:00:00Z",
        },
        {
            "name": "prod-east-master-1",
            "phase": "Running",
            "provider_id": "aws:///us-east-1b/i-0a1b2c3d4e5f60002",
            "node_ref": "master-2.prod-east.internal",
            "conditions": [],
            "creation_timestamp": "2026-01-10T08:00:00Z",
        },
        {
            "name": "prod-east-master-2",
            "phase": "Running",
            "provider_id": "aws:///us-east-1c/i-0a1b2c3d4e5f60003",
            "node_ref": "master-3.prod-east.internal",
            "conditions": [],
            "creation_timestamp": "2026-01-10T08:00:00Z",
        },
        {
            "name": "prod-east-worker-1",
            "phase": "Running",
            "provider_id": "aws:///us-east-1a/i-0a1b2c3d4e5f60004",
            "node_ref": "worker-1.prod-east.internal",
            "conditions": [],
            "creation_timestamp": "2026-01-10T08:00:00Z",
        },
        {
            "name": "prod-east-worker-2",
            "phase": "Running",
            "provider_id": "aws:///us-east-1b/i-0a1b2c3d4e5f60005",
            "node_ref": "worker-2.prod-east.internal",
            "conditions": [],
            "creation_timestamp": "2026-01-10T08:00:00Z",
        },
        {
            "name": "prod-east-worker-3",
            "phase": "Running",
            "provider_id": "aws:///us-east-1c/i-0a1b2c3d4e5f60006",
            "node_ref": "worker-3.prod-east.internal",
            "conditions": [{"type": "NodeHealthy", "status": "False", "reason": "NodeNotReady", "message": "Node worker-3.prod-east.internal is NotReady (DiskPressure)"}],
            "creation_timestamp": "2026-01-10T08:00:00Z",
        },
    ]
    return QueryResult(data=machines, total_available=len(machines), returned=len(machines))
```

Update `list_hpas`:

```python
async def list_hpas(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_hpas")
    hpas = [
        {
            "name": "catalog-service-hpa",
            "namespace": "ecommerce-prod",
            "min_replicas": 2,
            "max_replicas": 8,
            "current_replicas": 8,
            "desired_replicas": 12,
            "target_ref": "Deployment/catalog-service",
            "metrics": [
                {"type": "Resource", "resource_name": "cpu", "target_type": "Utilization", "target_value": 70},
            ],
            "conditions": {
                "AbleToScale": {"status": "True", "reason": "ReadyForNewScale", "message": "recommended size matches current size"},
                "ScalingActive": {"status": "True", "reason": "ValidMetricFound", "message": "the HPA was able to successfully calculate a replica count"},
                "ScalingLimited": {"status": "True", "reason": "TooManyReplicas", "message": "the desired replica count is more than the maximum replica count"},
            },
            "scaling_limited": True,
            "at_max": True,
        },
        {
            "name": "api-gateway-hpa",
            "namespace": "ecommerce-prod",
            "min_replicas": 3,
            "max_replicas": 10,
            "current_replicas": 3,
            "desired_replicas": 3,
            "target_ref": "Deployment/api-gateway",
            "metrics": [
                {"type": "Resource", "resource_name": "cpu", "target_type": "Utilization", "target_value": 80},
            ],
            "conditions": {
                "AbleToScale": {"status": "True", "reason": "ReadyForNewScale", "message": "recommended size matches current size"},
                "ScalingActive": {"status": "True", "reason": "ValidMetricFound", "message": "the HPA was able to successfully calculate a replica count"},
                "ScalingLimited": {"status": "False", "reason": "DesiredWithinRange", "message": "the desired count is within the acceptable range"},
            },
            "scaling_limited": False,
            "at_max": False,
        },
    ]
    if namespace:
        hpas = [h for h in hpas if h["namespace"] == namespace]
    return QueryResult(data=hpas, total_available=len(hpas), returned=len(hpas))
```

Update `get_cluster_version`:

```python
async def get_cluster_version(self) -> QueryResult:
    await _demo_delay("get_cluster_version")
    if self._platform != "openshift":
        return QueryResult()
    data = _load_fixture("cluster_ctrl_plane_mock.json")
    cv = data.get("cluster_version", {})
    return QueryResult(data=[cv], total_available=1, returned=1)
```

Update `list_service_accounts` to include `deployer-sa` missing permissions:

```python
async def list_service_accounts(self, namespace: str = "") -> QueryResult:
    await _demo_delay("list_service_accounts")
    service_accounts = [
        {"name": "default", "namespace": "ecommerce-prod", "secrets_count": 1, "automount_token": True},
        {"name": "default", "namespace": "kube-system", "secrets_count": 1, "automount_token": True},
        {"name": "deployer-sa", "namespace": "ecommerce-prod", "secrets_count": 1, "automount_token": False},
        {"name": "monitoring-sa", "namespace": "monitoring", "secrets_count": 1, "automount_token": True},
        {"name": "ci-deployer", "namespace": "ecommerce-prod", "secrets_count": 2, "automount_token": False},
    ]
    if namespace:
        service_accounts = [sa for sa in service_accounts if sa["namespace"] == namespace]
    return QueryResult(data=service_accounts, total_available=len(service_accounts), returned=len(service_accounts))
```

**Step 7: Run existing tests to verify nothing breaks**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_mock_cluster_client.py -v 2>&1 | tail -20`
Expected: Tests pass (some may need fixture field adjustments — fix as needed)

**Step 8: Commit**

```bash
git add backend/src/agents/cluster_client/mock_client.py
git commit -m "feat(demo): update MockClusterClient with demo delays and ecommerce scenario data"
```

---

### Task 6: Add demo event emissions to LangGraph pipeline nodes

**Files:**
- Modify: `backend/src/agents/cluster/graph.py`

**Step 1: Find the domain agent wrapper and add inter-stage delays with event emissions**

Look for the `_wrap_domain_agent` function or the graph node functions. Add `await asyncio.sleep(2)` + `emitter.emit(...)` calls between pipeline stages to create visible progress on the UI.

The key places to add thinking delays with event emissions:

1. After `dispatch_router` → before domain agents: "Dispatching domain agents: ctrl_plane, node, network, storage, rbac..."
2. After each domain agent completes: "ctrl_plane analysis complete — 3 anomalies detected"
3. Before `signal_normalizer`: "Extracting normalized signals from domain reports..."
4. Before `failure_pattern_matcher`: "Matching signals against known failure patterns..."
5. Before `temporal_analyzer`: "Analyzing temporal sequences and restart velocity..."
6. Before `diagnostic_graph_builder`: "Building cross-domain evidence graph..."
7. Before `hypothesis_engine`: "Generating root cause hypotheses..."
8. Before `critic_validator`: "Validating hypotheses (6-layer validation)..."
9. Before `synthesize`: "Synthesizing final diagnosis and remediation plan..."

Each emission should be 2-3 seconds apart.

The emitter is passed through the LangGraph config as `config["configurable"]["emitter"]`. Check how existing nodes access it and add the emissions.

**Step 2: Run the cluster diagnostic to verify the full pipeline works**

Start the backend, create a session with `cluster_diagnostics` capability in demo mode, and verify:
- Events emit progressively over 60-90 seconds
- The final state contains domain reports, causal chains, and health report
- No errors in logs

**Step 3: Commit**

```bash
git add backend/src/agents/cluster/graph.py
git commit -m "feat(demo): add inter-stage thinking delays and event emissions for progressive UI"
```

---

### Task 7: Update tests for new fixture data

**Files:**
- Modify: `backend/tests/test_mock_cluster_client.py`

**Step 1: Run existing tests and fix any failures**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_mock_cluster_client.py -v`

If tests fail because they assert on old fixture data (e.g., checking for specific node names like `master-01` instead of `master-1.prod-east.internal`), update the assertions to match the new data.

Key changes likely needed:
- Node names: `master-01` → `master-1.prod-east.internal`
- Namespaces: `production` → `ecommerce-prod`
- Pod names updated to match new fixture
- Deployment names updated

**Step 2: Run the full cluster test suite**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_cluster*.py backend/tests/test_mock_cluster_client.py -v 2>&1 | tail -30`

Fix any remaining failures.

**Step 3: Commit**

```bash
git add backend/tests/
git commit -m "test: update cluster tests for new demo fixture data"
```

---

### Task 8: End-to-end verification

**Step 1: Start the backend in demo mode**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && DEBUGDUCK_MODE=demo python -m uvicorn src.api.app:app --reload --port 8000`

**Step 2: Start the frontend**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npm run dev`

**Step 3: Create a cluster diagnostic session**

Use the UI form or curl:
```bash
curl -X POST http://localhost:8000/api/v4/session \
  -H "Content-Type: application/json" \
  -d '{"capability": "cluster_diagnostics", "incident_id": "demo-monday-outage", "service_name": "ecommerce-platform", "cluster_url": "https://api.prod-east.openshift.example.com:6443", "namespace": "ecommerce-prod"}'
```

**Step 4: Verify progressive UI updates**

- [ ] Topology SVG populates within 10s
- [ ] Agent status capsules show progress (ctrl_plane → node → network → storage)
- [ ] Center panel fills with findings progressively
- [ ] Causal chain / evidence graph appears after synthesis
- [ ] Total time: 60-90 seconds
- [ ] No console errors in frontend or backend

**Step 5: Verify Telescope drawer works**

Click on a pod name in the center panel → Telescope drawer opens → YAML/events/logs tabs load.

**Step 6: Final commit if any adjustments needed**

```bash
git add -A
git commit -m "feat(demo): end-to-end verified cluster diagnostic demo"
```
