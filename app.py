"""Local Streamlit interface. Run with: streamlit run app.py."""
from dataclasses import asdict
import csv
import io
import json
import matplotlib.pyplot as plt
import streamlit as st

from simulator import AccessDenied, Engine, Node, Principal, Task, generate_workload
from simulator.charts import result_figure
from simulator.experiments import run_experiments

st.set_page_config(page_title="Continuum | ARM 305", page_icon="◈", layout="wide")
st.markdown("""<style>
.stApp {background:#f7f9fc;} .block-container{padding-top:2.5rem;max-width:1450px}
h1,h2,h3 {letter-spacing:-.035em;} [data-testid="stMetric"] {background:white;padding:18px 22px;border:1px solid #e3e9ef;border-radius:12px;}
[data-testid="stSidebar"]{background:#edf3f7;} .eyebrow{color:#0d9488;font-size:12px;font-weight:700;letter-spacing:.16em}
.intro{color:#607186;font-size:17px;max-width:850px;margin:0 0 24px}.node-title{font-size:19px;font-weight:650;margin-bottom:2px}
</style>""", unsafe_allow_html=True)

if "engine" not in st.session_state:
    st.session_state.engine = Engine()
    st.session_state.batch = 0

profiles = {"Instructor · administrator": Principal("instructor", "staff", "admin"),
            "Alice · team-a": Principal("alice", "team-a"), "Bob · team-b": Principal("bob", "team-b")}
with st.sidebar:
    st.markdown("### ◈ Continuum")
    st.caption("EDGE / FOG / CLOUD LAB")
    profile = st.selectbox("Demo identity", list(profiles), key="identity")
    actor = profiles[profile]
    st.caption("Local teaching profiles. Switching identity is a demo feature, not a production login.")
    page = st.radio("Workspace", ["Simulation", "Nodes & VMs", "Experiments", "Security"], label_visibility="collapsed", key="page")
    st.divider()
    engine = st.session_state.engine
    st.metric("Simulation clock", f"{engine.now:.1f} ms")
    st.caption("CPU = virtual cores · RAM = GiB\n\nAll timings and machines are simulated.")
    if st.button("Reset simulation", width="stretch"):
        st.session_state.engine = Engine()
        st.session_state.batch += 1
        st.rerun()

engine = st.session_state.engine
st.markdown('<div class="eyebrow">ARM 305 / COMPUTING SYSTEMS SIMULATOR</div>', unsafe_allow_html=True)


def table(rows):
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No records yet.")


def node_cards():
    for col, n in zip(st.columns(3), engine.node_stats()):
        with col:
            with st.container(border=True):
                st.markdown(f'<div class="node-title">{n["tier"]}</div>', unsafe_allow_html=True)
                st.caption(f'{n["node_id"]} · {n["latency_ms"]:g} ms base latency')
                st.progress(min(n["cpu_pct"] / 100, 1), text=f'CPU  {n["used_cpu"]:g} / {n["cpu"]:g} cores')
                st.progress(min(n["ram_pct"] / 100, 1), text=f'RAM  {n["used_ram_gib"]:g} / {n["ram_gib"]:g} GiB')
                st.caption(f'Peak CPU {n["peak_cpu_pct"]:.1f}% · Peak RAM {n["peak_ram_pct"]:.1f}%')


if page == "Simulation":
    st.title("Place tasks across the continuum")
    st.markdown('<p class="intro">Explore how latency and available capacity shape a computing workload. Generate tasks, compare placement decisions, and inspect every simulated VM.</p>', unsafe_allow_html=True)
    node_cards()
    st.write("")
    with st.container(border=True):
        st.subheader("Workload controls")
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1.4])
        policy_label = c1.selectbox("Placement policy", ["Capacity aware", "Lowest latency first"], key="policy")
        count = c2.number_input("Task count", 10, 200, 12, key="count")
        seed = c3.number_input("Random seed", 0, 999999, 305, key="seed")
        finish = c4.checkbox("Complete after placement", value=True, key="finish")
        tenant = "team-a" if actor.role == "admin" else actor.tenant_id
        if actor.role == "admin":
            tenant = st.selectbox("Workload owner", ["team-a", "team-b"], key="owner")
        tasks = generate_workload(int(count), int(seed), tenant, f"B{st.session_state.batch}-")
        with st.expander("Preview generated workload"):
            table([asdict(t) for t in tasks])
        a, b = st.columns([1, 4])
        if a.button("Run workload", type="primary", width="stretch", key="run"):
            try:
                engine.run_workload(tasks, actor, "capacity_aware" if policy_label == "Capacity aware" else "lowest_latency", finish)
                st.session_state.batch += 1
                st.rerun()
            except (ValueError, AccessDenied) as exc:
                st.error(str(exc))
        b.caption("Burst arrival at the current clock. Clear 'Complete after placement' to inspect active reservations and stop VMs.")
    summary = engine.summary(actor)
    cols = st.columns(5)
    for col, label, value in zip(cols, ["Total tasks", "Completed", "Rejected", "Running", "Mean response"],
                                 [summary["total"], summary["completed"], summary["rejected"], summary["running"], f'{summary["mean_latency_ms"] or 0:.1f} ms']):
        col.metric(label, value)
    st.caption(f"Completed within budget / all submitted: {summary['qos_success_pct']:.1f}% · Cancelled: {summary['cancelled']} · Mean response includes all admitted tasks.")
    records = engine.records(actor)
    fig = result_figure(records, engine.node_stats())
    st.pyplot(fig, width="stretch")
    plt.close(fig)
    st.caption("Placement and response show records visible to the current identity. Node utilization is shared infrastructure telemetry.")
    st.subheader("Placement decisions")
    table(records)
    if records:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
        d1, d2 = st.columns(2)
        d1.download_button("Download my task results · CSV", buf.getvalue(), "tasks.csv", "text/csv")
        d2.download_button("Download my session · JSON", json.dumps(engine.export(actor), indent=2), "session.json", "application/json")
    with st.expander("Enter a task manually"):
        with st.form("manual"):
            x, y, z = st.columns(3)
            cpu = x.number_input("CPU cores", .1, 1000., 2., step=.5)
            ram = y.number_input("RAM GiB", .1, 1000., 4., step=.5)
            duration = z.number_input("Service time ms", 1., 2000., 30.)
            sensitivity = st.selectbox("Latency sensitivity", ["high", "medium", "low"])
            if st.form_submit_button("Submit task and create VM"):
                task = Task(f"M{st.session_state.batch}-{summary['total']}", tenant, cpu, ram, sensitivity, duration, engine.now)
                result = engine.submit(task, actor, "capacity_aware" if policy_label == "Capacity aware" else "lowest_latency")
                st.session_state.batch += 1
                st.rerun()

