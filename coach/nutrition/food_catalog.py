"""内置食物目录：公开食物成分参考值（约值），供搜索与记录起步使用。

来源声明纪律（2.0 §3.1/§3.2）：
- 数值为公开食物成分资料中常见参考值的约数，标注 source_name/license/
  source_version，供用户核对；
- 不复制训记或任何商业食品数据库；
- 自定义食物按用户隔离（custom_exercises 同一模式），可录入营养标签。
"""
from __future__ import annotations

SOURCE = {
    "source_name": "公开食物成分参考值（常见条目约值）",
    "source_version": "2026-10",
    "license": "通用参考数据，仅供参考；以包装营养标签或专业数据库为准",
    "verified_status": "reference",
}

# (name, aliases, category, serving_units, kcal, protein, carb, fat, fiber, sodium)
# 营养值均按每 100g（液体 ml）可食部；None = 该项未收录
_G = "克"
_ROWS: list[tuple] = [
    # ---- 主食谷物 ----
    ("米饭（熟）", ["白米饭", "大米饭"], "staple", [(_G, 1), ("碗", 200)], 116, 2.6, 25.9, 0.3, 0.3, 2),
    ("糙米饭（熟）", ["糙米"], "staple", [(_G, 1), ("碗", 200)], 112, 2.6, 23.5, 0.9, 1.8, 5),
    ("米粥", ["白粥", "稀饭"], "staple", [(_G, 1), ("碗", 250)], 46, 1.1, 9.9, 0.3, 0.1, 2),
    ("馒头", [], "staple", [(_G, 1), ("个", 100)], 223, 7.0, 47.0, 1.1, 1.3, 165),
    ("面条（熟）", ["汤面", "煮面"], "staple", [(_G, 1), ("碗", 250)], 110, 3.9, 22.0, 0.4, 1.2, 120),
    ("荞麦面（熟）", ["冷面"], "staple", [(_G, 1), ("碗", 250)], 99, 4.8, 21.0, 0.7, 1.5, 60),
    ("全麦面包", ["全麦吐司"], "staple", [(_G, 1), ("片", 35)], 246, 9.0, 45.0, 3.4, 6.0, 400),
    ("白面包", ["吐司"], "staple", [(_G, 1), ("片", 30)], 265, 8.5, 50.0, 3.5, 2.7, 490),
    ("燕麦片（干）", ["麦片", "即食燕麦"], "staple", [(_G, 1), ("把", 40)], 367, 15.0, 61.0, 6.7, 10.0, 3),
    ("红薯（熟）", ["地瓜", "番薯"], "staple", [(_G, 1), ("个", 150)], 90, 2.0, 20.7, 0.2, 2.0, 36),
    ("土豆（熟）", ["马铃薯"], "staple", [(_G, 1), ("个", 130)], 87, 1.9, 20.1, 0.1, 1.8, 4),
    ("玉米（鲜）", ["甜玉米"], "staple", [(_G, 1), ("根", 200)], 112, 4.0, 22.8, 1.2, 2.9, 1),
    # ---- 肉禽 ----
    ("鸡胸肉", ["鸡胸"], "meat", [(_G, 1), ("块", 120)], 133, 24.6, 0.6, 1.9, 0, 45),
    ("鸡腿肉（去皮）", ["鸡腿"], "meat", [(_G, 1), ("个", 130)], 146, 20.9, 0, 6.7, 0, 80),
    ("牛肉（瘦）", ["瘦牛肉"], "meat", [(_G, 1), ("块", 120)], 143, 21.3, 1.2, 5.2, 0, 60),
    ("牛腩", [], "meat", [(_G, 1)], 332, 17.1, 0, 28.8, 0, 60),
    ("猪里脊", ["里脊", "瘦肉"], "meat", [(_G, 1), ("块", 120)], 155, 20.2, 0.7, 7.9, 0, 43),
    ("五花肉", ["猪肉（肥瘦）"], "meat", [(_G, 1)], 568, 7.7, 0, 59.0, 0, 36),
    ("羊肉（瘦）", ["瘦羊肉"], "meat", [(_G, 1)], 118, 20.5, 0.2, 3.9, 0, 69),
    ("火腿肠", [], "processed", [(_G, 1), ("根", 60)], 212, 14.0, 15.6, 10.4, 0, 1030),
    ("培根", [], "processed", [(_G, 1), ("片", 15)], 541, 37.0, 1.4, 42.0, 0, 1717),
    # ---- 水产 ----
    ("三文鱼", ["鲑鱼"], "seafood", [(_G, 1), ("块", 150)], 139, 17.2, 0, 7.8, 0, 59),
    ("虾", ["基围虾", "明虾"], "seafood", [(_G, 1), ("只", 15)], 101, 18.2, 3.9, 1.4, 0, 172),
    ("鳕鱼", [], "seafood", [(_G, 1), ("块", 150)], 88, 20.4, 0.5, 0.5, 0, 130),
    ("带鱼", [], "seafood", [(_G, 1)], 127, 17.7, 3.1, 4.9, 0, 150),
    ("金枪鱼（水浸罐头）", ["吞拿鱼"], "seafood", [(_G, 1), ("罐", 100)], 116, 25.5, 0, 0.8, 0, 247),
    # ---- 蛋与奶 ----
    ("鸡蛋", ["土鸡蛋"], "egg_dairy", [(_G, 1), ("个", 50)], 144, 13.3, 2.8, 8.8, 0, 131),
    ("鸡蛋白", ["蛋清"], "egg_dairy", [(_G, 1), ("个", 35)], 60, 11.6, 3.1, 0.1, 0, 79),
    ("牛奶（全脂）", ["全脂牛奶"], "egg_dairy", [("毫升", 1), ("盒", 250)], 65, 3.3, 5.0, 3.6, 0, 37),
    ("牛奶（脱脂）", ["脱脂牛奶"], "egg_dairy", [("毫升", 1), ("盒", 250)], 34, 3.4, 5.0, 0.1, 0, 37),
    ("酸奶（原味）", ["酸奶"], "egg_dairy", [(_G, 1), ("杯", 150)], 72, 2.8, 9.3, 2.7, 0, 39),
    ("奶酪", ["芝士", "切达奶酪"], "egg_dairy", [(_G, 1), ("片", 20)], 328, 24.9, 1.3, 26.0, 0, 621),
    # ---- 豆制品 ----
    ("豆腐（北）", ["老豆腐"], "soy", [(_G, 1), ("块", 150)], 116, 12.2, 3.0, 6.6, 0.8, 7),
    ("内酯豆腐", ["嫩豆腐"], "soy", [(_G, 1), ("盒", 300)], 50, 5.0, 2.9, 2.5, 0.4, 6),
    ("豆浆（无糖）", ["豆奶"], "soy", [("毫升", 1), ("杯", 300)], 31, 3.0, 1.2, 1.6, 0.7, 3),
    ("黄豆（干）", ["大豆"], "soy", [(_G, 1), ("把", 30)], 390, 35.0, 34.0, 16.0, 15.5, 2),
    ("腐竹", ["豆腐皮"], "soy", [(_G, 1)], 459, 44.6, 22.3, 21.7, 1.0, 26),
    # ---- 蔬菜 ----
    ("西兰花", ["绿花椰菜"], "vegetable", [(_G, 1)], 36, 4.1, 4.3, 0.6, 1.6, 18),
    ("菠菜", [], "vegetable", [(_G, 1), ("把", 80)], 28, 2.6, 4.5, 0.3, 1.7, 85),
    ("生菜", ["莴苣叶"], "vegetable", [(_G, 1), ("棵", 100)], 16, 1.3, 2.0, 0.3, 0.7, 32),
    ("番茄", ["西红柿"], "vegetable", [(_G, 1), ("个", 150)], 20, 0.9, 4.0, 0.2, 0.5, 5),
    ("黄瓜", [], "vegetable", [(_G, 1), ("根", 150)], 16, 0.8, 2.9, 0.2, 0.5, 5),
    ("胡萝卜", [], "vegetable", [(_G, 1), ("根", 120)], 39, 1.0, 8.8, 0.2, 2.8, 71),
    ("大白菜", ["白菜"], "vegetable", [(_G, 1)], 20, 1.6, 3.4, 0.2, 0.9, 68),
    ("蘑菇（鲜）", ["香菇", "口蘑"], "vegetable", [(_G, 1)], 24, 2.7, 4.1, 0.1, 2.1, 8),
    ("芦笋", [], "vegetable", [(_G, 1), ("把", 100)], 22, 2.6, 3.3, 0.1, 1.9, 2),
    ("青椒", ["甜椒", "彩椒"], "vegetable", [(_G, 1), ("个", 100)], 22, 1.4, 5.4, 0.3, 1.4, 3),
    # ---- 水果 ----
    ("苹果", [], "fruit", [(_G, 1), ("个", 200)], 53, 0.4, 13.7, 0.2, 1.7, 1),
    ("香蕉", [], "fruit", [(_G, 1), ("根", 120)], 93, 1.4, 22.0, 0.2, 2.6, 1),
    ("橙子", ["甜橙"], "fruit", [(_G, 1), ("个", 180)], 48, 0.8, 11.1, 0.2, 0.6, 1),
    ("葡萄", [], "fruit", [(_G, 1), ("串", 300)], 45, 0.4, 10.3, 0.3, 0.4, 1),
    ("西瓜", [], "fruit", [(_G, 1), ("块", 300)], 31, 0.5, 6.8, 0.3, 0.3, 2),
    ("蓝莓", [], "fruit", [(_G, 1), ("盒", 125)], 57, 0.7, 14.5, 0.3, 2.4, 1),
    ("草莓", [], "fruit", [(_G, 1), ("盒", 250)], 32, 1.0, 7.1, 0.2, 1.1, 4),
    ("猕猴桃", ["奇异果"], "fruit", [(_G, 1), ("个", 100)], 61, 0.8, 14.5, 0.6, 2.6, 10),
    # ---- 坚果 ----
    ("杏仁", ["巴旦木"], "nuts", [(_G, 1), ("把", 15)], 579, 21.2, 21.6, 49.9, 12.5, 1),
    ("核桃", ["胡桃"], "nuts", [(_G, 1), ("个", 8)], 646, 14.9, 19.1, 58.8, 9.5, 2),
    ("花生", [], "nuts", [(_G, 1), ("把", 20)], 567, 25.8, 16.1, 49.2, 8.5, 5),
    ("腰果", [], "nuts", [(_G, 1), ("把", 15)], 559, 17.3, 41.6, 36.7, 3.6, 16),
    # ---- 油脂与调味 ----
    ("食用油", ["炒菜油", "植物油"], "oil", [(_G, 1), ("勺", 10)], 884, 0, 0, 100.0, 0, 0),
    ("橄榄油", [], "oil", [(_G, 1), ("勺", 10)], 884, 0, 0, 100.0, 0, 2),
    ("芝麻酱", [], "oil", [(_G, 1), ("勺", 15)], 630, 19.0, 21.5, 52.7, 5.9, 386),
    ("酱油", ["生抽"], "oil", [("毫升", 1), ("勺", 15)], 63, 5.6, 10.1, 0.1, 0.8, 5757),
    ("蛋黄酱", ["沙拉酱"], "oil", [(_G, 1), ("勺", 15)], 680, 1.0, 2.0, 74.0, 0, 635),
    # ---- 加工与即食 ----
    ("方便面（面饼）", ["泡面"], "processed", [(_G, 1), ("包", 85)], 472, 9.5, 61.0, 21.1, 2.0, 1144),
    ("饺子（猪肉白菜）", ["水饺"], "processed", [(_G, 1), ("个", 25)], 190, 8.0, 24.0, 7.0, 1.2, 480),
    ("包子（猪肉）", ["肉包"], "processed", [(_G, 1), ("个", 80)], 227, 8.1, 31.0, 8.9, 1.0, 486),
    # ---- 饮品与补剂 ----
    ("拿铁（全脂）", ["咖啡拿铁"], "beverage", [("毫升", 1), ("杯", 350)], 43, 2.3, 4.0, 2.0, 0, 30),
    ("橙汁", ["鲜榨橙汁"], "beverage", [("毫升", 1), ("杯", 250)], 45, 0.7, 10.4, 0.2, 0.2, 1),
    ("可乐", ["汽水"], "beverage", [("毫升", 1), ("罐", 330)], 43, 0, 10.6, 0, 0, 4),
    ("运动饮料", [], "beverage", [("毫升", 1), ("瓶", 500)], 26, 0, 6.5, 0, 0, 46),
    ("乳清蛋白粉", ["蛋白粉"], "beverage", [(_G, 1), ("勺", 30)], 400, 80.0, 8.0, 6.0, 1.0, 300),
]

