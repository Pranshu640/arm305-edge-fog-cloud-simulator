"""Pure Python simulation model. Time is simulated milliseconds, RAM is GiB.

Each admitted task owns one VM. CPU and RAM are reserved exclusively until
completion or stop. All tasks arrive at the current clock unless run_workload
advances to a later arrival_ms. No wall-clock sleep or real VM is involved.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
import random

DEADLINES = {"high": 100.0, "medium": 220.0, "low": 600.0}
POLICIES = ("lowest_latency", "capacity_aware")


class AccessDenied(PermissionError):
    pass


def positive(value: float, name: str, allow_zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}")


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str = "tenant"

    def __post_init__(self):
        if not self.user_id or not self.tenant_id or self.role not in ("tenant", "admin"):
            raise ValueError("A user, tenant and supported role are required")


@dataclass(frozen=True)
class Node:
    node_id: str
    tier: str
    cpu: float
    ram_gib: float
    latency_ms: float

    def __post_init__(self):
        if not self.node_id or self.tier not in ("Edge", "Fog", "Cloud"):
            raise ValueError("Node ID and Edge/Fog/Cloud tier are required")
        positive(self.cpu, "CPU")
        positive(self.ram_gib, "RAM")
        positive(self.latency_ms, "Latency", True)


@dataclass(frozen=True)
class Task:
    task_id: str
    tenant_id: str
    cpu: float
    ram_gib: float
    sensitivity: str
    duration_ms: float = 30
    arrival_ms: float = 0

    def __post_init__(self):
        if not self.task_id or not self.tenant_id:
            raise ValueError("Task ID and tenant are required")
        if self.sensitivity not in DEADLINES:
            raise ValueError("Sensitivity must be low, medium or high")
        positive(self.cpu, "CPU")
        positive(self.ram_gib, "RAM")
        positive(self.duration_ms, "Duration")
        positive(self.arrival_ms, "Arrival", True)


@dataclass
class VM:
    vm_id: str
    task_id: str
    tenant_id: str
    host_node: str
    cpu: float
    ram_gib: float
    status: str
    created_ms: float
    finish_ms: float


def default_nodes() -> list[Node]:
    return [Node("edge-01", "Edge", 8, 16, 5),
            Node("fog-01", "Fog", 16, 32, 22),
            Node("cloud-01", "Cloud", 32, 64, 85)]


def generate_workload(count=12, seed=305, tenant_id="team-a", prefix="T") -> list[Task]:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 10000:
        raise ValueError("Task count must be an integer between 1 and 10000")
    rng = random.Random(seed)
    return [Task(f"{prefix}{i + 1:03}", tenant_id, rng.choice([1, 2, 3, 4]),
                 rng.choice([1, 2, 4, 6]), rng.choice(["high", "medium", "low"]),
                 rng.choice([20, 30, 40, 60])) for i in range(count)]


class Engine:
    def __init__(self, nodes=None):
        configs = list(default_nodes() if nodes is None else nodes)
        if not configs or len({n.node_id for n in configs}) != len(configs):
            raise ValueError("Nodes must be nonempty and have unique IDs")
        self.nodes = {n.node_id: n for n in configs}
        self.now = 0.0
        self._vms: dict[str, VM] = {}
        self._records: dict[str, dict] = {}
        self._audit: list[dict] = []
        self._peak = {n.node_id: [0.0, 0.0] for n in configs}
        self._history: list[dict] = []
        self._snapshot()

    def _authorize(self, actor: Principal, tenant: str, action: str, target: str):
        allowed = actor.role == "admin" or actor.tenant_id == tenant
        self._audit.append(dict(time_ms=self.now, user_id=actor.user_id,
                                tenant_id=actor.tenant_id, action=action,
                                target=target, outcome="allowed" if allowed else "denied"))
        if not allowed:
            raise AccessDenied("Access denied: this record belongs to another tenant")

    def _admin(self, actor, action):
        if actor.role != "admin":
            self._audit.append(dict(time_ms=self.now, user_id=actor.user_id,
                                    tenant_id=actor.tenant_id, action=action,
                                    target="infrastructure", outcome="denied"))
            raise AccessDenied("Administrator role required")

    def _used(self, node_id):
        active = [v for v in self._vms.values() if v.host_node == node_id and v.status == "running"]
        return sum(v.cpu for v in active), sum(v.ram_gib for v in active)

    def _snapshot(self):
        for n in self.nodes.values():
            cpu, ram = self._used(n.node_id)
            self._peak[n.node_id][0] = max(self._peak[n.node_id][0], cpu / n.cpu * 100)
            self._peak[n.node_id][1] = max(self._peak[n.node_id][1], ram / n.ram_gib * 100)
            self._history.append(dict(time_ms=self.now, node_id=n.node_id,
                                      cpu_pct=round(cpu / n.cpu * 100, 2),
                                      ram_pct=round(ram / n.ram_gib * 100, 2)))

    def advance(self, target_ms: float):
        positive(target_ms, "Target time", True)
        if target_ms < self.now:
            raise ValueError("Simulation time cannot move backwards")
        due = sorted((v for v in self._vms.values() if v.status == "running" and v.finish_ms <= target_ms),
                     key=lambda v: (v.finish_ms, v.vm_id))
        for vm in due:
            self.now = vm.finish_ms
            vm.status = "completed"
            self._records[vm.task_id]["status"] = "completed"
            self._snapshot()
        self.now = float(target_ms)

    def drain(self):
        self.advance(max([self.now] + [v.finish_ms for v in self._vms.values() if v.status == "running"]))

    def submit(self, task: Task, actor: Principal, policy="capacity_aware") -> dict:
        self._authorize(actor, task.tenant_id, "submit", task.task_id)
        if policy not in POLICIES:
            raise ValueError(f"Unknown policy: {policy}")
        if task.task_id in self._records:
            raise ValueError("Task ID already exists")
        if task.arrival_ms > self.now:
            self.advance(task.arrival_ms)
        candidates, capacity_count = [], 0
        deadline = DEADLINES[task.sensitivity]
        for n in self.nodes.values():
            used_cpu, used_ram = self._used(n.node_id)
            if task.cpu + used_cpu > n.cpu + 1e-9 or task.ram_gib + used_ram > n.ram_gib + 1e-9:
                continue
            capacity_count += 1
            pressure = max((used_cpu + task.cpu) / n.cpu, (used_ram + task.ram_gib) / n.ram_gib)
            latency = n.latency_ms + task.duration_ms + 20 * pressure
            if latency > deadline:
                continue
            score = n.latency_ms if policy == "lowest_latency" else 0.35 * latency / deadline + 0.65 * pressure
            candidates.append((score, n.latency_ms, n.node_id, latency, pressure))
        record = dict(**asdict(task), policy=policy, submitted_ms=self.now, deadline_ms=deadline,
                      node_id=None, tier=None, vm_id=None, latency_ms=None, qos_met=False,
                      status="rejected", reason="No available CPU/RAM" if capacity_count == 0 else "No node meets latency budget")
        if candidates:
            score, _, node_id, latency, pressure = min(candidates)
            node = self.nodes[node_id]
            vm_id = f"VM{len(self._vms) + 1:04}"
            vm = VM(vm_id, task.task_id, task.tenant_id, node_id, task.cpu, task.ram_gib,
                    "running", self.now, self.now + latency)
            self._vms[vm_id] = vm
            record.update(node_id=node_id, tier=node.tier, vm_id=vm_id,
                          latency_ms=round(latency, 3), qos_met=True, status="running",
                          reason=f"{policy}: score={score:.4f}, projected pressure={pressure:.1%}")
        self._records[task.task_id] = record
        self._snapshot()
        return dict(record)

    def run_workload(self, tasks, actor: Principal, policy="capacity_aware", finish=True):
        tasks = list(tasks)
        # Validate the whole batch before allocating anything.
        ids = [t.task_id for t in tasks]
        if len(set(ids)) != len(ids) or any(tid in self._records for tid in ids):
            raise ValueError("Task IDs must be unique, including earlier runs")
        if policy not in POLICIES:
            raise ValueError("Unknown policy")
        for task in tasks:
            self._authorize(actor, task.tenant_id, "validate_batch", task.task_id)
        for task in sorted(tasks, key=lambda t: t.arrival_ms):
            self.submit(task, actor, policy)
        if finish:
            self.drain()
        return self.records(actor)

    def records(self, actor: Principal) -> list[dict]:
        return [dict(r) for r in self._records.values() if actor.role == "admin" or r["tenant_id"] == actor.tenant_id]

    def get_record(self, task_id: str, actor: Principal) -> dict:
        record = self._records.get(task_id)
        if record is None:
            raise KeyError("Record unavailable")
        self._authorize(actor, record["tenant_id"], "read_task", task_id)
        return dict(record)

    def vms(self, actor: Principal) -> list[dict]:
        return [asdict(v) for v in self._vms.values() if actor.role == "admin" or v.tenant_id == actor.tenant_id]

    def stop_vm(self, vm_id: str, actor: Principal):
        vm = self._vms[vm_id]
        self._authorize(actor, vm.tenant_id, "stop_vm", vm_id)
        if vm.status == "running":
            vm.status = "stopped"
            self._records[vm.task_id]["status"] = "cancelled"
            self._records[vm.task_id]["qos_met"] = False
            self._records[vm.task_id]["reason"] = "VM stopped before completion"
            self._snapshot()

    def update_node(self, config: Node, actor: Principal):
        self._admin(actor, "update_node")
        if config.node_id not in self.nodes:
            raise ValueError("Unknown node")
        if any(v.status == "running" for v in self._vms.values()) or self._records:
            raise ValueError("Reset the simulation before editing nodes so peak metrics stay comparable")
        self.nodes[config.node_id] = config
        self._history.clear()
        self._snapshot()

    def node_stats(self) -> list[dict]:
        rows = []
        for n in self.nodes.values():
            cpu, ram = self._used(n.node_id)
            rows.append(dict(**asdict(n), used_cpu=cpu, used_ram_gib=ram,
                             cpu_pct=round(cpu / n.cpu * 100, 2), ram_pct=round(ram / n.ram_gib * 100, 2),
                             peak_cpu_pct=round(self._peak[n.node_id][0], 2),
                             peak_ram_pct=round(self._peak[n.node_id][1], 2)))
        return rows

    def summary(self, actor: Principal) -> dict:
        rows = self.records(actor)
        admitted = [r for r in rows if r["node_id"] is not None]
        complete = sum(r["status"] == "completed" for r in rows)
        return dict(total=len(rows), admitted=len(admitted), completed=complete,
                    rejected=sum(r["status"] == "rejected" for r in rows),
                    cancelled=sum(r["status"] == "cancelled" for r in rows),
                    running=sum(r["status"] == "running" for r in rows),
                    mean_latency_ms=round(sum(r["latency_ms"] for r in admitted) / len(admitted), 3) if admitted else None,
                    qos_success_pct=round(100 * complete / len(rows), 2) if rows else 0,
                    clock_ms=round(self.now, 3))

    def audit(self, actor: Principal) -> list[dict]:
        return [dict(r) for r in self._audit if actor.role == "admin" or r["user_id"] == actor.user_id]

    def utilization_history(self, actor: Principal) -> list[dict]:
        self._admin(actor, "read_utilization_history")
        return [dict(r) for r in self._history]

    def export(self, actor: Principal) -> dict:
        # All protected records pass through the same tenant filters.
        return dict(summary=self.summary(actor), tasks=self.records(actor), vms=self.vms(actor),
                    nodes=self.node_stats(), audit=self.audit(actor))
