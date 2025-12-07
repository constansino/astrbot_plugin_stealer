import json
import os
from pathlib import Path

from astrbot.api import logger


class PluginConfigManager:
    """配置管理服务类，负责处理插件的所有配置操作。"""

    def __init__(self, plugin_instance):
        """初始化配置管理服务。

        Args:
            plugin_instance: StealerPlugin 实例，用于访问插件的基本信息
        """
        self.plugin = plugin_instance
        # 获取插件目录并构建配置目录路径
        plugin_dir = Path(__file__).parent.absolute()
        self.config_dir = os.path.join(plugin_dir, "config")
        self.config_file = os.path.join(self.config_dir, "config.json")

        # 默认配置
        self.default_config = {
            "steal_emoji": False,
            "auto_send": False,
            "emoji_chance": 0.1,
            "vision_model": "gpt-4o-mini",
            "base_dir": os.path.join(self.config_dir, "emojis"),
            "emoji_only": True,
            "max_reg_num": 1000,
            "do_replace": True,
            "maintenance_interval": 10,
            "raw_clean_interval": 60,
            "raw_retention_hours": 24,
            "content_filtration": True,
            "vision_max_retries": 3,
            "vision_retry_delay": 1.0
        }

        # 加载配置
        self.config = self._load_config()

    def _load_config(self):
        """从配置文件加载配置。"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, encoding="utf-8") as f:
                    return json.load(f)
            else:
                return self.default_config.copy()
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return self.default_config.copy()

    def save_config(self):
        """保存配置到配置文件。"""
        try:
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir, exist_ok=True)

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
                logger.debug(f"配置文件已保存到 {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False

    def update_config(self, key, value):
        """更新单个配置项。

        Args:
            key: 配置项名称
            value: 配置项值

        Returns:
            bool: 更新是否成功
        """
        try:
            self.config[key] = value
            return self.save_config()
        except Exception as e:
            logger.error(f"更新配置项失败: {key} = {value}, 错误: {e}")
            return False

    def get_config(self, key, default=None):
        """获取配置项值。

        Args:
            key: 配置项名称
            default: 默认值

        Returns:
            配置项值或默认值
        """
        return self.config.get(key, default)

    def update_config_from_dict(self, config_dict):
        """从字典更新多个配置项。

        Args:
            config_dict: 包含配置项的字典

        Returns:
            bool: 更新是否成功
        """
        try:
            self.config.update(config_dict)
            return self.save_config()
        except Exception as e:
            logger.error(f"从字典更新配置失败: {e}")
            return False

    def reset_config(self):
        """重置配置为默认值。"""
        try:
            self.config = self.default_config.copy()
            return self.save_config()
        except Exception as e:
            logger.error(f"重置配置失败: {e}")
            return False

    def ensure_directories(self):
        """确保所有必要的目录存在。"""
        try:
            base_dir = Path(self.config.get("base_dir"))
            if base_dir:
                # 创建基础目录
                base_dir.mkdir(parents=True, exist_ok=True)
                logger.debug(f"已创建基础目录: {base_dir}")

                # 创建子目录
                subdirs = ["raw", "categories"]
                for subdir in subdirs:
                    subdir_path = base_dir / subdir
                    subdir_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"已创建子目录: {subdir_path}")

                # 创建各个情绪分类目录
                categories = [
                    "开心", "难过", "愤怒", "惊讶", "恶心", "害怕",
                    "平静", "期待", "信任", "厌恶", "快乐", "悲伤",
                    "恐惧", "惊喜"
                ]
                for cat in categories:
                    cat_dir = base_dir / "categories" / cat
                    cat_dir.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"已创建分类目录: {cat_dir}")

                return True
            return False
        except Exception as e:
            logger.error(f"创建目录结构失败: {e}")
            return False
