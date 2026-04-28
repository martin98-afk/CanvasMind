# -*- coding: utf-8 -*-
"""
会话存储层 - 基于 SQLite 的持久化存储

解决 issue #374：会话记录存储架构存在高风险
- 原子性写入
- 并发支持
- 损坏隔离
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

from loguru import logger

from app.sqlite_database.db_manager import DatabaseManager


class SessionStore:
    """SQLite 会话存储层，提供原子性持久化"""

    TABLE_NAME = "sessions"
    MEMORIES_TABLE = "memories"
    DB_FILENAME = "sessions.db"

    def __init__(self, db_dir: str = "canvas_files"):
        self._db_dir = db_dir
        self._db_path = str(Path(db_dir) / self.DB_FILENAME)
        self._db: Optional[DatabaseManager] = None
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False
        self._init_schema()

    def _init_schema(self):
        """初始化数据库和表结构"""
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return

            try:
                # 使用 DatabaseManager（单例模式）
                self._db = DatabaseManager()
                self._db.connect(self._db_path)

                # 创建会话表（TIMESTAMP 改为 TEXT 避免时区问题）
                self._db.create_table(self.TABLE_NAME, [
                    {"name": "session_id", "type": "TEXT", "primary_key": True},
                    {"name": "canvas_id", "type": "TEXT", "not_null": True},
                    {"name": "title", "type": "TEXT"},
                    {"name": "messages", "type": "TEXT"},  # JSON 序列化
                    {"name": "system_prompt", "type": "TEXT"},
                    {"name": "compaction_state", "type": "TEXT"},  # JSON
                    {"name": "compaction_cache", "type": "TEXT"},  # JSON
                    {"name": "message_count", "type": "INTEGER", "default": 0},
                    {"name": "created_at", "type": "TEXT"},  # 使用 TEXT 避免 UTC 时区偏移
                    {"name": "updated_at", "type": "TEXT"},
                ])

                # 创建索引
                self._db.execute_sql(
                    f'CREATE INDEX IF NOT EXISTS idx_canvas_id ON {self.TABLE_NAME}(canvas_id)'
                )
                self._db.execute_sql(
                    f'CREATE INDEX IF NOT EXISTS idx_updated ON {self.TABLE_NAME}(updated_at DESC)'
                )

                # 创建长期记忆表
                self._db.create_table(self.MEMORIES_TABLE, [
                    {"name": "memory_id", "type": "TEXT", "primary_key": True},
                    {"name": "canvas_id", "type": "TEXT", "not_null": True},
                    {"name": "content", "type": "TEXT"},
                    {"name": "enabled", "type": "INTEGER", "default": 1},
                    {"name": "confidence", "type": "REAL", "default": 0.8},
                    {"name": "category", "type": "TEXT"},
                    {"name": "source", "type": "TEXT"},
                    {"name": "last_accessed", "type": "TEXT"},  # 使用 TEXT 避免 UTC 时区偏移
                    {"name": "created_at", "type": "TEXT"},
                    {"name": "updated_at", "type": "TEXT"},
                ])

                # 创建索引
                self._db.execute_sql(
                    f'CREATE INDEX IF NOT EXISTS idx_memories_canvas ON {self.MEMORIES_TABLE}(canvas_id)'
                )

                # 创建文件操作记录表（撤销功能）
                self._db.create_table("file_operations", [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "session_id", "type": "TEXT", "not_null": True},
                    {"name": "call_id", "type": "TEXT", "not_null": True},
                    {"name": "tool_name", "type": "TEXT", "not_null": True},
                    {"name": "file_path", "type": "TEXT", "not_null": True},
                    {"name": "backup_path", "type": "TEXT", "not_null": True},
                    {"name": "created_at", "type": "TEXT", "not_null": True},
                ])

                # 创建索引
                self._db.execute_sql(
                    'CREATE INDEX IF NOT EXISTS idx_fileops_session ON file_operations(session_id)'
                )
                self._db.execute_sql(
                    'CREATE INDEX IF NOT EXISTS idx_fileops_call ON file_operations(call_id)'
                )

                self._initialized = True
                logger.info(f"[SessionStore] 初始化完成: {self._db_path}")

            except Exception as e:
                logger.error(f"[SessionStore] 初始化失败: {e}")
                raise

    @property
    def is_initialized(self) -> bool:
        return self._initialized and self._db is not None and self._db.is_connected

    def _execute(self, sql: str, params: tuple = ()) -> Tuple[bool, Any]:
        """执行 SQL（内部使用）"""
        if not self._db:
            return False, "数据库未初始化"
        return self._db.execute_sql(sql, params)

    def save_session(self, session: Dict) -> bool:
        """
        原子性保存单个会话

        Args:
            session: 会话数据字典，包含以下字段:
                - session_id: str
                - canvas_id: str
                - title: str
                - messages: List[Dict]
                - system_prompt: str
                - compaction_state: Dict
                - compaction_cache: Dict
                - message_count: int

        Returns:
            bool: 保存是否成功
        """
        if not self.is_initialized:
            logger.warning("[SessionStore] 未初始化，无法保存")
            return False

        session_id = session.get("session_id")
        if not session_id:
            logger.warning("[SessionStore] session_id 不能为空")
            return False

        try:
            # 构建会话数据
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session_data = {
                "session_id": session_id,
                "canvas_id": session.get("canvas_id", "default"),
                "title": session.get("title", ""),
                "messages": json.dumps(session.get("messages", []), ensure_ascii=False),
                "system_prompt": session.get("system_prompt", ""),
                "compaction_state": json.dumps(session.get("compaction_state", {})),
                "compaction_cache": json.dumps(session.get("compaction_cache", {})),
                "message_count": session.get("message_count", 0),
            }

            # 使用 INSERT OR REPLACE，使用本地时间
            success, result = self._execute(f'''
                INSERT OR REPLACE INTO {self.TABLE_NAME}
                (session_id, canvas_id, title, messages, system_prompt,
                 compaction_state, compaction_cache, message_count,
                 created_at, updated_at)
                VALUES (
                    :session_id, :canvas_id, :title, :messages, :system_prompt,
                    :compaction_state, :compaction_cache, :message_count,
                    COALESCE((SELECT created_at FROM {self.TABLE_NAME} WHERE session_id = :session_id), :now),
                    :now
                )
            ''', self._dict_to_params(session_data) + (now,))

            if not success:
                logger.error(f"[SessionStore] 保存失败: {result}")
                return False

            logger.debug(f"[SessionStore] 保存成功: {session_id}")
            return True

        except Exception as e:
            logger.error(f"[SessionStore] 保存异常: {e}")
            return False

    def _dict_to_params(self, d: Dict) -> Tuple:
        """将字典转换为参数元组（按字段顺序）"""
        fields = [
            "session_id", "canvas_id", "title", "messages", "system_prompt",
            "compaction_state", "compaction_cache", "message_count"
        ]
        return tuple(d.get(f) for f in fields)

    def load_sessions(self, canvas_id: str, limit: int = 100) -> List[Dict]:
        """
        加载指定画布的会话列表（按更新时间倒序）

        Args:
            canvas_id: 画布 ID
            limit: 返回数量限制

        Returns:
            List[Dict]: 会话列表
        """
        if not self.is_initialized:
            logger.warning("[SessionStore] 未初始化，返回空列表")
            return []

        try:
            success, rows = self._execute(f'''
                SELECT * FROM {self.TABLE_NAME}
                WHERE canvas_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (canvas_id, limit))

            if not success:
                logger.error(f"[SessionStore] 加载失败: {rows}")
                return []

            sessions = []
            for row in rows:
                session = self._row_to_session(row)
                sessions.append(session)

            logger.debug(f"[SessionStore] 加载 {len(sessions)} 条会话: canvas={canvas_id}")
            return sessions

        except Exception as e:
            logger.error(f"[SessionStore] 加载异常: {e}")
            return []

    def get_session(self, session_id: str) -> Optional[Dict]:
        """根据 session_id 获取单个会话"""
        if not self.is_initialized:
            return None

        success, rows = self._execute(
            f'SELECT * FROM {self.TABLE_NAME} WHERE session_id = ?',
            (session_id,)
        )

        if success and rows:
            return self._row_to_session(rows[0])
        return None

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if not self.is_initialized:
            return False

        success, _ = self._execute(
            f'DELETE FROM {self.TABLE_NAME} WHERE session_id = ?',
            (session_id,)
        )
        return success

    def _row_to_session(self, row: Dict) -> Dict:
        """将数据库行转换为会话对象"""
        # 处理 Row 对象
        if hasattr(row, 'keys'):
            session = {k: row[k] for k in row.keys()}
        else:
            session = dict(row) if isinstance(row, dict) else {}
        
        # 反序列化 JSON 字段
        try:
            messages_str = session.get("messages", "[]")
            session["messages"] = json.loads(messages_str) if isinstance(messages_str, str) else (messages_str or [])
        except (json.JSONDecodeError, TypeError):
            session["messages"] = []

        try:
            state_str = session.get("compaction_state", "{}")
            session["compaction_state"] = json.loads(state_str) if isinstance(state_str, str) else (state_str or {})
        except (json.JSONDecodeError, TypeError):
            session["compaction_state"] = {}

        try:
            cache_str = session.get("compaction_cache", "{}")
            session["compaction_cache"] = json.loads(cache_str) if isinstance(cache_str, str) else (cache_str or {})
        except (json.JSONDecodeError, TypeError):
            session["compaction_cache"] = {}

        # 添加兼容字段
        # 优先使用消息列表中最后一条消息的时间，而非数据库更新时间
        if "updated_at" in session:
            session["updated_at"] = session["updated_at"]
        if "messages" in session and session["messages"]:
            last_ts = session["messages"][-1].get("timestamp") if session["messages"] else None
            if last_ts:
                session["last_time"] = last_ts
            elif "updated_at" in session:
                session["last_time"] = session["updated_at"]
        elif "last_time" not in session and "updated_at" in session:
            session["last_time"] = session["updated_at"]
        if "saved_at" not in session:
            session["saved_at"] = session.get("created_at", "")

        return session

    def get_session_count(self, canvas_id: str) -> int:
        """获取指定画布的会话数量"""
        if not self.is_initialized:
            return 0

        success, result = self._execute(
            f'SELECT COUNT(*) FROM {self.TABLE_NAME} WHERE canvas_id = ?',
            (canvas_id,)
        )

        if success and result:
            first = result[0]
            if isinstance(first, (int, float)):
                return int(first)
            if isinstance(first, tuple):
                return int(first[0]) if first[0] else 0
        return 0

    def migrate_from_json(self, json_path: str) -> int:
        """
        从 JSON 文件迁移数据到 SQLite

        Args:
            json_path: JSON 文件路径

        Returns:
            int: 迁移的会话数量
        """
        from app.utils.utils import deserialize_from_json
        import json as json_module

        if not self.is_initialized:
            return 0

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = deserialize_from_json(json_module.load(f))

            if not isinstance(data, list):
                return 0

            count = 0
            for session in data:
                session_id = session.get("session_id")
                if session_id:
                    # 检查是否已存在
                    existing = self.get_session(session_id)
                    if not existing:
                        session["canvas_id"] = session.get("canvas_id", "default")
                        if self.save_session(session):
                            count += 1

            logger.info(f"[SessionStore] 从 {json_path} 迁移了 {count} 条会话")
            return count

        except Exception as e:
            logger.error(f"[SessionStore] 迁移失败: {e}")
            return 0

    def close(self):
        """关闭数据库连接"""
        if self._db:
            self._db.close()
            self._db = None
            self._initialized = False

    # ==================== 长期记忆操作 ====================

    def save_memory(self, memory: Dict, canvas_id: str = "default") -> bool:
        """
        保存单条长期记忆

        Args:
            memory: 记忆数据，包含 content, category, confidence, source 等
            canvas_id: 画布 ID

        Returns:
            bool: 保存是否成功
        """
        if not self.is_initialized:
            return False

        # 生成唯一的 memory_id
        existing_id = memory.get("memory_id") or memory.get("id")
        if existing_id:
            memory_id = str(existing_id)
        else:
            # 使用 content hash + timestamp 确保唯一性
            import hashlib
            content_hash = hashlib.md5(str(memory.get("content", "")).encode()).hexdigest()[:8]
            memory_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{content_hash}"
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        success, _ = self._execute(f'''
            INSERT OR REPLACE INTO {self.MEMORIES_TABLE}
            (memory_id, canvas_id, content, enabled, confidence, category, source,
             last_accessed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            memory_id,
            canvas_id,
            memory.get("content", ""),
            1 if memory.get("enabled", True) else 0,
            memory.get("confidence", 0.8),
            memory.get("category", "key_knowledge"),
            memory.get("source", ""),
            now,
            memory.get("created_at") or now,
            now,
        ))

        return success

    def save_memories(self, memories: List[Dict], canvas_id: str = "default") -> bool:
        """批量保存记忆（全量替换，先清空再插入）"""
        if not self.is_initialized or not self._db:
            return False

        # 使用原生连接，避免 DatabaseManager 自动 commit 破坏事务
        conn = self._db._conn
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            
            # 先清空该画布的所有记忆（确保删除操作生效）
            cursor.execute(f'DELETE FROM {self.MEMORIES_TABLE} WHERE canvas_id = ?', (canvas_id,))
            
            # 重新插入所有记忆
            for memory in memories:
                self._save_memory_with_cursor(cursor, memory, canvas_id)
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"[SessionStore] 批量保存记忆失败: {e}")
            return False

    def _save_memory_with_cursor(self, cursor, memory: Dict, canvas_id: str):
        """使用指定 cursor 保存记忆（不自动 commit）"""
        existing_id = memory.get("memory_id") or memory.get("id")
        if existing_id:
            memory_id = str(existing_id)
        else:
            import hashlib
            content_hash = hashlib.md5(str(memory.get("content", "")).encode()).hexdigest()[:8]
            memory_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{content_hash}"
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(f'''
            INSERT OR REPLACE INTO {self.MEMORIES_TABLE}
            (memory_id, canvas_id, content, enabled, confidence, category, source,
             last_accessed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            memory_id,
            canvas_id,
            memory.get("content", ""),
            1 if memory.get("enabled", True) else 0,
            memory.get("confidence", 0.8),
            memory.get("category", "key_knowledge"),
            memory.get("source", ""),
            now,
            memory.get("created_at") or now,
            now,
        ))

    def load_memories(self, canvas_id: str = "default", limit: int = 100, include_disabled: bool = False) -> List[Dict]:
        """加载长期记忆列表
        
        Args:
            canvas_id: 画布 ID
            limit: 返回数量限制
            include_disabled: 是否包含禁用的记忆
        """
        if not self.is_initialized:
            return []

        if include_disabled:
            success, rows = self._execute(f'''
                SELECT * FROM {self.MEMORIES_TABLE}
                WHERE canvas_id = ?
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
            ''', (canvas_id, limit))
        else:
            success, rows = self._execute(f'''
                SELECT * FROM {self.MEMORIES_TABLE}
                WHERE canvas_id = ? AND enabled = 1
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
            ''', (canvas_id, limit))

        if not success:
            return []

        memories = []
        for row in rows:
            memory = self._row_to_memory(row)
            memories.append(memory)
        return memories

    def _row_to_memory(self, row: Any) -> Dict:
        """将数据库行转换为记忆对象"""
        if hasattr(row, 'keys'):
            memory = {k: row[k] for k in row.keys()}
        else:
            memory = dict(row) if isinstance(row, dict) else {}

        # 转换字段
        memory["memory_id"] = memory.get("memory_id", memory.get("id", ""))
        memory["enabled"] = bool(memory.get("enabled", 1))
        return memory

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if not self.is_initialized:
            return False

        success, _ = self._execute(
            f'DELETE FROM {self.MEMORIES_TABLE} WHERE memory_id = ?',
            (memory_id,)
        )
        return success

    def clear_memories(self, canvas_id: str = "default") -> bool:
        """清空指定画布的所有记忆"""
        if not self.is_initialized:
            return False

        success, _ = self._execute(
            f'DELETE FROM {self.MEMORIES_TABLE} WHERE canvas_id = ?',
            (canvas_id,)
        )
        return success

    def migrate_memories_from_json(self, json_path: str, canvas_id: str = "default") -> int:
        """
        从 JSON 文件迁移记忆到 SQLite

        Args:
            json_path: JSON 文件路径
            canvas_id: 画布 ID

        Returns:
            int: 迁移的记忆数量
        """
        import json as json_module

        if not self.is_initialized:
            return 0

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json_module.load(f)

            memories = data.get("user_memories", [])
            count = 0
            for memory in memories:
                if self.save_memory(memory, canvas_id):
                    count += 1

            logger.info(f"[SessionStore] 从 {json_path} 迁移了 {count} 条记忆")
            return count

        except Exception as e:
            logger.error(f"[SessionStore] 记忆迁移失败: {e}")
            return 0

    # ==================== 文件操作记录（撤销功能）====================

    def record_file_operation(self, session_id: str, call_id: str,
                             tool_name: str, file_path: str,
                             backup_path: str) -> bool:
        """
        记录文件操作

        Args:
            session_id: 会话 ID
            call_id: 工具调用 ID
            tool_name: 工具名称
            file_path: 操作的文件路径
            backup_path: 备份文件路径

        Returns:
            bool: 记录是否成功
        """
        if not self.is_initialized:
            return False

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        success, _ = self._execute('''
            INSERT INTO file_operations
            (session_id, call_id, tool_name, file_path, backup_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, call_id, tool_name, file_path, backup_path, now))

        return success

    def get_file_operations_after_call(self, session_id: str, call_id: str) -> List[Dict]:
        """
        获取某 call_id 之后的所有文件操作（用于撤销）

        Args:
            session_id: 会话 ID
            call_id: 目标 call_id，获取该 call_id 之后的所有操作

        Returns:
            List[Dict]: 按时间正序排列的操作列表
        """
        
        if not self.is_initialized:
            logger.warning("[SessionStore] 未初始化")
            return []

        # 获取目标 call_id 的 id（用于比较）
        success, rows = self._execute('''
            SELECT id FROM file_operations
            WHERE session_id = ? AND call_id = ?
            LIMIT 1
        ''', (session_id, call_id))

        
        
        if not success or not rows:
            return []

        target_id = rows[0][0] if isinstance(rows[0], tuple) else rows[0].get('id')
        

        # 获取该 id 之后的所有操作（正序，用于逆序回滚）
        success, ops = self._execute('''
            SELECT * FROM file_operations
            WHERE session_id = ? AND id > ?
            ORDER BY id ASC
        ''', (session_id, target_id))

        if not success:
            return []

        result = []
        for row in ops:
            if hasattr(row, 'keys'):
                op = {k: row[k] for k in row.keys()}
            else:
                op = dict(row) if isinstance(row, dict) else {}
            result.append(op)

        
        return result

    def get_file_operations_by_call_id(self, session_id: str, call_id: str) -> List[Dict]:
        """
        根据 call_id 获取文件操作记录

        Args:
            session_id: 会话 ID
            call_id: 工具调用 ID

        Returns:
            List[Dict]: 操作列表
        """
        
        if not self.is_initialized:
            return []

        success, ops = self._execute('''
            SELECT * FROM file_operations
            WHERE session_id = ? AND call_id = ?
            ORDER BY id ASC
        ''', (session_id, call_id))

        if not success:
            return []

        result = []
        for row in ops:
            if hasattr(row, 'keys'):
                op = {k: row[k] for k in row.keys()}
            else:
                op = dict(row) if isinstance(row, dict) else {}
            result.append(op)

        return result

    def get_all_file_operations(self, session_id: str) -> List[Dict]:
        """获取指定会话的所有文件操作"""
        
        if not self.is_initialized:
            return []

        success, ops = self._execute('''
            SELECT * FROM file_operations
            WHERE session_id = ?
            ORDER BY id ASC
        ''', (session_id,))

        if not success:
            return []

        result = []
        for row in ops:
            if hasattr(row, 'keys'):
                op = {k: row[k] for k in row.keys()}
            else:
                op = dict(row) if isinstance(row, dict) else {}
            result.append(op)

        logger.info(f"[SessionStore] 返回 {len(result)} 个操作")
        return result

    def delete_file_operations_after_id(self, session_id: str, after_id: int) -> int:
        """
        删除指定 session 中 id 大于 after_id 的所有操作记录

        Args:
            session_id: 会话 ID
            after_id: 起始 ID

        Returns:
            int: 删除的记录数量
        """
        if not self.is_initialized:
            return 0

        success, result = self._execute('''
            DELETE FROM file_operations
            WHERE session_id = ? AND id > ?
        ''', (session_id, after_id))

        if success and result:
            return result[0] if isinstance(result[0], tuple) else result
        return 0

    def clear_session_file_operations(self, session_id: str) -> Tuple[int, List[str]]:
        """
        清空会话的所有文件操作记录，返回被删除的备份文件路径列表

        Args:
            session_id: 会话 ID

        Returns:
            Tuple[int, List[str]]: (删除的记录数, 备份文件路径列表)
        """
        if not self.is_initialized:
            return 0, []

        # 先获取所有备份文件路径
        success, rows = self._execute(
            'SELECT backup_path FROM file_operations WHERE session_id = ?',
            (session_id,)
        )

        backup_paths = []
        if success and rows:
            for row in rows:
                path = row[0] if isinstance(row, tuple) else row.get('backup_path', '')
                if path:
                    backup_paths.append(path)

        # 删除记录
        success, result = self._execute(
            'DELETE FROM file_operations WHERE session_id = ?',
            (session_id,)
        )

        deleted_count = 0
        if success and result:
            deleted_count = result[0] if isinstance(result[0], tuple) else result

        return deleted_count, backup_paths