CATEGORIES: dict[str, str] = {
    "staple": "主食谷物", "meat": "肉禽", "seafood": "水产",
    "egg_dairy": "蛋奶", "soy": "豆制品", "vegetable": "蔬菜",
    "fruit": "水果", "nuts": "坚果", "oil": "油脂调味",
    "processed": "加工即食", "beverage": "饮品补剂", "other": "其他",
}


def _slug(name: str) -> str:
    import re
    keep = re.sub(r"[^\u4e00-\u9fff a-z0-9]+", "", name.lower()).strip()
    import hashlib
    return "bi-" + hashlib.md5(keep.encode()).hexdigest()[:12]


def builtin_foods() -> list[dict]:
    out = []
    for (name, aliases, cat, units, kcal, pro, carb, fat, fib, na) in _ROWS:
        out.append({
            "id": _slug(name), "user_id": None, "name": name,
            "aliases": aliases, "brand": None, "category": cat,
            "serving_units": [{"unit": u, "grams": g} for u, g in units],
            "energy_kcal": kcal, "protein_g": pro, "carbohydrate_g": carb,
            "fat_g": fat, "fiber_g": fib, "sodium_mg": na,
            "reference_amount": 100, "reference_unit": "毫升" if any(
                u == "毫升" for u, _ in units) else "g",
            **SOURCE,
        })
    return out


