"""P5-B2：确定性的动作替代候选与安全校验。

候选只按稳定动作 ID、器械 ID、动作模式、肌群、水平和 P3 限制计算；
名称仅用于给用户展示，不参与器械/安全判断。候选表示"可考虑的相近选择"，
不表示与原动作等价。
"""
from __future__ import annotations

from . import equipment as equipment_service
from . import exercise_service
from .rehab import restriction_service, safety_integration

REP_MEASUREMENTS = {"weight_reps", "bodyweight_reps", "assisted_reps"}
LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}
GOAL_PATTERNS = {
    "strength": {"squat", "hinge", "h_push", "v_push", "h_pull", "v_pull"},
    "muscle_gain": {"squat", "hinge", "h_push", "v_push", "h_pull", "v_pull"},
    "fat_loss": {"squat", "hinge", "lunge", "h_push", "h_pull", "cardio"},
    "health": {"squat", "hinge", "lunge", "h_push", "h_pull", "core", "cardio"},
    "shaping": {"isolation", "lunge", "core"},
}


class SubstitutionError(ValueError):
    pass


class SafetyGateError(SubstitutionError):
    pass


def _measurement_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    return a in REP_MEASUREMENTS and b in REP_MEASUREMENTS


def _semantically_related(source: dict, target: dict) -> bool:
    """最低训练目标相关性：同动作模式或主要目标肌群重叠。

    器械/测量兼容不能单独让一个无关动作成为替代候选。
    """
    if source.get("pattern") and source.get("pattern") == target.get("pattern"):
        return True
    if set(source.get("primary") or []) & set(target.get("primary") or []):
        return True
    return target.get("id") in (source.get("substitutes") or [])


def _measurement_label(t: str) -> str:
    return {
        "weight_reps": "重量×次数",
        "bodyweight_reps": "自重次数",
        "assisted_reps": "辅助次数",
        "duration": "时长",
        "distance_time": "距离+时间",
    }.get(t, t)


def _user_level(profile: dict) -> str:
    level = str((profile.get("experience") or {}).get("level") or "beginner")
    return level if level in LEVEL_ORDER else "beginner"


def _safety_view_or_raise(db, user_id: str):
    view = safety_integration.safety_view(db, user_id)
    if view.prescription_blocked:
        reasons = view.summary_lines() or ["当前安全状态不允许训练处方"]
        raise SafetyGateError("；".join(reasons))
    return view


def _difference_notes(source: dict, target: dict, catalog: dict,
                      user_level: str) -> list[str]:
    notes = []
    if source.get("pattern") == target.get("pattern"):
        notes.append(f"同为「{target.get('pattern')}」动作模式")
    else:
        notes.append(f"动作模式由 {source.get('pattern')} 变为 {target.get('pattern')}")
    overlap = sorted(set(source.get("primary") or []) & set(target.get("primary") or []))
    if overlap:
        notes.append(f"主要目标肌群重叠：{'、'.join(overlap)}")
    else:
        notes.append("主要目标肌群不完全相同")
    source_t = source.get("measurement") or "weight_reps"
    target_t = target.get("measurement") or "weight_reps"
    if source_t != target_t:
        notes.append(f"记录口径由{_measurement_label(source_t)}变为"
                     f"{_measurement_label(target_t)}，历史负荷不可直接比较")
    target_equipment = [catalog.get(x, {"name": x})["name"]
                        for x in (target.get("equipment") or [])]
    notes.append("所需器械：" + ("、".join(target_equipment) or "自重"))
    if target.get("level_min") != user_level:
        notes.append(f"最低训练水平：{target.get('level_min')}（你的水平：{user_level}）")
    return notes


