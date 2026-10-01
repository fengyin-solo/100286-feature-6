"""乔木管理业务规则：衰弱处置链、复壮去重、字段校验与看板口径都收在这里。

处置链：生长正常 → 长势衰弱 → 濒危 → 已枯死。
- 记录衰弱：同一轮衰弱期可重复登记，以最后一版为准。
- 登记复壮：同一管护人在一轮衰弱期内重复提交，只认第一次；登记后回到「观察中」。
- 确认枯死：只有「观察中」的树可确认，必须写明缘由，落库为「已枯死」。
- 管护交接：只换管护人，不动长势，上一位管护人留在交接记录里。
每一步都会写入时间线（时间 + 管护人），胸径或冠幅为空一律不许落库。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "tree"
REQUIRED_FIELDS = ["树木编号", "树种名称", "胸径", "冠幅"]
NORMAL = "生长正常"
WEAK = "长势衰弱"
ENDANGERED = "濒危"
OBSERVING = "观察中"
DEAD = "已枯死"
STATUS_ORDER = [NORMAL, WEAK, ENDANGERED, OBSERVING, DEAD]

# 看板口径：未处理 = 衰弱或濒危、且本轮衰弱期还没有被受理的复壮记录的株数。
PENDING_STATUSES = (WEAK, ENDANGERED)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_entry_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


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
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ------------------------------------------------------------------ 登记
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": _new_entry_id(rows)}
        for field in ["树木编号", "树种名称", "胸径", "冠幅", "树龄", "定植日期", "管护人员"]:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = value
        entry["status"] = NORMAL
        entry["树木状态"] = NORMAL
        entry["decline"] = None  # 当前衰弱期；枯死或恢复正常后置空
        entry["timeline"] = []
        entry["rejuvenations"] = []
        entry["handover_from"] = None
        operator = str(values.get("管护人员") or "").strip()
        self._append_timeline(entry, "登记乔木", operator, f"胸径 {entry['胸径']}、冠幅 {entry['冠幅']}")
        self._refresh_flags(entry)
        rows.append(entry)
        return entry, []

    # ------------------------------------------------------------------ 动作
    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"乔木 {entry_id} 不存在或已归档"
        self._ensure_chain(entry)
        operator = str(values.get("管护人员") or entry.get("管护人员") or "").strip()
        if not operator:
            return None, "请填写本次操作的管护人"

        if action == "记录衰弱":
            return self._record_decline(entry, operator, values)
        if action == "登记濒危":
            return self._mark_endangered(entry, operator, values)
        if action == "登记复壮":
            return self._register_rejuvenation(entry, operator, values)
        if action == "确认枯死":
            return self._confirm_dead(entry, operator, values)
        if action == "管护交接":
            return self._handover(entry, operator, values)
        return None, f"动作「{action}」不属于乔木管理可执行范围"

    def _record_decline(self, entry: dict[str, Any], operator: str, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """转成长势衰弱；同一轮衰弱期重复登记以最后一版为准。"""
        status = entry["status"]
        if status == DEAD:
            return None, "已枯死的乔木不能再登记衰弱"
        episode = entry.get("decline")
        if episode is None or status == OBSERVING:
            # 生长正常第一次衰弱；或观察中复壮效果不佳再度衰弱 —— 都开启新一轮衰弱期
            if episode is not None:
                episode["resolved"] = True
            episode = {
                "id": self._next_episode_id(entry),
                "weak_record": None,
                "registered_by": [],   # 已登记过复壮的管护人，重复提交只认第一次
                "resolved": False,
            }
            entry["decline"] = episode
            entry["status"] = WEAK
            note = "转为长势衰弱"
        else:
            note = "更新衰弱登记（以最后一版为准）"
        episode["weak_record"] = {
            "表现": str(values.get("衰弱表现") or "").strip(),
            "诱因": str(values.get("衰弱诱因") or "").strip(),
            "管护人": operator,
            "时间": _now(),
        }
        self._append_timeline(entry, "记录衰弱", operator, note, snapshot=dict(episode["weak_record"]))
        self._refresh_flags(entry)
        return entry, "衰弱已登记" if note.startswith("转为") else "衰弱登记已按最后一版覆盖"

    def _mark_endangered(self, entry: dict[str, Any], operator: str, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if entry["status"] != WEAK:
            return None, "只有长势衰弱的乔木才能登记濒危"
        entry["status"] = ENDANGERED
        note = str(values.get("濒危说明") or "").strip()
        self._append_timeline(entry, "登记濒危", operator, note or "长势恶化转为濒危")
        self._refresh_flags(entry)
        return entry, "已登记濒危"

    def _register_rejuvenation(self, entry: dict[str, Any], operator: str, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """登记复壮：同一管护人重复提交只认第一次；登记后进入观察中。"""
        episode = entry.get("decline")
        if episode is not None and operator in episode["registered_by"]:
            self._append_timeline(entry, "重复复壮（已忽略）", operator, "同一管护人重复提交，只认第一次")
            return None, f"{operator} 已提交过复壮，本轮重复提交只认第一次"
        # 衰弱/濒危阶段必须先复壮；观察中允许其他管护人补登记，但同一人只认第一次
        if episode is None or entry["status"] not in (WEAK, ENDANGERED, OBSERVING):
            return None, "只有长势衰弱、濒危或观察中的乔木需要登记复壮"
        measures = str(values.get("复壮措施") or "").strip()
        record = {
            "衰弱期": episode["id"],
            "管护人": operator,
            "措施": measures,
            "时间": _now(),
            "状态": "观察中",
        }
        entry["rejuvenations"].append(record)
        episode["registered_by"].append(operator)
        was_observing = entry["status"] == OBSERVING
        entry["status"] = OBSERVING
        default_note = "补充登记复壮，继续观察中" if was_observing else "已登记复壮，进入观察中"
        self._append_timeline(entry, "登记复壮", operator, measures or default_note, snapshot=dict(record))
        self._refresh_flags(entry)
        return entry, "复壮已补登记，继续观察中" if was_observing else "复壮已登记，乔木回到观察中"

    def _confirm_dead(self, entry: dict[str, Any], operator: str, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if entry["status"] != OBSERVING:
            return None, "只有观察中的乔木（已登记复壮）才能确认枯死"
        reason = str(values.get("枯死缘由") or values.get("缘由") or "").strip()
        if not reason:
            return None, "确认枯死必须写明缘由"
        episode = entry.get("decline")
        self._append_timeline(entry, "确认枯死", operator, f"缘由：{reason}")
        for item in entry["rejuvenations"]:
            if item.get("状态") == "观察中":
                item["状态"] = "已枯死"
        entry["status"] = DEAD
        entry["dead_reason"] = reason
        entry["decline"] = None
        if episode is not None:
            episode["resolved"] = True
        self._refresh_flags(entry)
        return entry, "已确认枯死并记录缘由"

    def _handover(self, entry: dict[str, Any], operator: str, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if entry["status"] == DEAD:
            return None, "已枯死的乔木不再办理交接"
        new_keeper = str(values.get("接手管护人") or "").strip()
        if not new_keeper:
            return None, "交接必须填写接手管护人"
        if new_keeper == entry.get("管护人员"):
            return None, "接手管护人与当前管护人相同，无需交接"
        previous = str(entry.get("管护人员") or "").strip()
        entry["管护人员"] = new_keeper
        # 交接之后仍要能看出上一位管护人是谁
        entry["handover_from"] = {"管护人": previous, "交接时间": _now(), "交接办理人": operator}
        self._append_timeline(entry, "管护交接", operator, f"{previous or '（空缺）'} → {new_keeper}")
        self._refresh_flags(entry)
        return entry, f"管护人已由 {previous or '（空缺）'} 交接给 {new_keeper}"

    # ------------------------------------------------------------------ 看板
    def board(self) -> dict[str, Any]:
        """乔木看板：未处理株数按复壮明细重算，长势衰弱株必须挂得上复壮记录。"""
        rows = store.rows(MODULE)
        unhandled = 0
        weak = endangered = observing = dead = normal = 0
        weak_missing_rejuv: list[dict[str, Any]] = []
        for row in rows:
            self._ensure_chain(row)
            status = row.get("status")
            if status == WEAK:
                weak += 1
            elif status == ENDANGERED:
                endangered += 1
            elif status == OBSERVING:
                observing += 1
            elif status == DEAD:
                dead += 1
            elif status == NORMAL:
                normal += 1
            if self._is_unhandled(row):
                unhandled += 1
            record = self.latest_weak_record(row)
            if record is not None and not self._linked_rejuvenation(row):
                weak_missing_rejuv.append({
                    "id": row.get("id"),
                    "树木编号": row.get("树木编号"),
                    "管护人员": row.get("管护人员"),
                    "最近衰弱登记": record,
                })
        return {
            "total": len(rows),
            "未处理株数": unhandled,
            "生长正常": normal,
            "长势衰弱": weak,
            "濒危": endangered,
            "观察中": observing,
            "已枯死": dead,
            "复壮记录数": sum(len(row.get("rejuvenations") or []) for row in rows),
            "衰弱缺复壮记录": weak_missing_rejuv,
        }

    def _is_unhandled(self, row: dict[str, Any]) -> bool:
        # 衰弱/濒危且本轮衰弱期没有任何已受理的复壮记录 → 未处理
        return row.get("status") in PENDING_STATUSES and not self._linked_rejuvenation(row)

    def _linked_rejuvenation(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """当前衰弱期挂上的复壮记录：以衰弱明细里的管护人和衰弱期编号为准。"""
        episode = row.get("decline")
        if episode is None:
            return None
        record = self.latest_weak_record(row)
        keepers = {record["管护人"]} if record else set()
        for rejuv in row.get("rejuvenations") or []:
            if rejuv.get("衰弱期") != episode["id"]:
                continue
            if rejuv.get("管护人") in keepers:
                return rejuv
        return None

    @staticmethod
    def latest_weak_record(row: dict[str, Any]) -> dict[str, Any] | None:
        episode = row.get("decline")
        if not episode:
            return None
        return episode.get("weak_record")

    @staticmethod
    def _next_episode_id(entry: dict[str, Any]) -> int:
        used = [int(item.get("衰弱期", 0)) for item in entry.get("rejuvenations") or []]
        if entry.get("decline"):
            used.append(int(entry["decline"].get("id", 0)))
        return max(used, default=0) + 1

    # ------------------------------------------------------------------ 内部
    def _append_timeline(
        self,
        entry: dict[str, Any],
        action: str,
        operator: str,
        note: str,
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        event: dict[str, Any] = {"动作": action, "管护人": operator, "时间": _now(), "说明": note}
        if snapshot:
            event["明细"] = snapshot
        entry.setdefault("timeline", []).append(event)

    def _refresh_flags(self, entry: dict[str, Any]) -> None:
        """同步 store.overview 依赖的 pending / abnormal 标记，看板随复壮明细重算。"""
        entry["pending"] = self._is_unhandled(entry)
        entry["abnormal"] = entry["status"] in (WEAK, ENDANGERED)
        entry["树木状态"] = entry["status"]

    def _ensure_chain(self, entry: dict[str, Any]) -> None:
        """兼容处置链上线前的老数据：补齐时间线、复壮明细与衰弱期结构。"""
        entry.setdefault("timeline", [])
        entry.setdefault("rejuvenations", [])
        entry.setdefault("handover_from", None)
        if "decline" in entry:
            return
        status = entry.get("status")
        if status in (WEAK, ENDANGERED):
            keeper = str(entry.get("管护人员") or "").strip()
            episode = {
                "id": 1,
                "weak_record": {
                    "表现": "历史数据迁入",
                    "诱因": "",
                    "管护人": keeper,
                    "时间": _now(),
                },
                "registered_by": [],
                "resolved": False,
            }
            entry["decline"] = episode
        else:
            entry["decline"] = None
        self._refresh_flags(entry)


service = TreeService()
