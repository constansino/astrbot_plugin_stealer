"""
增强存储系统初始化模块

提供存储系统的统一初始化接口和核心组件导出。
"""

from .config import EnhancedConfigManager, StorageConfig
from .database import DatabaseManager
from .setup import StorageSystemSetup
from .models import (
    LifecycleRecord,
    ProcessingStatus,
    RetentionPolicy,
    CleanupResult,
    StorageMetrics,
    QuotaStatus,
    DuplicateDetectionCache,
    TransactionLog,
    CircuitBreaker,
    ProcessingEventType,
    AccessType,
    TimePeriod,
    QuotaStrategy,
)

__all__ = [
    # 设置和初始化
    "StorageSystemSetup",
    
    # 配置管理
    "EnhancedConfigManager",
    "StorageConfig",
    
    # 数据库管理
    "DatabaseManager",
    
    # 核心模型
    "LifecycleRecord",
    "ProcessingStatus",
    "RetentionPolicy",
    "CleanupResult",
    "StorageMetrics",
    "QuotaStatus",
    "DuplicateDetectionCache",
    "TransactionLog",
    "CircuitBreaker",
    
    # 枚举类型
    "ProcessingEventType",
    "AccessType",
    "TimePeriod",
    "QuotaStrategy",
]