def ensure_builtin_foods(db) -> int:
    """装载/更新内置目录（按 id upsert；幂等）。返回条数。"""
    foods = builtin_foods()
    with db.conn:
        for food in foods:
            db.upsert_food(food)
    return len(foods)


def validate_custom_food(payload: dict) -> dict:
    """自定义食物录入校验（营养标签按 reference_amount 口径）。"""
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 40:
        raise ValueError("食物名称必填（≤40 字）")
    category = payload.get("category") or "other"
    if category not in CATEGORIES:
        raise ValueError(f"category 必须是 {list(CATEGORIES)} 之一")
    units = payload.get("serving_units")
    if not isinstance(units, list) or not units:
        units = [{"unit": "克", "grams": 1}]
    clean_units = []
    for u in units[:8]:
        if not isinstance(u, dict):
            continue
        unit, grams = str(u.get("unit") or "").strip(), u.get("grams")
        if unit and isinstance(grams, (int, float)) and not isinstance(grams, bool) \
                and 0 < grams <= 5000:
            clean_units.append({"unit": unit[:8], "grams": float(grams)})
    if not clean_units:
        raise ValueError("serving_units 需要至少一个 {unit, grams}（0<grams≤5000）")
    ref_amount = payload.get("reference_amount", 100)
    if not isinstance(ref_amount, (int, float)) or isinstance(ref_amount, bool) \
            or not 0 < ref_amount <= 1000:
        raise ValueError("reference_amount 必须是 0-1000 的数值")
    ref_unit = payload.get("reference_unit") or "g"
    if ref_unit not in ("g", "毫升"):
        raise ValueError("reference_unit 必须是 g 或 毫升")
    out = {
        "name": name,
        "aliases": [str(a)[:20] for a in (payload.get("aliases") or [])][:6],
        "brand": str(payload.get("brand") or "")[:30] or None,
        "category": category,
        "serving_units": clean_units,
        "reference_amount": float(ref_amount),
        "reference_unit": ref_unit,
    }
    for key in ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g",
                "fiber_g", "sodium_mg"):
        v = payload.get(key)
        if v is not None:
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                raise ValueError(f"{key} 必须是非负数值或留空（未知保留空）")
            out[key] = float(v)
        else:
            out[key] = None  # 未知就是未知，不用 0 冒充
    return out
