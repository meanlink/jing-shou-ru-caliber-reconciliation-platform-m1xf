"""源账列契约版本注册表。

渠道账源新增字段（如 2026-11 的结算标签）时登记新版本，旧版本继续有效：
- 字段新增按版本兼容：旧批次保持原契约，不重写历史数据；
- 缺必需字段、类型变化或未知关键字段：整批隔离，不放出半批；
- 同批记录不得混用契约：一批记录必须整体符合且仅符合一个版本；
- 分析与导出固定采用批次落库时判定的完整版本。
"""
import math

from sqlalchemy import select

from src.models import Dataset

BASE_COLUMNS = [
    {"key": "day", "label": "日期", "type": "string"},
    {"key": "channel", "label": "渠道", "type": "string"},
    {"key": "currency", "label": "币种", "type": "string"},
    {"key": "gross", "label": "含折扣前收入", "type": "number"},
    {"key": "refunds", "label": "退款", "type": "number"},
    {"key": "discount", "label": "折扣", "type": "number"},
    {"key": "recognized_net", "label": "源账认可净额", "type": "number"},
    {"key": "visits", "label": "有效访问", "type": "number"},
]
SETTLEMENT_TAG = {"key": "settlement_tag", "label": "结算标签", "type": "string"}

CONTRACTS = {
    "v1": {
        "version": "v1",
        "label": "基线源账契约",
        "introduced": "2026-09 初始口径：渠道日汇总八字段，统一 CNY。",
        "columns": BASE_COLUMNS,
    },
    "v2": {
        "version": "v2",
        "label": "结算标签契约",
        "introduced": "2026-11 渠道账源新增结算标签，用于按结算方式分组对账。",
        "columns": BASE_COLUMNS + [SETTLEMENT_TAG],
    },
}
VERSION_ORDER = ["v1", "v2"]
DEFAULT_VERSION = "v2"
DEFAULT_BASIS = (
    "新接入批次默认按 v2（含结算标签）校验；字段新增属版本兼容，"
    "2026-11 前的旧批次继续按 v1 有效，不重写历史数据。"
    "同批记录必须整体符合同一版本，缺必需字段、字段类型变化或出现未知字段时整批隔离。"
)


def contract(version):
    if version not in CONTRACTS:
        raise ValueError(f"未知的源账契约版本：{version}")
    return CONTRACTS[version]


def columns(version):
    return CONTRACTS[version]["columns"]


def supports(version, key):
    return any(c["key"] == key for c in columns(version))


def diff_versions(previous, current):
    """两个版本间的列差异：新增、移除与类型变化。"""
    before = {c["key"]: c for c in columns(previous)}
    after = {c["key"]: c for c in columns(current)}
    return {
        "added": [after[k] for k in after if k not in before],
        "removed": [before[k] for k in before if k not in after],
        "type_changed": [
            {"key": k, "from": before[k]["type"], "to": after[k]["type"], "label": after[k]["label"]}
            for k in before.keys() & after.keys() if before[k]["type"] != after[k]["type"]
        ],
    }


def _violation(record, version):
    """返回 record 违反指定契约的第一条原因；符合则返回 None。"""
    if not isinstance(record, dict):
        return "记录不是键值结构"
    known = {c["key"] for c in columns(version)}
    for key in record:
        if key not in known:
            return f"未知字段 {key}（不在 {version} 注册列中）"
    for c in columns(version):
        value = record.get(c["key"])
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"缺少必需字段 {c['label']}（{c['key']}）"
        if c["type"] == "number":
            if isinstance(value, bool):
                return f"字段 {c['label']}（{c['key']}）类型变化：应为有限数值"
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                return f"字段 {c['label']}（{c['key']}）类型变化：应为有限数值"
            if not math.isfinite(number):
                return f"字段 {c['label']}（{c['key']}）类型变化：应为有限数值"
        elif not isinstance(value, str):
            return f"字段 {c['label']}（{c['key']}）类型变化：应为文本"
        elif c["key"] == "settlement_tag" and len(value.strip()) > 40:
            return "结算标签超长（最多 40 字）"
    return None


def _normalize(record, version):
    row = {}
    for c in columns(version):
        value = record[c["key"]]
        row[c["key"]] = float(value) if c["type"] == "number" else value.strip()
    return row


def classify(records):
    """判定整批记录唯一符合的契约版本。

    返回 (version, normalized_records)；任何一条记录不符合共同版本时返回
    (None, reason)，调用方必须整批隔离，不得部分放行。
    """
    if not records:
        return None, "批次为空，无法判定契约版本"
    matched = []
    for record in records:
        matched.append({v for v in VERSION_ORDER if _violation(record, v) is None})
    common = set.intersection(*matched)
    if common:
        version = DEFAULT_VERSION if DEFAULT_VERSION in common else VERSION_ORDER[max(VERSION_ORDER.index(v) for v in common)]
        return version, [_normalize(r, version) for r in records]
    counts = {v: sum(v in m for m in matched) for v in VERSION_ORDER}
    best = max(VERSION_ORDER, key=lambda v: (counts[v], VERSION_ORDER.index(v)))
    if 0 < counts[best] < len(records):
        anchor = next(i for i, m in enumerate(matched) if best in m)
        first_bad = next(i for i, m in enumerate(matched) if best not in m)
        others = sorted(matched[first_bad] or set())
        if others:
            return None, (
                f"同批记录混用契约：第 {anchor + 1} 行符合 {best}，第 {first_bad + 1} 行符合 {'、'.join(others)}；"
                "同批记录不得混用契约，整批隔离"
            )
        return None, f"第 {first_bad + 1} 行{_violation(records[first_bad], best)}；整批隔离"
    first = records[0]
    return None, f"第 1 行{_violation(first, best)}；整批隔离"


def catalog():
    """契约版本目录：差异、默认版本与默认依据，供页面与 API 使用。"""
    versions = []
    for index, version in enumerate(VERSION_ORDER):
        entry = {**CONTRACTS[version], "default": version == DEFAULT_VERSION}
        entry["diff_from_previous"] = diff_versions(VERSION_ORDER[index - 1], version) if index else None
        versions.append(entry)
    return {"default_version": DEFAULT_VERSION, "default_basis": DEFAULT_BASIS, "versions": versions}


def revalidate_datasets(db):
    """升级后复核：逐批校验记录仍满足其固定契约，违反者整批隔离。

    幂等：仅在状态或原因变化时写入，中断重试不会重复写入，也不会放出半批。
    """
    changed = []
    for d in db.scalars(select(Dataset)):
        if d.status != "active":
            continue
        version, _ = classify(d.records)
        if version != d.contract_version:
            d.status = "quarantined"
            d.quarantine_reason = f"升级复核：批次记录不再满足固定契约 {d.contract_version}，整批隔离"
            changed.append(d.id)
    return changed
