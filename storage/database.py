"""
数据库架构和操作

定义了增强存储系统的数据库表结构和基本操作。
使用SQLite作为后端存储，支持生命周期记录和统计数据的持久化。
"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

from .models import (
    LifecycleRecord,
    ProcessingStatus,
    ProcessingEventType,
    TimePeriod,
    TransactionStatus,
    TransactionLog,
)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """初始化数据库"""
        async with self._lock:
            await self._create_tables()
            
    async def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._connection.row_factory = sqlite3.Row
            # 启用外键约束
            self._connection.execute("PRAGMA foreign_keys = ON")
            # 设置WAL模式以提高并发性能
            self._connection.execute("PRAGMA journal_mode = WAL")
            
        return self._connection
        
    async def _create_tables(self):
        """创建数据库表"""
        conn = await self._get_connection()
        
        # 生命周期记录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lifecycle_records (
                record_id TEXT PRIMARY KEY,
                raw_file_path TEXT NOT NULL,
                categorized_file_path TEXT,
                creation_timestamp DATETIME NOT NULL,
                processing_timestamp DATETIME,
                status TEXT NOT NULL,
                category TEXT,
                failure_reason TEXT,
                md5_hash TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                last_access_timestamp DATETIME,
                access_count INTEGER DEFAULT 0,
                priority_level INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 统计数据表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS storage_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                event_type TEXT NOT NULL,
                category TEXT,
                value REAL NOT NULL,
                metadata TEXT,
                aggregation_period TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 重复检测缓存表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_cache (
                md5_hash TEXT PRIMARY KEY,
                sha256_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                first_seen DATETIME NOT NULL,
                last_verified DATETIME NOT NULL,
                reference_count INTEGER DEFAULT 1,
                cache_expiry DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 事务日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transaction_logs (
                transaction_id TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                affected_files TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                status TEXT NOT NULL,
                rollback_data TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 配置历史表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT,
                change_reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引以提高查询性能
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_status ON lifecycle_records(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_category ON lifecycle_records(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_creation ON lifecycle_records(creation_timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_access ON lifecycle_records(last_access_timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_hashes ON lifecycle_records(md5_hash, sha256_hash)")
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON storage_statistics(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_event_type ON storage_statistics(event_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_category ON storage_statistics(category)")
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_hashes ON duplicate_cache(md5_hash, sha256_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_expiry ON duplicate_cache(cache_expiry)")
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transaction_timestamp ON transaction_logs(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transaction_status ON transaction_logs(status)")
        
        conn.commit()
        
    async def create_lifecycle_record(self, record: LifecycleRecord) -> bool:
        """创建生命周期记录"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                conn.execute("""
                    INSERT INTO lifecycle_records (
                        record_id, raw_file_path, categorized_file_path,
                        creation_timestamp, processing_timestamp, status,
                        category, failure_reason, md5_hash, sha256_hash,
                        file_size, last_access_timestamp, access_count, priority_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.record_id,
                    record.raw_file_path,
                    record.categorized_file_path,
                    record.creation_timestamp.isoformat(),
                    record.processing_timestamp.isoformat() if record.processing_timestamp else None,
                    record.status.value,
                    record.category,
                    record.failure_reason,
                    record.md5_hash,
                    record.sha256_hash,
                    record.file_size,
                    record.last_access_timestamp.isoformat() if record.last_access_timestamp else None,
                    record.access_count,
                    record.priority_level
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"创建生命周期记录失败: {e}")
                return False
                
    async def update_lifecycle_record(self, record_id: str, updates: Dict[str, Any]) -> bool:
        """更新生命周期记录"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                
                # 首先检查记录是否存在
                cursor = conn.execute("SELECT record_id FROM lifecycle_records WHERE record_id = ?", (record_id,))
                if not cursor.fetchone():
                    logger.error(f"生命周期记录不存在: {record_id}")
                    return False
                
                # 构建更新语句
                set_clauses = []
                values = []
                
                for key, value in updates.items():
                    if key in ['creation_timestamp', 'processing_timestamp', 'last_access_timestamp']:
                        if isinstance(value, datetime):
                            value = value.isoformat()
                    elif key == 'status' and hasattr(value, 'value'):
                        value = value.value
                        
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
                
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                values.append(record_id)
                
                query = f"UPDATE lifecycle_records SET {', '.join(set_clauses)} WHERE record_id = ?"
                cursor = conn.execute(query, values)
                
                # 检查是否有行被更新
                if cursor.rowcount == 0:
                    logger.error(f"更新生命周期记录失败，没有匹配的记录: {record_id}")
                    return False
                    
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"更新生命周期记录失败: {e}")
                return False
                
    async def get_lifecycle_record(self, record_id: str) -> Optional[LifecycleRecord]:
        """获取生命周期记录"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                cursor = conn.execute(
                    "SELECT * FROM lifecycle_records WHERE record_id = ?",
                    (record_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_lifecycle_record(row)
                return None
            except Exception as e:
                logger.error(f"获取生命周期记录失败: {e}")
                return None
                
    async def get_records_by_status(self, status: ProcessingStatus) -> List[LifecycleRecord]:
        """根据状态获取记录"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                cursor = conn.execute(
                    "SELECT * FROM lifecycle_records WHERE status = ?",
                    (status.value,)
                )
                rows = cursor.fetchall()
                
                return [self._row_to_lifecycle_record(row) for row in rows]
            except Exception as e:
                logger.error(f"根据状态获取记录失败: {e}")
                return []
    
    async def get_all_records(self) -> List[LifecycleRecord]:
        """获取所有记录"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                cursor = conn.execute("SELECT * FROM lifecycle_records")
                rows = cursor.fetchall()
                
                return [self._row_to_lifecycle_record(row) for row in rows]
            except Exception as e:
                logger.error(f"获取所有记录失败: {e}")
                return []
                
    async def find_orphaned_files(self) -> List[Tuple[str, str]]:
        """查找孤立文件"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                
                # 查找有分类文件但原始文件不存在的记录
                cursor = conn.execute("""
                    SELECT categorized_file_path, 'categorized' as file_type
                    FROM lifecycle_records 
                    WHERE categorized_file_path IS NOT NULL 
                    AND status = 'completed'
                """)
                
                orphaned = []
                for row in cursor.fetchall():
                    categorized_path = row['categorized_file_path']
                    if categorized_path and not Path(categorized_path).exists():
                        # 检查对应的原始文件是否存在
                        raw_cursor = conn.execute(
                            "SELECT raw_file_path FROM lifecycle_records WHERE categorized_file_path = ?",
                            (categorized_path,)
                        )
                        raw_row = raw_cursor.fetchone()
                        if raw_row and not Path(raw_row['raw_file_path']).exists():
                            orphaned.append((categorized_path, 'categorized'))
                            
                return orphaned
            except Exception as e:
                logger.error(f"查找孤立文件失败: {e}")
                return []
                
    async def record_statistics_event(self, event_type: ProcessingEventType, 
                                    category: Optional[str], value: float,
                                    metadata: Optional[Dict[str, Any]] = None) -> bool:
        """记录统计事件"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                conn.execute("""
                    INSERT INTO storage_statistics (
                        timestamp, event_type, category, value, metadata
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    event_type.value,
                    category,
                    value,
                    json.dumps(metadata) if metadata else None
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"记录统计事件失败: {e}")
                return False
                
    async def get_aggregated_stats(self, period: TimePeriod, 
                                 start_time: datetime, 
                                 end_time: datetime) -> Dict[str, Any]:
        """获取聚合统计数据"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                
                # 根据时间周期聚合数据
                if period == TimePeriod.HOURLY:
                    group_format = "%Y-%m-%d %H"
                elif period == TimePeriod.DAILY:
                    group_format = "%Y-%m-%d"
                elif period == TimePeriod.WEEKLY:
                    group_format = "%Y-%W"
                else:  # MONTHLY
                    group_format = "%Y-%m"
                
                cursor = conn.execute(f"""
                    SELECT 
                        strftime('{group_format}', timestamp) as period,
                        event_type,
                        category,
                        COUNT(*) as count,
                        AVG(value) as avg_value,
                        SUM(value) as sum_value
                    FROM storage_statistics 
                    WHERE timestamp BETWEEN ? AND ?
                    GROUP BY strftime('{group_format}', timestamp), event_type, category
                    ORDER BY period
                """, (start_time.isoformat(), end_time.isoformat()))
                
                results = {}
                for row in cursor.fetchall():
                    period_key = row['period']
                    if period_key not in results:
                        results[period_key] = {}
                    
                    event_type = row['event_type']
                    category = row['category'] or 'all'
                    
                    if event_type not in results[period_key]:
                        results[period_key][event_type] = {}
                    
                    results[period_key][event_type][category] = {
                        'count': row['count'],
                        'avg_value': row['avg_value'],
                        'sum_value': row['sum_value']
                    }
                
                return results
            except Exception as e:
                logger.error(f"获取聚合统计数据失败: {e}")
                return {}
                
    async def create_transaction_log(self, log: TransactionLog) -> bool:
        """创建事务日志"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                conn.execute("""
                    INSERT INTO transaction_logs (
                        transaction_id, operation_type, affected_files,
                        timestamp, status, rollback_data
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    log.transaction_id,
                    log.operation_type,
                    json.dumps(log.affected_files),
                    log.timestamp.isoformat(),
                    log.status.value,
                    json.dumps(log.rollback_data) if log.rollback_data else None
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"创建事务日志失败: {e}")
                return False
                
    async def update_transaction_status(self, transaction_id: str, 
                                      status: TransactionStatus,
                                      rollback_data: Optional[Dict[str, Any]] = None) -> bool:
        """更新事务状态"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                conn.execute("""
                    UPDATE transaction_logs 
                    SET status = ?, rollback_data = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE transaction_id = ?
                """, (
                    status.value,
                    json.dumps(rollback_data) if rollback_data else None,
                    transaction_id
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"更新事务状态失败: {e}")
                return False
                
    async def cleanup_expired_cache(self) -> int:
        """清理过期缓存"""
        async with self._lock:
            try:
                conn = await self._get_connection()
                cursor = conn.execute("""
                    DELETE FROM duplicate_cache 
                    WHERE cache_expiry < ?
                """, (datetime.now().isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count
            except Exception as e:
                logger.error(f"清理过期缓存失败: {e}")
                return 0
                
    def _row_to_lifecycle_record(self, row: sqlite3.Row) -> LifecycleRecord:
        """将数据库行转换为LifecycleRecord对象"""
        return LifecycleRecord(
            record_id=row['record_id'],
            raw_file_path=row['raw_file_path'],
            categorized_file_path=row['categorized_file_path'],
            creation_timestamp=datetime.fromisoformat(row['creation_timestamp']),
            processing_timestamp=datetime.fromisoformat(row['processing_timestamp']) if row['processing_timestamp'] else None,
            status=ProcessingStatus(row['status']),
            category=row['category'],
            failure_reason=row['failure_reason'],
            md5_hash=row['md5_hash'],
            sha256_hash=row['sha256_hash'],
            file_size=row['file_size'],
            last_access_timestamp=datetime.fromisoformat(row['last_access_timestamp']) if row['last_access_timestamp'] else None,
            access_count=row['access_count'],
            priority_level=row['priority_level']
        )
        
    async def close(self):
        """关闭数据库连接"""
        if self._connection:
            self._connection.close()
            self._connection = None