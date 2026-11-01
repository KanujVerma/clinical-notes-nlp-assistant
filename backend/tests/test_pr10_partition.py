"""PR #10 partition contract. No images, transcripts, or model calls."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "validation" / "pr10_partition_manifest.json"


def load():
    raw = MANIFEST.read_bytes()
    assert b"reference_text" not in raw
    data = json.loads(raw)
    assert data["schema"] == "pr10_partition_v1"
    assert data["privacy"] == "public_publisher_data_automated_partition_not_human_reviewed"
    assert "reviewer_id" not in raw.decode()
    return data


def test_amr_roles_are_disjoint_and_groups_are_intact():
    amr = load()["amr"]
    hist = amr["historical_regression"]
    dev = amr["development"]
    hold = amr["untouched_holdout"]
    assert [len(hist), len(dev), len(hold)] == [24, 20, 18]
    ids = [row["id"] for row in hist + dev + hold]
    assert len(ids) == len(set(ids)) == 62
    excluded = [row for row in hist if row["scoring"] == "excluded_identifier"]
    assert [row["id"] for row in excluded] == ["AMR_041"]
    assert "AMR_041" not in {row["id"] for row in dev + hold}
    dev_groups = {row["writer_group"] for row in dev}
    hold_groups = {row["writer_group"] for row in hold}
    assert dev_groups.isdisjoint(hold_groups)
    assert hold_groups == {f"writer_group_{i:02d}" for i in range(1, 8)}
    assert sum(row["page_count"] for row in dev + hold) == sum(
        len(row["page_sha256"]) for row in dev + hold)


def test_rx_official_test_is_kept_out_of_training():
    rx = load()["rxhandbd"]
    test = rx["official_test"]
    train = rx["train"]
    roles = {}
    for row in test:
        roles[row["role"]] = roles.get(row["role"], 0) + 1
    assert roles == {"historical_regression": 100, "untouched_official_test": 1015}
    train_roles = {}
    for row in train:
        train_roles[row["role"]] = train_roles.get(row["role"], 0) + 1
    assert train_roles == {"development": 3571, "internal_validation": 892}
    test_names = {row["image_name"] for row in test}
    train_names = {row["image_name"] for row in train}
    assert test_names.isdisjoint(train_names)
    assert len(test_names) == 1115 and len(train_names) == 4463
