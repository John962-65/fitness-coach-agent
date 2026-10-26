"""P5-B2：稳定器械目录与地点可用性。

动作 YAML 的 equipment 是稳定器械 ID；筛选和替代只比较 ID（及用户自定义
器械显式声明的等效系统 ID），绝不按中文名称猜器械。
"""
from __future__ import annotations

import uuid

CATEGORY_LABELS = {
    "free_weight": "自由重量",
    "bench_rack": "训练架/凳",
    "machine": "固定器械",
    "cardio": "有氧器械",
    "accessory": "辅助器械",
    "bodyweight": "自重",
    "other": "其他",
}

SYSTEM_EQUIPMENT = [
    {"id": "barbell", "name": "杠铃", "category": "free_weight",
     "aliases": ["奥杆", "杠铃杆"]},
    {"id": "dumbbell", "name": "哑铃", "category": "free_weight",
     "aliases": ["哑铃组"]},
    {"id": "bench", "name": "训练凳", "category": "bench_rack",
     "aliases": ["卧推凳", "健身凳"]},
    {"id": "rack", "name": "深蹲架", "category": "bench_rack",
     "aliases": ["杠铃架", "深蹲杆"]},
    {"id": "pullup_bar", "name": "单杠", "category": "bench_rack",
     "aliases": ["引体杆", "引体向上杆"]},
    {"id": "machine", "name": "固定器械", "category": "machine",
     "aliases": ["器械"]},
    {"id": "cable", "name": "龙门架/绳索", "category": "machine",
     "aliases": ["龙门架", "绳索"]},
    {"id": "band", "name": "弹力带", "category": "accessory",
     "aliases": ["阻力带"]},
    {"id": "wheel", "name": "健腹轮", "category": "accessory",
     "aliases": ["腹肌轮"]},
    {"id": "weight_belt", "name": "负重腰带", "category": "accessory",
     "aliases": ["配重带"]},
    {"id": "jump_rope", "name": "跳绳", "category": "cardio",
     "aliases": []},
    {"id": "treadmill", "name": "跑步机", "category": "cardio",
     "aliases": []},
    {"id": "elliptical_machine", "name": "椭圆机", "category": "cardio",
     "aliases": []},
    {"id": "stair_machine", "name": "爬楼机", "category": "cardio",
     "aliases": []},
    {"id": "stationary_bike", "name": "动感单车", "category": "cardio",
     "aliases": ["健身车"]},
    {"id": "bicycle", "name": "自行车", "category": "cardio",
     "aliases": ["户外自行车"]},
    {"id": "rowing_erg", "name": "划船机", "category": "cardio",
     "aliases": ["测功仪"]},
    {"id": "bodyweight", "name": "自重", "category": "bodyweight",
     "aliases": []},
]
_SYSTEM_BY_ID = {item["id"]: item for item in SYSTEM_EQUIPMENT}
SYSTEM_IDS = set(_SYSTEM_BY_ID)
# 支撑/安全配件：缺失时提示，但不单独判为"器械不可用"
OPTIONAL_EQUIPMENT_IDS = {"rack", "weight_belt"}
DEFAULT_LOCATIONS = [
    {"name": "健身房", "kind": "gym", "required_equipment": [],
     "optional_equipment": []},
    {"name": "居家", "kind": "home", "required_equipment": [],
     "optional_equipment": []},
    {"name": "户外", "kind": "outdoor", "required_equipment": [],
     "optional_equipment": []},
]
LOCATION_KINDS = ("gym", "home", "outdoor", "custom")


def system_equipment() -> list[dict]:
    return [{**item, "scope": "system"} for item in SYSTEM_EQUIPMENT]


def all_equipment(db, user_id: str) -> list[dict]:
    return system_equipment() + db.list_user_equipment(user_id)


def equipment_map(db, user_id: str) -> dict[str, dict]:
    return {item["id"]: item for item in all_equipment(db, user_id)}


def validate_equipment_ids(db, user_id: str, ids) -> list[str]:
    known = {item["id"] for item in all_equipment(db, user_id)}
    return [str(x) for x in (ids or []) if str(x) in known]


def normalize_location_equipment(db, user_id: str, required, optional) -> dict:
    required_ids = list(dict.fromkeys(validate_equipment_ids(db, user_id, required)))
    optional_ids = [x for x in dict.fromkeys(
        validate_equipment_ids(db, user_id, optional)) if x not in required_ids]
    return {"required_equipment": required_ids,
            "optional_equipment": optional_ids}


