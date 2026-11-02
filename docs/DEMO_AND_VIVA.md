# Demonstration and viva preparation

## Four minute demonstration

1. Start with `python -m streamlit run app.py`. Keep Instructor selected. Show the three nodes and explain CPU cores, RAM GiB, base latency and current versus peak use.
2. Generate 12 tasks with seed 305. Preview their CPU/RAM and sensitivity. Run capacity aware. Show completed and rejected counts, the placement table and one task's response budget. Explain why current utilization returns to zero after completion but peak use remains.
3. Reset, clear Complete after placement and submit a workload. Open Nodes & VMs. Stop a running VM. Show the stopped status, cancelled task and reduced reservation. Finish the remaining VMs with the clock control.
4. Open Experiments and run all four. Compare latency first with capacity aware on the same tasks. Explain the overload fallback and the 13 rejected tasks. Point out the upgraded Edge's changed capacity and latency.
5. Open Security and run the unauthorized-access demo. Explain the denial and Bob's filtered export. State that profiles are trusted local demo identities.

## Questions to prepare

**Why do we need Fog between Edge and Cloud?** In this model, Fog offers an intermediate capacity and latency choice. It can accept tasks that no longer fit on Edge while avoiding the Cloud's larger base delay.

**What are the placement rules?** Check available CPU/RAM, estimate response, filter by the task's latency budget and rank eligible nodes using the chosen policy. Equal scores use deterministic tie breakers.

**Does capacity aware always outperform latency first?** No. Here it lowers Edge peak pressure but raises mean response and completes the same 12 tasks. Its weights express a tradeoff.

**Is the simulated latency measured from hardware?** No. It is base latency plus service duration plus 20 ms multiplied by projected pressure. The constants are stated modeling assumptions.

**What makes a VM virtual here?** It is a resource-allocation record linked to a task and host. It reserves CPU/RAM, changes status and releases resources on stop/completion. No guest OS or hypervisor runs.

**Can a stopped VM complete later?** No. Completion handles running VMs only. Stop is idempotent and cannot release the same allocation twice.

**How do tenant checks work?** Protected lookups and VM stops compare the active principal's tenant to the owner's tenant. Lists and exports filter by tenant. Administrators can view all records. The demo profile selector is not authentication.

**Why do overload tasks fail?** Each request needs 3 CPU and 6 GiB. The simultaneous burst fills the three hosts to the point where their remaining resources cannot fit another entire request. There is no waiting queue.

**Why is mean response insufficient by itself?** It covers admitted tasks. A policy could reject most demand and report a low mean for the few it admits. Read completion/rejection counts and QoS percentage alongside it.

**What would improve the model?** More varied workloads, response-time calibration, network queues and bandwidth, energy/cost models, scheduling queues, durable storage and actual authentication.

Every member should be able to explain the complete model and their actual contribution. Complete TEAM.md with truthful details before the viva.
