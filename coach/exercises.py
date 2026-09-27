"""动作库：加载 exercises/*.yaml，提供动作名归一（设计书 20.2/20.4）

归一顺序：别名精确匹配 → 别名是输入子串（取最长）→ 输入是别名前缀 → difflib 模糊。
同一套逻辑同时服务打卡归一（20.4）与视频动作"对上号"（21.2 ②）。
"""
from __future__ import annotations

import difflib
from pathlib import Path

import yaml

EXERCISES_ROOT = Path(__file__).resolve().parent.parent / "exercises"


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
        """输入用户叫法，返回 (id 或 None, 官方名, 匹配方式 exact/sub/prefix/fuzzy/"")"""
        t = self._norm(text)
        if not t:
            return None, "", ""
        if t in self._alias:
            ex_id = self._alias[t]
            return ex_id, self._by_id[ex_id]["name"], "exact"
        subs = [(len(a), aid) for a, aid in self._alias.items() if a in t]
        if subs:
            ex_id = max(subs)[1]
            return ex_id, self._by_id[ex_id]["name"], "sub"
        prefixes = [aid for a, aid in self._alias.items()
                    if a.startswith(t) and len(t) >= 2]
        if len(prefixes) == 1:
            return prefixes[0], self._by_id[prefixes[0]]["name"], "prefix"
        close = difflib.get_close_matches(t, list(self._alias), n=1, cutoff=0.6)
        if close:
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