def _candidate_score(source: dict, target: dict, goal: str,
                     frequent_ids: set[str]) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    if target.get("pattern") == source.get("pattern"):
        score += 8
        reasons.append("动作模式一致")
    primary_overlap = set(source.get("primary") or []) & set(target.get("primary") or [])
    secondary_overlap = set(source.get("secondary") or []) & set(target.get("secondary") or [])
    score += 5 * len(primary_overlap) + 2 * len(secondary_overlap)
    if primary_overlap:
        reasons.append("主要肌群一致")
    if target.get("id") in (source.get("substitutes") or []):
        score += 6
        reasons.append("动作库已有替代关联")
    source_t = source.get("measurement") or "weight_reps"
    target_t = target.get("measurement") or "weight_reps"
    if source_t == target_t:
        score += 3
    elif _measurement_compatible(source_t, target_t):
        score += 1
    if target.get("pattern") in GOAL_PATTERNS.get(goal, set()):
        score += 2
        reasons.append("符合当前主要训练目标")
    if target.get("id") in frequent_ids:
        score += 1
        reasons.append("你以前练过")
    return score, reasons


def _validate_target(db, user_id: str, profile: dict, source: dict, target: dict,
                     location: dict, catalog: dict, available_ids: set[str],
                     user_level: str) -> dict:
    if target.get("status") != "approved":
        raise SubstitutionError("候选动作尚未审核，不能作为替代处方")
    if not _semantically_related(source, target):
        raise SubstitutionError("候选动作与原动作缺少共同动作模式或主要目标肌群")
    if LEVEL_ORDER.get(target.get("level_min") or "beginner", 0) > LEVEL_ORDER[user_level]:
        raise SubstitutionError("候选动作的最低训练水平高于你的当前水平")
    availability = equipment_service.exercise_availability(
        db, user_id, target, location, catalog, available_ids)
    if not availability["available"]:
        if not availability["location_ok"]:
            raise SubstitutionError("候选动作不适用于当前训练地点类型")
        missing = "、".join(availability["missing_equipment"]) or "必要器械"
        raise SubstitutionError(f"当前地点缺少：{missing}")
    if not _measurement_compatible(source.get("measurement") or "weight_reps",
                                   target.get("measurement") or "weight_reps"):
        raise SubstitutionError("候选动作的记录口径与原动作不兼容")
    hit = restriction_service.restriction_blocks(db, user_id, target)
    if hit:
        raise SubstitutionError(
            f"候选动作与当前训练限制冲突：{hit['reason']}；"
            f"限制依据：{hit['restriction']['restriction_description']}")
    return availability


def find_candidates(db, user_id: str, source_id: str,
                    location_id: int | None = None, limit: int = 8) -> dict:
    profile = db.get_existing_profile(user_id) or {}
    if not profile:
        raise SubstitutionError("用户不存在或尚未建档")
    _safety_view_or_raise(db, user_id)
    source = exercise_service.get_exercise(db, user_id, source_id)
    if not source:
        raise SubstitutionError("原动作不在动作库内")
    location = db.get_training_location(user_id, location_id) if location_id else \
        next((x for x in db.list_training_locations(user_id) if x["is_current"]), None)
    if not location:
        raise SubstitutionError("请先选择当前训练地点")
    catalog = equipment_service.equipment_map(db, user_id)
    available_ids = equipment_service.location_available_ids(db, user_id, location)
    user_level = _user_level(profile)
    goal = str((profile.get("goal") or {}).get("primary") or "")
    frequent_ids = {x["exercise_id"] for x in db.all_exercise_states(user_id)}

    excluded = {"safety": 0, "equipment_or_location": 0,
                "measurement_or_level": 0, "unapproved": 0, "unrelated": 0}
    scored = []
    for target in exercise_service.list_exercises(db, user_id):
        if target.get("id") == source_id:
            continue
        if target.get("status") != "approved":
            excluded["unapproved"] += 1
            continue
        if not _semantically_related(source, target):
            excluded["unrelated"] += 1
            continue
        if (not _measurement_compatible(source.get("measurement") or "weight_reps",
                                        target.get("measurement") or "weight_reps")
                or LEVEL_ORDER.get(target.get("level_min") or "beginner", 0)
                > LEVEL_ORDER[user_level]):
            excluded["measurement_or_level"] += 1
            continue
        availability = equipment_service.exercise_availability(
            db, user_id, target, location, catalog, available_ids)
        if not availability["available"]:
            excluded["equipment_or_location"] += 1
            continue
        hit = restriction_service.restriction_blocks(db, user_id, target)
        if hit:
            excluded["safety"] += 1
            continue
        score, reasons = _candidate_score(source, target, goal, frequent_ids)
        scored.append((score, target, reasons))
    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    candidates = []
    for score, target, reasons in scored[:limit]:
        target_t = target.get("measurement") or "weight_reps"
        source_t = source.get("measurement") or "weight_reps"
        candidates.append({
            "id": target["id"], "name": target["name"],
            "pattern": target.get("pattern"),
            "primary": target.get("primary") or [],
            "secondary": target.get("secondary") or [],
            "equipment": target.get("equipment") or [],
            "equipment_names": [catalog.get(x, {"name": x})["name"]
                                for x in (target.get("equipment") or [])],
            "measurement": target_t,
            "measurement_compatible": source_t == target_t,
            "level_min": target.get("level_min") or "beginner",
            "score": score, "reasons": reasons,
            "differences": _difference_notes(source, target, catalog, user_level),
        })
    return {
        "source": {"id": source["id"], "name": source["name"],
                   "pattern": source.get("pattern"),
                   "measurement": source.get("measurement") or "weight_reps"},
        "location": {"id": location["id"], "name": location["name"],
                     "kind": location["kind"]},
        "candidates": candidates,
        "excluded": excluded,
        "goal": goal,
        "disclaimer": "候选只表示训练模式或目标肌群相近，不代表动作等价；"
                      "请结合自身感受与安全限制选择。",
    }


