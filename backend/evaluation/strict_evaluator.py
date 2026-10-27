import os
import re
import json
import uuid
import hashlib
import datetime
from typing import Dict, Any, List, Tuple, Optional


def canonical_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip().lower()


def parse_dose_and_unit(dose_str: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """Strictly parses numeric dose and unit without dropping decimals or units."""
    if not dose_str:
        return None, None
    s = dose_str.strip().lower()
    # Match decimal or integer followed by optional unit
    m = re.match(r"^([\d.]+)\s*([a-z/%]+)?$", s)
    if m:
        try:
            num = float(m.group(1))
            unit = m.group(2) or ""
            return num, unit
        except ValueError:
            pass
    return None, s


def compare_strict_medications(
    preds: List[Dict[str, Any]],
    labels: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Match instances by source occurrence, never by dose/route correctness.

    The strict record count covers explicitly annotated gold attributes.
    Missing gold dimensions are unannotated, not automatically true negatives.
    Pair identity and evidence pairing are chosen independently from attribute
    correctness so duplicate-name errors cannot be optimized away.
    """
    from functools import lru_cache

    if not isinstance(preds, list) or not isinstance(labels, list):
        raise ValueError("Medication predictions and gold labels must be lists.")
    if not all(isinstance(x, dict) for x in preds + labels):
        raise ValueError("Medication occurrences must be objects.")
    if any(not canonical_str(x.get("name")) for x in labels):
        raise ValueError("Gold medication names must be nonempty.")

    attrs = ("dose", "route", "frequency", "duration", "qualifier",
             "prn", "action", "temporal_status")
    matched_p = set()
    matched_l = set()
    pair_indices = []
    ambiguity_flags = []

    def occurrence(item):
        return item.get("source_occurrence_id") or item.get("occurrence_id")

    def span(item):
        ev = item.get("evidence")
        if isinstance(ev, dict):
            a, b = ev.get("start"), ev.get("end")
        elif isinstance(item.get("span"), (list, tuple)) and len(item["span"]) == 2:
            a, b = item["span"]
        else:
            return None
        if type(a) is int and type(b) is int and 0 <= a < b:
            return (a, b)
        return None

    def overlap(p, l):
        ps, ls = span(preds[p]), span(labels[l])
        return max(0, min(ps[1], ls[1]) - max(ps[0], ls[0])) if ps and ls else 0

    # Explicit shared source-occurrence identities are authoritative when both
    # sides provide them, but never match a different normalized drug name.
    for p_idx, pred in enumerate(preds):
        pid = occurrence(pred)
        if pid is None:
            continue
        for l_idx, lab in enumerate(labels):
            if l_idx in matched_l:
                continue
            if (pid == occurrence(lab)
                    and canonical_str(pred.get("name")) == canonical_str(lab.get("name"))):
                pair_indices.append((p_idx, l_idx, "source_occurrence"))
                matched_p.add(p_idx)
                matched_l.add(l_idx)
                break

    names = sorted({canonical_str(item.get("name")) for item in preds + labels} - {""})
    for name in names:
        pi = [i for i, p in enumerate(preds)
              if i not in matched_p and canonical_str(p.get("name")) == name]
        li = [i for i, l in enumerate(labels)
              if i not in matched_l and canonical_str(l.get("name")) == name]
        if not pi or not li:
            continue

        # Position in the original source is preferred, then record order.
        pi.sort(key=lambda i: (span(preds[i])[0] if span(preds[i]) else float("inf"), i))
        li.sort(key=lambda i: (span(labels[i])[0] if span(labels[i]) else float("inf"), i))
        if max(len(pi), len(li)) > 12:
            raise ValueError("More than 12 duplicate medication instances require explicit source occurrence IDs")

        if len(pi) > 1 or len(li) > 1:
            ambiguity_flags.append({
                "name": name,
                "reason": "duplicate occurrence assignment",
                "source_evidence_available": any(
                    span(preds[p]) and span(labels[l]) for p in pi for l in li
                ),
            })

        # Exhaustive bounded one-to-one assignment maximizes evidence overlap
        # only. It does not use dose/route/frequency or strict-record success.
        small_is_pred = len(pi) <= len(li)
        small = pi if small_is_pred else li
        large = li if small_is_pred else pi

        @lru_cache(maxsize=None)
        def solve(pos, mask):
            if pos == len(small):
                return (0, 0, ())
            best = None
            for j, big in enumerate(large):
                if mask & (1 << j):
                    continue
                p_idx, l_idx = (small[pos], big) if small_is_pred else (big, small[pos])
                sc, distance, remainder = solve(pos + 1, mask | (1 << j))
                candidate = (
                    sc + overlap(p_idx, l_idx),
                    distance + abs(p_idx - l_idx),
                    ((p_idx, l_idx),) + remainder,
                )
                # Maximize source overlap; break ties by stable occurrence
                # order/distance and then lexicographic index order.
                if (best is None
                        or (-candidate[0], candidate[1], candidate[2])
                        < (-best[0], best[1], best[2])):
                    best = candidate
            return best

        _, _, chosen = solve(0, 0)
        for p_idx, l_idx in chosen:
            pair_indices.append((p_idx, l_idx, "source_overlap_or_order"))
            matched_p.add(p_idx)
            matched_l.add(l_idx)

    pair_indices.sort(key=lambda x: (x[1], x[0]))
    pairs = []
    attr_counts = {a: {"tp": 0, "fp": 0, "fn": 0, "excluded_unannotated": 0} for a in attrs}
    for p_idx, l_idx, match_type in pair_indices:
        p, l = preds[p_idx], labels[l_idx]
        mismatches = {}
        for attr in attrs:
            if attr not in l:
                attr_counts[attr]["excluded_unannotated"] += 1
                continue
            predicted, expected = canonical_str(p.get(attr)), canonical_str(l.get(attr))
            if predicted == expected:
                if expected:
                    attr_counts[attr]["tp"] += 1
            else:
                mismatches[attr] = (p.get(attr), l.get(attr))
                if predicted:
                    attr_counts[attr]["fp"] += 1
                if expected:
                    attr_counts[attr]["fn"] += 1
        # If explicit gold source identity or span exists, association is scored.
        source_ok = True
        if occurrence(l) is not None:
            source_ok = occurrence(p) == occurrence(l)
        elif span(l) is not None:
            source_ok = span(p) == span(l)
        if not source_ok:
            mismatches["source_association"] = (span(p), span(l))
        exact = not mismatches
        pairs.append({
            "pred_idx": p_idx, "label_idx": l_idx,
            "pred": p, "label": l, "match_type": match_type,
            "tp": 1 if exact else 0,
            "fp": 0 if exact else 1, "fn": 0 if exact else 1,
            "attribute_mismatches": mismatches,
            "unannotated_attributes": [a for a in attrs if a not in l],
        })

    unpaired_preds = [p for idx, p in enumerate(preds) if idx not in matched_p]
    unpaired_labels = [l for idx, l in enumerate(labels) if idx not in matched_l]

    # Unpaired gold labels remain FNs; per-attribute denominators remain visible.
    for gold in unpaired_labels:
        for attr in attrs:
            if attr in gold and canonical_str(gold[attr]):
                attr_counts[attr]["fn"] += 1
            elif attr not in gold:
                attr_counts[attr]["excluded_unannotated"] += 1
    for pred in unpaired_preds:
        for attr in attrs:
            if canonical_str(pred.get(attr)):
                attr_counts[attr]["fp"] += 1

    tp = sum(pair["tp"] for pair in pairs)
    fp = sum(pair["fp"] for pair in pairs) + len(unpaired_preds)
    fn = sum(pair["fn"] for pair in pairs) + len(unpaired_labels)
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "pairs": pairs,
        "false_positives": unpaired_preds,
        "false_negatives": unpaired_labels,
        "attribute_counts": attr_counts,
        "matching_ambiguities": ambiguity_flags,
        "contract": "strict_annotated_record_source_first_v3",
    }


def compare_strict_vitals(
    pred: Dict[str, Any],
    label: Dict[str, Any],
) -> Dict[str, Any]:
    """Strict vital comparison preserving units."""
    tp = fp = fn = 0
    mismatches = []
    all_keys = set(pred.keys()) | set(label.keys())

    for k in sorted(all_keys):
        p_val = pred.get(k)
        l_val = label.get(k)

        if p_val is not None and l_val is not None:
            # Extract values and units
            p_str = p_val.get("value") if isinstance(p_val, dict) else str(p_val)
            p_unit = p_val.get("unit") if isinstance(p_val, dict) else ""
            l_str = l_val.get("value") if isinstance(l_val, dict) else str(l_val)
            l_unit = l_val.get("unit") if isinstance(l_val, dict) else ""

            # Check value and unit
            val_match = canonical_str(p_str) == canonical_str(l_str)
            unit_match = (canonical_str(p_unit) == canonical_str(l_unit)) if (p_unit or l_unit) else True

            if val_match and unit_match:
                tp += 1
            else:
                fp += 1
                fn += 1
                mismatches.append({"key": k, "pred": (p_str, p_unit), "label": (l_str, l_unit)})
        elif p_val is not None:
            fp += 1
            mismatches.append({"key": k, "pred": p_val, "label": None})
        else:
            fn += 1
            mismatches.append({"key": k, "pred": None, "label": l_val})

    return {"tp": tp, "fp": fp, "fn": fn, "mismatches": mismatches}


def compare_strict_instructions(
    pred: Any,
    label: Any,
) -> Dict[str, Any]:
    """Strict comparison of instructions by category, unwrapping nested structures and verifying clinically critical terms."""
    tp = fp = fn = 0
    mismatches = []

    def extract_inst_text(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            val = item.get("value")
            if val is not None:
                return extract_inst_text(val)
            txt = item.get("text")
            if txt is not None:
                return extract_inst_text(txt)
            msg = item.get("message")
            if msg is not None:
                return extract_inst_text(msg)
        return str(item) if item is not None else ""

    pred_items = []
    if isinstance(pred, list):
        for item in pred:
            if isinstance(item, dict):
                pred_items.append({"category": item.get("category", "unknown"), "text": extract_inst_text(item)})
            else:
                pred_items.append({"category": "unknown", "text": str(item)})
    elif isinstance(pred, dict):
        for k, v in pred.items():
            pred_items.append({"category": k, "text": extract_inst_text(v)})

    label_items = []
    if isinstance(label, list):
        for item in label:
            if isinstance(item, dict):
                label_items.append({"category": item.get("category", "unknown"), "text": extract_inst_text(item)})
            else:
                label_items.append({"category": "unknown", "text": str(item)})
    elif isinstance(label, dict):
        for k, v in label.items():
            label_items.append({"category": k, "text": extract_inst_text(v)})

    matched_l = set()
    stop_words = {"stop", "discontinue", "avoid", "hold", "cease"}
    negation_words = {"not", "no", "never", "neither", "none", "without"}

    for p in pred_items:
        p_cat = canonical_str(p.get("category"))
        p_txt = canonical_str(p.get("text"))
        p_tokens = set(re.findall(r'\b\w+\b', p_txt))
        p_nums = set(re.findall(r'\b\d+\b', p_txt))
        p_has_stop = bool(p_tokens & stop_words)
        p_has_neg = bool(p_tokens & negation_words)

        found = False
        for l_idx, l in enumerate(label_items):
            if l_idx in matched_l:
                continue
            l_cat = canonical_str(l.get("category"))
            l_txt = canonical_str(l.get("text"))
            l_tokens = set(re.findall(r'\b\w+\b', l_txt))
            l_nums = set(re.findall(r'\b\d+\b', l_txt))
            l_has_stop = bool(l_tokens & stop_words)
            l_has_neg = bool(l_tokens & negation_words)

            nums_match = (p_nums == l_nums)
            polarity_match = (p_has_stop == l_has_stop) and (p_has_neg == l_has_neg)
            union_len = len(p_tokens | l_tokens)
            overlap = (len(p_tokens & l_tokens) / union_len) if union_len > 0 else 0.0

            if p_cat == l_cat and nums_match and polarity_match and (p_txt == l_txt or overlap >= 0.85):
                matched_l.add(l_idx)
                tp += 1
                found = True
                break
        if not found:
            fp += 1
            mismatches.append({"pred": p, "label": None})

    for l_idx, l in enumerate(label_items):
        if l_idx not in matched_l:
            fn += 1
            mismatches.append({"pred": None, "label": l})

    return {"tp": tp, "fp": fp, "fn": fn, "mismatches": mismatches}


def calculate_metrics(tp: int, fp: int, fn: int) -> Dict[str, Any]:
    support = tp + fn
    has_predictions = (tp + fp) > 0
    has_support = support > 0

    if not has_support and not has_predictions:
        return {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "precision": None,  # N/A
            "recall": None,     # N/A
            "f1": None,         # N/A
            "support": 0,
            "has_support": False,
        }

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "support": support,
        "has_support": has_support,
    }



def evaluate_corpus_strictly(
    notes_and_labels: List[Tuple[str, str, Dict[str, Any]]],  # [(note_id, raw_text, gold_label)]
    pipeline_fn: Any,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates a test corpus using strict criteria, generating detailed metrics and immutable run artifacts.
    """
    run_id = f"eval_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    case_results = []
    category_counts = {
        "medications": {"tp": 0, "fp": 0, "fn": 0},
        "vitals": {"tp": 0, "fp": 0, "fn": 0},
        "instructions": {"tp": 0, "fp": 0, "fn": 0},
        "metadata": {"tp": 0, "fp": 0, "fn": 0},
    }

    for note_id, note_text, gold_label in notes_and_labels:
        prediction = pipeline_fn(note_text)

        med_res = compare_strict_medications(
            prediction.get("medications", []),
            gold_label.get("medications", []),
        )
        vit_res = compare_strict_vitals(
            prediction.get("vitals", {}),
            gold_label.get("vitals", {}),
        )
        inst_res = compare_strict_instructions(
            prediction.get("instructions", {}),
            gold_label.get("instructions", {}),
        )
        meta_res = compare_strict_vitals(
            prediction.get("metadata", {}),
            gold_label.get("metadata", {}),
        )

        for cat, res in [("medications", med_res), ("vitals", vit_res), ("instructions", inst_res), ("metadata", meta_res)]:
            category_counts[cat]["tp"] += res["tp"]
            category_counts[cat]["fp"] += res["fp"]
            category_counts[cat]["fn"] += res["fn"]

        case_results.append({
            "note_id": note_id,
            "medications": med_res,
            "vitals": vit_res,
            "instructions": inst_res,
            "metadata": meta_res,
        })

    summary_metrics = {}
    total_tp = total_fp = total_fn = 0
    for cat, counts in category_counts.items():
        summary_metrics[cat] = calculate_metrics(counts["tp"], counts["fp"], counts["fn"])
        total_tp += counts["tp"]
        total_fp += counts["fp"]
        total_fn += counts["fn"]

    summary_metrics["overall"] = calculate_metrics(total_tp, total_fp, total_fn)
    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    run_bundle = {
        "run_id": run_id,
        "evaluator_version": "2.0.0_strict",
        "started_at": started_at,
        "finished_at": finished_at,
        "note_count": len(notes_and_labels),
        "summary": summary_metrics,
        "cases": case_results,
    }

    if output_dir:
        target_dir = os.path.join(output_dir, run_id)
        os.makedirs(target_dir, exist_ok=True)

        meta_path = os.path.join(target_dir, "run_metadata.json")
        summary_path = os.path.join(target_dir, "summary_metrics.json")
        cases_path = os.path.join(target_dir, "case_results.json")
        manifest_path = os.path.join(target_dir, "manifest.json")

        metadata = {
            "run_id": run_id,
            "evaluator": "strict_multiset_v2",
            "started_at": started_at,
            "finished_at": finished_at,
            "note_count": len(notes_and_labels),
        }

        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)
        with open(summary_path, "w") as f:
            json.dump(summary_metrics, f, indent=2)
        with open(cases_path, "w") as f:
            json.dump(case_results, f, indent=2)

        # Build SHA-256 manifest
        manifest = {}
        for fname, fpath in [("run_metadata.json", meta_path), ("summary_metrics.json", summary_path), ("case_results.json", cases_path)]:
            with open(fpath, "rb") as f:
                manifest[fname] = hashlib.sha256(f.read()).hexdigest()

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        run_bundle["artifact_dir"] = target_dir

    return run_bundle
