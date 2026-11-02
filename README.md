# ARM 305 Edge Fog and Cloud Simulator

A local Python simulator for task placement, exclusive CPU/RAM allocation, simulated VM lifecycles, tenant authorization and QoS comparison. The Streamlit app is named **Continuum**. All workloads and timings are synthetic.

[Project report](docs/ARM305_Project_Report.pdf) · [Presentation](docs/ARM305_Presentation.pptx) · [Demo and viva guide](docs/DEMO_AND_VIVA.md) · [Experiment results](results/summary.csv)

## Team collaboration

Clone this repository, then follow the setup instructions below:

```bash
git clone https://github.com/Pranshu640/arm305-edge-fog-cloud-simulator.git
cd arm305-edge-fog-cloud-simulator
```

The repository is private. The owner must invite teammates through the repository's **Settings → Collaborators** before they can clone it. Keep changes on separate branches and open pull requests for review. Record actual team contributions in [TEAM.md](docs/TEAM.md). Generated environments, caches and the submission ZIP stay out of Git; rebuild the ZIP with `python tools/package_submission.py` when needed.

## Start the app

Use Python **3.11 or newer**. This submission was tested with Python 3.14. Internet access is needed only for installing packages; the app runs locally afterward.

macOS or Linux, from the extracted project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open [the local app](http://127.0.0.1:8501). Stop the server with Ctrl+C. If that port is busy, add `--server.port 8502` and open port 8502 instead. The app binds to the local computer using `.streamlit/config.toml`.

No cloud account, Docker, database, hypervisor or real VM is needed. `requirements.txt` pins the two direct dependencies used by the application. `requirements-lock.txt` records the complete tested environment as additional evidence.

## Use the workspace

1. Leave **Instructor · administrator** selected in the sidebar for an overview. Choose either placement policy, 12 tasks and seed 305. Preview the workload and click **Run workload**.
2. Inspect the placement table, CPU/RAM meters, completed/rejected counts and Matplotlib charts. Download scoped task results as CSV or session results as JSON.
3. **Complete after placement** is selected by default. Clear it before running to leave VMs active. Open **Nodes & VMs**, select a running VM and stop it. Its allocation is freed and its task becomes cancelled. Advance the clock to finish remaining VMs.
4. A manual task can be entered at the bottom of **Simulation**. Submitting it creates a running VM if an eligible node exists. A rejection creates no VM.
5. Use **Reset simulation** before editing node capacity/latency. It clears the simulation and restores the default nodes. In **Nodes & VMs**, the Instructor can configure a node and then rerun a workload.
6. In **Experiments**, run all four reproducible scenarios. This panel is available only to the administrator because its evidence includes multiple tenants.
7. In **Security**, run the isolated unauthorized-access demo. For a manual check, select Alice, submit a task and note its ID; switch to Bob and request that ID. The simulator denies the read. Bob's Simulation table, VM list and downloads exclude Alice's records.

The profile selector is an explicit teaching feature. The local operator can switch profiles, reset the shared simulation or inspect source files. This is a trusted local authorization demonstration, not production authentication. No passwords or sensitive data are stored. Aggregate infrastructure telemetry is shared; protected task/VM records are tenant scoped.

## Command-line runs and saved evidence

After activating the environment:

```bash
python cli.py demo --tasks 12 --seed 305 --policy capacity_aware --output results/demo
python cli.py demo --policy lowest_latency --output results/latency-demo
python cli.py experiments --output results
python -m unittest discover -s tests -v
```

The CLI prints decisions and summaries and saves CSV/JSON and Matplotlib charts. The experiment command exits with a nonzero status if an experiment assertion fails. To test just the dependency-free simulator core:

```bash
python -m unittest discover -s tests -p test_simulator.py -v
```

The UI uses in-memory session state. Closing or restarting the server clears it. Downloads and CLI exports are durable local files. UI experiments run in separate fresh engines and do not change the current simulation.

## Model and placement rules

| Node | CPU cores | RAM GiB | Base latency ms |
| --- | ---: | ---: | ---: |
| Edge | 8 | 16 | 5 |
| Fog | 16 | 32 | 22 |
| Cloud | 32 | 64 | 85 |

Every task has an ID, tenant ID, CPU and RAM request, latency sensitivity, service time and arrival time. Seed 305 produces the included 12-task burst. The UI supports 10–200 generated tasks plus individual manual tasks. The generator API supports up to 10,000 tasks.

For each task:

1. Complete VMs due at or before the task's arrival. Burst tasks use the current clock as their effective submission time.
2. Remove nodes without sufficient available CPU or RAM.
3. Compute projected pressure as `max((used_cpu + requested_cpu) / total_cpu, (used_ram + requested_ram) / total_ram)`.
4. Predict response as `base_latency_ms + service_duration_ms + 20 * projected_pressure`. Budgets are 100 ms for high sensitivity, 220 ms for medium and 600 ms for low. Remove nodes whose response exceeds the budget.
5. For **lowest latency first**, choose the eligible node with the smallest base latency, breaking ties by node ID. For **capacity aware**, minimize `0.35 * response / budget + 0.65 * projected_pressure`, breaking ties by base latency and node ID. Reject when no node remains.

An admitted task creates one VM. Its exclusive CPU/RAM allocation remains reserved for the whole predicted response interval. There is no waiting queue or overcommit. `drain()` advances simulated time to completion without sleeping. `stop_vm()` releases resources once and marks the task cancelled. VM statuses are running, completed and stopped; task statuses are running, completed, rejected and cancelled.

Current utilization uses active allocations. Peak utilization remains available after completion. Mean response covers **admitted** tasks, including running or later-cancelled tasks. QoS success is **completed tasks / all submitted tasks**, and is conservative while tasks are running. Successful completion always meets the modeled budget because admission enforces it. Rejected/cancelled tasks are unsuccessful. Shared infrastructure use may include other tenants, while task metrics and exports use the current tenant's records.

## Recorded experiments

| Experiment | Setup and expected behavior | Actual result |
| --- | --- | --- |
| E1 policy comparison | Same 12 tasks and default nodes; compare locality and pressure | Both complete 12; 10 placements differ; mean response 69.25 ms vs 97.099 ms |
| E2 overload | 30 tasks, each 3 CPU/6 GiB/40 ms, medium sensitivity; fill nearby nodes then reject | 17 complete, 13 reject; Edge 2, Fog 5, Cloud 10 |
| E3 unauthorized access | Bob reads Alice's PRIVATE-A and exports his own records | Read denied; export contains only Bob's PRIVATE-B |
| E4 Edge upgrade | Repeat E1 latency policy with Edge 16 CPU/32 GiB/2 ms | 4 placements change; mean response falls to 59.292 ms |

All four scenarios record setup, expected outcome, actual outcome, pass status and evidence paths in `results/experiments.json`. Each run has workload, task, node and timeline CSVs. Rejected tasks carry a capacity or latency reason. `results/summary.csv` is the comparison table. `results/comparison.png` and the per-run charts show placement, peak CPU/RAM and QoS.

Capacity aware reduces Edge peak CPU from 100% to 37.5% in E1, with a higher mean response and the same completion count. The upgraded Edge improves mean response by about 14.4%. These findings apply to the included synthetic workload, not general cloud performance.

## Submission contents

| Path | Purpose |
| --- | --- |
| `app.py` | Local Streamlit interface |
| `cli.py` | Demo and experiment runner |
| `simulator/` | Model, scheduler, security, charts and experiments |
| `tests/` | 16 core tests and 3 interface workflow tests |
| `requirements.txt` | Direct application dependencies |
| `requirements-lock.txt` | Full tested environment snapshot |
| `docs/architecture.svg` and `docs/architecture.pdf` | Editable vector diagram and PDF copy |
| `docs/ARM305_Project_Report.pdf` | Seven-page project report |
| `docs/ARM305_Presentation.pptx` | Six-slide editable deck with presenter notes |
| `docs/DEMO_AND_VIVA.md` | Live demo sequence and viva preparation |
| `docs/TEAM.md` | Team details and contribution form to complete |
| `results/` | Experiment setup, decisions, comparisons, CSV/JSON and charts |
| `evidence/` | Test output, browser check and interface screenshots |
| `tools/package_submission.py` | Rebuild the ZIP using standard-library Python |

Run `python tools/package_submission.py` to create `output/ARM305_Submission.zip`. The archive excludes virtual environments, caches and temporary authoring files. It has one top-level project folder. Add your team names, IDs and actual contributions in `docs/TEAM.md` before submission. Do not claim contributions you did not make.

## Limitations

The response model uses a linear pressure penalty, equal processing behavior across tiers and exclusive reservations. It omits bandwidth, network queues, energy, cost, migration, preemption and runtime failures. Workload order affects placement. The small deterministic experiment is useful for explanation, but broad scheduler claims require varied workloads and sensitivity analysis. The local identity selector and export files do not provide authentication or encrypted storage for untrusted users.

The project follows the supplied ARM305_Mini_Project.pdf. Streamlit interface testing follows its [official AppTest documentation](https://docs.streamlit.io/develop/api-reference/app-testing). All reported measurements are generated by the included code.
