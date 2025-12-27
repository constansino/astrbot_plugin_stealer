"""
清理管理器

实现智能清理操作，协调原始目录和分类目录的清理，
防止孤立文件和竞态条件。
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# 简单的logger替代品
class SimpleLogger:
    def debug(self, msg): print(f"DEBUG: {msg}")
    def info(self, msg): print(f"INFO: {msg}")
    def warning(self, msg): print(f"WARNING: {msg}")
    def error(self, msg): print(f"ERROR: {msg}")

try:
    from astrbot.api import logger
except ImportError:
    logger = SimpleLogger()

from .database import DatabaseManager
from .lifecycle_manager import FileLifecycleManager
from .statistics_tracker import StatisticsTracker
from .models import (
    CleanupError,
    CleanupResult,
    CleanupStats,
    LifecycleRecord,
    OrphanedFile,
    ProcessingEventType,
    ProcessingStatus,
    RetentionPolicy,
)


class CleanupManager:
    """清理管理器
    
    负责协调智能清理操作，检查文件生命周期状态，
    防止孤立文件和竞态条件。
    """
    
    def __init__(self, 
                 database_manager: DatabaseManager,
                 lifecycle_manager: FileLifecycleManager,
                 statistics_tracker: Optional[StatisticsTracker] = None):
        """初始化清理管理器
        
        Args:
            database_manager: 数据库管理器实例
            lifecycle_manager: 文件生命周期管理器实例
            statistics_tracker: 统计跟踪器实例（可选）
        """
        self.db = database_manager
        self.lifecycle_manager = lifecycle_manager
        self.stats_tracker = statistics_tracker
        self._lock = asyncio.Lock()
        
    async def perform_coordinated_cleanup(self, 
                                        retention_policy: RetentionPolicy,
                                        raw_directory: Optional[Path] = None,
                                        categories_directory: Optional[Path] = None) -> CleanupResult:
        """执行协调清理
        
        协调原始目录和分类目录的清理操作，防止竞态条件。
        
        Args:
            retention_policy: 保留策略
            raw_directory: 原始文件目录（可选）
            categories_directory: 分类文件目录（可选）
            
        Returns:
            CleanupResult: 清理结果
            
        Validates: Requirements 2.6
        """
        async with self._lock:
            start_time = datetime.now()
            result = CleanupResult()
            
            try:
                logger.info("开始协调清理操作")
                
                # 1. 首先检测孤立文件
                orphaned_files = await self.detect_orphaned_files()
                orphan_stats = await self._cleanup_orphaned_files(orphaned_files)
                result.orphaned_files_removed = orphan_stats.files_removed
                result.space_freed += orphan_stats.space_freed
                result.errors.extend(orphan_stats.errors)
                
                # 2. 清理原始目录
                if raw_directory:
                    raw_stats = await self.cleanup_raw_directory(retention_policy, raw_directory)
                    result.raw_files_removed = raw_stats.files_removed
                    result.space_freed += raw_stats.space_freed
                    result.errors.extend(raw_stats.errors)
                
                # 3. 清理分类目录
                if categories_directory:
                    cat_stats = await self.cleanup_categories_directory(retention_policy, categories_directory)
                    result.categorized_files_removed = cat_stats.files_removed
                    result.space_freed += cat_stats.space_freed
                    result.errors.extend(cat_stats.errors)
                
                # 4. 记录清理统计
                if self.stats_tracker:
                    await self.stats_tracker.record_processing_event(
                        ProcessingEventType.CLEANUP_PERFORMED,
                        {
                            'raw_files_removed': result.raw_files_removed,
                            'categorized_files_removed': result.categorized_files_removed,
                            'orphaned_files_removed': result.orphaned_files_removed,
                            'space_freed': result.space_freed,
                            'errors_count': len(result.errors)
                        }
                    )
                
                result.duration = datetime.now() - start_time
                logger.info(f"协调清理完成: 删除 {result.raw_files_removed + result.categorized_files_removed + result.orphaned_files_removed} 个文件，释放 {result.space_freed} 字节")
                
                return result
                
            except Exception as e:
                error = CleanupError(
                    file_path="",
                    error_message=str(e),
                    error_type="coordination_error"
                )
                result.errors.append(error)
                result.duration = datetime.now() - start_time
                logger.error(f"协调清理异常: {e}")
                return result
                
    async def cleanup_raw_directory(self, 
                                  retention_policy: RetentionPolicy,
                                  raw_directory: Path) -> CleanupStats:
        """清理原始目录
        
        根据保留策略清理原始目录中的文件。
        
        Args:
            retention_policy: 保留策略
            raw_directory: 原始文件目录
            
        Returns:
            CleanupStats: 清理统计
            
        Validates: Requirements 2.1, 2.4
        """
        start_time = datetime.now()
        stats = CleanupStats()
        
        try:
            logger.debug(f"开始清理原始目录: {raw_directory}")
            
            if not raw_directory.exists():
                logger.warning(f"原始目录不存在: {raw_directory}")
                return stats
            
            # 获取所有生命周期记录
            all_records = []
            for status in ProcessingStatus:
                records = await self.lifecycle_manager.get_files_by_status(status)
                all_records.extend(records)
            
            # 检查每个记录是否符合清理条件
            for record in all_records:
                if await self.is_eligible_for_cleanup(record, retention_policy):
                    # 检查文件是否存在
                    if os.path.exists(record.raw_file_path):
                        try:
                            # 获取文件大小
                            file_size = os.path.getsize(record.raw_file_path)
                            
                            # 标记为待删除
                            await self.lifecycle_manager.mark_for_deletion(record.record_id)
                            
                            # 删除文件
                            os.remove(record.raw_file_path)
                            
                            stats.files_removed += 1
                            stats.space_freed += file_size
                            
                            logger.debug(f"已删除原始文件: {record.raw_file_path}")
                            
                        except Exception as e:
                            error = CleanupError(
                                file_path=record.raw_file_path,
                                error_message=str(e),
                                error_type="file_deletion_error"
                            )
                            stats.errors.append(error)
                            logger.error(f"删除原始文件失败: {record.raw_file_path}, 错误: {e}")
            
            stats.duration = datetime.now() - start_time
            logger.debug(f"原始目录清理完成: 删除 {stats.files_removed} 个文件")
            return stats
            
        except Exception as e:
            error = CleanupError(
                file_path=str(raw_directory),
                error_message=str(e),
                error_type="directory_cleanup_error"
            )
            stats.errors.append(error)
            stats.duration = datetime.now() - start_time
            logger.error(f"清理原始目录异常: {e}")
            return stats
            
    async def cleanup_categories_directory(self, 
                                         retention_policy: RetentionPolicy,
                                         categories_directory: Path) -> CleanupStats:
        """清理分类目录
        
        清理分类目录中的文件，确保与原始文件的一致性。
        
        Args:
            retention_policy: 保留策略
            categories_directory: 分类文件目录
            
        Returns:
            CleanupStats: 清理统计
            
        Validates: Requirements 2.2
        """
        start_time = datetime.now()
        stats = CleanupStats()
        
        try:
            logger.debug(f"开始清理分类目录: {categories_directory}")
            
            if not categories_directory.exists():
                logger.warning(f"分类目录不存在: {categories_directory}")
                return stats
            
            # 获取所有已标记为删除的记录
            marked_records = await self.lifecycle_manager.get_files_by_status(ProcessingStatus.MARKED_FOR_DELETION)
            
            # 删除对应的分类文件
            for record in marked_records:
                if record.categorized_file_path and os.path.exists(record.categorized_file_path):
                    try:
                        # 获取文件大小
                        file_size = os.path.getsize(record.categorized_file_path)
                        
                        # 删除分类文件
                        os.remove(record.categorized_file_path)
                        
                        stats.files_removed += 1
                        stats.space_freed += file_size
                        
                        logger.debug(f"已删除分类文件: {record.categorized_file_path}")
                        
                    except Exception as e:
                        error = CleanupError(
                            file_path=record.categorized_file_path,
                            error_message=str(e),
                            error_type="file_deletion_error"
                        )
                        stats.errors.append(error)
                        logger.error(f"删除分类文件失败: {record.categorized_file_path}, 错误: {e}")
            
            stats.duration = datetime.now() - start_time
            logger.debug(f"分类目录清理完成: 删除 {stats.files_removed} 个文件")
            return stats
            
        except Exception as e:
            error = CleanupError(
                file_path=str(categories_directory),
                error_message=str(e),
                error_type="directory_cleanup_error"
            )
            stats.errors.append(error)
            stats.duration = datetime.now() - start_time
            logger.error(f"清理分类目录异常: {e}")
            return stats
            
    async def detect_orphaned_files(self) -> List[OrphanedFile]:
        """检测孤立文件
        
        检测失去对应关系的孤立文件。
        
        Returns:
            List[OrphanedFile]: 孤立文件列表
            
        Validates: Requirements 2.3
        """
        try:
            # 使用生命周期管理器检测孤立文件
            orphaned_files = await self.lifecycle_manager.find_orphaned_files()
            
            logger.debug(f"检测到 {len(orphaned_files)} 个孤立文件")
            return orphaned_files
            
        except Exception as e:
            logger.error(f"检测孤立文件异常: {e}")
            return []
            
    async def is_eligible_for_cleanup(self, 
                                    record: LifecycleRecord, 
                                    policy: RetentionPolicy) -> bool:
        """检查文件是否符合清理条件
        
        根据多个时间因素判断文件是否可以清理。
        
        Args:
            record: 生命周期记录
            policy: 保留策略
            
        Returns:
            bool: 是否符合清理条件
            
        Validates: Requirements 2.4
        """
        try:
            now = datetime.now()
            
            # 检查文件年龄
            age_days = (now - record.creation_timestamp).days
            if age_days < policy.max_age_days:
                return False
            
            # 检查最后访问时间
            if record.last_access_timestamp:
                access_age_days = (now - record.last_access_timestamp).days
                if access_age_days < policy.max_access_age_days:
                    return False
            
            # 检查处理状态
            if record.status == ProcessingStatus.PROCESSING:
                return False  # 正在处理的文件不能删除
            
            # 检查失败文件的特殊保留期
            if record.status == ProcessingStatus.FAILED:
                failure_age_days = (now - (record.processing_timestamp or record.creation_timestamp)).days
                if failure_age_days < policy.failure_retention_days:
                    return False
            
            # 检查优先级文件的特殊保留期
            if record.priority_level > 0:
                priority_age_days = (now - record.creation_timestamp).days
                if priority_age_days < policy.priority_image_retention:
                    return False
            
            # 检查分类特定策略
            if record.category and record.category in policy.category_specific_policies:
                cat_policy = policy.category_specific_policies[record.category]
                
                # 检查分类特定的年龄限制
                if age_days < cat_policy.max_age_days:
                    return False
                
                # 检查分类特定的访问时间限制
                if record.last_access_timestamp:
                    access_age_days = (now - record.last_access_timestamp).days
                    if access_age_days < cat_policy.max_access_age_days:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查清理条件异常: {e}")
            return False
            
    async def _cleanup_orphaned_files(self, orphaned_files: List[OrphanedFile]) -> CleanupStats:
        """清理孤立文件
        
        Args:
            orphaned_files: 孤立文件列表
            
        Returns:
            CleanupStats: 清理统计
        """
        start_time = datetime.now()
        stats = CleanupStats()
        
        try:
            for orphaned_file in orphaned_files:
                if os.path.exists(orphaned_file.file_path):
                    try:
                        # 删除孤立文件
                        os.remove(orphaned_file.file_path)
                        
                        stats.files_removed += 1
                        stats.space_freed += orphaned_file.size
                        
                        logger.debug(f"已删除孤立文件: {orphaned_file.file_path}")
                        
                    except Exception as e:
                        error = CleanupError(
                            file_path=orphaned_file.file_path,
                            error_message=str(e),
                            error_type="orphan_cleanup_error"
                        )
                        stats.errors.append(error)
                        logger.error(f"删除孤立文件失败: {orphaned_file.file_path}, 错误: {e}")
            
            stats.duration = datetime.now() - start_time
            logger.debug(f"孤立文件清理完成: 删除 {stats.files_removed} 个文件")
            return stats
            
        except Exception as e:
            error = CleanupError(
                file_path="",
                error_message=str(e),
                error_type="orphan_cleanup_error"
            )
            stats.errors.append(error)
            stats.duration = datetime.now() - start_time
            logger.error(f"清理孤立文件异常: {e}")
            return stats
            
    async def get_cleanup_candidates(self, 
                                   retention_policy: RetentionPolicy) -> List[LifecycleRecord]:
        """获取清理候选文件
        
        返回符合清理条件的文件列表，但不执行实际清理。
        
        Args:
            retention_policy: 保留策略
            
        Returns:
            List[LifecycleRecord]: 清理候选文件列表
        """
        try:
            candidates = []
            
            # 获取所有生命周期记录
            all_records = []
            for status in ProcessingStatus:
                records = await self.lifecycle_manager.get_files_by_status(status)
                all_records.extend(records)
            
            # 检查每个记录是否符合清理条件
            for record in all_records:
                if await self.is_eligible_for_cleanup(record, retention_policy):
                    candidates.append(record)
            
            logger.debug(f"找到 {len(candidates)} 个清理候选文件")
            return candidates
            
        except Exception as e:
            logger.error(f"获取清理候选文件异常: {e}")
            return []
            
    async def estimate_cleanup_impact(self, 
                                    retention_policy: RetentionPolicy) -> Dict[str, Any]:
        """估算清理影响
        
        估算执行清理操作的影响，包括文件数量和空间释放。
        
        Args:
            retention_policy: 保留策略
            
        Returns:
            Dict[str, Any]: 清理影响估算
        """
        try:
            candidates = await self.get_cleanup_candidates(retention_policy)
            orphaned_files = await self.detect_orphaned_files()
            
            total_files = len(candidates) + len(orphaned_files)
            total_space = sum(record.file_size for record in candidates) + sum(f.size for f in orphaned_files)
            
            impact = {
                'candidate_files': len(candidates),
                'orphaned_files': len(orphaned_files),
                'total_files': total_files,
                'estimated_space_freed': total_space,
                'categories_affected': list(set(record.category for record in candidates if record.category)),
                'oldest_file_age_days': max(
                    [(datetime.now() - record.creation_timestamp).days for record in candidates],
                    default=0
                )
            }
            
            logger.debug(f"清理影响估算: {impact}")
            return impact
            
        except Exception as e:
            logger.error(f"估算清理影响异常: {e}")
            return {}
            
    async def cleanup(self):
        """清理资源"""
        # 目前没有需要清理的资源
        pass