"""User-facing workflows tested with Streamlit's official AppTest harness."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()

    def test_workload_and_vm_stop(self):
        at = self.app
        self.assertFalse(at.exception)
        at.checkbox(key="finish").uncheck().run()
        at.button(key="run").click().run()
        self.assertFalse(at.exception)
        at.radio(key="page").set_value("Nodes & VMs").run()
        at.button(key="stop_vm").click().run()
        self.assertFalse(at.exception)
        engine = at.session_state["engine"]
        self.assertEqual(engine.summary(__import__("simulator").Principal("x", "staff", "admin"))["cancelled"], 1)

    def test_experiments_and_tenant_view(self):
        at = self.app
        at.radio(key="page").set_value("Experiments").run()
        at.button(key="experiments").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(all(s["passed"] for s in at.session_state["experiment_bundle"]["scenarios"]))
        at.selectbox(key="identity").set_value("Bob · team-b").run()
        self.assertTrue(any("multiple tenants" in item.value for item in at.info))

    def test_security_demonstration(self):
        at = self.app
        at.radio(key="page").set_value("Security").run()
        at.button(key="security_demo").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("denied" in s.value for s in at.success))


if __name__ == "__main__":
    unittest.main()
