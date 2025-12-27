"""
核心数据模型和枚举定义

定义了图像存储改进系统的核心数据结构，包括生命周期记录、处理状态、
保留策略、清理结果等。
"""

import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


class ProcessingStatus(enum.Enum):
    """图像处理状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MARKED_FOR_DELETION = "marked_for_deletion"


class QuotaStrategy(enum.Enum):
    """配额策略枚举"""
    COUNT_BASED = "count_based"
    SIZE_BASED = "size_based"
    HYBRID = "hybrid"


class ProcessingEventType(enum.Enum):
    """处理事件类型枚举"""
    IMAGE_STORED = "image_stored"
    IMAGE_PROCESSED = "image_processed"
    IMAGE_FAILED = "image_failed"
    IMAGE_ACCESSED = "image_accessed"
    IMAGE_DELETED = "image_deleted"
    CLEANUP_PERFORMED = "cleanup_performed"
    QUOTA_ENFORCED = "quota_enforced"


class AccessType(enum.Enum):
    """访问类型枚举"""
    READ = "read"
    SEND = "send"
    PROCESS = "process"


class TimePeriod(enum.Enum):
    """时间周期枚举"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TransactionStatus(enum.Enum):
    """事务状态枚举"""
    PENDING = "pending"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class CircuitState(enum.Enum):
    """断路器状态枚举"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class LifecycleRecord:
    """文件生命周期记录"""
    record_id: str
    raw_file_path: str
    categorized_file_path: Optional[str] = None
    creation_timestamp: datetime = field(default_factory=datetime.now)
    processing_timestamp: Optional[datetime] = None
    status: ProcessingStatus = ProcessingStatus.PENDING
    category: Optional[str] = None
    failure_reason: Optional[str] = None
    md5_hash: str = ""
    sha256_hash: str = ""
    file_size: int = 0
    last_access_timestamp: Optional[datetime] = None
    access_count: int = 0
    priority_level: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "record_id": self.record_id,
            "raw_file_path": self.raw_file_path,
            "categorized_file_path": self.categorized_file_path,
            "creation_timestamp": self.creation_timestamp.isoformat() if self.creation_timestamp else None,
            "processing_timestamp": self.processing_timestamp.isoformat() if self.processing_timestamp else None,
            "status": self.status.value,
            "category": self.category,
            "failure_reason": self.failure_reason,
            "md5_hash": self.md5_hash,
            "sha256_hash": self.sha256_hash,
            "file_size": self.file_size,
            "last_access_timestamp": self.last_access_timestamp.isoformat() if self.last_access_timestamp else None,
            "access_count": self.access_count,
            "priority_level": self.priority_level,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LifecycleRecord":
        """从字典创建实例"""
        # 处理时间戳字段
        creation_timestamp = None
        if data.get("creation_timestamp"):
            creation_timestamp = datetime.fromisoformat(data["creation_timestamp"])
        
        processing_timestamp = None
        if data.get("processing_timestamp"):
            processing_timestamp = datetime.fromisoformat(data["processing_timestamp"])
        
        last_access_timestamp = None
        if data.get("last_access_timestamp"):
            last_access_timestamp = datetime.fromisoformat(data["last_access_timestamp"])

        return cls(
            record_id=data["record_id"],
            raw_file_path=data["raw_file_path"],
            categorized_file_path=data.get("categorized_file_path"),
            creation_timestamp=creation_timestamp or datetime.now(),
            processing_timestamp=processing_timestamp,
            status=ProcessingStatus(data.get("status", ProcessingStatus.PENDING.value)),
            category=data.get("category"),
            failure_reason=data.get("failure_reason"),
            md5_hash=data.get("md5_hash", ""),
            sha256_hash=data.get("sha256_hash", ""),
            file_size=data.get("file_size", 0),
            last_access_timestamp=last_access_timestamp,
            access_count=data.get("access_count", 0),
            priority_level=data.get("priority_level", 0),
        )


@dataclass
class CategoryPolicy:
    """分类特定策略"""
    max_age_days: int = 30
    max_access_age_days: int = 7
    priority_multiplier: float = 1.0
    reserved_space_mb: int = 0


@dataclass
class RetentionPolicy:
    """保留策略配置"""
    max_age_days: int = 30
    max_access_age_days: int = 7
    category_specific_policies: Dict[str, CategoryPolicy] = field(default_factory=dict)
    priority_image_retention: int = 90
    failure_retention_days: int = 1


@dataclass
class CleanupError:
    """清理错误信息"""
    file_path: str
    error_message: str
    error_type: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CleanupStats:
    """清理统计信息"""
    files_removed: int = 0
    space_freed: int = 0
    errors: List[CleanupError] = field(default_factory=list)
    duration: timedelta = field(default_factory=lambda: timedelta(0))


@dataclass
class CleanupResult:
    """清理结果"""
    raw_files_removed: int = 0
    categorized_files_removed: int = 0
    orphaned_files_removed: int = 0
    space_freed: int = 0
    errors: List[CleanupError] = field(default_factory=list)
    duration: timedelta = field(default_factory=lambda: timedelta(0))


@dataclass
class OrphanedFile:
    """孤立文件信息"""
    file_path: str
    file_type: str  # "raw" or "categorized"
    size: int
    last_modified: datetime
    reason: str  # 孤立原因


@dataclass
class AccessStats:
    """访问统计信息"""
    total_accesses: int = 0
    last_access: Optional[datetime] = None
    access_frequency: float = 0.0  # 每天访问次数
    peak_access_hour: int = 0


@dataclass
class StorageMetrics:
    """存储指标"""
    total_images: int = 0
    successful_classifications: int = 0
    failed_classifications: int = 0
    total_disk_usage: int = 0
    images_per_category: Dict[str, int] = field(default_factory=dict)
    average_processing_time: float = 0.0
    duplicate_detection_rate: float = 0.0
    cleanup_frequency: int = 0
    access_patterns: Dict[str, AccessStats] = field(default_factory=dict)


@dataclass
class AggregatedStats:
    """聚合统计信息"""
    period: TimePeriod
    start_time: datetime
    end_time: datetime
    metrics: StorageMetrics
    anomalies_detected: int = 0


@dataclass
class StorageAnomaly:
    """存储异常信息"""
    anomaly_type: str
    description: str
    severity: str  # "low", "medium", "high", "critical"
    detected_at: datetime = field(default_factory=datetime.now)
    affected_files: List[str] = field(default_factory=list)
    recommended_action: str = ""


@dataclass
class QuotaStatus:
    """配额状态"""
    current_count: int = 0
    max_count: int = 0
    current_size: int = 0
    max_size: int = 0
    usage_percentage: float = 0.0
    warning_threshold: float = 0.8
    critical_threshold: float = 0.95
    is_warning: bool = False
    is_critical: bool = False


@dataclass
class RemovalCandidate:
    """移除候选项"""
    file_path: str
    record: LifecycleRecord
    priority_score: float
    removal_reason: str


@dataclass
class QuotaWarning:
    """配额警告"""
    warning_type: str
    message: str
    current_usage: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class QuotaEnforcementResult:
    """配额执行结果"""
    files_removed: int = 0
    space_freed: int = 0
    warnings_generated: List[QuotaWarning] = field(default_factory=list)
    errors: List[CleanupError] = field(default_factory=list)


@dataclass
class DuplicateDetectionCache:
    """重复检测缓存"""
    md5_hash: str
    sha256_hash: str
    file_size: int
    first_seen: datetime = field(default_factory=datetime.now)
    last_verified: datetime = field(default_factory=datetime.now)
    reference_count: int = 1
    cache_expiry: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=24))


@dataclass
class TransactionLog:
    """事务日志"""
    transaction_id: str
    operation_type: str
    affected_files: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    status: TransactionStatus = TransactionStatus.PENDING
    rollback_data: Optional[Dict[str, Any]] = None


@dataclass
class CircuitBreaker:
    """断路器实现"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    state: CircuitState = CircuitState.CLOSED

    def record_success(self):
        """记录成功操作"""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED

    def record_failure(self):
        """记录失败操作"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """检查是否可以执行操作"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if (self.last_failure_time and 
                datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        
        # HALF_OPEN state
        return True