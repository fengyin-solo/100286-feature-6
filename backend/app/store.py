"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        # 乔木的待处理/异常口径挂在复壮明细上，标志位随处置链实时重算，
        # 不能直接信种子数据里写死的 pending/abnormal。
        tree_flags: dict[int, tuple[bool, bool]] = {}
        tree_module = "tree"
        try:
            from app.services.tree import MODULE as TREE_MODULE
            from app.services.tree import TreeService

            tree_module = TREE_MODULE
            tree_service = TreeService()
            tree_flags = {
                int(row.get("id", 0)): (tree_service.is_pending(row), tree_service.is_abnormal(row))
                for row in self.rows(TREE_MODULE)
            }
        except Exception:  # pragma: no cover - 看板不能因为单模块口径异常而整体不可用
            tree_flags = {}

        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            if name == tree_module and tree_flags:
                pending = sum(1 for row in rows if tree_flags.get(int(row.get("id", 0)), (False, False))[0])
                abnormal = sum(1 for row in rows if tree_flags.get(int(row.get("id", 0)), (False, False))[1])
            else:
                pending = sum(1 for row in rows if row.get("pending"))
                abnormal = sum(1 for row in rows if row.get("abnormal"))
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": pending,
                "abnormal": abnormal,
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
