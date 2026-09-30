"""乔木管理业务规则：衰弱处置链、字段校验与看板口径都收在这里。

处置链：生长正常 → 长势衰弱 → 濒危 → 已枯死。
- 记录衰弱可重复提交，同一株树以最后一版为准；衰弱株必须挂得上复壮记录。
- 登记复壮：同一管护人重复提交只认第一次；登记后回到观察中（生长正常）。
- 濒危株才能确认枯死，枯死必须写明缘由。
- 每一步都落时间与管护人；交接后仍保留上一位管护人。
- 胸径、冠幅为空不许落库。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "tree"
REQUIRED_FIELDS = ["树木编号", "树种名称", "胸径", "冠幅"]
LIST_FIELDS = ["树龄", "定植日期"]
STATUS_ORDER = ["生长正常", "长势衰弱", "濒危", "已枯死"]
OBSERVING = "生长正常"
DEAD = "已枯死"

# 看板「未处理」口径：衰弱、濒危且还没有复壮记录认领的株数
PENDING_STATUSES = ["长势衰弱", "濒危"]
ABNORMAL_STATUSES = ["长势衰弱", "濒危"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text(values: dict[str, Any], field: str) -> str:
    return str(values.get(field) or "").strip()


class TreeService:
    # ------------------------------------------------------------------ 查询
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("树木编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def stats(self) -> dict[str, int]:
        """乔木看板指标：未处理株数随复壮明细实时重算。"""
        rows = store.rows(MODULE)
        return {
            "正常乔木": sum(1 for row in rows if row.get("status") == OBSERVING),
            "衰弱乔木": sum(1 for row in rows if row.get("status") in ABNORMAL_STATUSES),
            "枯死乔木": sum(1 for row in rows if row.get("status") == DEAD),
            # 衰弱/濒危但还没有复壮记录认领，才算未处理
            "未处理株数": sum(1 for row in rows if self.is_pending(row)),
        }

    @staticmethod
    def is_pending(row: dict[str, Any]) -> bool:
        return row.get("status") in PENDING_STATUSES and not row.get("复壮记录")

    @staticmethod
    def is_abnormal(row: dict[str, Any]) -> bool:
        return row.get("status") in ABNORMAL_STATUSES

    def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        """出参补一份随明细重算的看板标志；衰弱株必须带出复壮记录。"""
        data = dict(row)
        data.setdefault("复壮记录", [])
        data.setdefault("处置历程", [])
        data["pending"] = self.is_pending(row)
        data["abnormal"] = self.is_abnormal(row)
        return data

    # ------------------------------------------------------------------ 登记
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _text(values, field)]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": OBSERVING,
            "pending": True,
            "abnormal": False,
            "管护人员": "",
            "上一位管护人": "",
            "交接时间": "",
            "复壮记录": [],
            "处置历程": [],
        }
        for field in REQUIRED_FIELDS + LIST_FIELDS:
            entry[field] = _text(values, field)
        keeper = _text(values, "管护人员")
        if keeper:
            entry["管护人员"] = keeper
        rows.append(entry)
        return self._present(entry), []

    def update_keeper(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """管护交接：换新管护人，旧的一位留在「上一位管护人」里。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"乔木 {entry_id} 不存在或已归档"
        keeper = _text(values, "管护人员")
        if not keeper:
            return None, "交接时必须填写接手管护人"
        operator = _text(values, "operator") or keeper
        previous = str(entry.get("管护人员") or "").strip()
        if previous and previous != keeper:
            entry["上一位管护人"] = previous
        entry["管护人员"] = keeper
        entry["交接时间"] = _now()
        entry.setdefault("处置历程", []).append(
            {"动作": "管护交接", "管护人": operator, "时间": entry["交接时间"],
             "说明": (f"{previous or '—'} → {keeper}" if previous != keeper else keeper)}
        )
        return self._present(entry), f"管护人已交接给{keeper}"

    # ------------------------------------------------------------------ 处置
    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"乔木 {entry_id} 不存在或已归档"
        operator = _text(values, "operator") or str(entry.get("管护人员") or "").strip()
        if not operator:
            return None, "处置时必须登记管护人"

        if action == "记录衰弱":
            return self._mark_declining(entry, values, operator)
        if action == "登记复壮":
            return self._register_rejuvenation(entry, values, operator)
        if action == "确认濒危":
            return self._mark_endangered(entry, operator)
        if action == "登记枯死":
            return self._mark_dead(entry, values, operator)
        return None, f"动作「{action}」不属于乔木管理可执行范围"

    def _mark_declining(
        self, entry: dict[str, Any], values: dict[str, Any], operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] == DEAD:
            return None, "已枯死的乔木不能再登记衰弱"
        # 重复登记衰弱以最后一版为准：衰弱说明/管护人直接覆盖，时间刷新
        symptom = _text(values, "衰弱说明")
        entry["status"] = "长势衰弱"
        entry["衰弱说明"] = symptom
        if not entry.get("管护人员"):
            entry["管护人员"] = operator
        entry.setdefault("衰弱登记", []).append(
            {"管护人": operator, "时间": _now(), "衰弱说明": symptom}
        )
        entry.setdefault("处置历程", []).append(
            {"动作": "记录衰弱", "管护人": operator, "时间": _now(), "说明": symptom or "长势转弱"}
        )
        self._refresh_flags(entry)
        return self._present(entry), "已登记长势衰弱，等待认领复壮"

    def _register_rejuvenation(
        self, entry: dict[str, Any], values: dict[str, Any], operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] not in ("长势衰弱", "濒危"):
            return None, "只有长势衰弱或濒危的乔木才能登记复壮"
        records = entry.setdefault("复壮记录", [])
        # 同一管护人重复提交复壮，只认第一次
        if any(str(record.get("管护人") or "").strip() == operator for record in records):
            return None, f"管护人{operator}已提交过复壮，重复提交只认第一次"
        measure = _text(values, "复壮措施") or _text(values, "remark")
        if not measure:
            return None, "登记复壮必须填写复壮措施"
        records.append({"管护人": operator, "时间": _now(), "复壮措施": measure})
        # 登记复壮后回到观察中
        entry["status"] = OBSERVING
        entry["衰弱说明"] = ""
        entry.setdefault("处置历程", []).append(
            {"动作": "登记复壮", "管护人": operator, "时间": _now(), "说明": measure}
        )
        self._refresh_flags(entry)
        return self._present(entry), f"已登记{operator}的复壮措施，乔木回到观察中"

    def _mark_endangered(
        self, entry: dict[str, Any], operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != "长势衰弱":
            return None, "只有长势衰弱的乔木才能确认濒危"
        if not entry.get("复壮记录"):
            return None, "长势衰弱的乔木必须挂上复壮记录后才能确认濒危"
        entry["status"] = "濒危"
        entry.setdefault("处置历程", []).append(
            {"动作": "确认濒危", "管护人": operator, "时间": _now(), "说明": "复壮后仍未好转"}
        )
        self._refresh_flags(entry)
        return self._present(entry), "已确认濒危，等待下一步处置"

    def _mark_dead(
        self, entry: dict[str, Any], values: dict[str, Any], operator: str
    ) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != "濒危":
            return None, "只有濒危的乔木才能确认枯死"
        reason = _text(values, "枯死缘由") or _text(values, "remark")
        if not reason:
            return None, "确认枯死必须写明枯死缘由"
        entry["status"] = DEAD
        entry["枯死缘由"] = reason
        entry.setdefault("处置历程", []).append(
            {"动作": "登记枯死", "管护人": operator, "时间": _now(), "说明": reason}
        )
        self._refresh_flags(entry)
        return self._present(entry), "已落到已枯死并记录缘由"

    def _refresh_flags(self, entry: dict[str, Any]) -> None:
        entry["pending"] = self.is_pending(entry)
        entry["abnormal"] = self.is_abnormal(entry)
