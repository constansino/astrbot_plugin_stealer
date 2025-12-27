"""
统计跟踪器

实现全面的指标收集和监控功能，包括处理事件记录、访问统计、
聚合统计生成和异常检测。
"""

import asyncio
import json
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
from .models import (
    AccessStats,
    AccessType,
    AggregatedStats,
    ProcessingEventType,
    StorageAnomaly,
    StorageMetrics,
    TimePeriod,
)


class StatisticsTracker:
    """统计跟踪器
    
    负责收集和维护存储系统的全面指标，包括处理统计、
    访问模式、性能指标和异常检测。
    """
    
    def __init__(self, database_manager: DatabaseManager):
        """初始化统计跟踪器
        
        Args:
            database_manager: 数据库管理器实例
        """
        self.db = database_manager
        self._lock = asyncio.Lock()
        self._metrics_cache: Dict[str, Any] = {}
        self._cache_expiry: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)  # 缓存5分钟
        
    async def record_processing_event(self, event_type: ProcessingEventType, 
                                    metadata: Optional[Dict[str, Any]] = None) -> None:
        """记录处理事件
        
        记录图像处理操作和结果的统计事件。
        
        Args:
            event_type: 事件类型
            metadata: 可选的事件元数据
            
        Validates: Requirements 3.1
        """
        async with self._lock:
            try:
                # 从元数据中提取分类信息
                category = None
                value = 1.0  # 默认计数值
                
                if metadata:
                    category = metadata.get('category')
                    value = metadata.get('value', 1.0)
                
                # 记录到数据库
                success = await self.db.record_statistics_event(
                    event_type, category, value, metadata
                )
                
                if success:
                    logger.debug(f"已记录处理事件: {event_type.value}, 分类: {category}")
                    # 清除缓存以确保下次查询获取最新数据
                    self._invalidate_cache()
                else:
                    logger.error(f"记录处理事件失败: {event_type.value}")
                    
            except Exception as e:
                logger.error(f"记录处理事件异常: {e}")
                
    async def record_access_event(self, image_path: str, access_type: AccessType) -> None:
        """记录访问事件
        
        记录图像访问操作，用于统计访问模式和频率。
        
        Args:
            image_path: 图像文件路径
            access_type: 访问类型
            
        Validates: Requirements 3.4
        """
        async with self._lock:
            try:
                metadata = {
                    'image_path': image_path,
                    'access_type': access_type.value,
                    'timestamp': datetime.now().isoformat()
                }
                
                # 记录访问事件
                success = await self.db.record_statistics_event(
                    ProcessingEventType.IMAGE_ACCESSED,
                    None,  # 访问事件不按分类统计
                    1.0,
                    metadata
                )
                
                if success:
                    logger.debug(f"已记录访问事件: {image_path}, 类型: {access_type.value}")
                    self._invalidate_cache()
                else:
                    logger.error(f"记录访问事件失败: {image_path}")
                    
            except Exception as e:
                logger.error(f"记录访问事件异常: {e}")
                
    async def get_storage_metrics(self) -> StorageMetrics:
        """获取存储指标
        
        返回当前的存储使用情况和性能指标。
        
        Returns:
            StorageMetrics: 存储指标对象
            
        Validates: Requirements 3.2
        """
        try:
            # 检查缓存
            if self._is_cache_valid():
                cached_metrics = self._metrics_cache.get('storage_metrics')
                if cached_metrics:
                    logger.debug("返回缓存的存储指标")
                    return StorageMetrics(**cached_metrics)
            
            # 计算新的指标
            metrics = await self._calculate_storage_metrics()
            
            # 更新缓存
            self._metrics_cache['storage_metrics'] = metrics.to_dict() if hasattr(metrics, 'to_dict') else {
                'total_images': metrics.total_images,
                'successful_classifications': metrics.successful_classifications,
                'failed_classifications': metrics.failed_classifications,
                'total_disk_usage': metrics.total_disk_usage,
                'images_per_category': metrics.images_per_category,
                'average_processing_time': metrics.average_processing_time,
                'duplicate_detection_rate': metrics.duplicate_detection_rate,
                'cleanup_frequency': metrics.cleanup_frequency,
                'access_patterns': {k: {
                    'total_accesses': v.total_accesses,
                    'last_access': v.last_access.isoformat() if v.last_access else None,
                    'access_frequency': v.access_frequency,
                    'peak_access_hour': v.peak_access_hour
                } for k, v in metrics.access_patterns.items()}
            }
            self._cache_expiry = datetime.now() + self._cache_duration
            
            logger.debug("计算并缓存新的存储指标")
            return metrics
            
        except Exception as e:
            logger.error(f"获取存储指标异常: {e}")
            return StorageMetrics()
            
    async def get_aggregated_stats(self, period: TimePeriod, 
                                 start_time: Optional[datetime] = None,
                                 end_time: Optional[datetime] = None) -> AggregatedStats:
        """获取聚合统计数据
        
        返回指定时间周期内的聚合统计信息。
        
        Args:
            period: 时间周期
            start_time: 开始时间（可选，默认为一个周期前）
            end_time: 结束时间（可选，默认为当前时间）
            
        Returns:
            AggregatedStats: 聚合统计数据
            
        Validates: Requirements 3.5
        """
        try:
            # 设置默认时间范围
            if end_time is None:
                end_time = datetime.now()
                
            if start_time is None:
                if period == TimePeriod.HOURLY:
                    start_time = end_time - timedelta(hours=1)
                elif period == TimePeriod.DAILY:
                    start_time = end_time - timedelta(days=1)
                elif period == TimePeriod.WEEKLY:
                    start_time = end_time - timedelta(weeks=1)
                else:  # MONTHLY
                    start_time = end_time - timedelta(days=30)
            
            # 从数据库获取聚合数据
            raw_stats = await self.db.get_aggregated_stats(period, start_time, end_time)
            
            # 计算聚合指标
            metrics = await self._calculate_aggregated_metrics(raw_stats, start_time, end_time)
            
            # 检测异常
            anomalies_count = len(await self.detect_anomalies())
            
            aggregated_stats = AggregatedStats(
                period=period,
                start_time=start_time,
                end_time=end_time,
                metrics=metrics,
                anomalies_detected=anomalies_count
            )
            
            logger.debug(f"生成聚合统计: {period.value}, 异常数: {anomalies_count}")
            return aggregated_stats
            
        except Exception as e:
            logger.error(f"获取聚合统计异常: {e}")
            return AggregatedStats(
                period=period,
                start_time=start_time or datetime.now(),
                end_time=end_time or datetime.now(),
                metrics=StorageMetrics()
            )
            
    async def detect_anomalies(self) -> List[StorageAnomaly]:
        """检测存储异常
        
        分析存储模式并检测异常情况，如快速增长或异常失败率。
        
        Returns:
            List[StorageAnomaly]: 检测到的异常列表
            
        Validates: Requirements 3.6
        """
        try:
            anomalies = []
            
            # 检测快速增长异常
            growth_anomalies = await self._detect_rapid_growth()
            anomalies.extend(growth_anomalies)
            
            # 检测高失败率异常
            failure_anomalies = await self._detect_high_failure_rate()
            anomalies.extend(failure_anomalies)
            
            # 检测存储空间异常
            space_anomalies = await self._detect_storage_space_anomalies()
            anomalies.extend(space_anomalies)
            
            # 检测访问模式异常
            access_anomalies = await self._detect_access_pattern_anomalies()
            anomalies.extend(access_anomalies)
            
            logger.debug(f"检测到 {len(anomalies)} 个存储异常")
            return anomalies
            
        except Exception as e:
            logger.error(f"检测异常失败: {e}")
            return []
            
    async def get_performance_metrics(self) -> Dict[str, float]:
        """获取性能指标
        
        返回处理时间、吞吐量等性能相关指标。
        
        Returns:
            Dict[str, float]: 性能指标字典
            
        Validates: Requirements 3.3
        """
        try:
            # 获取最近24小时的处理事件
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            
            raw_stats = await self.db.get_aggregated_stats(
                TimePeriod.HOURLY, start_time, end_time
            )
            
            # 计算性能指标
            total_processed = 0
            total_processing_time = 0.0
            successful_count = 0
            failed_count = 0
            
            for period_data in raw_stats.values():
                if ProcessingEventType.IMAGE_PROCESSED.value in period_data:
                    processed_data = period_data[ProcessingEventType.IMAGE_PROCESSED.value]
                    for category_data in processed_data.values():
                        total_processed += category_data['count']
                        total_processing_time += category_data['sum_value']
                        successful_count += category_data['count']
                
                if ProcessingEventType.IMAGE_FAILED.value in period_data:
                    failed_data = period_data[ProcessingEventType.IMAGE_FAILED.value]
                    for category_data in failed_data.values():
                        failed_count += category_data['count']
            
            # 计算指标
            avg_processing_time = total_processing_time / total_processed if total_processed > 0 else 0.0
            success_rate = successful_count / (successful_count + failed_count) if (successful_count + failed_count) > 0 else 1.0
            throughput = total_processed / 24.0  # 每小时处理量
            
            performance_metrics = {
                'average_processing_time': avg_processing_time,
                'success_rate': success_rate,
                'throughput_per_hour': throughput,
                'total_processed_24h': total_processed,
                'failure_rate': 1.0 - success_rate
            }
            
            logger.debug(f"性能指标: {performance_metrics}")
            return performance_metrics
            
        except Exception as e:
            logger.error(f"获取性能指标异常: {e}")
            return {}
            
    async def _calculate_storage_metrics(self) -> StorageMetrics:
        """计算存储指标"""
        try:
            # 获取最近的统计数据来计算指标
            end_time = datetime.now()
            start_time = end_time - timedelta(days=1)  # 最近24小时
            
            raw_stats = await self.db.get_aggregated_stats(
                TimePeriod.DAILY, start_time, end_time
            )
            
            # 初始化指标
            total_images = 0
            successful_classifications = 0
            failed_classifications = 0
            images_per_category = {}
            
            # 处理统计数据
            for period_data in raw_stats.values():
                # 统计存储的图像
                if ProcessingEventType.IMAGE_STORED.value in period_data:
                    stored_data = period_data[ProcessingEventType.IMAGE_STORED.value]
                    for category, data in stored_data.items():
                        total_images += data['count']
                
                # 统计成功分类
                if ProcessingEventType.IMAGE_PROCESSED.value in period_data:
                    processed_data = period_data[ProcessingEventType.IMAGE_PROCESSED.value]
                    for category, data in processed_data.items():
                        successful_classifications += data['count']
                        if category != 'all':
                            images_per_category[category] = images_per_category.get(category, 0) + data['count']
                
                # 统计失败分类
                if ProcessingEventType.IMAGE_FAILED.value in period_data:
                    failed_data = period_data[ProcessingEventType.IMAGE_FAILED.value]
                    for category, data in failed_data.items():
                        failed_classifications += data['count']
            
            # 获取性能指标
            performance_metrics = await self.get_performance_metrics()
            
            return StorageMetrics(
                total_images=total_images,
                successful_classifications=successful_classifications,
                failed_classifications=failed_classifications,
                total_disk_usage=0,  # 需要从文件系统计算
                images_per_category=images_per_category,
                average_processing_time=performance_metrics.get('average_processing_time', 0.0),
                duplicate_detection_rate=0.0,  # 需要从重复检测统计计算
                cleanup_frequency=0,  # 需要从清理事件统计计算
                access_patterns={}  # 需要从访问事件计算
            )
            
        except Exception as e:
            logger.error(f"计算存储指标异常: {e}")
            return StorageMetrics()
            
    async def _calculate_aggregated_metrics(self, raw_stats: Dict[str, Any], 
                                          start_time: datetime, 
                                          end_time: datetime) -> StorageMetrics:
        """计算聚合指标"""
        try:
            # 基于原始统计数据计算聚合指标
            total_images = 0
            successful_classifications = 0
            failed_classifications = 0
            images_per_category = {}
            
            for period_data in raw_stats.values():
                if ProcessingEventType.IMAGE_STORED.value in period_data:
                    stored_data = period_data[ProcessingEventType.IMAGE_STORED.value]
                    for category, data in stored_data.items():
                        total_images += data['count']
                
                if ProcessingEventType.IMAGE_PROCESSED.value in period_data:
                    processed_data = period_data[ProcessingEventType.IMAGE_PROCESSED.value]
                    for category, data in processed_data.items():
                        successful_classifications += data['count']
                        if category != 'all':
                            images_per_category[category] = images_per_category.get(category, 0) + data['count']
                
                if ProcessingEventType.IMAGE_FAILED.value in period_data:
                    failed_data = period_data[ProcessingEventType.IMAGE_FAILED.value]
                    for category, data in failed_data.items():
                        failed_classifications += data['count']
            
            return StorageMetrics(
                total_images=total_images,
                successful_classifications=successful_classifications,
                failed_classifications=failed_classifications,
                images_per_category=images_per_category
            )
            
        except Exception as e:
            logger.error(f"计算聚合指标异常: {e}")
            return StorageMetrics()
            
    async def _detect_rapid_growth(self) -> List[StorageAnomaly]:
        """检测快速增长异常"""
        try:
            anomalies = []
            
            # 获取最近两个时间段的数据进行比较
            end_time = datetime.now()
            mid_time = end_time - timedelta(hours=1)
            start_time = end_time - timedelta(hours=2)
            
            # 获取当前小时和前一小时的数据
            current_stats = await self.db.get_aggregated_stats(
                TimePeriod.HOURLY, mid_time, end_time
            )
            previous_stats = await self.db.get_aggregated_stats(
                TimePeriod.HOURLY, start_time, mid_time
            )
            
            # 计算增长率
            current_count = sum(
                sum(category_data['count'] for category_data in event_data.values())
                for period_data in current_stats.values()
                for event_data in period_data.values()
            )
            
            previous_count = sum(
                sum(category_data['count'] for category_data in event_data.values())
                for period_data in previous_stats.values()
                for event_data in period_data.values()
            )
            
            # 如果增长率超过200%，标记为异常
            if previous_count > 0:
                growth_rate = (current_count - previous_count) / previous_count
                if growth_rate > 2.0:  # 200%增长
                    anomaly = StorageAnomaly(
                        anomaly_type="rapid_growth",
                        description=f"存储增长率异常: {growth_rate:.1%}",
                        severity="high",
                        recommended_action="检查是否有批量导入操作或系统异常"
                    )
                    anomalies.append(anomaly)
            
            return anomalies
            
        except Exception as e:
            logger.error(f"检测快速增长异常失败: {e}")
            return []
            
    async def _detect_high_failure_rate(self) -> List[StorageAnomaly]:
        """检测高失败率异常"""
        try:
            anomalies = []
            
            # 获取最近1小时的处理统计
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
            
            raw_stats = await self.db.get_aggregated_stats(
                TimePeriod.HOURLY, start_time, end_time
            )
            
            total_processed = 0
            total_failed = 0
            
            for period_data in raw_stats.values():
                if ProcessingEventType.IMAGE_PROCESSED.value in period_data:
                    processed_data = period_data[ProcessingEventType.IMAGE_PROCESSED.value]
                    for category_data in processed_data.values():
                        total_processed += category_data['count']
                
                if ProcessingEventType.IMAGE_FAILED.value in period_data:
                    failed_data = period_data[ProcessingEventType.IMAGE_FAILED.value]
                    for category_data in failed_data.values():
                        total_failed += category_data['count']
            
            # 如果失败率超过20%，标记为异常
            total_attempts = total_processed + total_failed
            if total_attempts > 0:
                failure_rate = total_failed / total_attempts
                if failure_rate > 0.2:  # 20%失败率
                    severity = "critical" if failure_rate > 0.5 else "high"
                    anomaly = StorageAnomaly(
                        anomaly_type="high_failure_rate",
                        description=f"处理失败率异常: {failure_rate:.1%}",
                        severity=severity,
                        recommended_action="检查处理逻辑和系统资源"
                    )
                    anomalies.append(anomaly)
            
            return anomalies
            
        except Exception as e:
            logger.error(f"检测高失败率异常失败: {e}")
            return []
            
    async def _detect_storage_space_anomalies(self) -> List[StorageAnomaly]:
        """检测存储空间异常"""
        try:
            anomalies = []
            
            # 这里可以添加磁盘空间检测逻辑
            # 目前返回空列表，实际实现需要检查文件系统使用情况
            
            return anomalies
            
        except Exception as e:
            logger.error(f"检测存储空间异常失败: {e}")
            return []
            
    async def _detect_access_pattern_anomalies(self) -> List[StorageAnomaly]:
        """检测访问模式异常"""
        try:
            anomalies = []
            
            # 获取最近的访问统计
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
            
            raw_stats = await self.db.get_aggregated_stats(
                TimePeriod.HOURLY, start_time, end_time
            )
            
            total_accesses = 0
            for period_data in raw_stats.values():
                if ProcessingEventType.IMAGE_ACCESSED.value in period_data:
                    access_data = period_data[ProcessingEventType.IMAGE_ACCESSED.value]
                    for category_data in access_data.values():
                        total_accesses += category_data['count']
            
            # 如果访问量异常高（超过1000次/小时），标记为异常
            if total_accesses > 1000:
                anomaly = StorageAnomaly(
                    anomaly_type="high_access_volume",
                    description=f"访问量异常: {total_accesses} 次/小时",
                    severity="medium",
                    recommended_action="检查是否有异常的访问模式或爬虫行为"
                )
                anomalies.append(anomaly)
            
            return anomalies
            
        except Exception as e:
            logger.error(f"检测访问模式异常失败: {e}")
            return []
            
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        return (self._cache_expiry is not None and 
                datetime.now() < self._cache_expiry)
                
    def _invalidate_cache(self):
        """使缓存失效"""
        self._cache_expiry = None
        self._metrics_cache.clear()
        
    async def cleanup(self):
        """清理资源"""
        self._invalidate_cache()