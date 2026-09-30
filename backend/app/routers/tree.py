"""乔木管理接口：维护乔木，覆盖记录衰弱、登记复壮、确认濒危、登记枯死与管护交接。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.tree import STATUS_ORDER, TreeService

router = APIRouter(prefix="/api/tree", tags=["乔木管理"])

service = TreeService()

LIST_FIELDS = ["树木编号", "树种名称", "胸径", "冠幅", "树龄", "定植日期", "管护人员", "上一位管护人", "树木状态"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按树木编号检索"),
    status: str | None = Query(default=None, description="生长正常、长势衰弱、濒危、已枯死"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按树木编号与状态过滤乔木管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats", response_model=dict)
def tree_stats() -> dict[str, int]:
    """乔木看板指标：未处理株数随复壮明细实时重算。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出乔木管理清单：返回全量数据（含复壮记录与处置历程）。

    必须排在 /{entry_id} 之前，否则 export 会被当成树木编号匹配。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "tree", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条乔木明细（含复壮记录与处置历程）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"乔木 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条乔木；胸径或冠幅空着不许落库，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="乔木已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条乔木执行处置链动作；每一步都会记下时间与管护人，不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    values = dict(payload.values)
    if payload.remark and "remark" not in values:
        values["remark"] = payload.remark
    entry, message = service.run_action(entry_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/keeper", response_model=ActionResult)
def handover_keeper(entry_id: int, payload: EntryPayload) -> ActionResult:
    """管护交接：换新管护人，上一位管护人仍保留在明细里。"""
    entry, message = service.update_keeper(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
