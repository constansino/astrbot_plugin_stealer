"""
增强存储系统设置和初始化

负责创建必要的目录结构、初始化数据库、设置默认配置等。
"""

import asyncio
from pathlib import Path
from typing import Optional

from astrbot.api import logger

from .config import EnhancedConfigManager, StorageConfig
from .database import DatabaseManager


class StorageSystemSetup:
    """存储系统设置管理器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.storage_dir = base_dir / "storage"
        self.db_path = self.storage_dir / "lifecycle.db"
        self.config_path = self.storage_dir / "enhanced_config.json"
        
    async def initialize_storage_system(self, base_config_service=None) -> tuple[DatabaseManager, EnhancedConfigManager]:
        """初始化完整的存储系统"""
        try:
            # 1. 创建目录结构
            await self._create_directory_structure()
            
            # 2. 初始化配置管理器
            config_manager = EnhancedConfigManager(self.config_path, base_config_service)
            await config_manager.initialize()
            
            # 3. 初始化数据库
            db_manager = DatabaseManager(self.db_path)
            await db_manager.initialize()
            
            # 4. 验证系统完整性
            await self._verify_system_integrity(db_manager, config_manager)
            
            logger.info("增强存储系统初始化完成")
            return db_manager, config_manager
            
        except Exception as e:
            logger.error(f"初始化增强存储系统失败: {e}")
            raise
            
    async def _create_directory_structure(self):
        """创建必要的目录结构"""
        directories = [
            self.storage_dir,
            self.storage_dir / "backups",
            self.storage_dir / "logs",
            self.storage_dir / "temp",
            self.storage_dir / "cache",
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"已创建目录: {directory}")
            
    async def _verify_system_integrity(self, db_manager: DatabaseManager, 
                                     config_manager: EnhancedConfigManager):
        """验证系统完整性"""
        try:
            # 验证数据库连接
            test_record_id = "test_integrity_check"
            from .models import LifecycleRecord, ProcessingStatus
            from datetime import datetime
            
            test_record = LifecycleRecord(
                record_id=test_record_id,
                raw_file_path="/test/path",
                md5_hash="test_hash",
                sha256_hash="test_hash_256",
                file_size=0,
                status=ProcessingStatus.PENDING
            )
            
            # 测试创建和删除记录
            success = await db_manager.create_lifecycle_record(test_record)
            if success:
                # 清理测试记录
                conn = await db_manager._get_connection()
                conn.execute("DELETE FROM lifecycle_records WHERE record_id = ?", (test_record_id,))
                conn.commit()
                logger.debug("数据库完整性验证通过")
            else:
                raise Exception("数据库完整性验证失败")
                
            # 验证配置管理器
            test_config = config_manager.get_config("enable_lifecycle_tracking", True)
            if test_config is not None:
                logger.debug("配置管理器完整性验证通过")
            else:
                raise Exception("配置管理器完整性验证失败")
                
        except Exception as e:
            logger.error(f"系统完整性验证失败: {e}")
            raise
            
    async def migrate_existing_data(self, old_index_path: Optional[Path] = None):
        """迁移现有数据到新系统"""
        if not old_index_path or not old_index_path.exists():
            logger.info("没有找到需要迁移的旧数据")
            return
            
        try:
            import json
            from datetime import datetime
            from .models import LifecycleRecord, ProcessingStatus
            
            # 读取旧索引文件
            with open(old_index_path, 'r', encoding='utf-8') as f:
                old_index = json.load(f)
                
            # 初始化数据库管理器
            db_manager = DatabaseManager(self.db_path)
            await db_manager.initialize()
            
            migrated_count = 0
            failed_count = 0
            
            for file_path, record_data in old_index.items():
                try:
                    # 转换旧记录格式到新格式
                    lifecycle_record = LifecycleRecord(
                        record_id=f"migrated_{hash(file_path)}",
                        raw_file_path=file_path,
                        categorized_file_path=file_path,  # 假设已分类文件
                        creation_timestamp=datetime.now(),
                        status=ProcessingStatus.COMPLETED,
                        category=record_data.get("category", "unknown"),
                        md5_hash=record_data.get("md5_hash", ""),
                        sha256_hash=record_data.get("sha256_hash", ""),
                        file_size=record_data.get("file_size", 0),
                        access_count=record_data.get("usage_count", 0),
                    )
                    
                    success = await db_manager.create_lifecycle_record(lifecycle_record)
                    if success:
                        migrated_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"迁移记录失败 {file_path}: {e}")
                    failed_count += 1
                    
            logger.info(f"数据迁移完成: 成功 {migrated_count}, 失败 {failed_count}")
            
            # 备份旧索引文件
            backup_path = old_index_path.parent / f"{old_index_path.name}.backup"
            old_index_path.rename(backup_path)
            logger.info(f"已备份旧索引文件到: {backup_path}")
            
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            raise
            
    async def cleanup_storage_system(self, db_manager: Optional[DatabaseManager] = None):
        """清理存储系统资源"""
        try:
            if db_manager:
                await db_manager.close()
                
            logger.info("存储系统资源清理完成")
            
        except Exception as e:
            logger.error(f"清理存储系统资源失败: {e}")
            
    async def backup_storage_system(self, backup_dir: Optional[Path] = None) -> Path:
        """备份存储系统"""
        if backup_dir is None:
            backup_dir = self.storage_dir / "backups"
            
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        from datetime import datetime
        import shutil
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"storage_backup_{timestamp}"
        backup_path = backup_dir / backup_name
        backup_path.mkdir(exist_ok=True)
        
        try:
            # 备份数据库
            if self.db_path.exists():
                shutil.copy2(self.db_path, backup_path / "lifecycle.db")
                
            # 备份配置
            if self.config_path.exists():
                shutil.copy2(self.config_path, backup_path / "enhanced_config.json")
                
            logger.info(f"存储系统备份完成: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"备份存储系统失败: {e}")
            raise
            
    async def restore_storage_system(self, backup_path: Path) -> bool:
        """从备份恢复存储系统"""
        try:
            if not backup_path.exists():
                logger.error(f"备份路径不存在: {backup_path}")
                return False
                
            import shutil
            
            # 恢复数据库
            backup_db = backup_path / "lifecycle.db"
            if backup_db.exists():
                shutil.copy2(backup_db, self.db_path)
                
            # 恢复配置
            backup_config = backup_path / "enhanced_config.json"
            if backup_config.exists():
                shutil.copy2(backup_config, self.config_path)
                
            logger.info(f"存储系统恢复完成: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"恢复存储系统失败: {e}")
            return False