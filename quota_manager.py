"""
存储配额管理器

实现智能配额执行，支持多种配额策略，基于使用模式和图像质量的优先级删除，
早期警告系统和优先级图像的保留空间。
"""

import asyncio
import uuid
from datetime import datetime, timedelta
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
from .cleanup_manager import CleanupManager
from .models import (
    LifecycleRecord,
    ProcessingEventType,
    ProcessingStatus,
    QuotaEnforcementResult,
    QuotaStatus,
    QuotaStrategy,
    QuotaWarning,
    RemovalCandidate,
    RetentionPolicy,
)


class StorageQuotaManager:
    """存储配额管理器
    
    负责监控存储使用情况，实施智能配额执行，
    支持多种配额策略和优先级管理。
    """
    
    def __init__(self, 
                 database_manager: DatabaseManager,
                 lifecycle_manager: FileLifecycleManager,
                 cleanup_manager: CleanupManager,
                 statistics_tracker: Optional[StatisticsTracker] = None):
        """初始化存储配额管理器
        
        Args:
            database_manager: 数据库管理器实例
            lifecycle_manager: 文件生命周期管理器实例
            cleanup_manager: 清理管理器实例
            statistics_tracker: 统计跟踪器实例（可选）
        """
        self.db = database_manager
        self.lifecycle_manager = lifecycle_manager
        self.cleanup_manager = cleanup_manager
        self.stats_tracker = statistics_tracker
        self._lock = asyncio.Lock()
        
        # 默认配额配置
        self.max_count = 10000  # 最大文件数
        self.max_size = 1024 * 1024 * 1024  # 最大大小（1GB）
        self.quota_strategy = QuotaStrategy.HYBRID
        self.warning_threshold = 0.8  # 80%警告阈值
        self.critical_threshold = 0.95  # 95%临界阈值
        self.reserved_space_percentage = 0.1  # 10%保留空间
        
    async def check_quota_status(self) -> QuotaStatus:
        """检查配额状态
        
        监控当前存储使用情况并返回配额状态。
        
        Returns:
            QuotaStatus: 当前配额状态
            
        Validates: Requirements 4.3
        """
        try:
            # 获取当前存储统计
            stats = await self.lifecycle_manager.get_statistics()
            
            current_count = stats.get('total_records', 0)
            current_size = stats.get('total_size', 0)
            
            # 计算使用百分比
            count_percentage = current_count / self.max_count if self.max_count > 0 else 0.0
            size_percentage = current_size / self.max_size if self.max_size > 0 else 0.0
            
            # 根据策略确定主要使用百分比
            if self.quota_strategy == QuotaStrategy.COUNT_BASED:
                usage_percentage = count_percentage
            elif self.quota_strategy == QuotaStrategy.SIZE_BASED:
                usage_percentage = size_percentage
            else:  # HYBRID
                usage_percentage = max(count_percentage, size_percentage)
            
            # 检查警告和临界状态
            is_warning = usage_percentage >= self.warning_threshold
            is_critical = usage_percentage >= self.critical_threshold
            
            quota_status = QuotaStatus(
                current_count=current_count,
                max_count=self.max_count,
                current_size=current_size,
                max_size=self.max_size,
                usage_percentage=usage_percentage,
                warning_threshold=self.warning_threshold,
                critical_threshold=self.critical_threshold,
                is_warning=is_warning,
                is_critical=is_critical
            )
            
            logger.debug(f"配额状态: 使用率={usage_percentage:.1%}, 警告={is_warning}, 临界={is_critical}")
            return quota_status
            
        except Exception as e:
            logger.error(f"检查配额状态异常: {e}")
            return QuotaStatus()
            
    async def enforce_quota_limits(self) -> QuotaEnforcementResult:
        """执行配额限制
        
        当存储超过限制时，执行智能清理以释放空间。
        
        Returns:
            QuotaEnforcementResult: 配额执行结果
            
        Validates: Requirements 4.1, 4.4
        """
        async with self._lock:
            result = QuotaEnforcementResult()
            
            try:
                logger.info("开始执行配额限制")
                
                # 检查当前配额状态
                quota_status = await self.check_quota_status()
                
                # 生成警告
                warnings = await self.get_quota_warnings()
                result.warnings_generated = warnings
                
                # 如果未超过临界阈值，只生成警告
                if not quota_status.is_critical:
                    logger.debug("未超过临界阈值，仅生成警告")
                    return result
                
                # 计算需要释放的空间
                target_usage = self.warning_threshold  # 降到警告阈值以下
                
                if self.quota_strategy == QuotaStrategy.COUNT_BASED:
                    target_count = int(self.max_count * target_usage)
                    files_to_remove = quota_status.current_count - target_count
                    space_to_free = 0
                elif self.quota_strategy == QuotaStrategy.SIZE_BASED:
                    target_size = int(self.max_size * target_usage)
                    space_to_free = quota_status.current_size - target_size
                    files_to_remove = 0
                else:  # HYBRID
                    target_count = int(self.max_count * target_usage)
                    target_size = int(self.max_size * target_usage)
                    files_to_remove = max(0, quota_status.current_count - target_count)
                    space_to_free = max(0, quota_status.current_size - target_size)
                
                logger.info(f"需要删除文件: {files_to_remove}, 需要释放空间: {space_to_free} 字节")
                
                # 获取删除候选文件
                candidates = await self.calculate_removal_priority()
                
                # 执行删除
                removed_files = 0
                freed_space = 0
                
                for candidate in candidates:
                    if (files_to_remove > 0 and removed_files >= files_to_remove) or \
                       (space_to_free > 0 and freed_space >= space_to_free):
                        break
                    
                    try:
                        # 标记文件为删除
                        success = await self.lifecycle_manager.mark_for_deletion(candidate.record.record_id)
                        if success:
                            removed_files += 1
                            freed_space += candidate.record.file_size
                            
                            logger.debug(f"标记删除文件: {candidate.file_path}")
                        
                    except Exception as e:
                        logger.error(f"删除文件失败: {candidate.file_path}, 错误: {e}")
                
                # 记录配额执行事件
                if self.stats_tracker:
                    await self.stats_tracker.record_processing_event(
                        ProcessingEventType.QUOTA_ENFORCED,
                        {
                            'files_removed': removed_files,
                            'space_freed': freed_space,
                            'quota_strategy': self.quota_strategy.value,
                            'usage_before': quota_status.usage_percentage
                        }
                    )
                
                result.files_removed = removed_files
                result.space_freed = freed_space
                
                logger.info(f"配额执行完成: 删除 {removed_files} 个文件，释放 {freed_space} 字节")
                return result
                
            except Exception as e:
                logger.error(f"执行配额限制异常: {e}")
                return result
                
    async def calculate_removal_priority(self, 
                                       records: Optional[List[LifecycleRecord]] = None) -> List[RemovalCandidate]:
        """计算删除优先级
        
        基于多个因素对文件进行优先级排序，优先删除低价值文件。
        
        Args:
            records: 可选的记录列表，如果不提供则获取所有记录
            
        Returns:
            List[RemovalCandidate]: 按删除优先级排序的候选文件列表
            
        Validates: Requirements 4.1
        """
        try:
            if records is None:
                # 获取所有已完成的记录
                records = await self.lifecycle_manager.get_files_by_status(ProcessingStatus.COMPLETED)
            
            candidates = []
            now = datetime.now()
            
            for record in records:
                # 跳过优先级文件
                if record.priority_level > 0:
                    continue
                
                # 计算各种因素的分数
                age_score = self._calculate_age_score(record, now)
                access_score = self._calculate_access_score(record, now)
                size_score = self._calculate_size_score(record)
                category_score = self._calculate_category_score(record)
                
                # 综合优先级分数（分数越高，越优先删除）
                priority_score = (
                    age_score * 0.3 +      # 年龄权重30%
                    access_score * 0.4 +   # 访问权重40%
                    size_score * 0.2 +     # 大小权重20%
                    category_score * 0.1   # 分类权重10%
                )
                
                # 生成删除原因
                reasons = []
                if age_score > 0.7:
                    reasons.append("文件较旧")
                if access_score > 0.7:
                    reasons.append("访问频率低")
                if size_score > 0.7:
                    reasons.append("文件较大")
                
                removal_reason = ", ".join(reasons) if reasons else "综合评分较低"
                
                candidate = RemovalCandidate(
                    file_path=record.raw_file_path,
                    record=record,
                    priority_score=priority_score,
                    removal_reason=removal_reason
                )
                candidates.append(candidate)
            
            # 按优先级分数排序（降序，分数高的优先删除）
            candidates.sort(key=lambda c: c.priority_score, reverse=True)
            
            logger.debug(f"计算删除优先级: {len(candidates)} 个候选文件")
            return candidates
            
        except Exception as e:
            logger.error(f"计算删除优先级异常: {e}")
            return []
            
    async def reserve_space_for_priority_images(self, image_paths: List[str]) -> bool:
        """为优先级图像保留空间
        
        确保高优先级图像有足够的保留空间。
        
        Args:
            image_paths: 优先级图像路径列表
            
        Returns:
            bool: 是否成功保留空间
            
        Validates: Requirements 4.5
        """
        try:
            # 计算保留空间需求
            reserved_space_needed = 0
            for image_path in image_paths:
                record = await self.lifecycle_manager.get_record_by_file_path(image_path)
                if record:
                    reserved_space_needed += record.file_size
            
            # 计算可用保留空间
            reserved_space_available = int(self.max_size * self.reserved_space_percentage)
            
            if reserved_space_needed > reserved_space_available:
                logger.warning(f"保留空间不足: 需要 {reserved_space_needed}, 可用 {reserved_space_available}")
                return False
            
            # 更新优先级图像的优先级标记
            for image_path in image_paths:
                record = await self.lifecycle_manager.get_record_by_file_path(image_path)
                if record:
                    await self.db.update_lifecycle_record(record.record_id, {
                        'priority_level': max(record.priority_level, 1)
                    })
            
            logger.info(f"为 {len(image_paths)} 个优先级图像保留了 {reserved_space_needed} 字节空间")
            return True
            
        except Exception as e:
            logger.error(f"保留优先级图像空间异常: {e}")
            return False
            
    async def get_quota_warnings(self) -> List[QuotaWarning]:
        """获取配额警告
        
        生成当前存储状态的警告信息。
        
        Returns:
            List[QuotaWarning]: 配额警告列表
            
        Validates: Requirements 4.3
        """
        try:
            warnings = []
            quota_status = await self.check_quota_status()
            
            # 生成使用率警告
            if quota_status.is_critical:
                warning = QuotaWarning(
                    warning_type="critical_usage",
                    message=f"存储使用率达到临界水平: {quota_status.usage_percentage:.1%}",
                    current_usage=quota_status.usage_percentage,
                    threshold=quota_status.critical_threshold
                )
                warnings.append(warning)
            elif quota_status.is_warning:
                warning = QuotaWarning(
                    warning_type="high_usage",
                    message=f"存储使用率较高: {quota_status.usage_percentage:.1%}",
                    current_usage=quota_status.usage_percentage,
                    threshold=quota_status.warning_threshold
                )
                warnings.append(warning)
            
            # 生成特定策略警告
            if self.quota_strategy == QuotaStrategy.COUNT_BASED:
                count_usage = quota_status.current_count / quota_status.max_count
                if count_usage >= quota_status.warning_threshold:
                    warning = QuotaWarning(
                        warning_type="file_count_high",
                        message=f"文件数量接近限制: {quota_status.current_count}/{quota_status.max_count}",
                        current_usage=count_usage,
                        threshold=quota_status.warning_threshold
                    )
                    warnings.append(warning)
            
            elif self.quota_strategy == QuotaStrategy.SIZE_BASED:
                size_usage = quota_status.current_size / quota_status.max_size
                if size_usage >= quota_status.warning_threshold:
                    size_mb = quota_status.current_size / (1024 * 1024)
                    max_mb = quota_status.max_size / (1024 * 1024)
                    warning = QuotaWarning(
                        warning_type="storage_size_high",
                        message=f"存储大小接近限制: {size_mb:.1f}MB/{max_mb:.1f}MB",
                        current_usage=size_usage,
                        threshold=quota_status.warning_threshold
                    )
                    warnings.append(warning)
            
            logger.debug(f"生成配额警告: {len(warnings)} 个")
            return warnings
            
        except Exception as e:
            logger.error(f"获取配额警告异常: {e}")
            return []
            
    def configure_quota(self, 
                       max_count: Optional[int] = None,
                       max_size: Optional[int] = None,
                       strategy: Optional[QuotaStrategy] = None,
                       warning_threshold: Optional[float] = None,
                       critical_threshold: Optional[float] = None,
                       reserved_space_percentage: Optional[float] = None):
        """配置配额参数
        
        Args:
            max_count: 最大文件数
            max_size: 最大存储大小（字节）
            strategy: 配额策略
            warning_threshold: 警告阈值
            critical_threshold: 临界阈值
            reserved_space_percentage: 保留空间百分比
        """
        if max_count is not None:
            self.max_count = max_count
        if max_size is not None:
            self.max_size = max_size
        if strategy is not None:
            self.quota_strategy = strategy
        if warning_threshold is not None:
            self.warning_threshold = warning_threshold
        if critical_threshold is not None:
            self.critical_threshold = critical_threshold
        if reserved_space_percentage is not None:
            self.reserved_space_percentage = reserved_space_percentage
            
        logger.info(f"配额配置已更新: 最大文件数={self.max_count}, "
                   f"最大大小={self.max_size}字节, 策略={self.quota_strategy.value}")
                   
    def _calculate_age_score(self, record: LifecycleRecord, now: datetime) -> float:
        """计算年龄分数（0-1，1表示最旧）"""
        age_days = (now - record.creation_timestamp).days
        # 30天以上的文件得分较高
        return min(age_days / 30.0, 1.0)
        
    def _calculate_access_score(self, record: LifecycleRecord, now: datetime) -> float:
        """计算访问分数（0-1，1表示访问频率最低）"""
        if record.access_count == 0:
            return 1.0  # 从未访问的文件优先删除
        
        # 计算访问频率（次数/天）
        if record.last_access_timestamp:
            days_since_access = (now - record.last_access_timestamp).days
            if days_since_access == 0:
                days_since_access = 1  # 避免除零
        else:
            days_since_access = (now - record.creation_timestamp).days
            if days_since_access == 0:
                days_since_access = 1
        
        access_frequency = record.access_count / days_since_access
        
        # 访问频率低的文件得分高
        return max(0.0, 1.0 - min(access_frequency, 1.0))
        
    def _calculate_size_score(self, record: LifecycleRecord) -> float:
        """计算大小分数（0-1，1表示文件最大）"""
        # 大文件优先删除以释放更多空间
        # 假设10MB以上的文件为大文件
        max_size = 10 * 1024 * 1024  # 10MB
        return min(record.file_size / max_size, 1.0)
        
    def _calculate_category_score(self, record: LifecycleRecord) -> float:
        """计算分类分数（0-1，1表示优先级最低的分类）"""
        # 可以根据分类设置不同的优先级
        # 这里简化处理，所有分类相同优先级
        return 0.5
        
    async def cleanup(self):
        """清理资源"""
        # 目前没有需要清理的资源
        pass