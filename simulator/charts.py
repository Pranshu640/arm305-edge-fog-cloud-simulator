"""Matplotlib figures used by the app, CLI and experiment bundle."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"Edge": "#0d9488", "Fog": "#4f46e5", "Cloud": "#e49a24"}


def result_figure(records, nodes):
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "white"}):
        fig, axes = plt.subplots(1, 3, figsize=(14, 4), layout="constrained")
        tiers = ["Edge", "Fog", "Cloud"]
        counts = [sum(r["tier"] == t for r in records) for t in tiers]
        bars = axes[0].bar(tiers, counts, color=[COLORS[t] for t in tiers], width=.55)
        axes[0].bar_label(bars, padding=3)
        axes[0].set(title="Task placement", ylabel="Admitted tasks", ylim=(0, max(counts + [1]) + 2))
        labels = [n["tier"] for n in nodes]
        x = list(range(len(nodes)))
        axes[1].bar([v-.17 for v in x], [n["peak_cpu_pct"] for n in nodes], .34, label="CPU", color="#0d9488")
        axes[1].bar([v+.17 for v in x], [n["peak_ram_pct"] for n in nodes], .34, label="RAM", color="#6366f1")
        axes[1].set(xticks=x, xticklabels=labels, ylim=(0, 115), title="Peak resource utilization", ylabel="Capacity (%)")
        axes[1].legend(frameon=False)
        admitted = [r for r in records if r["node_id"]]
        if admitted:
            axes[2].scatter(range(len(admitted)), [r["latency_ms"] for r in admitted],
                            c=[COLORS[r["tier"]] for r in admitted], s=38, label="Simulated response")
            axes[2].plot(range(len(admitted)), [r["deadline_ms"] for r in admitted],
                         "_", color="#9ca3af", markersize=12, label="Latency budget")
        else:
            axes[2].text(.5, .5, "Submit a workload to see QoS", ha="center", transform=axes[2].transAxes)
        axes[2].set(title="Response time and QoS", xlabel="Admitted task index", ylabel="Milliseconds")
        if admitted:
            axes[2].legend(frameon=False, fontsize=8)
        return fig
