import json
import time
import unittest
from unittest.mock import patch
import test_engine


class SharedApprovalTests(unittest.TestCase):
    setUp = test_engine.PaperEngineTests.setUp
    tearDown = test_engine.PaperEngineTests.tearDown
    buy = test_engine.PaperEngineTests.buy

    def test_manual_ticket_receives_all_eight_reviews(self):
        p = self.buy()
        self.assertEqual(p["origin"], "manual")
        self.assertEqual(len(p["team_reviews"]), 8)
        risk = next(r for r in p["team_reviews"] if r["bot"] == "Risk Officer")
        self.assertTrue(risk["binding"])
        self.assertEqual(risk["opinion"], "eligible")
        self.assertTrue(
            all(
                not r["binding"]
                for r in p["team_reviews"]
                if r["bot"] != "Risk Officer"
            )
        )

    @patch(
        "engine.core.assess",
        return_value={"action": "buy", "reason": "Explicit test signal"},
    )
    def test_scanner_defaults_to_human_approval_and_expires_old_previews(self, signal):
        self.e.scan()
        s = self.e.snapshot()
        self.assertFalse(s["journal"])
        pending = [p for p in s["proposals"] if p["status"] == "pending"]
        self.assertGreater(len(pending), 0)
        p = pending[0]
        p["created"] = time.time() - 100
        self.e.db.execute(
            "UPDATE proposals SET body=? WHERE id=?", (json.dumps(p), p["id"])
        )
        self.e.db.commit()
        self.e.scan()
        self.assertEqual(
            self.e.db.execute(
                "SELECT status FROM proposals WHERE id=?", (p["id"],)
            ).fetchone()[0],
            "expired",
        )

    def test_automation_cannot_approve_manual_ticket(self):
        p = self.buy()
        self.e.set_approval_policy("automatic_paper")
        with self.assertRaises(ValueError):
            self.e.decide(p["id"], True, actor="paper_automation")
        self.assertFalse(self.e.snapshot()["journal"])

    def test_auto_approval_requires_explicit_policy(self):
        p = self.e.propose("Market Scout", "BTC-USD", "5")
        with self.assertRaises(ValueError):
            self.e.decide(p["id"], True, actor="paper_automation")
        self.e.set_approval_policy("automatic_paper")
        self.e.decide(p["id"], True, actor="paper_automation")
        self.assertEqual(
            self.e.snapshot()["journal"][0]["decision"]["actor"], "paper_automation"
        )

    def test_manual_exit_preserves_owner_and_human_origin(self):
        p = self.e.propose("Market Scout", "BTC-USD", "5")
        self.e.decide(p["id"], True)
        pos = self.e.snapshot()["positions"][0]
        close = self.e.propose("Manual", "BTC-USD", pos["qty"], "sell", pos["id"])
        self.assertEqual(close["bot"], "Market Scout")
        self.assertEqual(close["origin"], "manual")
        self.assertEqual(close["requested_by"], "Manual")

    def test_human_approval_audited_and_risk_rechecked(self):
        p = self.buy()
        self.e.set_kill(True)
        with self.assertRaises(ValueError):
            self.e.decide(p["id"], True)
        self.e.set_kill(False)
        self.e.decide(p["id"], True)
        event = self.e.snapshot()["journal"][0]
        self.assertEqual(event["decision"]["actor"], "human")
        self.assertTrue(event["decision"]["approved"])
        self.assertEqual(len(event["team_reviews"]), 8)

    def test_rejected_decision_persisted(self):
        p = self.buy()
        self.e.decide(p["id"], False)
        saved = self.e.snapshot()["proposals"][0]
        self.assertEqual(saved["decision"]["approved"], False)
        self.assertEqual(saved["decision"]["actor"], "human")

    def test_invalid_policy_or_approval_rejected(self):
        with self.assertRaises(ValueError):
            self.e.set_approval_policy("automatic_live")
        p = self.buy()
        with self.assertRaises(ValueError):
            self.e.decide(p["id"], "yes")