def validate_substitution(db, user_id: str, source_id: str, target_id: str,
                          location_id: int | None = None) -> dict:
    profile = db.get_existing_profile(user_id) or {}
    if not profile:
        raise SubstitutionError("用户不存在或尚未建档")
    _safety_view_or_raise(db, user_id)
    source = exercise_service.get_exercise(db, user_id, source_id)
    target = exercise_service.get_exercise(db, user_id, target_id)
    if not source or not target:
        raise SubstitutionError("原动作或候选动作不在动作库内")
    if source_id == target_id:
        raise SubstitutionError("候选动作不能与原动作相同")
    location = db.get_training_location(user_id, location_id) if location_id else \
        next((x for x in db.list_training_locations(user_id) if x["is_current"]), None)
    if not location:
        raise SubstitutionError("请先选择当前训练地点")
    catalog = equipment_service.equipment_map(db, user_id)
    availability = _validate_target(
        db, user_id, profile, source, target, location, catalog,
        equipment_service.location_available_ids(db, user_id, location),
        _user_level(profile))
    return {
        "source": {"id": source["id"], "name": source["name"]},
        "target": {"id": target["id"], "name": target["name"],
                   "measurement": target.get("measurement") or "weight_reps"},
        "location": {"id": location["id"], "name": location["name"]},
        "differences": _difference_notes(source, target, catalog, _user_level(profile)),
        "availability": availability,
        "safety_checked": True,
    }


def validate_session_replacement_safety(db, user_id: str, target_id: str,
                                        set_logs=None) -> None:
    """保存训练时复核临时替换动作的安全与记录口径。"""
    profile = db.get_existing_profile(user_id) or {}
    if not profile:
        raise SafetyGateError("用户不存在或尚未建档")
    _safety_view_or_raise(db, user_id)
    target = exercise_service.get_exercise(db, user_id, target_id)
    if not target:
        raise SafetyGateError("临时替换动作不在动作库内")
    hit = restriction_service.restriction_blocks(db, user_id, target)
    if hit:
        raise SafetyGateError(
            f"替换动作「{target.get('name')}」与当前训练限制冲突：{hit['reason']}")
    expected = target.get("measurement") or "weight_reps"
    for log in set_logs or []:
        if not isinstance(log, dict) or log.get("warmup"):
            continue
        actual = log.get("type") or "weight_reps"
        if actual != expected:
            raise SafetyGateError(
                f"替换动作「{target.get('name')}」应使用 {expected} 记录口径，"
                f"不能用 {actual} 落库")
