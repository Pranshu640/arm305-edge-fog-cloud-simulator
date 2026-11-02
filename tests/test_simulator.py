import json
import math
import unittest
from simulator import AccessDenied, Engine, Node, Principal, Task, default_nodes, generate_workload
from simulator.experiments import run_experiments

A = Principal("alice", "a")
B = Principal("bob", "b")
ADMIN = Principal("admin", "staff", "admin")


class SimulatorTests(unittest.TestCase):
    def test_seed_reproducibility(self):
        self.assertEqual(generate_workload(seed=305), generate_workload(seed=305))
        self.assertNotEqual(generate_workload(seed=305), generate_workload(seed=306))

    def test_capacity_fallback_and_rejection(self):
        engine = Engine([Node("e", "Edge", 1, 1, 1), Node("f", "Fog", 1, 1, 10)])
        for i in range(3):
            engine.submit(Task(str(i), "a", 1, 1, "low"), A, "lowest_latency")
        self.assertEqual([r["node_id"] for r in engine.records(A)], ["e", "f", None])
        self.assertEqual(engine.summary(A)["rejected"], 1)

    def test_ram_independent_of_cpu(self):
        engine = Engine([Node("e", "Edge", 8, 1, 1)])
        result = engine.submit(Task("t", "a", 1, 2, "low"), A)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(engine.vms(A))

    def test_latency_budget_rejects(self):
        engine = Engine([Node("c", "Cloud", 100, 100, 200)])
        result = engine.submit(Task("t", "a", 1, 1, "high"), A)
        self.assertEqual(result["reason"], "No node meets latency budget")

    def test_stop_releases_once(self):
        engine = Engine([Node("e", "Edge", 2, 2, 5)])
        result = engine.submit(Task("t", "a", 2, 2, "low"), A)
        self.assertEqual(engine.node_stats()[0]["cpu_pct"], 100)
        engine.stop_vm(result["vm_id"], A)
        engine.stop_vm(result["vm_id"], A)
        engine.drain()
        self.assertEqual(engine.node_stats()[0]["used_cpu"], 0)
        self.assertEqual(engine.summary(A)["cancelled"], 1)
        self.assertEqual(engine.vms(A)[0]["status"], "stopped")

    def test_completion_releases_resources_and_keeps_peak(self):
        engine = Engine([Node("e", "Edge", 2, 2, 5)])
        engine.submit(Task("t", "a", 2, 2, "low"), A)
        engine.drain()
        stats = engine.node_stats()[0]
        self.assertEqual(stats["used_cpu"], 0)
        self.assertEqual(stats["peak_cpu_pct"], 100)
        self.assertEqual(engine.summary(A)["completed"], 1)

    def test_arrival_reuses_completed_capacity(self):
        engine = Engine([Node("e", "Edge", 1, 1, 1)])
        engine.run_workload([Task("1", "a", 1, 1, "low", 10, 0), Task("2", "a", 1, 1, "low", 10, 100)], A)
        self.assertEqual(engine.summary(A)["completed"], 2)

    def test_no_time_travel(self):
        engine = Engine()
        engine.advance(10)
        with self.assertRaises(ValueError):
            engine.advance(9)

    def test_tenant_read_list_export_and_stop(self):
        engine = Engine()
        first = engine.submit(Task("private", "a", 1, 1, "high"), A)
        engine.submit(Task("bob", "b", 1, 1, "high"), B)
        with self.assertRaises(AccessDenied):
            engine.get_record("private", B)
        with self.assertRaises(AccessDenied):
            engine.stop_vm(first["vm_id"], B)
        self.assertEqual([r["task_id"] for r in engine.records(B)], ["bob"])
        self.assertEqual([r["task_id"] for r in engine.vms(B)], ["bob"])
        export = json.loads(json.dumps(engine.export(B)))
        self.assertEqual([r["task_id"] for r in export["tasks"]], ["bob"])
        self.assertEqual(engine.summary(B)["total"], 1)
        self.assertEqual(len(engine.records(ADMIN)), 2)

    def test_cannot_submit_for_another_tenant(self):
        engine = Engine()
        with self.assertRaises(AccessDenied):
            engine.submit(Task("t", "a", 1, 1, "high"), B)
        self.assertEqual(engine.summary(ADMIN)["total"], 0)

    def test_batch_rejects_atomically(self):
        engine = Engine()
        with self.assertRaises(AccessDenied):
            engine.run_workload([Task("1", "a", 1, 1, "high"), Task("2", "b", 1, 1, "high")], A)
        self.assertEqual(engine.summary(A)["total"], 0)

    def test_duplicate_batch_and_existing_id(self):
        engine = Engine()
        task = Task("t", "a", 1, 1, "high")
        with self.assertRaises(ValueError):
            engine.run_workload([task, task], A)
        self.assertFalse(engine.records(A))
        engine.submit(task, A)
        with self.assertRaises(ValueError):
            engine.submit(task, A)

    def test_invalid_resources(self):
        for invalid in [-1, 0, float("nan"), float("inf"), True]:
            with self.assertRaises(ValueError):
                Task("t", "a", invalid, 1, "high")
        with self.assertRaises(ValueError):
            Node("x", "Edge", 0, 10, 1)
        with self.assertRaises(ValueError):
            Task("t", "a", 1, 1, "unknown")

    def test_node_config_role_and_live_state(self):
        engine = Engine()
        config = Node("edge-01", "Edge", 16, 32, 2)
        with self.assertRaises(AccessDenied):
            engine.update_node(config, A)
        engine.update_node(config, ADMIN)
        self.assertEqual(engine.nodes["edge-01"].cpu, 16)
        engine.submit(Task("t", "a", 1, 1, "high"), A)
        with self.assertRaises(ValueError):
            engine.update_node(config, ADMIN)

    def test_snapshots_never_exceed_capacity(self):
        engine = Engine()
        engine.run_workload(generate_workload(200, tenant_id="a"), A)
        for row in engine.utilization_history(ADMIN):
            self.assertTrue(0 <= row["cpu_pct"] <= 100)
            self.assertTrue(0 <= row["ram_pct"] <= 100)
        self.assertTrue(all(r["latency_ms"] <= r["deadline_ms"] for r in engine.records(A) if r["node_id"]))

    def test_four_required_experiments(self):
        evidence = run_experiments(make_charts=False)
        self.assertTrue(all(s["passed"] for s in evidence["scenarios"]))
        self.assertEqual(evidence["runs"]["policy_latency"]["workload"], evidence["runs"]["policy_capacity"]["workload"])


if __name__ == "__main__":
    unittest.main()
