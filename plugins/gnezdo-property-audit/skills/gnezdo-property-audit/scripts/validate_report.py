#!/usr/bin/env python3
"""Structural checks only; this does not establish legal/factual correctness."""
from pathlib import Path
from datetime import datetime
import json
import sys

MATRIX = Path(__file__).resolve().parents[1] / "references/check-matrix.json"


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ["Report must be an object"]
    if data.get("schema_version") != "1.1":
        errors.append("schema_version must be 1.1")

    def text(value, label):
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: nonempty text required")

    def timestamp(value, label):
        try:
            if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            errors.append(f"{label}: ISO timestamp with timezone required")

    text(data.get("case_id"), "case_id")
    timestamp(data.get("as_of"), "as_of")
    matrix = {c["id"]: c for c in json.loads(MATRIX.read_text())["checks"]}
    scope = data.get("scope")
    if not isinstance(scope, dict):
        return errors + ["scope must be an object"]
    for key in ("jurisdiction", "region", "purpose"):
        text(scope.get(key), f"scope.{key}")
    scenario = scope.get("scenario")
    client_statuses = {
        "owner_listing_intake": {
            "Можно заключать агентский договор",
            "Не заключать агентский договор до устранения вопросов",
            "Рекомендуется отказаться от принятия объекта",
        },
        "buyer_purchase_due_diligence": {
            "Можно продолжать подготовку сделки",
            "Можно продолжать только после выполнения условий",
            "Не вносить аванс до устранения рисков",
            "Приостановить сделку",
        },
    }
    if scenario not in client_statuses:
        errors.append("scope.scenario: invalid scenario")
    if not isinstance(scope.get("objects"), list) or not scope["objects"]:
        errors.append("scope.objects must be a nonempty list")
    selected = scope.get("selected_check_ids")
    if not isinstance(selected, list) or not selected or not all(isinstance(v, str) for v in selected):
        return errors + ["selected_check_ids must be a nonempty list of check IDs"]
    if len(set(selected)) != len(selected):
        errors.append("selected_check_ids contains duplicates")
    if set(selected) - matrix.keys():
        errors.append("selected_check_ids contains unknown matrix IDs")

    def rows(key):
        value = data.get(key)
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            errors.append(f"{key} must be an array of objects")
            return []
        return value

    sources, checks, findings = rows("sources"), rows("checks"), rows("findings")
    source_map = {}
    for i, source in enumerate(sources):
        label = f"sources[{i}]"
        for key in ("id", "title", "locator"):
            text(source.get(key), f"{label}.{key}")
        sid = source.get("id")
        if isinstance(sid, str):
            if sid in source_map:
                errors.append(f"{label}: duplicate source ID")
            source_map[sid] = source
        if source.get("kind") not in {"uploaded_document", "official_web", "official_response", "legislation", "secondary_web", "seller_statement"}:
            errors.append(f"{label}: invalid kind")
        if source.get("status") not in {"reviewed", "supplied_unverified", "unavailable"}:
            errors.append(f"{label}: invalid status")
        timestamp(source.get("accessed_at"), f"{label}.accessed_at")
        if "document_date" not in source:
            errors.append(f"{label}: document_date or explicit null required")

    def evidence(items, label, required=False):
        if not isinstance(items, list):
            errors.append(f"{label}: evidence must be a list")
            return
        if required and not items:
            errors.append(f"{label}: reviewed evidence required")
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"{label}: malformed evidence")
                continue
            for key in ("source_id", "locator", "support"):
                text(item.get(key), f"{label}.{key}")
            sid = item.get("source_id")
            source = source_map.get(sid) if isinstance(sid, str) else None
            if not source:
                errors.append(f"{label}: evidence source is absent from inventory")
            elif required and source.get("status") != "reviewed":
                errors.append(f"{label}: unreviewed source cannot support checked facts")

    check_ids = []
    for i, check in enumerate(checks):
        label = f"checks[{i}]"
        cid = check.get("id")
        if not isinstance(cid, str):
            errors.append(f"{label}: check ID must be a string")
            continue
        check_ids.append(cid)
        if cid not in matrix:
            errors.append(f"{label}: unknown check ID")
        elif check.get("critical_to_close") is not matrix[cid]["critical_to_close"]:
            errors.append(f"{label}: critical flag differs from matrix")
        app, status, result = check.get("applicability"), check.get("status"), check.get("result")
        if app not in {"yes", "no", "unresolved"}:
            errors.append(f"{label}: invalid applicability")
        if status not in {"checked", "partial", "not_checked", "unavailable", "not_applicable"}:
            errors.append(f"{label}: invalid status")
        if result not in {"adverse", "no_issue_detected", "inconsistent", "unknown", "not_applicable"}:
            errors.append(f"{label}: invalid result")
        if check.get("freshness") not in {"fit_for_purpose", "stale", "unknown", "not_applicable"}:
            errors.append(f"{label}: invalid freshness")
        text(check.get("explanation"), f"{label}.explanation")
        if app == "no":
            if status != "not_applicable" or result != "not_applicable":
                errors.append(f"{label}: inapplicable item must be marked not_applicable")
        elif status == "not_applicable" or result == "not_applicable":
            errors.append(f"{label}: unresolved/applicable item cannot be excluded")
        if result == "no_issue_detected" and (status != "checked" or app != "yes"):
            errors.append(f"{label}: no_issue_detected requires a completed applicable check")
        if status in {"not_checked", "unavailable"} and result != "unknown":
            errors.append(f"{label}: no completed observation; result must be unknown")
        evidence(check.get("evidence"), label, required=status == "checked")
        if status != "checked" and app != "no":
            text(check.get("next_action"), f"{label}.next_action")
    if len(check_ids) != len(set(check_ids)):
        errors.append("checks contains duplicate IDs")
    if set(check_ids) != set(selected):
        errors.append("checks must cover selected_check_ids exactly, including gaps")

    finding_ids = set()
    for i, finding in enumerate(findings):
        label = f"findings[{i}]"
        for key in ("id", "statement", "impact", "action", "responsible", "closure_evidence", "legal_basis"):
            text(finding.get(key), f"{label}.{key}")
        fid = finding.get("id")
        if isinstance(fid, str):
            if fid in finding_ids:
                errors.append(f"{label}: duplicate finding ID")
            finding_ids.add(fid)
        if finding.get("severity") not in {"blocker", "high", "medium", "low"}:
            errors.append(f"{label}: invalid severity")
        if finding.get("fact_state") not in {"observed", "inference", "unverified"}:
            errors.append(f"{label}: invalid fact_state")
        ids = finding.get("check_ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(v, str) and v in check_ids for v in ids):
            errors.append(f"{label}: finding must refer to selected checks")
        evidence(finding.get("evidence"), label, required=finding.get("fact_state") in {"observed", "inference"})

    decision = data.get("decision")
    if not isinstance(decision, dict):
        return errors + ["decision must be an object"]
    if decision.get("status") not in {"insufficient_data", "hold", "conditional", "no_material_findings_in_scope"}:
        errors.append("invalid decision status")
    if scenario in client_statuses and decision.get("client_status") not in client_statuses[scenario]:
        errors.append("decision.client_status does not match scope.scenario")
    favorable_client_status = {
        "owner_listing_intake": "Можно заключать агентский договор",
        "buyer_purchase_due_diligence": "Можно продолжать подготовку сделки",
    }
    if decision.get("status") == "no_material_findings_in_scope" and decision.get("client_status") != favorable_client_status.get(scenario):
        errors.append("favorable machine status requires the favorable client status")
    if decision.get("status") != "no_material_findings_in_scope" and decision.get("client_status") == favorable_client_status.get(scenario):
        errors.append("favorable client status conflicts with a non-favorable machine status")
    text(decision.get("rationale"), "decision.rationale")
    if not isinstance(decision.get("conditions"), list):
        errors.append("decision.conditions must be an array")
    if decision.get("status") == "conditional" and not decision.get("conditions"):
        errors.append("conditional decision requires conditions")
    if not isinstance(data.get("limitations"), list):
        errors.append("limitations must be an array")
    if decision.get("status") == "no_material_findings_in_scope":
        if not any(c.get("applicability") == "yes" and c.get("status") == "checked" for c in checks):
            errors.append("favorable result requires actual completed checks")
        for check in checks:
            if check.get("applicability") != "no" and (check.get("status") != "checked" or check.get("result") != "no_issue_detected" or check.get("freshness") != "fit_for_purpose"):
                errors.append("favorable result conflicts with unresolved/adverse/stale checks")
        if any(f.get("severity") in {"blocker", "high", "medium"} for f in findings):
            errors.append("favorable result conflicts with material findings")
    return errors


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 validate_report.py report.json")
    try:
        result = validate(json.loads(Path(sys.argv[1]).read_text()))
    except (OSError, ValueError) as error:
        print(f"Cannot validate input: {type(error).__name__}")
        raise SystemExit(2)
    if result:
        print("STRUCTURAL VALIDATION FAILED")
        for error in result:
            print("-", error)
        raise SystemExit(1)
    print("STRUCTURE OK. Facts, authenticity, legal interpretation and completeness of scope are not certified.")
