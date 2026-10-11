"""R6a：动作库扩充到 ~60 个（含居家），一次生成全部新 YAML

新动作 status: draft（结构化字段待发起人审核，21.2 ③b）；
_provenance 标明各字段来源：video=博主 / llm=通用知识推断 / pending=待发起人判断。
"""
import yaml
from pathlib import Path

ROOT = Path("./exercises")

# id, name, aliases, pattern, primary, secondary, equipment, location,
# level_min, skill, fatigue, stress(knee,lumbar,shoulder,wrist), track, substitutes, prog
E = [
    # ---- 健身房补充：胸 ----
    ("machine_chest_press", "器械推胸", ["坐姿推胸", "推胸器"], "h_push",
     ["chest"], ["triceps", "front_delt"], ["machine"], ["gym"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["barbell_bench_press", "dumbbell_bench_press"], "load"),
    ("cable_fly", "绳索夹胸", ["龙门架夹胸", "绳索飞鸟"], "isolation",
     ["chest"], ["front_delt"], ["cable"], ["gym"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["pec_deck", "dumbbell_fly"], "load"),
    ("pec_deck", "蝴蝶机夹胸", ["夹胸器", "蝶机夹胸"], "isolation",
     ["chest"], ["front_delt"], ["machine"], ["gym"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["cable_fly"], "load"),
    ("dips", "双杠臂屈伸", ["臂屈伸", "杠上臂屈伸"], "h_push",
     ["chest", "triceps"], ["front_delt"], ["bodyweight"], ["gym"],
     "intermediate", "medium", "medium", (0, 0, 2, 0), False,
     ["machine_chest_press", "close_grip_bench_press"], "reps"),
    ("close_grip_bench_press", "窄距卧推", ["窄握卧推"], "h_push",
     ["triceps"], ["chest", "front_delt"], ["barbell", "bench"], ["gym"],
     "intermediate", "medium", "medium", (0, 0, 1, 1), True,
     ["cable_pushdown", "skull_crusher"], "load"),
    # ---- 肩 ----
    ("machine_shoulder_press", "器械推肩", ["坐姿推肩"], "v_push",
     ["front_delt", "side_delt"], ["triceps"], ["machine"], ["gym"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["dumbbell_shoulder_press", "overhead_press"], "load"),
    ("cable_lateral_raise", "绳索侧平举", ["龙门架侧平举"], "isolation",
     ["side_delt"], [], ["cable"], ["gym"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["lateral_raise"], "load"),
    ("rear_delt_fly", "哑铃俯身飞鸟", ["反飞鸟", "俯身飞鸟", "哑铃反飞鸟"], "isolation",
     ["rear_delt"], ["mid_back"], ["dumbbell"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["face_pull", "band_pull_apart"], "load"),
    # ---- 背 ----
    ("cable_row", "坐姿绳索划船", ["绳索划船", "龙门架划船"], "h_pull",
     ["lats", "mid_back"], ["biceps"], ["cable"], ["gym"],
     "beginner", "low", "low", (0, 1, 0, 0), True,
     ["seated_row", "dumbbell_row"], "load"),
    ("chest_supported_row", "斜板支撑划船", ["俯身支撑划船", "上斜板划船"], "h_pull",
     ["lats", "mid_back"], ["biceps"], ["dumbbell", "bench"], ["gym"],
     "beginner", "low", "medium", (0, 0, 0, 0), True,
     ["dumbbell_row", "seated_row"], "load"),
    ("t_bar_row", "T杠划船", ["T字划船"], "h_pull",
     ["lats", "mid_back"], ["biceps", "erectors"], ["barbell"], ["gym"],
     "intermediate", "medium", "medium", (0, 2, 0, 1), True,
     ["barbell_row", "chest_supported_row"], "load"),
    ("chin_up", "反手引体向上", ["反握引体"], "v_pull",
     ["lats", "biceps"], ["mid_back"], ["bodyweight"], ["gym", "home"],
     "intermediate", "high", "medium", (0, 0, 1, 0), True,
     ["pull_up", "lat_pulldown"], "reps"),
    # ---- 手臂 ----
    ("cable_pushdown", "绳索下压", ["三头下压", "屈臂下压"], "isolation",
     ["triceps"], [], ["cable"], ["gym"],
     "beginner", "low", "low", (0, 0, 0, 1), False,
     ["skull_crusher", "close_grip_bench_press"], "load"),
    ("skull_crusher", "仰卧臂屈伸", ["碎颅式", "仰卧三头屈伸"], "isolation",
     ["triceps"], [], ["dumbbell", "bench"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 0, 2), False,
     ["cable_pushdown"], "load"),
    ("hammer_curl", "锤式弯举", ["锤式二头弯举"], "isolation",
     ["biceps"], ["forearms"], ["dumbbell"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 0, 0), False,
     ["barbell_curl"], "load"),
    # ---- 腿/臀 ----
    ("hack_squat", "哈克深蹲", ["倒蹲机"], "squat",
     ["quads", "glutes"], ["adductors"], ["machine"], ["gym"],
     "beginner", "medium", "medium", (2, 0, 0, 0), True,
     ["leg_press", "barbell_back_squat"], "load"),
    ("front_squat", "颈前深蹲", ["前蹲"], "squat",
     ["quads"], ["glutes", "core"], ["barbell", "rack"], ["gym"],
     "intermediate", "high", "high", (3, 1, 1, 1), True,
     ["barbell_back_squat", "hack_squat"], "load"),
    ("walking_lunge", "行走箭步蹲", ["箭步走", "行走弓步"], "lunge",
     ["quads", "glutes"], ["hamstrings"], ["dumbbell"], ["gym", "home"],
     "beginner", "medium", "medium", (2, 0, 0, 0), False,
     ["split_squat", "bulgarian_split_squat"], "load"),
    ("step_up", "箱上登阶", ["登台阶", "箱式登阶"], "lunge",
     ["quads", "glutes"], [], ["dumbbell", "bench"], ["gym", "home"],
     "beginner", "low", "low", (1, 0, 0, 0), False,
     ["split_squat", "walking_lunge"], "load"),
    ("leg_extension", "坐姿腿屈伸", ["腿屈伸"], "isolation",
     ["quads"], [], ["machine"], ["gym"],
     "beginner", "low", "low", (1, 0, 0, 0), False,
     ["leg_press"], "load"),
    ("seated_calf_raise", "坐姿提踵", ["坐姿小腿提踵"], "isolation",
     ["calves"], [], ["machine"], ["gym"],
     "beginner", "low", "low", (0, 0, 0, 0), False,
     ["standing_calf_raise"], "load"),
    ("hip_thrust", "臀推", ["杠铃臀桥", "臀冲"], "hinge",
     ["glutes"], ["hamstrings"], ["barbell", "bench"], ["gym"],
     "beginner", "medium", "medium", (0, 0, 0, 0), True,
     ["glute_bridge", "romanian_deadlift"], "load"),
    ("good_morning", "早安式体前屈", ["早安式"], "hinge",
     ["hamstrings", "erectors"], ["glutes"], ["barbell"], ["gym"],
     "intermediate", "medium", "medium", (0, 3, 0, 0), True,
     ["romanian_deadlift", "back_extension"], "load"),
    ("back_extension", "山羊挺身", ["背伸展", "罗马椅背伸"], "hinge",
     ["erectors"], ["glutes", "hamstrings"], ["bodyweight"], ["gym"],
     "beginner", "low", "low", (0, 1, 0, 0), False,
     ["good_morning"], "reps"),
    # ---- 核心 / 负重行走 ----
    ("hanging_leg_raise", "悬垂举腿", ["吊环举腿", "引体架举腿"], "core",
     ["core"], ["hip_flexors"], ["bodyweight"], ["gym", "home"],
     "intermediate", "medium", "medium", (0, 0, 1, 0), False,
     ["cable_crunch", "plank"], "reps"),
    ("cable_crunch", "绳索卷腹", ["跪姿卷腹"], "core",
     ["core"], [], ["cable"], ["gym"],
     "beginner", "low", "low", (0, 1, 0, 0), False,
     ["plank"], "load"),
    ("plank", "平板支撑", ["撑体"], "core",
     ["core"], ["front_delt"], ["bodyweight"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 0, 0), False,
     [], "reps"),
    ("farmer_carry", "农夫行走", ["农夫走"], "carry",
     ["traps", "core"], ["forearms"], ["dumbbell"], ["gym", "home"],
     "beginner", "low", "medium", (0, 1, 0, 0), False,
     [], "load"),
    ("ab_wheel", "腹肌轮", ["健腹轮"], "core",
     ["core"], ["front_delt"], ["wheel"], ["gym", "home"],
     "intermediate", "medium", "medium", (0, 2, 1, 0), False,
     ["plank", "cable_crunch"], "reps"),
    # ---- 居家（自重 / 弹力带 / 哑铃） ----
    ("push_up", "俯卧撑", ["标准俯卧撑"], "h_push",
     ["chest"], ["triceps", "front_delt"], ["bodyweight"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["knee_push_up", "dumbbell_bench_press"], "reps"),
    ("knee_push_up", "跪姿俯卧撑", ["跪式俯卧撑"], "h_push",
     ["chest"], ["triceps"], ["bodyweight"], ["home"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["push_up"], "reps"),
    ("incline_push_up", "上斜俯卧撑", ["高位俯卧撑"], "h_push",
     ["chest"], ["triceps"], ["bodyweight"], ["home"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["push_up", "knee_push_up"], "reps"),
    ("pike_push_up", "倒V俯卧撑", ["派克俯卧撑", "折刀俯卧撑"], "v_push",
     ["front_delt", "side_delt"], ["triceps"], ["bodyweight"], ["home"],
     "intermediate", "high", "medium", (0, 0, 2, 0), False,
     ["dumbbell_shoulder_press"], "reps"),
    ("bodyweight_squat", "徒手深蹲", ["自重深蹲", "空蹲"], "squat",
     ["quads", "glutes"], ["adductors"], ["bodyweight"], ["gym", "home"],
     "beginner", "low", "low", (1, 0, 0, 0), False,
     ["goblet_squat", "barbell_back_squat"], "reps"),
    ("split_squat", "分腿蹲", ["静态弓步蹲", "剪蹲"], "lunge",
     ["quads", "glutes"], ["adductors"], ["bodyweight"], ["gym", "home"],
     "beginner", "low", "low", (1, 0, 0, 0), False,
     ["walking_lunge", "bulgarian_split_squat"], "reps"),
    ("glute_bridge", "臀桥", ["徒手臀桥"], "hinge",
     ["glutes"], ["hamstrings"], ["bodyweight"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 0, 0), False,
     ["hip_thrust"], "reps"),
    ("dumbbell_rdl", "哑铃罗马尼亚硬拉", ["哑铃RDL", "哑铃直腿硬拉"], "hinge",
     ["hamstrings", "glutes"], ["erectors"], ["dumbbell"], ["gym", "home"],
     "beginner", "medium", "medium", (0, 2, 0, 0), True,
     ["romanian_deadlift", "glute_bridge"], "load"),
    ("dumbbell_row", "哑铃划船", ["单臂哑铃划船"], "h_pull",
     ["lats", "mid_back"], ["biceps"], ["dumbbell"], ["gym", "home"],
     "beginner", "low", "low", (0, 1, 0, 0), True,
     ["barbell_row", "chest_supported_row"], "load"),
    ("band_pull_apart", "弹力带扩胸", ["弹力带后束展开", "带式面拉"], "isolation",
     ["rear_delt"], ["mid_back"], ["band"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["face_pull", "rear_delt_fly"], "reps"),
    ("dumbbell_fly", "哑铃飞鸟", ["哑铃夹胸", "平卧飞鸟"], "isolation",
     ["chest"], ["front_delt"], ["dumbbell"], ["gym", "home"],
     "beginner", "low", "low", (0, 0, 1, 0), False,
     ["cable_fly", "pec_deck"], "load"),
]

TEMPLATE = """id: {id}
name: {name}
aliases: [{aliases}]
pattern: {pattern}
primary: {primary}
secondary: {secondary}
equipment: {equipment}
location: {location}
level_min: {level_min}
skill: {skill}
laterality: bilateral
joint_stress: {{knee: {k}, lumbar: {l}, shoulder: {s}, wrist: {w}}}
fatigue: {fatigue}
progression: {{type: {prog}{unit}}}
track_e1rm: {track}
regressions: []
progressions: []
substitutes: {subs}
knowledge_refs: []
status: draft
_provenance:
  name_video_fields: llm        # 教学要点与结构化判断均来自通用知识，非博主原话
  pattern: llm
  joint_stress: pending         # 必须由发起人判断（21.2 ③b）
  substitutes: pending
"""

written = 0
for (eid, name, aliases, pattern, primary, secondary, equipment, location,
     level_min, skill, fatigue, stress, track, subs, prog) in E:
    path = ROOT / f"{eid}.yaml"
    if path.exists():
        continue
    unit = ", increment_kg: 2.5" if prog == "load" else ""
    body = TEMPLATE.format(
        id=eid, name=name, aliases=", ".join(aliases), pattern=pattern,
        primary=primary, secondary=secondary, equipment=equipment,
        location=location, level_min=level_min, skill=skill, fatigue=fatigue,
        k=stress[0], l=stress[1], s=stress[2], w=stress[3],
        track="true" if track else "false", subs=subs, prog=prog, unit=unit)
    path.write_text(body, encoding="utf-8")
    written += 1
print(f"生成 {written} 个新动作 YAML")
