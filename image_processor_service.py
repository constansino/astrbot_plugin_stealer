import asyncio
import base64
import hashlib
import os
import shutil
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class ImageProcessorService:
    """图片处理服务类，负责处理所有与图片相关的操作。"""

    def __init__(self, plugin_instance):
        """初始化图片处理服务。

        Args:
            plugin_instance: StealerPlugin 实例，用于访问插件的配置和服务
        """
        self.plugin = plugin_instance
        self.base_dir = None
        self.emoji_mapping = {}
        self.image_classification_prompt = "请分析这张图片的情感倾向，无需解释，只返回一个中文情绪词，例如：开心、难过、愤怒、惊讶、恶心、害怕、平静、期待、信任、厌恶、快乐、悲伤、恐惧、惊喜等"
        self.content_filtration_prompt = "请判断这张图片是否包含违反规定的内容，仅回复'是'或'否'。如果包含裸露、暴力、敏感或违法内容，回复'是'，否则回复'否'"

    async def load_emoji_mapping(self):
        """加载表情关键字映射表。"""
        try:
            map_path = os.path.join(self.plugin.config_dir, "emoji_mapping.json")
            if os.path.exists(map_path):
                import json
                with open(map_path, encoding="utf-8") as f:
                    self.emoji_mapping = json.load(f)
            else:
                # 默认的表情关键字映射表
                self.emoji_mapping = {
                    "开心": ["开心", "高兴", "快乐", "愉悦", "欢喜", "兴奋", "愉快", "愉悦", "欢快", "喜悦", "欢乐", "喜笑颜开", "眉开眼笑", "笑逐颜开", "哈哈大笑", "大笑", "傻笑", "痴笑", "笑哈哈", "笑", "乐呵呵"],
                    "难过": ["难过", "悲伤", "伤心", "哀伤", "悲痛", "沮丧", "忧郁", "忧伤", "哀愁", "悲凉", "悲切", "心如刀割", "肝肠寸断", "伤心欲绝", "悲痛欲绝", "哀痛", "哀戚", "愁眉苦脸", "闷闷不乐"],
                    "愤怒": ["愤怒", "生气", "恼火", "发火", "恼怒", "恼火", "愤恨", "愤慨", "愤然", "勃然大怒", "怒不可遏", "怒火中烧", "火冒三丈", "暴跳如雷", "气急败坏", "怒气冲天", "气冲冲", "气呼呼"],
                    "惊讶": ["惊讶", "吃惊", "震惊", "惊诧", "讶异", "意外", "意想不到", "大吃一惊", "目瞪口呆", "瞠目结舌", "震惊", "惊悉", "惊呆了", "惊了", "惊到", "惊", "讶"],
                    "恶心": ["恶心", "厌恶", "反感", "厌烦", "腻烦", "憎恶", "嫌恶", "讨厌", "反感", "恶感", "作呕", "反胃", "倒胃口", "讨厌", "嫌"]
                }
                # 保存默认映射表
                with open(map_path, "w", encoding="utf-8") as f:
                    json.dump(self.emoji_mapping, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"加载表情映射表失败: {e}")
            # 使用默认映射表
            self.emoji_mapping = {
                "开心": ["开心", "高兴", "快乐", "愉悦", "欢喜", "兴奋", "愉快", "愉悦", "欢快", "喜悦", "欢乐", "喜笑颜开", "眉开眼笑", "笑逐颜开", "哈哈大笑", "大笑", "傻笑", "痴笑", "笑哈哈", "笑", "乐呵呵"],
                "难过": ["难过", "悲伤", "伤心", "哀伤", "悲痛", "沮丧", "忧郁", "忧伤", "哀愁", "悲凉", "悲切", "心如刀割", "肝肠寸断", "伤心欲绝", "悲痛欲绝", "哀痛", "哀戚", "愁眉苦脸", "闷闷不乐"],
                "愤怒": ["愤怒", "生气", "恼火", "发火", "恼怒", "恼火", "愤恨", "愤慨", "愤然", "勃然大怒", "怒不可遏", "怒火中烧", "火冒三丈", "暴跳如雷", "气急败坏", "怒气冲天", "气冲冲", "气呼呼"],
                "惊讶": ["惊讶", "吃惊", "震惊", "惊诧", "讶异", "意外", "意想不到", "大吃一惊", "目瞪口呆", "瞠目结舌", "震惊", "惊悉", "惊呆了", "惊了", "惊到", "惊", "讶"],
                "恶心": ["恶心", "厌恶", "反感", "厌烦", "腻烦", "憎恶", "嫌恶", "讨厌", "反感", "恶感", "作呕", "反胃", "倒胃口", "讨厌", "嫌"]
            }

    async def _process_image(self, event: AstrMessageEvent, img_path: str, is_temp=False) -> tuple[bool, dict]:
        """统一处理图片：存储、分类、过滤。

        Args:
            event: 消息事件
            img_path: 图片路径
            is_temp: 是否为临时文件

        Returns:
            tuple: (是否成功, 图片索引)
        """
        idx = await self.plugin._load_index()
        base_path = Path(img_path)
        if not base_path.exists():
            logger.error(f"图片文件不存在: {img_path}")
            return False, None

        # 计算图片哈希作为唯一标识符
        hasher = hashlib.md5()
        with open(img_path, "rb") as f:
            hasher.update(f.read())
        hash_val = hasher.hexdigest()

        # 检查图片是否已存在
        for k, v in idx.items():
            if isinstance(v, dict) and v.get("hash") == hash_val:
                logger.debug(f"图片已存在: {hash_val}")
                if is_temp and os.path.exists(img_path):
                    await self._safe_remove_file(img_path)
                return False, None

        # 存储图片到raw目录
        if self.base_dir:
            raw_dir = os.path.join(self.base_dir, "raw")
            os.makedirs(raw_dir, exist_ok=True)
            ext = base_path.suffix.lower() if base_path.suffix else ".jpg"
            filename = f"{int(time.time())}_{hash_val[:8]}{ext}"
            raw_path = os.path.join(raw_dir, filename)
            if is_temp:
                shutil.move(img_path, raw_path)
            else:
                shutil.copy2(img_path, raw_path)
        else:
            raw_path = img_path

        # 过滤图片
        try:
            if await self._filter_image(event, raw_path):
                # 图片分类
                category = await self._classify_image(event, raw_path)
                logger.debug(f"图片分类结果: {category}")

                # 复制图片到对应分类目录
                cat_dir = os.path.join(self.base_dir, "categories", category)
                os.makedirs(cat_dir, exist_ok=True)
                cat_path = os.path.join(cat_dir, os.path.basename(raw_path))
                shutil.copy2(raw_path, cat_path)

                # 更新索引
                idx[raw_path] = {
                    "hash": hash_val,
                    "category": category,
                    "created_at": int(time.time()),
                    "usage_count": 0,
                    "last_used": 0
                }

                return True, idx
            else:
                logger.debug("图片未通过内容过滤，已删除")
                await self._safe_remove_file(raw_path)
                return False, None
        except Exception as e:
            logger.error(f"处理图片失败: {e}")
            await self._safe_remove_file(raw_path)
            return False, None

    async def _classify_image(self, event: AstrMessageEvent, img_path: str) -> str:
        """使用视觉模型对图片进行分类。

        Args:
            event: 消息事件
            img_path: 图片路径

        Returns:
            str: 分类结果
        """
        try:
            if not os.path.exists(img_path):
                logger.error(f"图片文件不存在: {img_path}")
                return None

            # 选择视觉模型
            model = self.plugin.vision_model if hasattr(self.plugin, "vision_model") else "gpt-4o-mini"
            logger.debug(f"使用视觉模型 {model} 对图片进行分类")

            # 构建提示词
            prompt = self.image_classification_prompt

            # 调用LLM生成分类结果
            max_retries = int(self.plugin.config.get("vision_max_retries", 3))
            retry_delay = float(self.plugin.config.get("vision_retry_delay", 1.0))

            for attempt in range(max_retries):
                try:
                    result = await self.plugin.context.llm_generate(event, prompt, image_path=img_path, model=model)
                    if result:
                        # 清理结果，只保留情绪词
                        category = result.strip().replace('"', "").replace("'", "")
                        # 检查分类结果是否在有效情绪列表中
                        valid_emotions = ["开心", "难过", "愤怒", "惊讶", "恶心", "害怕", "平静", "期待", "信任", "厌恶", "快乐", "悲伤", "恐惧", "惊喜"]
                        if category in valid_emotions:
                            return category
                        logger.debug(f"无效的分类结果: {category}")
                except Exception as e:
                    error_msg = str(e)
                    # 检查是否为限流错误
                    is_rate_limit = "429" in error_msg or "RateLimit" in error_msg or "exceeded your current request limit" in error_msg
                    if is_rate_limit:
                        logger.warning(f"图片分类请求被限流，正在重试 ({attempt+1}/{max_retries})")
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                    else:
                        logger.error(f"图片分类失败 (尝试 {attempt+1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (2 ** attempt))
                        else:
                            break
            logger.error("图片分类失败，达到最大重试次数")
            return None
        except Exception as e:
            logger.error(f"图片分类失败: {e}")
            return None

    async def _filter_image(self, event: AstrMessageEvent, img_path: str) -> bool:
        """使用LLM过滤图片内容。

        Args:
            event: 消息事件
            img_path: 图片路径

        Returns:
            bool: 是否通过过滤
        """
        try:
            if not self.plugin.config.get("content_filtration", True):
                return True

            if not os.path.exists(img_path):
                logger.error(f"图片文件不存在: {img_path}")
                return True

            # 构建提示词
            prompt = self.content_filtration_prompt
            model = self.plugin.vision_model if hasattr(self.plugin, "vision_model") else "gpt-4o-mini"

            # 调用LLM进行内容过滤
            max_retries = int(self.plugin.config.get("vision_max_retries", 3))
            retry_delay = float(self.plugin.config.get("vision_retry_delay", 1.0))

            for attempt in range(max_retries):
                try:
                    result = await self.plugin.context.llm_generate(event, prompt, image_path=img_path, model=model)
                    if result and result.strip() == "是":
                        logger.debug("图片未通过内容过滤")
                        return False
                    return True
                except Exception as e:
                    error_msg = str(e)
                    # 检查是否为限流错误
                    is_rate_limit = "429" in error_msg or "RateLimit" in error_msg or "exceeded your current request limit" in error_msg
                    if is_rate_limit:
                        logger.warning(f"图片过滤请求被限流，正在重试 ({attempt+1}/{max_retries})")
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                    else:
                        logger.error(f"图片过滤失败 (尝试 {attempt+1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (2 ** attempt))
                        else:
                            break
            logger.error("图片过滤失败，达到最大重试次数，默认允许通过")
            return True
        except Exception as e:
            logger.error(f"图片过滤失败: {e}")
            return True

    async def _extract_emotions_from_text(self, event: AstrMessageEvent, text: str) -> tuple[list, str]:
        """从文本中提取情绪关键词。

        Args:
            event: 消息事件
            text: 文本内容

        Returns:
            tuple: (情绪关键词列表, 清理后的文本)
        """
        try:
            import re

            # 清理文本
            cleaned_text = re.sub(r"\[图片.*?\]", "", text)
            cleaned_text = re.sub(r"\[表情.*?\]", "", cleaned_text)
            cleaned_text = cleaned_text.strip()
            if not cleaned_text:
                return [], cleaned_text

            # 使用情绪映射表提取关键词
            emotions = []
            for emotion, keywords in self.emoji_mapping.items():
                for keyword in keywords:
                    if keyword in cleaned_text:
                        emotions.append(emotion)
                        break

            return list(set(emotions)), cleaned_text
        except Exception as e:
            logger.error(f"提取情绪关键词失败: {e}")
            return [], text

    async def _file_to_base64(self, file_path: str) -> str:
        """将文件转换为base64编码。

        Args:
            file_path: 文件路径

        Returns:
            str: base64编码
        """
        try:
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"文件转换为base64失败: {e}")
            return ""

    async def _safe_remove_file(self, file_path: str) -> bool:
        """安全删除文件。

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否删除成功
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"已删除文件: {file_path}")
                return True
            logger.debug(f"文件不存在，无需删除: {file_path}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False

    async def _load_index(self) -> dict:
        """加载图片索引。

        Returns:
            dict: 图片索引
        """
        try:
            index_path = os.path.join(self.plugin.config_dir, "index.json")
            if os.path.exists(index_path):
                import json
                with open(index_path, encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            return {}

    async def _save_index(self, idx: dict) -> bool:
        """保存图片索引。

        Args:
            idx: 图片索引

        Returns:
            bool: 是否保存成功
        """
        try:
            index_path = os.path.join(self.plugin.config_dir, "index.json")
            import json
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(idx, f, ensure_ascii=False, indent=4)
            logger.debug("索引文件已保存")
            return True
        except Exception as e:
            logger.error(f"保存索引失败: {e}")
            return False

    async def _compute_hash(self, file_path: str) -> str:
        """计算文件哈希值。

        Args:
            file_path: 文件路径

        Returns:
            str: 哈希值
        """
        try:
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                hasher.update(f.read())
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败: {e}")
            return ""