elif page == "Nodes & VMs":
    st.title("Resources and virtual machines")
    st.markdown('<p class="intro">Each admitted task creates one simulated VM. Running VMs reserve resources until completion or an explicit stop.</p>', unsafe_allow_html=True)
    node_cards()
    st.subheader("VM registry")
    table(engine.vms(actor))
    active = [v["vm_id"] for v in engine.vms(actor) if v["status"] == "running"]
    if active:
        chosen = st.selectbox("Running VM", active)
        a, b = st.columns(2)
        if a.button("Stop selected VM", key="stop_vm"):
            engine.stop_vm(chosen, actor)
            st.rerun()
        if b.button("Advance clock to all completions", key="drain"):
            engine.drain()
            st.rerun()
    st.caption("Create a VM by submitting a task on the Simulation page. Rejected tasks do not create a VM. Stopping marks the task cancelled and frees its resources.")
    if actor.role == "admin":
        st.subheader("Configure a node")
        st.caption("Reset before changing configuration. Existing results retain their original configuration.")
        node_id = st.selectbox("Node", list(engine.nodes))
        n = engine.nodes[node_id]
        with st.form("nodes"):
            a, b, c = st.columns(3)
            cpu = a.number_input("Node CPU cores", 1., 1024., float(n.cpu), key=f"cpu-{node_id}")
            ram = b.number_input("Node RAM GiB", 1., 4096., float(n.ram_gib), key=f"ram-{node_id}")
            latency = c.number_input("Base latency ms", 0., 2000., float(n.latency_ms), key=f"latency-{node_id}")
            if st.form_submit_button("Apply node configuration"):
                try:
                    engine.update_node(Node(node_id, n.tier, cpu, ram, latency), actor)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

elif page == "Experiments":
    st.title("Reproducible experiments")
    st.markdown('<p class="intro">Four experiments cover policy tradeoffs, overload, tenant isolation, and a capacity and latency upgrade. Every run starts from a fresh simulator.</p>', unsafe_allow_html=True)
    if actor.role != "admin":
        st.info("Experiment evidence covers multiple tenants. Select the Instructor demo identity to view it.")
    else:
        if st.button("Run all four experiments", type="primary", key="experiments"):
            st.session_state.experiment_bundle = run_experiments(make_charts=False)
        if "experiment_bundle" in st.session_state:
            bundle = st.session_state.experiment_bundle
            table(bundle["summary"])
            for s in bundle["scenarios"]:
                with st.expander(f"{s['id']} · {s['name']} · {'PASS' if s['passed'] else 'FAIL'}", expanded=True):
                    for field in ["setup", "expected", "actual"]:
                        st.write(f"**{field.title()}**  {s[field]}")
            names = list(bundle["runs"])
            selected = st.selectbox("Inspect run", names)
            data = bundle["runs"][selected]
            fig = result_figure(data["tasks"], data["nodes"])
            st.pyplot(fig)
            plt.close(fig)
            table(data["tasks"])
            st.download_button("Download experiment evidence · JSON", json.dumps(bundle, indent=2), "experiments.json", "application/json")

else:
    st.title("Tenant isolation")
    st.markdown('<p class="intro">Task lookups, VM controls, lists, and exports check the active identity. Demo profiles use synthetic IDs and store no passwords.</p>', unsafe_allow_html=True)
    st.write(f"Active user: **{actor.user_id}** · tenant: **{actor.tenant_id}** · role: **{actor.role}**")
    st.subheader("Protected record lookup")
    with st.form("lookup"):
        task_id = st.text_input("Task ID", placeholder="Enter a known task ID from the simulation")
        if st.form_submit_button("Read protected task", key="lookup"):
            try:
                st.json(engine.get_record(task_id, actor))
            except AccessDenied as exc:
                st.error(str(exc))
            except KeyError:
                st.warning("Record unavailable")
    if st.button("Run isolated unauthorized-access demo", key="security_demo"):
        demo = Engine()
        alice, bob = profiles["Alice · team-a"], profiles["Bob · team-b"]
        demo.submit(Task("PRIVATE-A", "team-a", 1, 1, "high"), alice)
        try:
            demo.get_record("PRIVATE-A", bob)
        except AccessDenied:
            st.success("PASS: Bob's read of Alice's PRIVATE-A task was denied. Bob's task export is empty.")
        st.json({"bob_visible_tasks": demo.records(bob), "bob_visible_vms": demo.vms(bob), "bob_audit": demo.audit(bob)})
    st.subheader("Access audit")
    table(engine.audit(actor))
    st.caption("The local operator can select any demo profile and inspect source files. This demonstrates authorization logic, not hardened authentication or an untrusted multi-user service.")
