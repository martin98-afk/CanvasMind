# -*- coding: utf-8 -*-
"""
文件操作记录器 - 支持撤销功能

用于记录文件操作并在需要时回滚
"""

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from loguru import logger

from app.llm_chatter.utils.session_store import SessionStore


@dataclass
class RollbackResult:
    """回滚结果"""
    success_count: int = 0
    failed_count: int = 0
    failed_files: List[str] = None

    def __post_init__(self):
        if self.failed_files is None:
            self.failed_files = []


class FileOperationRecorder:
    """
    文件操作记录器

    在文件操作前备份，记录操作信息，支持撤销回滚
    """

    # 支持记录的文件操作类型
    TRACKED_OPERATIONS = {
        "write", "edit", "multiedit", "patch",  # tool_executor 中的名称
        "write_file", "edit_file", "multi_edit", "apply_patch", "delete_file",  # 兼容别名
    }

    def __init__(self, session_store: Optional[SessionStore] = None):
        self._session_store = session_store or SessionStore(db_dir="canvas_files")
        self._backup_base_dir = Path("canvas_files") / "backups"

    def is_tracked_operation(self, tool_name: str) -> bool:
        """判断是否为需要记录的操作"""
        return tool_name in self.TRACKED_OPERATIONS

    # 编辑后备份文件的后缀
    AFTER_BACKUP_SUFFIX = ".after.bak"

    def record_operation(self, session_id: str, call_id: str,
                        tool_name: str, file_path: str) -> Optional[str]:
        """
        记录文件操作前先备份

        Args:
            session_id: 会话 ID
            call_id: 工具调用 ID
            tool_name: 工具名称
            file_path: 目标文件路径

        Returns:
            str: 备份文件路径，失败返回 None
        """
        
        
        if not self.is_tracked_operation(tool_name):
            logger.debug(f"[FileRecorder] 工具不在追踪列表: {tool_name}")
            return None

        try:
            resolved_path = Path(file_path).resolve()
            

            # 如果文件不存在，可能是新建的文件，创建一个空备份文件用于差异比较
            file_existed = resolved_path.exists()
            if not file_existed:
                # 创建备份目录
                backup_dir = self._backup_base_dir / session_id
                backup_dir.mkdir(parents=True, exist_ok=True)
                
                # 生成备份文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = self._sanitize_filename(resolved_path.name)
                call_prefix = call_id[:8] if len(call_id) >= 8 else call_id
                backup_name = f"{safe_name}_{timestamp}_{call_prefix}.bak"
                backup_path = backup_dir / backup_name
                
                # 创建一个空的备份文件
                backup_path.touch()
                logger.info(f"[FileRecorder] 新文件已创建空备份: {file_path} -> {backup_path}")
                
                # 记录到数据库
                self._session_store.record_file_operation(
                    session_id=session_id,
                    call_id=call_id,
                    tool_name=tool_name,
                    file_path=str(resolved_path),
                    backup_path=str(backup_path)
                )
                
                return str(backup_path)

            # 创建备份目录
            backup_dir = self._backup_base_dir / session_id
            backup_dir.mkdir(parents=True, exist_ok=True)

            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._sanitize_filename(resolved_path.name)
            call_prefix = call_id[:8] if len(call_id) >= 8 else call_id
            backup_name = f"{safe_name}_{timestamp}_{call_prefix}.bak"
            backup_path = backup_dir / backup_name

            # 复制文件到备份
            shutil.copy2(resolved_path, backup_path)
            logger.info(f"[FileRecorder] 已备份: {file_path} -> {backup_path}")

            # 记录到数据库
            
            self._session_store.record_file_operation(
                session_id=session_id,
                call_id=call_id,
                tool_name=tool_name,
                file_path=str(resolved_path),
                backup_path=str(backup_path)
            )
            

            return str(backup_path)

        except Exception as e:
            logger.error(f"[FileRecorder] 备份失败: {e}")
            import traceback
            
            return None

    def record_after_operation(self, session_id: str, call_id: str,
                               tool_name: str, file_path: str) -> Optional[str]:
        """
        记录文件操作后的备份（用于差异对比）

        Args:
            session_id: 会话 ID
            call_id: 工具调用 ID
            tool_name: 工具名称
            file_path: 目标文件路径

        Returns:
            str: 编辑后备份文件路径，失败返回 None
        """
        if not self.is_tracked_operation(tool_name):
            return None

        try:
            resolved_path = Path(file_path).resolve()
            
            # 获取对应的备份路径
            backup_path = self._get_backup_path(session_id, call_id)
            if not backup_path:
                logger.warning(f"[FileRecorder] 未找到对应的备份路径: session={session_id}, call={call_id}")
                return None
            
            backup_file = Path(backup_path)
            # 生成编辑后备份路径：xxx.bak -> xxx.after.bak
            after_backup_path = backup_file.with_suffix('.after.bak')
            
            # 如果文件不存在（被删除），创建空文件
            if not resolved_path.exists():
                after_backup_path.touch()
            else:
                shutil.copy2(resolved_path, after_backup_path)
            
            logger.info(f"[FileRecorder] 已备份编辑后: {file_path} -> {after_backup_path}")
            return str(after_backup_path)

        except Exception as e:
            logger.error(f"[FileRecorder] 编辑后备份失败: {e}")
            return None

    def _get_backup_path(self, session_id: str, call_id: str) -> Optional[str]:
        """根据 session_id 和 call_id 获取备份路径"""
        operations = self._session_store.get_file_operations_by_call_id(session_id, call_id)
        if operations:
            return operations[0].get("backup_path")
        return None

    def _get_after_backup_path(self, backup_path: str) -> str:
        """根据备份路径获取编辑后备份路径"""
        return str(Path(backup_path).with_suffix(self.AFTER_BACKUP_SUFFIX))

    def _cleanup_backup_files(self, backup_path: str):
        """清理备份文件及其对应的编辑后备份"""
        try:
            backup_file = Path(backup_path)
            # 删除主备份文件
            if backup_file.exists():
                backup_file.unlink()
                logger.debug(f"[FileRecorder] 已删除备份: {backup_file}")
            
            # 删除编辑后备份文件
            after_backup = self._get_after_backup_path(backup_path)
            after_file = Path(after_backup)
            if after_file.exists():
                after_file.unlink()
                logger.debug(f"[FileRecorder] 已删除编辑后备份: {after_file}")
        except Exception as e:
            logger.warning(f"[FileRecorder] 清理备份失败: {e}")

        except Exception as e:
            logger.error(f"[FileRecorder] 备份失败: {e}")
            import traceback
            
            return None

    def get_operations_for_preview(self, session_id: str, call_id: str) -> List[Dict]:
        """
        获取指定 call_id 的操作记录

        Args:
            session_id: 会话 ID
            call_id: 工具调用 ID

        Returns:
            List[Dict]: 操作列表
        """
        
        operations = self._session_store.get_file_operations_by_call_id(session_id, call_id)
        
        return operations

    def get_all_operations_for_session(self, session_id: str) -> List[Dict]:
        """获取指定会话的所有文件操作"""
        
        return self._session_store.get_all_file_operations(session_id)

    def rollback_operations(self, operations: List[Dict]) -> RollbackResult:
        """
        回滚一组操作

        Args:
            operations: 操作列表（应按时间正序传入）

        Returns:
            RollbackResult: 回滚结果
        """
        result = RollbackResult()

        # 逆序回滚（后执行的操作先回滚）
        for op in reversed(operations):
            try:
                file_path = op.get("file_path")
                backup_path = op.get("backup_path")
                tool_name = op.get("tool_name", "")

                if not file_path:
                    continue

                # 处理 write_file 和 delete_file
                if tool_name == "delete_file":
                    # delete_file 的备份文件实际上是原文件，撤销时恢复
                    if backup_path and Path(backup_path).exists():
                        resolved_path = Path(file_path)
                        resolved_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup_path, resolved_path)
                        Path(backup_path).unlink()
                        result.success_count += 1
                        logger.info(f"[FileRecorder] 已恢复删除的文件: {file_path}")
                    continue

                # 检查备份文件是否存在
                if not backup_path or not Path(backup_path).exists():
                    logger.warning(f"[FileRecorder] 备份文件不存在: {backup_path}")
                    result.failed_count += 1
                    result.failed_files.append(file_path)
                    continue

                backup_file = Path(backup_path)
                
                # 检查是否是新建文件（备份文件为空）
                is_new_file = backup_file.stat().st_size == 0
                
                if is_new_file:
                    # 新建文件的回滚：删除创建的文件
                    resolved_path = Path(file_path)
                    if resolved_path.exists():
                        resolved_path.unlink()
                    backup_file.unlink()
                    result.success_count += 1
                    logger.info(f"[FileRecorder] 已删除新建的文件: {file_path}")
                else:
                    # 恢复备份文件
                    resolved_path = Path(file_path)
                    shutil.copy2(backup_file, resolved_path)

                    # 删除备份文件（包括编辑后备份）
                    self._cleanup_backup_files(backup_path)

                    result.success_count += 1
                    logger.info(f"[FileRecorder] 已回滚: {file_path}")

            except FileNotFoundError:
                # 文件已被外部删除，跳过
                result.failed_count += 1
                result.failed_files.append(op.get("file_path", "unknown"))
                logger.warning(f"[FileRecorder] 文件已被删除，无法回滚: {op.get('file_path')}")
            except PermissionError as e:
                result.failed_count += 1
                result.failed_files.append(op.get("file_path", "unknown"))
                logger.error(f"[FileRecorder] 权限错误: {e}")
            except Exception as e:
                result.failed_count += 1
                result.failed_files.append(op.get("file_path", "unknown"))
                logger.error(f"[FileRecorder] 回滚失败: {e}")

        return result

    def clear_session(self, session_id: str) -> Tuple[int, List[str]]:
        """
        清空会话的所有文件操作和备份

        Args:
            session_id: 会话 ID

        Returns:
            Tuple[int, List[str]]: (删除的记录数, 备份文件路径列表)
        """
        deleted_count, backup_paths = self._session_store.clear_session_file_operations(session_id)

        # 删除备份文件（包括编辑后备份）
        for backup_path in backup_paths:
            self._cleanup_backup_files(backup_path)

        # 删除备份目录（如果为空）
        backup_dir = self._backup_base_dir / session_id
        if backup_dir.exists() and not any(backup_dir.iterdir()):
            try:
                backup_dir.rmdir()
            except Exception:
                pass

        return deleted_count, backup_paths

    def _sanitize_filename(self, filename: str) -> str:
        """移除文件名中不合法的字符"""
        import re
        return re.sub(r'[<>:"/\\|?*]', "_", filename)