def create_custom_equipment(db, user_id: str, data: dict) -> dict:
    name = str(data.get("name") or "").strip()[:40]
    if not name:
        raise ValueError("器械名称必填")
    category = str(data.get("category") or "other")
    if category not in CATEGORY_LABELS:
        raise ValueError("器械分类无效")
    fulfills = str(data.get("fulfills") or "").strip() or None
    if fulfills and fulfills not in SYSTEM_IDS:
        raise ValueError("等效器械必须是系统器械")
    aliases = [str(x).strip()[:30] for x in (data.get("aliases") or [])
               if str(x).strip()][:8]
    equipment_id = f"custom_eq_{uuid.uuid4().hex[:10]}"
    return db.add_user_equipment(user_id, equipment_id, {
        "name": name, "category": category, "aliases": aliases,
        "fulfills": fulfills,
    })


def update_custom_equipment(db, user_id: str, equipment_id: str,
                            data: dict) -> dict:
    if not db.get_user_equipment(user_id, equipment_id):
        raise ValueError("自定义器械不存在")
    patch = {}
    if "name" in data:
        name = str(data.get("name") or "").strip()[:40]
        if not name:
            raise ValueError("器械名称必填")
        patch["name"] = name
    if "category" in data:
        category = str(data.get("category") or "other")
        if category not in CATEGORY_LABELS:
            raise ValueError("器械分类无效")
        patch["category"] = category
    if "aliases" in data:
        patch["aliases"] = [str(x).strip()[:30] for x in (data.get("aliases") or [])
                            if str(x).strip()][:8]
    if "fulfills" in data:
        fulfills = str(data.get("fulfills") or "").strip() or None
        if fulfills and fulfills not in SYSTEM_IDS:
            raise ValueError("等效器械必须是系统器械")
        patch["fulfills"] = fulfills
    return db.update_user_equipment(user_id, equipment_id, patch)


def seed_default_locations(db, user_id: str, current_kind: str = "gym") -> None:
    for item in DEFAULT_LOCATIONS:
        db.create_training_location(
            user_id, item, make_current=item["kind"] == current_kind)


def location_view(db, user_id: str, location: dict, catalog: dict | None = None) -> dict:
    catalog = catalog or equipment_map(db, user_id)
    required = [catalog[i] for i in location.get("required_equipment") or [] if i in catalog]
    optional = [catalog[i] for i in location.get("optional_equipment") or [] if i in catalog]
    return {**location, "required_equipment": required,
            "optional_equipment": optional,
            "required_equipment_ids": [x["id"] for x in required],
            "optional_equipment_ids": [x["id"] for x in optional]}


def location_available_ids(db, user_id: str, location: dict | None) -> set[str]:
    if not location:
        return set()
    configured = set(location.get("required_equipment") or []) \
        | set(location.get("optional_equipment") or [])
    catalog = equipment_map(db, user_id)
    available = {x for x in configured if x in SYSTEM_IDS or x in catalog}
    for eq_id in configured:
        doc = catalog.get(eq_id) or {}
        if doc.get("fulfills"):
            available.add(doc["fulfills"])
    available.add("bodyweight")
    return available


def exercise_availability(db, user_id: str, exercise_doc: dict,
                          location: dict | None,
                          catalog: dict | None = None,
                          available_ids: set[str] | None = None) -> dict:
    catalog = catalog or equipment_map(db, user_id)
    available = available_ids if available_ids is not None else \
        location_available_ids(db, user_id, location)
    required = [x for x in (exercise_doc.get("equipment") or [])
                if x not in OPTIONAL_EQUIPMENT_IDS and x != "bodyweight"]
    optional = [x for x in (exercise_doc.get("equipment") or [])
                if x in OPTIONAL_EQUIPMENT_IDS]
    missing = [eq_id for eq_id in required if eq_id not in available]
    missing_optional = [eq_id for eq_id in optional if eq_id not in available]
    kind = (location or {}).get("kind")
    location_ok = True
    if location and kind in ("gym", "home", "outdoor"):
        locations = exercise_doc.get("location") or []
        location_ok = not locations or kind in locations
    return {
        "available": bool(location) and not missing and location_ok,
        "missing_equipment_ids": missing,
        "missing_equipment": [catalog.get(x, {"name": x})["name"] for x in missing],
        "missing_optional_equipment_ids": missing_optional,
        "missing_optional_equipment": [
            catalog.get(x, {"name": x})["name"] for x in missing_optional],
        "location_ok": location_ok,
    }


def location_payload(db, user_id: str, location_id: int) -> dict:
    location = db.get_training_location(user_id, location_id)
    if not location:
        raise ValueError("训练地点不存在")
    catalog = equipment_map(db, user_id)
    return location_view(db, user_id, location, catalog)
