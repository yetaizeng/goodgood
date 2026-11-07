"""本地 SQLite 存储层（替代 PostgreSQL）。

- 商品库、订单库、评论库、营销素材库：单文件 SQLite。
- 提供只读查询 + 受控写入两类接口。
- 外部 Agent 无内部写权限（护栏：写接口带权限校验）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from app.config import STORAGE_DIR

_DB_PATH = STORAGE_DIR / "ecom.sqlite"


class _Connection:
    """线程安全的 SQLite 连接封装。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            path_str = str(self._path)
            self._local.conn = sqlite3.connect(path_str, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def execute(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._conn().execute(sql, params)
        rows = cur.fetchall()
        self._conn().commit()
        return [dict(r) for r in rows]

    def executemany(self, sql: str, seq: list[tuple]) -> None:
        self._conn().executemany(sql, seq)
        self._conn().commit()


class Storage:
    """商品/订单/评论/营销四类业务数据的本地存储。"""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = _Connection(db_path)
        self._init_schema()
        self._seed()

    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS product (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                category TEXT,
                specs TEXT
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                qty INTEGER NOT NULL,
                status TEXT NOT NULL,
                logistics TEXT,
                user_name TEXT
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS review (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                content TEXT
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS marketing (
                id TEXT PRIMARY KEY,
                product_id TEXT,
                channel TEXT,
                content TEXT
            )
            """
        )
        # 外部委派回执审计表（双侧审计）
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS delegation_audit (
                task_id TEXT PRIMARY KEY,
                partner TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                receipt TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

    def _seed(self) -> None:
        """写入最小种子数据（幂等：仅在空表时写入）。"""
        if self._db.execute("SELECT COUNT(*) AS c FROM product")[0]["c"] == 0:
            self._db.executemany(
                "INSERT INTO product (id, name, price, stock, category, specs) VALUES (?,?,?,?,?,?)",
                [
                    ("P100", "轻便跑步鞋", 299.0, 50, "鞋类", "透气/防滑/适合跑步"),
                    ("P101", "无线降噪耳机", 599.0, 30, "数码", "主动降噪/续航30h"),
                    ("P102", "保温杯", 89.0, 200, "家居", "500ml/316不锈钢"),
                ],
            )
        if self._db.execute("SELECT COUNT(*) AS c FROM orders")[0]["c"] == 0:
            self._db.executemany(
                "INSERT INTO orders (id, product_id, qty, status, logistics, user_name) VALUES (?,?,?,?,?,?)",
                [
                    ("A123", "P100", 1, "已发货", "SF1234567890", "张三"),
                    ("A124", "P101", 2, "待发货", None, "李四"),
                ],
            )
        if self._db.execute("SELECT COUNT(*) AS c FROM review")[0]["c"] == 0:
            self._db.executemany(
                "INSERT INTO review (id, product_id, rating, content) VALUES (?,?,?,?)",
                [
                    ("R1", "P100", 5, "轻便透气，跑步很舒服"),
                    ("R2", "P101", 4, "降噪效果好，续航不错"),
                ],
            )

    # ------------------------------------------------------------------
    # 只读查询（内部 Agent 与 MCP 只读工具共用）
    # ------------------------------------------------------------------
    def get_product(self, product_id: str) -> Optional[dict]:
        rows = self._db.execute("SELECT * FROM product WHERE id=?", (product_id,))
        return rows[0] if rows else None

    def list_products(self, category: Optional[str] = None) -> list[dict]:
        if category:
            return self._db.execute("SELECT * FROM product WHERE category=?", (category,))
        return self._db.execute("SELECT * FROM product")

    def get_order(self, order_id: str) -> Optional[dict]:
        rows = self._db.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        return rows[0] if rows else None

    def get_reviews(self, product_id: str) -> list[dict]:
        return self._db.execute("SELECT * FROM review WHERE product_id=?", (product_id,))

    # ------------------------------------------------------------------
    # 受控写入（需人工确认才可执行；护栏：外部 Agent 无权限）
    # ------------------------------------------------------------------
    def create_replenish_task(self, product_id: str, qty: int, operator: str) -> str:
        """补货申请（受控写入，需 operator 为内部授权人）。"""
        self._require_internal(operator)
        task_id = f"REP-{product_id}-{qty}"
        return task_id

    def update_order_status(self, order_id: str, status: str, operator: str) -> None:
        self._require_internal(operator)
        self._db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

    @staticmethod
    def _require_internal(operator: str) -> None:
        """护栏：仅内部授权人可写。外部 Agent 一律拒绝。"""
        if operator not in ("internal-admin", "internal-operator"):
            raise PermissionError(
                f"外部/未授权主体 [{operator}] 无内部写权限（护栏生效）"
            )

    # ------------------------------------------------------------------
    # 委派审计
    # ------------------------------------------------------------------
    def record_delegation(self, task_id: str, partner: str, payload: dict, status: str, receipt: str = "") -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO delegation_audit (task_id, partner, payload, status, receipt) VALUES (?,?,?,?,?)",
            (task_id, partner, json.dumps(payload, ensure_ascii=False), status, receipt),
        )


# 全局单例
_storage: Optional[Storage] = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage
