"""Run a reproducible demo without the web interface."""
import argparse
import json
from pathlib import Path
from simulator import Engine, Principal, generate_workload
from simulator.experiments import run_experiments, write_csv


def main():
    parser = argparse.ArgumentParser(description="ARM 305 Edge/Fog/Cloud simulator")
    parser.add_argument("command", choices=["demo", "experiments"], nargs="?", default="demo")
    parser.add_argument("--policy", choices=["lowest_latency", "capacity_aware"], default="capacity_aware")
    parser.add_argument("--tasks", type=int, default=12)
    parser.add_argument("--seed", type=int, default=305)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    if args.command == "experiments":
        bundle = run_experiments(args.output)
        for scenario in bundle["scenarios"]:
            print(f"{scenario['id']} {'PASS' if scenario['passed'] else 'FAIL'}  {scenario['name']}: {scenario['actual']}")
        if not all(s["passed"] for s in bundle["scenarios"]):
            raise SystemExit(1)
    else:
        actor = Principal("alice", "team-a")
        engine = Engine()
        engine.run_workload(generate_workload(args.tasks, args.seed), actor, args.policy)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "demo.json").write_text(json.dumps(engine.export(actor), indent=2), encoding="utf-8")
        write_csv(args.output / "demo_tasks.csv", engine.records(actor))
        from simulator.charts import result_figure
        import matplotlib.pyplot as plt
        fig = result_figure(engine.records(actor), engine.node_stats())
        fig.savefig(args.output / "demo_chart.png", dpi=160)
        plt.close(fig)
        for record in engine.records(actor):
            print(f"{record['task_id']:5} {record['sensitivity']:6} {str(record['node_id'] or 'REJECTED'):10} {str(record['latency_ms']):>7} ms  {record['status']}")
        print(json.dumps(engine.summary(actor), indent=2))
    print(f"Results saved to {args.output.resolve()}")


if __name__ == "__main__":
    main()
