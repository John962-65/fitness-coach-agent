"""M6.4-B B0.2/B1：结构化动作教学内容（teaching/*.yaml）。

与 knowledge/ 教学文档（M6.2，人工整理的原文）分层：
- knowledge/ = 来源文档（原文 + 来源元数据）；
- teaching/<ex_id>.yaml = 面向展示的结构化教学（准备/执行/呼吸/常见错误/
  注意事项/适用条件），逐节标注审核状态。

内容完整性规则（B0.2）：
- 六个核心节：setup（准备姿势）/ execution（执行过程）/ common_errors
  （常见错误）/ cautions（注意事项）/ conditions（适用条件）/ sources
  （参考来源）；breathing（呼吸及节奏）仅在有可靠依据时要求。
- 每节状态 ∈ {draft, reviewed, approved, incomplete}；
- 动作基础属性的 status（approved）不得继承为教学审核通过——
  本模块计算 teaching review_status 时只看教学文件自身声明。

纪律：AI 可辅助整理，但不得伪造来源与人工审核结果。凡未人工审核的
整理稿一律 status=draft，展示层必须可见"整理稿"标注。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .exercises import library

TEACHING_DIR = (Path(__file__).resolve().parent.parent / "teaching").resolve()

SECTION_KEYS = ("setup", "execution", "breathing", "common_errors",
                "cautions", "conditions")
SECTION_LABELS = {
    "setup": "准备姿势", "execution": "执行步骤", "breathing": "呼吸与节奏",
    "common_errors": "常见错误", "cautions": "注意事项", "conditions": "适用条件",
}
STATUS_DRAFT, STATUS_REVIEWED, STATUS_APPROVED, STATUS_INCOMPLETE = (
    "draft", "reviewed", "approved", "incomplete")
VALID_SECTION_STATUS = {STATUS_DRAFT, STATUS_REVIEWED, STATUS_APPROVED,
                        STATUS_INCOMPLETE}
# 未有可靠依据时允许整节缺失（breathing）或标 incomplete
REQUIRED_SECTIONS = ("setup", "execution", "common_errors", "cautions",
                     "conditions")


class TeachingError(ValueError):
    """教学文件结构不合法（缺字段/枚举外取值/来源缺失）。"""


def _validate(doc: dict, path: Path) -> dict:
    ex_id = doc.get("exercise_id")
    if not isinstance(ex_id, str) or not ex_id:
        raise TeachingError(f"{path.name}: 缺 exercise_id")
    if library.get(ex_id) is None:
        raise TeachingError(f"{path.name}: exercise_id={ex_id} 不在动作库（不允许第二套动作库）")
    if doc.get("review_status") not in VALID_SECTION_STATUS:
        raise TeachingError(f"{path.name}: review_status 非法：{doc.get('review_status')!r}")
    sources = doc.get("sources")
    if not isinstance(sources, list) or not sources:
        raise TeachingError(f"{path.name}: 缺 sources（参考来源不可伪造也不可缺失）")
    sections = doc.get("sections")
    if not isinstance(sections, dict):
        raise TeachingError(f"{path.name}: 缺 sections")
    for key, sec in sections.items():
        if key not in SECTION_KEYS:
            raise TeachingError(f"{path.name}: 未知教学节 {key}")
        if not isinstance(sec, dict) or sec.get("status") not in VALID_SECTION_STATUS:
            raise TeachingError(f"{path.name}:{key}: 节状态非法")
        items = sec.get("items")
        if items is None:
            items = []
        if not isinstance(items, list):
            raise TeachingError(f"{path.name}:{key}: items 必须为列表")
        for it in items:
            # 纯字符串或 {error, consequence?, fix?} 结构；其余（含 YAML 半角
            # 冒号误解析出的 map）直接拒绝，避免渲染成 [object Object]
            if isinstance(it, str):
                continue
            if isinstance(it, dict) and it.get("error") \
                    and set(it) <= {"error", "consequence", "fix"}:
                continue
            raise TeachingError(
                f"{path.name}:{key}: 条目必须是字符串或 error/consequence/fix "
                f"结构（半角冒号会被 YAML 解析成 map，请用全角冒号或改写）")
        if sec["status"] != STATUS_INCOMPLETE and not items:
            raise TeachingError(
                f"{path.name}:{key}: 状态非 incomplete 但没有内容")
    for key in REQUIRED_SECTIONS:
        if key not in sections:
            raise TeachingError(f"{path.name}: 缺核心教学节 {key}")
    return doc


def load_one(ex_id: str) -> dict | None:
    """读取并校验单个动作的教学文件；不存在返回 None，坏文件抛 TeachingError。"""
    path = TEACHING_DIR / f"{ex_id}.yaml"
    if not path.is_file():
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise TeachingError(f"{path.name}: YAML 解析失败：{e}") from e
    if not isinstance(doc, dict):
        raise TeachingError(f"{path.name}: 结构必须为映射")
    doc = _validate(doc, path)
    doc["content_version"] = int(doc.get("content_version") or 1)
    # review_notes：交付/复核审查挂起的争议点（可追溯，不改写原文）
    notes = doc.get("review_notes")
    if notes is not None and not isinstance(notes, list):
        raise TeachingError(f"{path.name}: review_notes 必须为列表")
    return doc


def load_all() -> dict[str, dict]:
    """teaching/ 全量加载（供审计工具与测试；坏文件立即抛错，绝不静默吞）。"""
    out: dict[str, dict] = {}
    if not TEACHING_DIR.is_dir():
        return out
    for path in sorted(TEACHING_DIR.glob("*.yaml")):
        doc = load_one(path.stem)
        if doc:
            out[doc["exercise_id"]] = doc
    return out


def completeness(doc: dict | None) -> str:
    """内容完整性判定（B0.2）：incomplete < draft < reviewed/approved。

    「关联了一篇教学文档」不等于「已有完整教学」——只有结构化六节齐备
    （breathing 允许缺失）才算完整层级；层级取各节最低状态。
    """
    if not doc:
        return STATUS_INCOMPLETE
    order = {STATUS_INCOMPLETE: 0, STATUS_DRAFT: 1,
             STATUS_REVIEWED: 2, STATUS_APPROVED: 3}
    # breathing 允许无依据缺失，不拉低整体；核心节缺失/最低状态决定层级
    core = [doc["sections"][k] for k in REQUIRED_SECTIONS
            if k in doc.get("sections", {})]
    if len(core) != len(REQUIRED_SECTIONS):
        return STATUS_INCOMPLETE
    worst = min(order.get(sec.get("status"), 0) for sec in core)
    return {0: STATUS_INCOMPLETE, 1: STATUS_DRAFT,
            2: STATUS_REVIEWED, 3: STATUS_APPROVED}[worst]


def public_teaching(ex_id: str) -> dict | None:
    """动作详情接口用：结构化教学 + 完整性（不含 internal 字段）。"""
    doc = load_one(ex_id)
    if not doc:
        return None
    return {
        "exercise_id": doc["exercise_id"],
        "content_version": doc["content_version"],
        "updated": str(doc.get("updated") or ""),
        "review_status": doc["review_status"],
        "completeness": completeness(doc),
        "sources": doc["sources"],
        "sections": {k: doc["sections"][k] for k in SECTION_KEYS
                     if k in doc["sections"]},
        "review_notes": doc.get("review_notes") or [],
    }
