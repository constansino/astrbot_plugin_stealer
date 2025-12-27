"""
增强存储系统配置管理

扩展现有的配置系统，添加新的存储参数和配置验证功能。
支持运行时配置更新、配置历史记录和回滚功能。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from .models import QuotaStrategy, RetentionPolicy, CategoryPolicy


@dataclass
class StorageConfig:
    """存储系统配置"""
    
    # 文件生命周期管理配置
    enable_lifecycle_tracking: bool = True
    lifecycle_db_path: str = "storage/lifecycle.db"
    
    # 清理管理配置
    enable_intelligent_cleanup: bool = True
    cleanup_check_interval: int = 300  # 5分钟
    default_retention_policy: RetentionPolicy = field(default_factory=RetentionPolicy)
    
    # 统计跟踪配置
    enable_statistics_tracking: bool = True
    statistics_aggregation_interval: int = 3600  # 1小时
    statistics_retention_days: int = 90
    
    # 配额管理配置
    enable_quota_management: bool = True
    quota_strategy: QuotaStrategy = QuotaStrategy.HYBRID
    max_total_images: int = 10000
    max_total_size_mb: int = 5000
    quota_warning_threshold: float = 0.8
    quota_critical_threshold: float = 0.95
    
    # 重复检测配置
    enable_duplicate_detection: bool = True
    duplicate_cache_expiry_hours: int = 24
    content_verification_enabled: bool = True
    
    # 错误恢复配置
    enable_transaction_logging: bool = True
    max_retry_attempts: int = 3
    retry_backoff_multiplier: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60
    
    # 性能优化配置
    enable_async_processing: bool = True
    processing_queue_size: int = 100
    batch_operation_size: int = 50
    cache_size_mb: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, (RetentionPolicy, CategoryPolicy)):
                result[key] = value.__dict__
            elif isinstance(value, QuotaStrategy):
                result[key] = value.value
            else:
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageConfig":
        """从字典创建配置实例"""
        config = cls()
        
        for key, value in data.items():
            if hasattr(config, key):
                if key == "default_retention_policy" and isinstance(value, dict):
                    # 处理RetentionPolicy
                    policy_data = value.copy()
                    category_policies = {}
                    if "category_specific_policies" in policy_data:
                        for cat, cat_data in policy_data["category_specific_policies"].items():
                            category_policies[cat] = CategoryPolicy(**cat_data)
                        policy_data["category_specific_policies"] = category_policies
                    setattr(config, key, RetentionPolicy(**policy_data))
                elif key == "quota_strategy" and isinstance(value, str):
                    setattr(config, key, QuotaStrategy(value))
                else:
                    setattr(config, key, value)
        
        return config


@dataclass
class ConfigChange:
    """配置变更记录"""
    config_key: str
    old_value: Any
    new_value: Any
    changed_by: str
    change_reason: str
    timestamp: datetime = field(default_factory=datetime.now)


class EnhancedConfigManager:
    """增强配置管理器"""
    
    def __init__(self, config_path: Path, base_config_service=None):
        self.config_path = config_path
        self.base_config_service = base_config_service
        self.storage_config = StorageConfig()
        self.config_history: List[ConfigChange] = []
        self._config_cache: Dict[str, Any] = {}
        
    async def initialize(self):
        """初始化配置管理器"""
        await self.load_config()
        
    async def load_config(self):
        """加载配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    
                # 加载存储配置
                if "storage_config" in config_data:
                    self.storage_config = StorageConfig.from_dict(config_data["storage_config"])
                
                # 加载配置历史
                if "config_history" in config_data:
                    self.config_history = [
                        ConfigChange(**change) for change in config_data["config_history"]
                    ]
                    
                logger.info("已加载增强存储配置")
            else:
                # 创建默认配置
                await self.save_config()
                logger.info("已创建默认增强存储配置")
                
        except Exception as e:
            logger.error(f"加载增强存储配置失败: {e}")
            # 使用默认配置
            self.storage_config = StorageConfig()
            
    async def save_config(self):
        """保存配置"""
        try:
            config_data = {
                "storage_config": self.storage_config.to_dict(),
                "config_history": [
                    {
                        "config_key": change.config_key,
                        "old_value": change.old_value,
                        "new_value": change.new_value,
                        "changed_by": change.changed_by,
                        "change_reason": change.change_reason,
                        "timestamp": change.timestamp.isoformat()
                    }
                    for change in self.config_history[-100:]  # 只保留最近100条记录
                ]
            }
            
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                
            logger.info("已保存增强存储配置")
            
        except Exception as e:
            logger.error(f"保存增强存储配置失败: {e}")
            
    async def update_config(self, key: str, value: Any, 
                          changed_by: str = "system", 
                          change_reason: str = "runtime_update") -> bool:
        """更新配置项"""
        try:
            if not hasattr(self.storage_config, key):
                logger.error(f"未知的配置项: {key}")
                return False
                
            old_value = getattr(self.storage_config, key)
            
            # 验证新值
            if not self._validate_config_value(key, value):
                logger.error(f"配置值验证失败: {key} = {value}")
                return False
                
            # 记录变更
            change = ConfigChange(
                config_key=key,
                old_value=old_value,
                new_value=value,
                changed_by=changed_by,
                change_reason=change_reason
            )
            self.config_history.append(change)
            
            # 更新配置
            setattr(self.storage_config, key, value)
            
            # 保存配置
            await self.save_config()
            
            logger.info(f"已更新配置: {key} = {value}")
            return True
            
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False
            
    async def rollback_config(self, target_timestamp: datetime) -> bool:
        """回滚配置到指定时间点"""
        try:
            # 找到目标时间点之前的最后一个配置状态
            target_changes = [
                change for change in self.config_history
                if change.timestamp <= target_timestamp
            ]
            
            if not target_changes:
                logger.warning("没有找到可回滚的配置状态")
                return False
                
            # 按时间排序，获取每个配置项的最新值
            config_state = {}
            for change in sorted(target_changes, key=lambda x: x.timestamp):
                config_state[change.config_key] = change.new_value
                
            # 应用配置状态
            for key, value in config_state.items():
                if hasattr(self.storage_config, key):
                    setattr(self.storage_config, key, value)
                    
            # 记录回滚操作
            rollback_change = ConfigChange(
                config_key="system_rollback",
                old_value=None,
                new_value=target_timestamp.isoformat(),
                changed_by="system",
                change_reason=f"rollback_to_{target_timestamp.isoformat()}"
            )
            self.config_history.append(rollback_change)
            
            await self.save_config()
            
            logger.info(f"已回滚配置到 {target_timestamp}")
            return True
            
        except Exception as e:
            logger.error(f"配置回滚失败: {e}")
            return False
            
    def _validate_config_value(self, key: str, value: Any) -> bool:
        """验证配置值"""
        try:
            # 基本类型验证
            if key in ["cleanup_check_interval", "statistics_aggregation_interval", 
                      "statistics_retention_days", "max_total_images", "max_total_size_mb"]:
                return isinstance(value, int) and value > 0
                
            if key in ["quota_warning_threshold", "quota_critical_threshold", 
                      "retry_backoff_multiplier"]:
                return isinstance(value, (int, float)) and 0 < value <= 1
                
            if key in ["enable_lifecycle_tracking", "enable_intelligent_cleanup",
                      "enable_statistics_tracking", "enable_quota_management"]:
                return isinstance(value, bool)
                
            if key == "quota_strategy":
                return isinstance(value, (QuotaStrategy, str)) and (
                    value in QuotaStrategy or 
                    (isinstance(value, str) and value in [s.value for s in QuotaStrategy])
                )
                
            # 路径验证
            if key in ["lifecycle_db_path"]:
                return isinstance(value, str) and len(value) > 0
                
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
            
    async def get_config_impact(self, key: str, value: Any) -> Dict[str, str]:
        """获取配置变更的影响分析"""
        impacts = {}
        
        try:
            if key == "enable_lifecycle_tracking":
                if not value:
                    impacts["warning"] = "禁用生命周期跟踪将影响文件管理和清理功能"
                    
            elif key == "cleanup_check_interval":
                if value < 60:
                    impacts["warning"] = "清理检查间隔过短可能影响性能"
                elif value > 3600:
                    impacts["info"] = "清理检查间隔较长，可能延迟清理操作"
                    
            elif key == "max_total_images":
                current_count = await self._get_current_image_count()
                if value < current_count:
                    impacts["critical"] = f"新限制({value})小于当前图片数量({current_count})，将触发清理"
                    
            elif key == "quota_warning_threshold":
                if value > 0.95:
                    impacts["warning"] = "警告阈值过高，可能无法及时发出警告"
                    
            elif key == "enable_duplicate_detection":
                if not value:
                    impacts["warning"] = "禁用重复检测可能导致存储空间浪费"
                    
        except Exception as e:
            logger.error(f"分析配置影响失败: {e}")
            
        return impacts
        
    async def _get_current_image_count(self) -> int:
        """获取当前图片数量（占位符实现）"""
        # 这里应该调用实际的统计服务
        return 0
        
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if hasattr(self.storage_config, key):
            return getattr(self.storage_config, key)
        return default
        
    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.storage_config.to_dict()
        
    def get_config_history(self, limit: int = 50) -> List[ConfigChange]:
        """获取配置历史"""
        return self.config_history[-limit:]