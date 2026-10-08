"""待审素材分流体检：桶互斥穷尽、优先级正确、重叠窗口只认领后出现者。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from tools.triage_claims import (BUCKETS, applicability_empty, bucket_of,
                                 duplicate_ids, load_claims, speaker_unresolved,
                                 triage)


def _claim(cid, **fields):
    base = {"id": cid, "video": "BV1FcdZBNEm3", "ts": [10.0, 20.0],
            "claim": "观点", "type": "cue", "speaker": "凯圣王",
            "provenance": "transcript", "status": "draft",
            "anti_hallucination": "pass", "applies_to": {"level": ["beginner"],
                                                         "goal": [], "condition": []}}
    base.update(fields)
    return base


def test_real_pool_buckets_are_disjoint_and_exhaustive():
    claims = load_claims()
    report = triage(claims)
    counts = {name: report["buckets"][name]["count"] for name, _, _ in BUCKETS}
    assert sum(counts.values()) == len(claims) > 0
    assert report["total"] == len(claims)


def test_card_reference_outranks_quarantine_and_conflict():
    """同一条目既在卡片绑定又被登记问题时，以已签核的卡片归属为准。"""
    claim = _claim("ksw-x-1", anti_hallucination="FLAGGED")
    assert bucket_of(claim, {"ksw-x-1"}, {"ksw-x-1"}, {"ksw-x-1"}, set()) == "card_bound"


def test_quarantine_outranks_conflict_and_content_defects():
    claim = _claim("ksw-x-2", speaker="待确认", anti_hallucination="FLAGGED")
    assert bucket_of(claim, set(), {"ksw-x-2"}, {"ksw-x-2"}, set()) == "quarantined"


def test_speaker_pending_is_checked_before_applicability():
    """发言者未确认更靠前，避免把归因缺口记成适用性缺口。"""
    claim = _claim("ksw-x-3", speaker="待确认",
                   applies_to={"level": [], "goal": [], "condition": []})
    assert bucket_of(claim, set(), set(), set(), set()) == "speaker_unresolved"


def test_context_attribution_counts_as_unresolved_speaker():
    assert speaker_unresolved(_claim("ksw-x-4", speaker="凯圣王（语境归因）"))
    assert not speaker_unresolved(_claim("ksw-x-5", speaker="凯圣王"))
    assert applicability_empty(_claim("ksw-x-6", applies_to={
        "level": [], "goal": [], "condition": []}))


def test_duplicate_window_only_claims_later_entries():
    claims = [_claim("a", ts=[0.0, 30.0]), _claim("b", ts=[20.0, 40.0]),
              _claim("c", ts=[100.0, 120.0]),
              _claim("d", video="BVother", ts=[0.0, 10.0])]
    assert duplicate_ids(claims) == {"b"}
