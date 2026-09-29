"""动作库：加载 exercises/*.yaml，提供动作名归一（设计书 20.2/20.4）

归一顺序：别名精确匹配 → 别名是输入子串（取最长）→ 输入是别名前缀 → difflib 模糊。
同一套逻辑同时服务打卡归一（20.4）与视频动作"对上号"（21.2 ②）。

变式保护（2026-09-29）：子串/模糊命中时，若输入比别名多出了"变式词"
（跳/史密斯/箱式/相扑/单腿/窄距……），说明用户做的是另一个变式动作——
不归一、返回 None 进待确认队列，避免"深蹲跳"被静默记成杠铃深蹲、
污染 e1RM 趋势从而触发虚假的停滞/加重建议。
"""
from __future__ import annotations

import difflib
from pathlib import Path

import yaml

EXERCISES_ROOT = Path(__file__).resolve().parent.parent / "exercises"

# 变式修饰词：输入含有而命中别名不含 → 是另一个动作（或库里没有的新变式）
_VARIANT_MARKERS = (
    "跳", "史密斯", "箱", "相扑", "单腿", "单臂", "窄", "宽",
    "上斜", "下斜", "暂停", "半程", "赤字", "弹力带", "负重",
    "器械", "绳索", "坐姿", "站姿", "俯身",
)


def _has_extra_variant(t: str, alias: str) -> bool:
    """输入相对命中别名多出了变式词（如 "相扑硬拉" vs "硬拉"）"""
    return any(m in t and m not in alias for m in _VARIANT_MARKERS)


class ExerciseLibrary:
    def __init__(self, root: Path = EXERCISES_ROOT) -> None:
        self.root = root
        self._by_id: dict[str, dict] = {}
        self._alias: dict[str, str] = {}  # 归一化别名 -> id
        self._load()

    @staticmethod
    def _norm(text: str) -> str:
        return "".join(str(text).split()).lower()

    def _load(self) -> None:
        for path in sorted(self.root.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            ex_id = data["id"]
            self._by_id[ex_id] = data
            for a in [data["name"], *(data.get("aliases") or [])]:
                key = self._norm(a)
                if key in self._alias and self._alias[key] != ex_id:
                    raise ValueError(
                        f"别名冲突：{a!r} 同时属于 {self._alias[key]} 和 {ex_id}")
                self._alias[key] = ex_id

    def __len__(self) -> int:
        return len(self._by_id)

    def all(self) -> list[dict]:
        """全部动作（按 id 排序，保证确定性）"""
        return [self._by_id[k] for k in sorted(self._by_id)]

    def get(self, ex_id: str) -> dict | None:
        return self._by_id.get(ex_id)

    def normalize(self, text: str) -> tuple[str | None, str, str]:
        """输入用户叫法，返回 (id 或 None, 官方名, 匹配方式 exact/sub/prefix/fuzzy/"")

        sub/fuzzy 命中后做变式检查：输入多出变式词则放弃该命中
        （变式动作不归一到基础动作，返回 None 由调用方进待确认队列）。
        """
        t = self._norm(text)
        if not t:
            return None, "", ""
        if t in self._alias:
            ex_id = self._alias[t]
            return ex_id, self._by_id[ex_id]["name"], "exact"
        subs = [(len(a), a, aid) for a, aid in self._alias.items() if a in t]
        if subs:
            _, alias, ex_id = max(subs, key=lambda x: (x[0], x[2]))
            if not _has_extra_variant(t, alias):
                return ex_id, self._by_id[ex_id]["name"], "sub"
            # 子串命中被变式词否决（"窄距卧推"⊃"卧推"但多了"窄"）：
            # 不静默合并，继续尝试前缀/模糊（如"窄距卧推"还能对上"窄握卧推"）
        prefixes = [aid for a, aid in self._alias.items()
                    if a.startswith(t) and len(t) >= 2]
        if len(prefixes) == 1:
            return prefixes[0], self._by_id[prefixes[0]]["name"], "prefix"
        close = difflib.get_close_matches(t, list(self._alias), n=1, cutoff=0.6)
        if close:
            if not _has_extra_variant(t, close[0]):
                ex_id = self._alias[close[0]]
                return ex_id, self._by_id[ex_id]["name"], "fuzzy"
        return None, text, ""

    def track_e1rm_names(self, names: list[str]) -> list[str]:
        """从给定名字里筛出库中 track_e1rm=true 的官方名（保持原顺序去重）"""
        out: list[str] = []
        for n in names:
            ex_id, official, _via = self.normalize(n)
            if ex_id and self._by_id[ex_id].get("track_e1rm") \
                    and official not in out:
                out.append(official)
        return out


# 模块级共享实例（加载失败要在测试里立刻暴露，不做静默兜底）
library = ExerciseLibrary()
