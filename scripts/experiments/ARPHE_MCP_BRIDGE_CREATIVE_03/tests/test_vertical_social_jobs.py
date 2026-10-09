from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class VerticalSocialJobTests(unittest.TestCase):
    def _module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("bridge.vertical_social_jobs"),
            "bridge.vertical_social_jobs must exist",
        )
        return importlib.import_module("bridge.vertical_social_jobs")

    def _plan(self, module, action_type: str = "CUT"):
        return module.new_vertical_social_plan(
            workstation_id="PC_PERSONALE",
            target={"project": "ARPHE_PROJECT", "timeline": "ADV_V1", "fps": "30"},
            actions=[{"action_id": "cut-1", "type": action_type, "phase": "PROVISIONAL_EDIT"}],
        )

    def test_fingerprint_changes_for_material_plan_revision(self):
        module = self._module()
        first = self._plan(module)
        second = module.new_vertical_social_plan(
            workstation_id="PC_PERSONALE",
            target={"project": "ARPHE_PROJECT", "timeline": "ADV_V2", "fps": "30"},
            actions=[{"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"}],
            plan_id=first.plan_id,
            version=2,
        )
        self.assertNotEqual(module.plan_fingerprint(first), module.plan_fingerprint(second))

    def test_store_enforces_workstation_and_idempotent_transition(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            store = module.VerticalSocialPlanStore(Path(raw_root) / "plans.json", "PC_PERSONALE")
            plan = store.create(self._plan(module))
            applied = module.transition_action(
                store, plan.plan_id, "cut-1", "APPROVED", "APPLIED", {"duration_frames": 24}
            )
            repeated = module.transition_action(
                store, plan.plan_id, "cut-1", "APPROVED", "APPLIED", {"duration_frames": 24}
            )
            self.assertEqual("APPLIED", applied.action("cut-1").state)
            self.assertEqual(applied, repeated)
            with self.assertRaisesRegex(Exception, "workstation"):
                module.VerticalSocialPlanStore(Path(raw_root) / "plans.json", "PC_SEGRETERIA")

    def test_blocked_action_does_not_change_verified_action_and_resume_is_local(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as raw_root:
            store = module.VerticalSocialPlanStore(Path(raw_root) / "plans.json", "PC_PERSONALE")
            plan = module.new_vertical_social_plan(
                workstation_id="PC_PERSONALE",
                target={"project": "ARPHE_PROJECT", "timeline": "ADV_V1", "fps": "30"},
                actions=[
                    {"action_id": "cut-1", "type": "CUT", "phase": "PROVISIONAL_EDIT"},
                    {"action_id": "broll-1", "type": "B_ROLL", "phase": "PROVISIONAL_EDIT"},
                ],
            )
            store.create(plan)
            module.transition_action(store, plan.plan_id, "cut-1", "APPROVED", "VERIFIED", {"ok": True})
            result = module.transition_action(
                store, plan.plan_id, "broll-1", "APPROVED", "BLOCKED", {"reason": "asset missing"}
            )
            self.assertEqual("VERIFIED", result.action("cut-1").state)
            self.assertEqual("broll-1", module.next_safe_action(result).action_id)


if __name__ == "__main__":
    unittest.main()

