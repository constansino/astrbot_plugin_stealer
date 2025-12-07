import asyncio
import json
import os
import random
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.event.filter import (
    event_message_type, platform_adapter_type, on_decorating_result,
    command, permission_type, EventMessageType, PlatformAdapterType, PermissionType
)
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_root

from .cache_service import CacheService

# 导入新创建的服务类
from .command_handler import CommandHandler
from .config_manager import PluginConfigManager

# 导入原有服务类 - 使用标准的相对导入
from .config_service import ConfigService
from .emotion_analyzer import EmotionAnalyzer
from .emotion_analyzer_service import EmotionAnalyzerService
from .event_handler import EventHandler
from .image_processor import ImageProcessor
from .image_processor_service import ImageProcessorService
from .task_scheduler import TaskScheduler

try:
    # 可选依赖，用于通过图片尺寸/比例进行快速过滤，未安装时自动降级
    from PIL import Image as PILImage  # type: ignore[import]
except Exception:  # pragma: no cover - 仅作为兼容分支
    PILImage = None




@register("astrbot_plugin_stealer", "nagatoquin33", "自动偷取并分类表情包，在合适时机发送", "1.0.0")
class StealerPlugin(Star):
    """表情包偷取与发送插件。

    功能：
    - 监听消息中的图片并自动保存到插件数据目录
    - 使用当前会话的多模态模型进行情绪分类与标签生成
    - 建立分类索引，支持自动与手动在合适时机发送表情包
    """

    # 常量定义
    BACKEND_TAG = "emoji_stealer"
    DEFAULT_FILTRATION_PROMPT = "符合公序良俗"

    # 提示词常量
    IMAGE_FILTER_PROMPT = "根据以下审核准则判断图片是否符合: {filtration_rule}。只返回是或否。"
    TEXT_EMOTION_PROMPT_TEMPLATE = """请基于这段文本的情绪选择一个最匹配的类别: {categories}。
请使用&&emotion&&格式返回，例如&&happy&&、&&sad&&。
只返回表情标签，不要添加任何其他内容。文本: {text}"""

    # 从外部文件加载的提示词
    EMOTION_DETECTION_PROMPT = ""

    # 缓存相关常量和方法已迁移到CacheService类

    # 情绪分类列表（英文标签）
    CATEGORIES = [
        "happy",
        "sad",
        "angry",
        "shy",
        "surprised",
        "smirk",
        "cry",
        "confused",
        "embarrassed",
        "love",
        "disgust",
        "fear",
        "excitement",
        "tired",
        "sigh",  # 叹气分类
        "speechless",  # 无语分类
    ]

    # 预先声明类属性，避免实例化时出现AttributeError
    _EMOTION_MAPPING = {}

    # 情绪类别映射 - 实例属性，在 initialize 方法中从文件加载

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)

        # 初始化基础路径
        self.base_dir: Path = StarTools.get_data_dir("astrbot_plugin_stealer")
        self.config_path: Path = self.base_dir / "config.json"
        self.raw_dir: Path = self.base_dir / "raw"
        self.categories_dir: Path = self.base_dir / "categories"
        self.cache_dir: Path = self.base_dir / "cache"

        # 人格注入相关属性
        self.prompt_head = ""
        self.prompt_tail_1 = ""
        self.prompt_tail_2 = ""
        self.max_emotions_per_message = 1
        self.persona_backup = None

        # 初始化原有服务类
        self.config_service = ConfigService(
            base_dir=self.base_dir,
            astrbot_config=config
        )
        self.config_service.initialize()

        # 从配置服务获取初始配置
        self.auto_send = self.config_service.auto_send
        self.emoji_chance = self.config_service.emoji_chance
        self.max_reg_num = self.config_service.max_reg_num
        self.do_replace = self.config_service.do_replace
        self.maintenance_interval = self.config_service.maintenance_interval
        self.steal_emoji = self.config_service.steal_emoji
        self.content_filtration = self.config_service.content_filtration
        self.filtration_prompt = self.config_service.filtration_prompt
        self.emoji_only = self.config_service.emoji_only
        self.vision_provider_id = self.config_service.vision_provider_id
        self.raw_retention_hours = self.config_service.raw_retention_hours
        self.raw_clean_interval = self.config_service.raw_clean_interval

        # 添加缺失的兼容mainv2的配置项
        self.raw_emoji_only = getattr(self.config_service, "raw_emoji_only", False)
        self.max_raw_emoji_size = getattr(self.config_service, "max_raw_emoji_size", 3 * 1024 * 1024)
        self.steal_type = getattr(self.config_service, "steal_type", "both")

        # 获取分类列表
        self.categories = self.config_service.categories

        # 创建必要的目录
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.categories_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        for category in self.categories:
            (self.categories_dir / category).mkdir(parents=True, exist_ok=True)

        # 初始化原有其他服务类
        self.cache_service = CacheService(self.cache_dir)
        self.image_processor = ImageProcessor(
            context=self.context,
            base_dir=self.base_dir,  # 直接传递Path对象，不再转换为字符串
            vision_provider_id=self.vision_provider_id,
            cache_service=self.cache_service
        )
        self.emotion_analyzer = EmotionAnalyzer(
            categories=self.categories,
            context=self.context
        )
        self.task_scheduler = TaskScheduler()

        # 初始化新创建的服务类
        self.config_manager = PluginConfigManager(self)
        self.command_handler = CommandHandler(self)
        self.event_handler = EventHandler(self)
        self.image_processor_service = ImageProcessorService(self)
        self.emotion_analyzer_service = EmotionAnalyzerService(self)

        # 运行时属性
        self.backend_tag: str = self.BACKEND_TAG
        self._scanner_task: asyncio.Task | None = None

    # _clean_cache方法已迁移到CacheService类

    def _reload_personas(self):
        """重新注入人格"""
        # 构建情绪分类的描述字符串
        categories_desc = "\n"
        for category in self.categories:
            categories_desc += f"- {category}\n"

        # 构建人格注入的提示词
        self.prompt_head = "请在回复用户时，根据当前对话内容分析情绪，并将分析出的情绪用&&包裹，放在回复的开头，例如：&&happy&&你好啊！\n"
        self.prompt_head += f"预设情绪列表：{categories_desc}"

        self.prompt_tail_1 = "每次只分析出一种情绪。\n"

        self.prompt_tail_2 = "\n分析情绪时，请遵循以下规则：\n"
        self.prompt_tail_2 += "1. 只使用预设的情绪列表中的情绪标签\n"
        self.prompt_tail_2 += "2. 情绪分析要准确，不要随意添加情绪\n"
        self.prompt_tail_2 += "3. 不要在回复中直接提及情绪分析的过程\n"

        # 合并提示词
        self.sys_prompt_add = self.prompt_head + self.prompt_tail_1 + self.prompt_tail_2

        # 获取当前的所有人格
        personas = self.context.provider_manager.personas

        # 保存原始人格
        if self.persona_backup is None:
            import copy
            self.persona_backup = copy.deepcopy(personas)

        # 注入新的人格
        for persona, persona_backup in zip(personas, self.persona_backup):
            persona["prompt"] = persona_backup["prompt"] + self.sys_prompt_add

    def _update_config_from_dict(self, config_dict: dict):
        """从配置字典更新插件配置。"""
        if not config_dict:
            return

        try:
            # 使用配置服务更新配置
            if self.config_service:
                self.config_service.update_config_from_dict(config_dict)

                # 同步更新实例属性以保持兼容性
                self.auto_send = self.config_service.get_config("auto_send")
                self.emoji_chance = self.config_service.get_config("emoji_chance")
                self.max_reg_num = self.config_service.get_config("max_reg_num")
                self.do_replace = self.config_service.get_config("do_replace")
                self.maintenance_interval = self.config_service.get_config("maintenance_interval")
                self.content_filtration = self.config_service.get_config("content_filtration")
                self.filtration_prompt = self.config_service.get_config("filtration_prompt")
                self.emoji_only = self.config_service.get_config("emoji_only")
                self.vision_provider_id = str(self.config_service.get_config("vision_provider_id")) if self.config_service.get_config("vision_provider_id") else None
                self.raw_retention_hours = self.config_service.get_config("raw_retention_hours")
                self.raw_clean_interval = self.config_service.get_config("raw_clean_interval")

                # 更新兼容mainv2的配置属性
                self.raw_emoji_only = config_dict.get("raw_emoji_only", getattr(self.config_service, "raw_emoji_only", False))
                self.max_raw_emoji_size = config_dict.get("max_raw_emoji_size", getattr(self.config_service, "max_raw_emoji_size", 3 * 1024 * 1024))
                self.steal_type = config_dict.get("steal_type", getattr(self.config_service, "steal_type", "both"))

                # 更新分类列表
                self.categories = self.config_service.get_config("categories") or self.CATEGORIES

                # 更新其他服务的配置
                self.image_processor.update_config(
                    categories=self.categories,
                    content_filtration=self.content_filtration,
                    filtration_prompt=self.filtration_prompt,
                    vision_provider_id=self.vision_provider_id,
                    emoji_only=self.emoji_only
                )

                self.emotion_analyzer.update_config(
                    categories=self.categories
                )
        except Exception as e:
            logger.error(f"更新配置失败: {e}")

    async def initialize(self):
        """初始化插件运行时资源。

        加载情绪映射和提示词等运行时需要的资源。
        """
        try:
            # 创建必要的数据目录结构
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            self.categories_dir.mkdir(parents=True, exist_ok=True)
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            # 加载情绪映射文件
            try:
                # 使用__file__获取当前脚本所在目录，即插件安装目录
                plugin_dir = Path(__file__).parent
                mapping_path = plugin_dir / "emotion_mapping.json"
                if mapping_path.exists():
                    with open(mapping_path, encoding="utf-8") as f:
                        self._EMOTION_MAPPING = json.load(f)
                        logger.info(f"已加载情绪映射文件: {mapping_path}")
                else:
                    logger.warning(f"情绪映射文件不存在: {mapping_path}")
            except Exception as e:
                logger.error(f"加载情绪映射文件失败: {e}")
                self._EMOTION_MAPPING = {}

            # 加载提示词文件
            try:
                # 使用__file__获取当前脚本所在目录，即插件安装目录
                plugin_dir = Path(__file__).parent
                prompts_path = plugin_dir / "prompts.json"
                if prompts_path.exists():
                    with open(prompts_path, encoding="utf-8") as f:
                        prompts = json.load(f)
                        self.EMOTION_DETECTION_PROMPT = prompts.get("EMOTION_DETECTION_PROMPT", self.EMOTION_DETECTION_PROMPT)
                        logger.info(f"已加载提示词文件: {prompts_path}")
                else:
                    logger.warning(f"提示词文件不存在: {prompts_path}")
            except Exception as e:
                logger.error(f"加载提示词文件失败: {e}")

            # 加载配置
            self.auto_send = self.config_service.get_config("auto_send")
            self.emoji_chance = self.config_service.get_config("emoji_chance")
            self.max_reg_num = self.config_service.get_config("max_reg_num")
            self.do_replace = self.config_service.get_config("do_replace")
            self.maintenance_interval = self.config_service.get_config("maintenance_interval")
            self.content_filtration = self.config_service.get_config("content_filtration")
            self.filtration_prompt = self.config_service.get_config("filtration_prompt")
            self.emoji_only = self.config_service.get_config("emoji_only")
            self.vision_provider_id = str(self.config_service.get_config("vision_provider_id")) if self.config_service.get_config("vision_provider_id") else None
            self.raw_retention_hours = self.config_service.get_config("raw_retention_hours")
            self.raw_clean_interval = self.config_service.get_config("raw_clean_interval")
            self.categories = self.config_service.get_config("categories") or self.CATEGORIES

            # 初始化子目录
            for category in self.categories:
                (self.categories_dir / category).mkdir(parents=True, exist_ok=True)

            # 启动扫描任务
            self.task_scheduler.create_task("scanner_loop", self._scanner_loop())

            # 加载并注入人格
            self._reload_personas()

        except Exception as e:
            logger.error(f"初始化插件失败: {e}")
            raise

    async def terminate(self):
        """插件销毁生命周期钩子。清理任务。"""

        try:
            # 使用任务调度器停止扫描任务
            self.task_scheduler.cancel_task("scanner_loop")

            # 清理各服务资源
            self.cache_service.cleanup()
            self.image_processor.cleanup()
            self.emotion_analyzer.cleanup()
            self.task_scheduler.cleanup()
            self.config_service.cleanup()

            # 恢复原始人格
            if self.persona_backup and hasattr(self.context, "persona") and isinstance(self.context.persona, dict):
                self.context.persona["prompt"] = self.persona_backup
                logger.info("已恢复原始人格")

        except Exception as e:
            logger.error(f"终止插件失败: {e}")

        return

    def _persist_config(self):
        """持久化插件运行配置。"""
        try:
            # 使用配置服务更新并保存配置
            config_updates = {
            "auto_send": self.auto_send,
            "categories": self.categories,
            "backend_tag": self.backend_tag,
            "emoji_chance": self.emoji_chance,
            "max_reg_num": self.max_reg_num,
            "do_replace": self.do_replace,
            "maintenance_interval": self.maintenance_interval,
            "content_filtration": self.content_filtration,
            "filtration_prompt": self.filtration_prompt,
            "emoji_only": self.emoji_only,
            "vision_provider_id": self.vision_provider_id,
            "raw_retention_hours": self.raw_retention_hours,
            "raw_clean_interval": self.raw_clean_interval,
            "enabled": self.enabled
            }

            self.config_service.update_config(config_updates)
            self.config_service.save_config()

        except Exception as e:
            logger.error(f"保存配置失败: {e}")



    async def _load_index(self) -> dict:
        """加载分类索引文件。

        Returns:
            dict: 键为文件路径，值为包含 category 与 tags 的字典。
        """
        try:
            # 使用缓存服务加载索引
            return self.cache_service.get_cache("index_cache") or {}
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            return {}

    async def _save_index(self, idx: dict):
        """保存分类索引文件。"""
        try:
            # 使用缓存服务保存索引
            self.cache_service.set_cache("index_cache", idx)
        except Exception as e:
            logger.error(f"保存索引文件失败: {e}")

    async def _load_aliases(self) -> dict:
        """加载分类别名文件。

        Returns:
            dict: 别名映射字典。
        """
        try:
            return self.config_service.get_aliases()
        except Exception as e:
            logger.error(f"加载别名失败: {e}")
            return {}

    async def _save_aliases(self, aliases: dict):
        """保存分类别名文件。"""
        try:
            self.config_service.update_aliases(aliases)
        except Exception as e:
            logger.error(f"保存别名文件失败: {e}")



    # _normalize_category 方法已迁移到 EmotionAnalyzer 类

    def _is_likely_emoji_by_metadata(self, file_path: str) -> bool:
        """基于文件大小与图像尺寸做一次启发式过滤，减少明显非表情图片。

        这里只做“明显不是表情包”的快速排除，避免误删正常表情：
        - 非常大的文件（>3MB）且分辨率较高时更像是照片/长图
        - 长宽比极端（>6:1）时更像长截图/漫画页
        - 过小的图片也直接排除
        """
        return self.image_processor_service._is_likely_emoji_by_metadata(file_path)

    async def _classify_image(self, event: AstrMessageEvent | None, file_path: str) -> tuple[str, list[str], str, str]:
        """调用多模态模型对图片进行情绪分类与标签抽取。

        Args:
            event: 当前消息事件，用于获取 provider 配置。
            file_path: 本地图片路径。

        Returns:
            (category, tags, desc, emotion): 类别、标签、详细描述、情感标签。
        """
        try:
            # 委托给ImageProcessor类处理
            result = await self.image_processor.classify_image(
                event=event,
                file_path=file_path,
                emoji_only=self.emoji_only,
                categories=self.categories
            )
            return result
        except Exception as e:
            logger.error(f"图片分类失败: {e}", exc_info=True)
            fallback = "无语" if "无语" in self.categories else "其它"
            return fallback, [], "", fallback

    async def _compute_hash(self, file_path: str) -> str:
        try:
            return await self.image_processor_service._compute_hash(file_path)
        except Exception as e:
            logger.error(f"计算哈希值失败: {e}")
            return ""

    async def _file_to_base64(self, path: str) -> str:
        try:
            return await self.image_processor_service._file_to_base64(path)
        except Exception as e:
            logger.error(f"文件转Base64失败: {e}")
            return ""

    async def _filter_image(self, event: AstrMessageEvent | None, file_path: str) -> bool:
        try:
            return await self.image_processor_service._filter_image(
                event,
                file_path,
                self.filtration_prompt,
                self.content_filtration
            )
        except Exception as e:
            logger.error(f"调用图片处理器过滤方法失败: {e}")
            return True

    async def _store_image(self, src_path: str, category: str) -> str:
        try:
            return await self.image_processor_service._store_image(src_path, category)
        except Exception as e:
            logger.error(f"调用图片处理器存储方法失败: {e}")
            return src_path

    async def _safe_remove_file(self, file_path: str) -> bool:
        """安全删除文件，处理可能的异常"""
        try:
            return await self.image_processor_service._safe_remove_file(file_path)
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False

    async def _process_image(self, event: AstrMessageEvent | None, file_path: str, is_temp: bool = False, idx: dict | None = None) -> tuple[bool, dict | None]:
        """统一处理图片的方法，包括过滤、分类、存储和索引更新

        Args:
            event: 消息事件对象，可为None
            file_path: 图片文件路径
            is_temp: 是否为临时文件，处理后需要删除
            idx: 可选的索引字典，如果提供则直接使用，否则加载新的

        Returns:
            (成功与否, 更新后的索引字典)
        """
        try:
            # 委托给ImageProcessor类处理
            success, updated_idx = await self.image_processor.process_image(
                event=event,
                file_path=file_path,
                is_temp=is_temp,
                idx=idx,
                categories=self.categories,
                emoji_only=self.emoji_only,
                content_filtration=self.content_filtration,
                filtration_prompt=self.filtration_prompt,
                backend_tag=self.backend_tag
            )

            # 如果没有提供索引，我们需要加载完整的索引
            if idx is None and updated_idx is not None:
                # 加载完整索引
                full_idx = await self._load_index()
                # 合并更新
                full_idx.update(updated_idx)
                return success, full_idx

            return success, updated_idx
        except Exception as e:
            logger.error(f"处理图片失败: {e}")
            if is_temp:
                await self._safe_remove_file(file_path)
            return False, idx

    def _is_in_parentheses(self, text: str, index: int) -> bool:
        """判断字符串中指定索引位置是否在括号内。

        支持圆括号()和方括号[]。
        """
        parentheses_count = 0
        bracket_count = 0

        for i in range(index):
            if text[i] == "(":
                parentheses_count += 1
            elif text[i] == ")":
                parentheses_count -= 1
            elif text[i] == "[":
                bracket_count += 1
            elif text[i] == "]":
                bracket_count -= 1

        return parentheses_count > 0 or bracket_count > 0

    async def _classify_text_category(self, event: AstrMessageEvent, text: str) -> str:
        """调用文本模型判断文本情绪并映射到插件分类。"""
        try:
            # 委托给EmotionAnalyzerService类进行文本情绪分类
            result = await self.emotion_analyzer_service.classify_text_emotion(event, text)
            return result
        except Exception as e:
            logger.error(f"文本情绪分类失败: {e}")
            return ""

    async def _extract_emotions_from_text(self, event: AstrMessageEvent | None, text: str) -> tuple[list[str], str]:
        """从文本中提取情绪关键词，本地提取不到时使用 LLM。

        委托给 EmotionAnalyzerService 类处理
        """
        try:
            return await self.emotion_analyzer_service.extract_emotions_from_text(event, text)
        except Exception as e:
            logger.error(f"提取文本情绪失败: {e}")
            return [], text

    async def _pick_vision_provider(self, event: AstrMessageEvent | None) -> str | None:
        if self.vision_provider_id:
            return self.vision_provider_id
        if event is None:
            return None
        return await self.context.get_current_chat_provider_id(event.unified_msg_origin)



    def _is_safe_path(self, path: str) -> tuple[bool, str]:
        """检查路径是否安全，防止路径遍历攻击。

        Args:
            path: 要检查的文件路径

        Returns:
            tuple[bool, str]: (是否安全, 规范化后的安全路径)
        """
        # 处理路径格式问题并防止路径遍历攻击
        if not os.path.isabs(path):
            # 使用 AstrBot 核心提供的路径获取函数来确保在任何环境（包括 Docker）中都能正确获取路径
            if path.startswith("data/") or path.startswith("data\\"):
                # 如果是相对于 data 目录的路径
                relative_path = path[5:]
                # 安全检查：确保相对路径不包含路径遍历
                if ".." in relative_path.replace("\\", "/").split("/"):
                    logger.error(f"检测到路径遍历尝试: {path}")
                    return False, path
                path = os.path.join(get_astrbot_data_path(), relative_path)
            elif path.startswith("AstrBot/") or path.startswith("AstrBot\\"):
                # 如果是AstrBot开头的路径，使用get_astrbot_root()作为基准
                # 安全检查：确保路径不包含路径遍历
                # 计算正确的前缀长度
                prefix_len = 8 if path.startswith("AstrBot\\") else 7  # 'AstrBot\\'长度为8，'AstrBot/'长度为7
                relative_path = path[prefix_len:]  # 移除 'AstrBot/' 或 'AstrBot\\' 前缀
                if ".." in relative_path.replace("\\", "/").split("/"):
                    logger.error(f"检测到路径遍历尝试: {path}")
                    return False, path
                path = os.path.join(get_astrbot_root(), relative_path)
            else:
                # 尝试使用当前工作目录作为基准
                path = os.path.abspath(path)

        # 安全检查：确保最终路径在预期的目录内
        expected_directories = [
            get_astrbot_data_path(),
            get_astrbot_root(),
            os.getcwd()
        ]

        # 规范化路径以消除任何路径遍历
        normalized_path = os.path.normpath(path)

        # 检查路径是否在预期目录内
        is_safe = False
        for expected_dir in expected_directories:
            normalized_expected = os.path.normpath(expected_dir)
            if normalized_path.startswith(normalized_expected + os.sep):
                is_safe = True
                break

        if not is_safe:
            logger.error(f"检测到不安全的文件路径: {path}")
            return False, normalized_path

        return True, normalized_path

    @event_message_type(EventMessageType.ALL)
    @platform_adapter_type(PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent, *args, **kwargs):
        """消息监听：偷取消息中的图片并分类存储。"""
        # 委托给 EventHandler 类处理
        await self.event_handler.on_message(event, *args, **kwargs)

    async def _scanner_loop(self):
        """扫描循环：定期清理文件和执行维护任务。"""
        # 委托给 EventHandler 类处理
        await self.event_handler._scanner_loop()



    # 已移除_scan_register_emoji_folder方法（扫描系统表情包目录功能，无实际用途）

    async def _clean_raw_directory(self):
        """按时间定时清理raw目录中的原始图片"""
        # 委托给 EventHandler 类处理
        await self.event_handler._clean_raw_directory()

    async def _enforce_capacity(self, idx: dict):
        """执行容量控制，删除低使用频率/旧文件。"""
        # 委托给 EventHandler 类处理
        await self.event_handler._enforce_capacity(idx)





    @on_decorating_result()
    async def before_send(self, event: AstrMessageEvent, *args, **kwargs):
        if not self.auto_send or not self.base_dir:
            return
        result = event.get_result()
        # 只在有文本结果时尝试匹配表情包
        if result is None:
            return

        # 文本仅用于本地规则提取情绪关键字，不再请求额外的 LLM
        text = result.get_plain_text() or event.get_message_str()
        if not text or not text.strip():
            logger.debug("没有可处理的文本内容，未触发图片发送")
            return

        emotions, cleaned_text = await self._extract_emotions_from_text(event, text)

        # 先执行标签清理，无论是否发送表情包都需要清理标签
        if cleaned_text != text:
            # 创建新的结果对象并更新内容
            new_result = event.make_result().set_result_content_type(result.result_content_type)

            # 添加除了Plain文本外的其他组件
            for comp in result.chain:
                if not isinstance(comp, Plain):
                    new_result.chain.append(comp)

            # 添加清除标签后的文本
            if cleaned_text.strip():
                new_result.message(cleaned_text.strip())

            # 设置新的结果对象
            event.set_result(new_result)

            # 更新result和text变量，使用清理后的结果
            result = new_result
            text = cleaned_text

        # 如果没有情绪标签，不需要继续处理图片发送
        if not emotions:
            logger.debug("未从文本中提取到情绪关键词，未触发图片发送")
            return

        # 只有在有情绪标签时才检查发送概率
        try:
            chance = float(self.emoji_chance)
            # 兜底保护，防止配置错误导致永远/从不触发
            if chance <= 0:
                logger.debug("表情包自动发送概率为0，未触发图片发送")
                return
            if chance > 1:
                chance = 1.0
            if random.random() >= chance:
                logger.debug(f"表情包自动发送概率检查未通过 ({chance}), 未触发图片发送")
                return
        except Exception:
            logger.error("解析表情包自动发送概率配置失败，未触发图片发送")
            return

        logger.debug("表情包自动发送概率检查通过，开始处理图片发送")

        logger.debug(f"提取到情绪关键词: {emotions}")

        # 目前只取第一个识别到的情绪类别
        category = emotions[0]
        cat_dir = self.base_dir / "categories" / category
        if not cat_dir.exists():
            logger.debug(f"情绪'{category}'对应的图片目录不存在，未触发图片发送")
            # 目录不存在时，仍需使用清理后的文本
            if cleaned_text != text:
                # 创建新的结果对象并更新内容
                new_result = event.make_result().set_result_content_type(result.result_content_type)

                # 添加除了Plain文本外的其他组件
                for comp in result.chain:
                    if not isinstance(comp, Plain):
                        new_result.chain.append(comp)

                # 添加清除标签后的文本
                if cleaned_text.strip():
                    new_result.message(cleaned_text.strip())

                # 设置新的结果对象
                event.set_result(new_result)
            return

        files = [p for p in cat_dir.iterdir() if p.is_file()]
        if not files:
            logger.debug(f"情绪'{category}'对应的图片目录为空，未触发图片发送")
            # 目录为空时，仍需使用清理后的文本
            if cleaned_text != text:
                # 创建新的结果对象并更新内容
                new_result = event.make_result().set_result_content_type(result.result_content_type)

                # 添加除了Plain文本外的其他组件
                for comp in result.chain:
                    if not isinstance(comp, Plain):
                        new_result.chain.append(comp)

                # 添加清除标签后的文本
                if cleaned_text.strip():
                    new_result.message(cleaned_text.strip())

                # 设置新的结果对象
                event.set_result(new_result)
            return

        logger.debug(f"从'{category}'目录中找到 {len(files)} 张图片")
        pick = random.choice(files)
        idx = await self._load_index()
        rec = idx.get(pick.as_posix())
        if isinstance(rec, dict):
            rec["usage_count"] = int(rec.get("usage_count", 0)) + 1
            rec["last_used"] = int(asyncio.get_event_loop().time())
            idx[pick.as_posix()] = rec
            await self._save_index(idx)
        # 创建新的结果对象并更新内容
        new_result = event.make_result().set_result_content_type(result.result_content_type)

        # 添加除了Plain文本外的其他组件
        for comp in result.chain:
            if not isinstance(comp, Plain):
                new_result.chain.append(comp)

        # 添加清除标签后的文本
        if cleaned_text.strip():
            new_result.message(cleaned_text.strip())

        # 添加图片
        b64 = await self._file_to_base64(pick.as_posix())
        new_result.base64_image(b64)

        # 设置新的结果对象
        event.set_result(new_result)

    @command("meme on")
    async def meme_on(self, event: AstrMessageEvent):
        """开启偷表情包功能。"""
        return await self.command_handler.meme_on(event)

    @command("meme off")
    async def meme_off(self, event: AstrMessageEvent):
        """关闭偷表情包功能。"""
        return await self.command_handler.meme_off(event)

    @command("meme auto_on")
    async def auto_on(self, event: AstrMessageEvent):
        """开启自动发送功能。"""
        return await self.command_handler.auto_on(event)

    @command("meme auto_off")
    async def auto_off(self, event: AstrMessageEvent):
        """关闭自动发送功能。"""
        return await self.command_handler.auto_off(event)



    @command("meme set_vision")
    async def set_vision(self, event: AstrMessageEvent, provider_id: str = ""):
        if not provider_id:
            yield event.plain_result("请提供视觉模型的 provider_id")
            return
        self.vision_provider_id = provider_id
        self._persist_config()
        yield event.plain_result(f"已设置视觉模型: {provider_id}")



    @command("meme show_providers")
    async def show_providers(self, event: AstrMessageEvent):
        vp = self.vision_provider_id or "当前会话"
        yield event.plain_result(f"视觉模型: {vp}")



    @command("meme emoji_only")
    async def meme_emoji_only(self, event: AstrMessageEvent, enable: str = ""):
        """切换是否仅偷取表情包模式。"""
        if enable.lower() in ["on", "开启", "true"]:
            self.emoji_only = True
            self._persist_config()
            yield event.plain_result("已开启仅偷取表情包模式")
        elif enable.lower() in ["off", "关闭", "false"]:
            self.emoji_only = False
            self._persist_config()
            yield event.plain_result("已关闭仅偷取表情包模式")
        else:
            status = "开启" if self.emoji_only else "关闭"
            yield event.plain_result(f"当前仅偷取表情包模式: {status}")

    @command("meme status")
    async def status(self, event: AstrMessageEvent):
        """显示当前偷取状态与后台标识。"""
        st_on = "开启" if self.enabled else "关闭"
        st_auto = "开启" if self.auto_send else "关闭"
        st_emoji_only = "开启" if self.emoji_only else "关闭"
        idx = await self._load_index()
        # 添加视觉模型信息
        vision_model = self.vision_provider_id or "未设置（将使用当前会话默认模型）"
        yield event.plain_result(
            f"偷取: {st_on}\n自动发送: {st_auto}\n仅偷取表情包: {st_emoji_only}\n已注册数量: {len(idx)}\n概率: {self.emoji_chance}\n上限: {self.max_reg_num}\n替换: {self.do_replace}\n维护周期: {self.maintenance_interval}min\n审核: {self.content_filtration}\n视觉模型: {vision_model}"
        )

    async def get_count(self) -> int:
        idx = await self._load_index()
        return len(idx)

    async def get_info(self) -> dict:
        idx = await self._load_index()
        return {
            "current_count": len(idx),
            "max_count": self.max_reg_num,
            "available_emojis": len(idx),
        }

    async def get_emotions(self) -> list[str]:
        idx = await self._load_index()
        s = set()
        for v in idx.values():
            if isinstance(v, dict):
                emo = v.get("emotion")
                if isinstance(emo, str) and emo:
                    s.add(emo)
        return sorted(s)

    async def get_descriptions(self) -> list[str]:
        idx = await self._load_index()
        res = []
        for v in idx.values():
            if isinstance(v, dict):
                d = v.get("desc")
                if isinstance(d, str) and d:
                    res.append(d)
        return res

    async def _load_all_records(self) -> list[tuple[str, dict]]:
        idx = await self._load_index()
        return [(k, v) for k, v in idx.items() if isinstance(v, dict) and os.path.exists(k)]

    async def get_random_paths(self, count: int | None = 1) -> list[tuple[str, str, str]]:
        recs = await self._load_all_records()
        if not recs:
            return []
        n = max(1, int(count or 1))
        pick = random.sample(recs, min(n, len(recs)))
        res = []
        for p, v in pick:
            d = str(v.get("desc", ""))
            emo = str(v.get("emotion", v.get("category", self.categories[0] if self.categories else "开心")))
            res.append((p, d, emo))
        return res

    async def get_by_emotion_path(self, emotion: str) -> tuple[str, str, str] | None:
        recs = await self._load_all_records()
        cands = []
        for p, v in recs:
            emo = str(v.get("emotion", v.get("category", "")))
            tags = v.get("tags", [])
            if emotion and (emotion == emo or (isinstance(tags, list) and emotion in [str(t) for t in tags])):
                cands.append((p, v))
        if not cands:
            return None
        p, v = random.choice(cands)
        return (p, str(v.get("desc", "")), str(v.get("emotion", v.get("category", self.categories[0] if self.categories else "开心"))))

    async def get_by_description_path(self, description: str) -> tuple[str, str, str] | None:
        recs = await self._load_all_records()
        cands = []
        for p, v in recs:
            d = str(v.get("desc", ""))
            if description and description in d:
                cands.append((p, v))
        if not cands:
            for p, v in recs:
                tags = v.get("tags", [])
                if isinstance(tags, list):
                    if any(str(description) in str(t) for t in tags):
                        cands.append((p, v))
        if not cands:
            return None
        p, v = random.choice(cands)
        return (p, str(v.get("desc", "")), str(v.get("emotion", v.get("category", self.categories[0] if self.categories else "开心"))))

    @permission_type(PermissionType.ADMIN)
    @command("meme push")
    async def push(self, event: AstrMessageEvent, category: str = "", alias: str = ""):
        if not self.base_dir:
            return
        if alias:
            aliases = await self._load_aliases()
            if alias in aliases:
                aliases[alias]
            else:
                yield event.plain_result("别名不存在")
                return
        cat = category or (self.categories[0] if self.categories else "happy")
        cat_dir = self.base_dir / "categories" / cat
        if not cat_dir.exists():
            yield event.plain_result("分类不存在")
            return
        files = [p for p in cat_dir.iterdir() if p.is_file()]
        if not files:
            yield event.plain_result("该分类暂无表情包")
            return
        pick = random.choice(files)
        b64 = await self._file_to_base64(pick.as_posix())
        chain = MessageChain().base64_image(b64)
        # 统一使用yield返回结果，保持交互体验一致
        yield event.result_with_message_chain(chain)

    @permission_type(PermissionType.ADMIN)
    @command("meme debug_image")
    async def debug_image(self, event: AstrMessageEvent):
        """调试命令：处理当前消息中的图片并显示详细信息"""

        # 收集所有图片组件
        imgs = [comp for comp in event.message_obj.message if isinstance(comp, Image)]

        if not imgs:
            yield event.plain_result("当前消息中没有图片")
            return

        for i, img in enumerate(imgs):
            try:
                # 转换图片到临时文件路径
                temp_path = await img.convert_to_file_path()
                yield event.plain_result(f"图片 {i+1}: 临时路径: {temp_path}")

                # 检查路径安全性
                is_safe, safe_path = self._is_safe_path(temp_path)
                if not is_safe:
                    yield event.plain_result(f"图片 {i+1}: 路径不安全，跳过处理")
                    continue

                temp_path = safe_path
                yield event.plain_result(f"图片 {i+1}: 安全路径: {temp_path}")

                # 确保临时文件存在且可访问
                if not os.path.exists(temp_path):
                    yield event.plain_result(f"图片 {i+1}: 临时文件不存在，跳过处理")
                    continue

                # 使用统一的图片处理方法
                yield event.plain_result(f"图片 {i+1}: 开始处理...")
                success, idx = await self._process_image(event, temp_path, is_temp=True)

                if success:
                    if idx:
                        await self._save_index(idx)
                        yield event.plain_result(f"图片 {i+1}: 处理成功！已保存到索引")
                        # 显示处理结果
                        for img_path, img_info in idx.items():
                            if os.path.exists(img_path):
                                yield event.plain_result(f"图片 {i+1}: 保存路径: {img_path}")
                                yield event.plain_result(f"图片 {i+1}: 分类: {img_info.get('category', '未知')}")
                                yield event.plain_result(f"图片 {i+1}: 情绪: {img_info.get('emotion', '未知')}")
                                yield event.plain_result(f"图片 {i+1}: 描述: {img_info.get('desc', '无')}")
                    else:
                        yield event.plain_result(f"图片 {i+1}: 处理成功，但没有生成索引")
                else:
                    yield event.plain_result(f"图片 {i+1}: 处理失败")
            except Exception as e:
                yield event.plain_result(f"图片 {i+1}: 处理出错: {str(e)}")
                logger.error(f"调试图片处理失败: {e}", exc_info=True)












