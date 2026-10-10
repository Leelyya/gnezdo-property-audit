import copy
import unittest
from validate_report import validate


def report():
    return {"schema_version":"1.1","case_id":"synthetic-case","as_of":"2026-09-29T15:00:00+03:00",
      "scope":{"scenario":"buyer_purchase_due_diligence","jurisdiction":"RU","region":"test","purpose":"document comparison only","objects":["synthetic-object"],"selected_check_ids":["DOC-02"]},
      "sources":[{"id":"D1","kind":"uploaded_document","title":"Synthetic excerpt","locator":"test.txt","accessed_at":"2026-09-29T15:00:00+03:00","document_date":"2026-09-29","status":"reviewed","notes":"Not a real property"}],
      "checks":[{"id":"DOC-02","applicability":"yes","status":"checked","result":"no_issue_detected","critical_to_close":True,"freshness":"fit_for_purpose","explanation":"Synthetic narrow check","evidence":[{"source_id":"D1","locator":"line 1","support":"Synthetic fact"}],"next_action":""}],
      "findings":[],"decision":{"status":"no_material_findings_in_scope","client_status":"Можно продолжать подготовку сделки","rationale":"Only the explicitly narrow synthetic scope","conditions":[]},"limitations":["Synthetic test, no legal conclusion"]}


class ValidationTests(unittest.TestCase):
    def test_narrow_consistent_report(self):
        self.assertEqual(validate(report()), [])

    def test_missing_evidence_is_not_favorable(self):
        value=report();value["checks"][0]["evidence"]=[]
        self.assertTrue(validate(value))

    def test_unknown_source_is_rejected(self):
        value=report();value["checks"][0]["evidence"][0]["source_id"]="invented"
        self.assertTrue(validate(value))

    def test_inaccessible_source_is_not_reviewed_evidence(self):
        value=report();value["sources"][0]["status"]="unavailable"
        self.assertTrue(validate(value))

    def test_favorable_status_cannot_hide_unchecked_item(self):
        value=report();value["checks"][0].update(status="not_checked",result="unknown",next_action="Request source")
        self.assertTrue(validate(value))

    def test_same_gap_can_be_honestly_reported(self):
        value=report();value["checks"][0].update(status="not_checked",result="unknown",next_action="Request source",evidence=[])
        value["decision"]["status"]="insufficient_data"
        value["decision"]["client_status"]="Не вносить аванс до устранения рисков"
        self.assertEqual(validate(value),[])

    def test_scope_cannot_silently_drop_a_selected_item(self):
        value=report();value["scope"]["selected_check_ids"].append("LAND-01")
        self.assertTrue(validate(value))

    def test_client_status_must_match_scenario(self):
        value=report();value["decision"]["client_status"]="Можно заключать агентский договор"
        self.assertTrue(validate(value))

    def test_owner_scenario_accepts_owner_status(self):
        value=report();value["scope"]["scenario"]="owner_listing_intake"
        value["decision"]["client_status"]="Можно заключать агентский договор"
        self.assertEqual(validate(value),[])

    def test_favorable_client_status_cannot_hide_hold(self):
        value=report();value["decision"]["status"]="hold"
        self.assertTrue(validate(value))

    def test_non_favorable_client_status_cannot_hide_favorable_machine_result(self):
        value=report();value["decision"]["client_status"]="Приостановить сделку"
        self.assertTrue(validate(value))

    def test_critical_flag_cannot_be_lowered(self):
        value=report();value["checks"][0]["critical_to_close"]=False
        self.assertTrue(validate(value))

    def test_old_information_cannot_give_favorable_current_result(self):
        value=report();value["checks"][0]["freshness"]="stale"
        self.assertTrue(validate(value))

    def test_excluding_every_check_is_not_a_favorable_check(self):
        value=report();value["checks"][0].update(applicability="no",status="not_applicable",result="not_applicable",evidence=[])
        self.assertTrue(validate(value))

    def test_malformed_structures_fail_without_crashing(self):
        for key in ("sources","checks","findings"):
            value=report();value[key]=[None]
            self.assertTrue(validate(value))

    def test_material_finding_prevents_favorable_result(self):
        value=report();value["findings"]=[{"id":"R1","check_ids":["DOC-02"],"severity":"high","fact_state":"inference","statement":"Synthetic contradiction","impact":"Requires clarification","evidence":copy.deepcopy(value["checks"][0]["evidence"]),"action":"Request originals","responsible":"Analyst","closure_evidence":"Reconciled original","legal_basis":"Not yet established"}]
        self.assertTrue(validate(value))


if __name__ == "__main__":
    unittest.main()
