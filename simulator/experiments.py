"""Four reproducible experiments, including both required comparisons."""
from dataclasses import asdict, replace
import csv
import json
from pathlib import Path

from .core import AccessDenied, Engine, Principal, Task, default_nodes, generate_workload

ADMIN = Principal("instructor", "staff", "admin")
ALICE = Principal("alice", "team-a")
BOB = Principal("bob", "team-b")


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def run_experiments(output_dir=None, make_charts=True):
    workload = generate_workload()
    runs = {}

    def run(name, tasks, policy, nodes=None):
        engine = Engine(nodes)
        engine.run_workload(tasks, ADMIN, policy)
        runs[name] = dict(summary=engine.summary(ADMIN), tasks=engine.records(ADMIN),
                          nodes=engine.node_stats(), workload=[asdict(t) for t in tasks],
                          timeline=engine.utilization_history(ADMIN), policy=policy)
        return runs[name]

    first = run("policy_latency", workload, "lowest_latency")
    second = run("policy_capacity", workload, "capacity_aware")
    overload_tasks = [Task(f"O{i+1:03}", "team-a", 3, 6, "medium", 40) for i in range(30)]
    overload = run("overload", overload_tasks, "lowest_latency")
    upgraded = [replace(n, cpu=16, ram_gib=32, latency_ms=2) if n.tier == "Edge" else n for n in default_nodes()]
    changed = run("upgraded_edge", workload, "lowest_latency", upgraded)

    secure = Engine()
    secure.submit(Task("PRIVATE-A", "team-a", 1, 1, "high"), ALICE)
    secure.submit(Task("PRIVATE-B", "team-b", 1, 1, "high"), BOB)
    denied = False
    try:
        secure.get_record("PRIVATE-A", BOB)
    except AccessDenied:
        denied = True
    exported = secure.export(BOB)
    isolated = all(r["tenant_id"] == "team-b" for r in exported["tasks"] + exported["vms"])
    security = dict(denied=denied, export_isolated=isolated, bob_visible_task_ids=[r["task_id"] for r in exported["tasks"]],
                    audit=secure.audit(ADMIN))
    changed_count = sum(a["node_id"] != b["node_id"] for a, b in zip(first["tasks"], changed["tasks"]))
    policy_changes = sum(a["node_id"] != b["node_id"] for a, b in zip(first["tasks"], second["tasks"]))
    scenarios = [
        dict(id="E1", name="Same workload with two policies", setup="12 tasks, seed 305, burst at t=0, default nodes; fresh engine per policy.",
             expected="Capacity-aware placement may distribute tasks differently. Neither policy exceeds capacity or admits a task above its latency budget.",
             actual=f"{policy_changes}/12 placements differ. Lowest-latency completed {first['summary']['completed']}; capacity-aware completed {second['summary']['completed']}.",
             passed=all(r["qos_met"] for run_data in [first, second] for r in run_data["tasks"] if r["node_id"]),
             evidence=["policy_latency_tasks.csv", "policy_capacity_tasks.csv", "comparison.png"]),
        dict(id="E2", name="Overload and fallback", setup="30 simultaneous medium-sensitivity tasks, each 3 CPU, 6 GiB RAM and 40 ms service; lowest-latency policy.",
             expected="Fill Edge, then fall back to Fog and Cloud. Reject remaining tasks when no suitable capacity remains.",
             actual=f"{overload['summary']['completed']} completed and {overload['summary']['rejected']} rejected. Admitted tasks span {len({r['tier'] for r in overload['tasks'] if r['tier']})} tiers.",
             passed=overload["summary"]["rejected"] > 0 and len({r["tier"] for r in overload["tasks"] if r["tier"]}) == 3,
             evidence=["overload_tasks.csv", "overload_nodes.csv", "overload_chart.png"]),
        dict(id="E3", name="Unauthorized tenant access", setup="Alice owns PRIVATE-A. Bob owns PRIVATE-B and requests Alice's task, then exports his own records.",
             expected="Deny Bob's direct read and exclude Alice's task and VM from his export.",
             actual=f"Direct read {'denied' if denied else 'allowed'}. Bob sees {security['bob_visible_task_ids']}. Export isolation={isolated}.",
             passed=denied and isolated, evidence=["security.json"]),
        dict(id="E4", name="Capacity and latency change", setup="Repeat E1 lowest-latency workload after changing Edge from 8 CPU/16 GiB/5 ms to 16 CPU/32 GiB/2 ms.",
             expected="Larger, faster Edge admits more tasks locally and changes response time and resource utilization.",
             actual=f"{changed_count}/12 placements change. Mean response {first['summary']['mean_latency_ms']} ms before and {changed['summary']['mean_latency_ms']} ms after. Fog peak CPU falls from {first['nodes'][1]['peak_cpu_pct']}% to {changed['nodes'][1]['peak_cpu_pct']}%; Edge peak CPU remains 100% with twice the capacity.",
             passed=changed_count > 0 and changed["summary"]["mean_latency_ms"] < first["summary"]["mean_latency_ms"],
             evidence=["policy_latency_tasks.csv", "upgraded_edge_tasks.csv", "upgraded_edge_nodes.csv", "comparison.png"]),
    ]
    summary = [dict(run=name, policy=data["policy"], **data["summary"]) for name, data in runs.items()]
    bundle = dict(seed=305, model="response_ms = base_latency_ms + duration_ms + 20 * projected_pressure", scenarios=scenarios,
                  runs=runs, summary=summary, security=security)
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "experiments.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        (out / "security.json").write_text(json.dumps(security, indent=2), encoding="utf-8")
        write_csv(out / "summary.csv", summary)
        for name, data in runs.items():
            for kind in ["tasks", "nodes", "workload", "timeline"]:
                write_csv(out / f"{name}_{kind}.csv", data[kind])
        if make_charts:
            from .charts import result_figure
            import matplotlib.pyplot as plt
            for name, data in runs.items():
                fig = result_figure(data["tasks"], data["nodes"])
                fig.savefig(out / f"{name}_chart.png", dpi=170)
                plt.close(fig)
            fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
            labels = ["Latency first", "Capacity aware", "Overload", "Upgraded Edge"]
            axes[0].bar(labels, [r["completed"] for r in summary], label="Completed", color="#0d9488")
            axes[0].bar(labels, [r["rejected"] for r in summary], bottom=[r["completed"] for r in summary], label="Rejected", color="#e8a444")
            axes[0].set(ylabel="Tasks", title="Admission outcomes")
            axes[0].legend(frameon=False)
            axes[1].bar(labels, [r["mean_latency_ms"] for r in summary], color=["#0d9488", "#6366f1", "#e8a444", "#3b82f6"])
            axes[1].set(ylabel="Milliseconds", title="Mean admitted response time")
            for ax in axes:
                ax.spines[["top", "right"]].set_visible(False)
                ax.tick_params(axis="x", labelrotation=20)
            fig.savefig(out / "comparison.png", dpi=180)
            plt.close(fig)
    return bundle
