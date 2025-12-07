import asyncio
import base64
import hashlib
import json
import os
import random
import shutil
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

# 标准的相对导入
from .cache_service import CacheService

# 尝试导入 PIL 用于图片元数据检查
try:
    from PIL import Image as PILImage  # type: ignore[import]
except Exception:
    PILImage = None


class ImageProcessor:
    """图片处理服务类，负责图片的分类、过滤、存储等功能。"""

    # 图片分类提示词模板
    IMAGE_CLASSIFICATION_PROMPT = '你是专业的表情包分析专家，请严格按照以下要求处理图片：\n1. 观察图片内容，生成简洁、准确、具体的描述（10-30字），包含：\n   - 主要内容（人物/动物/物体/风格）\n   - 表情特征（如嘴角上扬、眼睛弯成月牙、脸红、流泪等）\n   - 具体情绪\n2. 从以下英文情绪标签中选择唯一最匹配的：happy, neutral, sad, angry, shy, surprised, smirk, cry, confused, embarrassed, sigh, speechless\n3. 同时提取2-5个能描述图片特征的关键词标签（如cute, smile, blush, tear, angry等）\n4. 必须返回严格的JSON格式，包含以下三个字段：\n   - description: 生成的图片描述\n   - category: 选择的英文情绪标签\n   - tags: 提取的关键词数组\n5. 如果是二次元/动漫/卡通角色，必须根据表情实际情绪分类\n6. 不要添加任何JSON之外的内容，确保JSON可以被程序直接解析\n\n正确示例：\n- {"description":"一个卡通猫角色,眼睛弯成月牙,嘴角上扬,露出开心的笑容","category":"happy","tags":["cute","smile","cartoon"]}\n- {"description":"一个动漫女孩,脸红低头,表现出害羞的样子","category":"shy","tags":["blush","anime","girl"]}\n- {"description":"一个角色,眼泪流下,表情悲伤","category":"cry","tags":["tear","sad","cartoon"]}'

    # 图片过滤提示词模板
    IMAGE_FILTER_PROMPT = "根据以下审核准则判断图片是否符合: {filtration_rule}。只返回是或否。"

    def __init__(self, context: Context, base_dir: Path, vision_provider_id: str | None = None, cache_service: CacheService = None):
        """初始化图片处理器。

        Args:
            context: 插件上下文
            base_dir: 插件基础目录
            vision_provider_id: 视觉模型提供商ID
            cache_service: 缓存服务实例
        """
        self.context = context
        self.base_dir = Path(base_dir)  # 确保base_dir是Path对象
        self.vision_provider_id = vision_provider_id
        self.cache_service = cache_service

        # 加载提示词配置
        self._load_prompts()

    def _load_prompts(self):
        """加载提示词配置。"""
        prompts_file_path = Path(__file__).parent / "prompts.json"
        try:
            with open(prompts_file_path, encoding="utf-8") as f:
                prompts = json.load(f)
                if "IMAGE_CLASSIFICATION_PROMPT" in prompts:
                    self.IMAGE_CLASSIFICATION_PROMPT = prompts["IMAGE_CLASSIFICATION_PROMPT"]
        except Exception as e:
            logger.warning(f"加载提示词文件失败: {e}，将使用默认提示词")

    async def _pick_vision_provider(self, event: AstrMessageEvent | None, backend_tag: str = "") -> str | None:
        """选择视觉模型提供商。

        Args:
            event: 消息事件对象
            backend_tag: 后端标签

        Returns:
            视觉模型提供商ID
        """
        if self.vision_provider_id:
            return self.vision_provider_id
        if backend_tag:
            # 如果提供了backend_tag，尝试使用它获取模型
            try:
                model = self.context.model_manager.get_visual_model(backend_tag=backend_tag)
                if model:
                    return backend_tag
            except Exception as e:
                logger.debug(f"通过backend_tag获取视觉模型失败: {e}")
        if event is None:
            logger.error("未设置视觉模型，且没有消息事件对象来获取默认模型")
            return None
        try:
            provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
            if not provider_id:
                logger.error("无法获取当前聊天的视觉模型提供商")
            return provider_id
        except Exception as e:
            logger.error(f"获取视觉模型提供商时出错: {e}")
            return None

    async def _compute_hash(self, file_path: str) -> str:
        """计算文件的SHA256哈希值。

        Args:
            file_path: 文件路径

        Returns:
            文件哈希值
        """
        try:
            def sync_compute_hash():
                with open(file_path, "rb") as f:
                    data = f.read()
                return hashlib.sha256(data).hexdigest()
            return await asyncio.to_thread(sync_compute_hash)
        except Exception:
            return ""

    async def _file_to_base64(self, path: str) -> str:
        """将文件转换为base64编码。

        Args:
            path: 文件路径

        Returns:
            base64编码字符串
        """
        try:
            def sync_file_to_base64():
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            return await asyncio.to_thread(sync_file_to_base64)
        except Exception:
            return ""

    async def _filter_image(self, event: AstrMessageEvent | None, file_path: str, filtration_prompt: str, content_filtration: bool) -> bool:
        """过滤图片内容。

        Args:
            event: 消息事件对象
            file_path: 图片文件路径
            filtration_prompt: 过滤提示词
            content_filtration: 是否启用内容过滤

        Returns:
            是否通过过滤
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"过滤图片时文件不存在: {file_path}")
                return True  # 文件不存在时默认不过滤

            if not content_filtration:
                return True
            prov_id = await self._pick_vision_provider(event)
            if not prov_id:
                return True
            prompt = self.IMAGE_FILTER_PROMPT.format(filtration_rule=filtration_prompt)

            # 添加API调用重试机制
            max_retries = 3
            retry_delay = 1  # 秒

            for retry in range(max_retries):
                try:
                    resp = await self.context.llm_generate(
                        chat_provider_id=prov_id,
                        prompt=prompt,
                        image_urls=[f"file:///{os.path.abspath(file_path)}"],
                    )
                    txt = resp.completion_text.strip()
                    # 逻辑取反：如果返回"是"表示图片包含违规内容，应该返回False表示过滤未通过
                    return not (("是" in txt) or ("符合" in txt) or ("yes" in txt.lower()))
                except Exception as e:
                    # 检查是否为限流错误
                    error_str = str(e)
                    is_rate_limit = "429" in error_str or "RateLimit" in error_str or "exceeded your current request limit" in error_str

                    if retry < max_retries - 1:
                        if is_rate_limit:
                            logger.warning(f"API请求限流，{retry_delay}秒后重试 ({retry+1}/{max_retries})")
                        else:
                            logger.warning(f"API请求失败，{retry_delay}秒后重试 ({retry+1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        if is_rate_limit:
                            logger.error(f"API请求限流，重试失败: {e}")
                        else:
                            logger.error(f"API请求失败，重试失败: {e}")
                        return True  # 重试失败时默认不过滤
        except Exception:
            return True

    async def _store_image(self, src_path: str, category: str | None = None) -> str:
        """将图片保存到raw目录，并基于内容去重。
        如果提供了category，则同时保存到分类目录。

        Args:
            src_path: 源图片路径
            category: 图片分类（可选）

        Returns:
            保存到raw目录的图片路径
        """
        if not self.base_dir:
            return src_path

        # 计算图片内容的SHA256哈希值用于去重
        file_hash = await self._compute_hash(src_path)
        if not file_hash:
            # 如果哈希计算失败，回退到时间戳+随机数的命名方式
            name = f"{int(asyncio.get_event_loop().time()*1000)}_{random.randint(1000,9999)}"
        else:
            # 使用哈希值作为文件名，实现内容去重
            name = file_hash

        ext = os.path.splitext(src_path)[1] or ".jpg"
        raw_dir = self.base_dir / "raw"
        raw_dest = raw_dir / f"{name}{ext}"

        try:
            def sync_store_image():
                # 同步部分
                raw_dir.mkdir(parents=True, exist_ok=True)  # 确保raw目录存在

                # 检查raw目录中文件是否已存在
                if raw_dest.exists():
                    logger.debug(f"图片已存在于raw目录: {raw_dest}")
                else:
                    # 复制到raw目录
                    shutil.copyfile(src_path, raw_dest)
                    logger.debug(f"图片已存储到raw目录: {raw_dest}")

                # 如果提供了分类，则复制到分类目录
                if category:
                    cat_dir = self.base_dir / "categories" / category
                    cat_dest = cat_dir / f"{name}{ext}"
                    cat_dir.mkdir(parents=True, exist_ok=True)  # 确保分类目录存在

                    # 检查分类目录中文件是否已存在
                    if cat_dest.exists():
                        logger.debug(f"图片已存在于分类目录: {cat_dest}")
                    else:
                        shutil.copyfile(src_path, cat_dest)
                        logger.debug(f"图片已存储到分类目录: {cat_dest}")

            await asyncio.to_thread(sync_store_image)

            return raw_dest.as_posix()
        except Exception as e:
            logger.error(f"存储图片失败: {e}")
            return src_path

    async def _safe_remove_file(self, file_path: str) -> bool:
        """安全删除文件。

        Args:
            file_path: 文件路径

        Returns:
            是否删除成功
        """
        try:
            await asyncio.to_thread(os.remove, file_path)
            return True
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False

    def _is_likely_emoji_by_metadata(self, file_path: str) -> bool:
        """根据图片元数据判断是否可能是表情包。

        Args:
            file_path: 图片文件路径

        Returns:
            是否可能是表情包
        """
        if PILImage is None:
            return True  # 没有PIL时默认通过

        try:
            with PILImage.open(file_path) as img:
                width, height = img.size
                # 检查图片尺寸是否符合表情包特征
                if max(width, height) > 1500 or min(width, height) < 50:  # 调整为更严格的尺寸限制
                    return False
                # 检查图片宽高比
                aspect_ratio = max(width, height) / min(width, height)
                if aspect_ratio > 3.5:  # 调整为更严格的宽高比限制
                    return False
                # 检查文件大小
                file_size = os.path.getsize(file_path)
                if file_size > 2 * 1024 * 1024:  # 超过2MB的图片可能不是表情包
                    return False
                return True
        except Exception:
            return True

    async def classify_image(self, event: AstrMessageEvent | None, file_path: str, emoji_only: bool, categories: list[str] = None, backend_tag: str = "") -> tuple[str, list[str], str, str]:
        """调用多模态模型对图片进行情绪分类与标签抽取。

        Args:
            event: 当前消息事件
            file_path: 本地图片路径
            emoji_only: 是否仅处理表情包
            categories: 情绪分类列表

        Returns:
            (category, tags, desc, emotion): 类别、标签、详细描述、情感标签
        """
        try:
            logger.debug(f"开始分类图片: {file_path}, emoji_only: {emoji_only}")

            # 确保file_path是绝对路径
            file_path = os.path.abspath(file_path)

            # 确保categories是一个列表
            if categories is None:
                categories = []

            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"分类图片时文件不存在: {file_path}")
                fallback = categories[0] if categories else "其它"
                return fallback, [], "", fallback

            # 计算文件哈希用于缓存
            h = await self._compute_hash(file_path)

            # 检查图片分类结果缓存
            if h and self.cache_service:
                cached_result = self.cache_service.get("image_cache", h)
                if cached_result and len(cached_result) >= 4:
                    logger.debug(f"使用图片分类缓存结果: {h}")
                    return cached_result

            # 仅在启用表情包过滤时进行判断
            if emoji_only:
                # 先用元数据做一次快速过滤，明显不是表情图片的直接跳过
                is_likely_emoji = self._is_likely_emoji_by_metadata(file_path)
                logger.debug(f"元数据判断是否为表情包: {is_likely_emoji}")
                if not is_likely_emoji:
                    return "非表情包", [], "", "非表情包"

            # 获取视觉模型
            prov_id = await self._pick_vision_provider(event, backend_tag)
            if not prov_id:
                # 当无法获取到视觉模型时，仍然将图片分类为默认分类并存储
                logger.warning("无法获取视觉模型，将使用默认分类处理图片")
                fallback = categories[0] if categories else "其它"
                return fallback, [], "", fallback
            logger.debug(f"获取视觉模型成功: {prov_id}")

            # 使用与_filter_image方法一致的方式生成file URI
            file_url = f"file:///{os.path.abspath(file_path)}"

            # 合并表情包判断和分类为一次LLM调用，减少API请求次数
            max_retries = 3
            retry_delay = 1  # 秒

            for retry in range(max_retries):
                try:
                    if emoji_only:
                        # 动态生成情绪标签列表
                        emotion_labels_str = ", ".join(categories) if categories else "happy, neutral, sad, angry, shy, surprised, smirk, cry, confused, embarrassed, sigh, speechless"

                        combined_prompt = (
                            "你是专业的表情包分析专家，请严格按照以下要求处理图片：\n"
                            "首先判断：这张图片是否为聊天表情包（emoji/meme/sticker）？\n"
                            "表情包通常具有以下特征：\n"
                            "1）尺寸相对较小，主要用于聊天中快速表达情绪或态度；\n"
                            "2）画面主体清晰突出，通常集中在人物/卡通形象/动物或简洁抽象图案上；\n"
                            "3）可能包含少量文字、夸张表情或动作来强化情绪表达；\n"
                            "4）常以方图或接近方图的比例出现（宽高比通常在1:2到2:1之间）；\n"
                            "5）风格简洁明了，能在短时间内传达情绪。\n"
                            "以下情况一律视为非表情包：\n"
                            "- 风景照、生活照片、人像摄影等写实类图片\n"
                            "- 完整漫画页、长截图（高度远大于宽度）\n"
                            "- 聊天记录截图、社交媒体界面截图\n"
                            "- 宣传海报、商业广告、产品图片\n"
                            "- 电脑/手机壁纸（通常尺寸较大且内容复杂）\n"
                            "- 含大量说明文字的信息图、流程图、文档截图\n"
                            "- 视频帧截图、电影/动漫截图（非专门制作的表情）\n"
                            "- 像素极低或严重模糊无法识别内容的图片\n"
                            "\n"
                            '如果不是表情包，请直接返回："非表情包"\n'
                            "\n"
                            "如果是表情包，请继续按照以下要求进行分类：\n"
                            "1. 观察图片内容，生成简洁、准确、具体的描述（10-30字），包含：\n"
                            "   - 主要内容（人物/动物/物体/风格）\n"
                            "   - 表情特征（如嘴角上扬、眼睛弯成月牙、脸红、流泪等）\n"
                            "   - 具体情绪\n"
                            f"2. 从以下英文情绪标签中选择唯一最匹配的：{emotion_labels_str}\n"
                            "3. 同时提取2-5个能描述图片特征的关键词标签（如cute, smile, blush, tear, angry等）\n"
                            "4. 必须返回严格的JSON格式，包含以下三个字段：\n"
                            "   - description: 生成的图片描述\n"
                            "   - category: 选择的英文情绪标签\n"
                            "   - tags: 提取的关键词数组\n"
                            "5. 如果是二次元/动漫/卡通角色，必须根据表情实际情绪分类\n"
                            "6. 不要添加任何JSON之外的内容，确保JSON可以被程序直接解析\n"
                            "\n"
                            "正确示例：\n"
                            '- {"description":"一个卡通猫角色,眼睛弯成月牙,嘴角上扬,露出开心的笑容","category":"happy","tags":["cute","smile","cartoon"]}\n'
                            '- {"description":"一个动漫女孩,脸红低头,表现出害羞的样子","category":"shy","tags":["blush","anime","girl"]}\n'
                            '- {"description":"一个角色,眼泪流下,表情悲伤","category":"cry","tags":["tear","sad","cartoon"]}'
                        )
                        resp = await self.context.llm_generate(
                            chat_provider_id=prov_id,
                            prompt=combined_prompt,
                            image_urls=[file_url],
                        )
                        txt = resp.completion_text.strip()

                        # 检查是否为非表情包
                        if txt == "非表情包":
                            return "非表情包", [], "", "非表情包"
                    else:
                        # 不启用表情包过滤时，动态生成分类提示词
                        # 动态生成情绪标签列表
                        emotion_labels_str = ", ".join(categories) if categories else "happy, neutral, sad, angry, shy, surprised, smirk, cry, confused, embarrassed, sigh, speechless"

                        # 替换提示词中的情绪标签列表
                        dynamic_prompt = self.IMAGE_CLASSIFICATION_PROMPT.replace(
                            "happy, neutral, sad, angry, shy, surprised, smirk, cry, confused, embarrassed, sigh, speechless",
                            emotion_labels_str
                        )

                        resp = await self.context.llm_generate(
                            chat_provider_id=prov_id,
                            prompt=dynamic_prompt,
                            image_urls=[file_url],
                        )
                        txt = resp.completion_text.strip()

                    # 成功获取结果，跳出重试循环
                    break
                except Exception as e:
                    # 检查是否为限流错误
                    error_str = str(e)
                    is_rate_limit = "429" in error_str or "RateLimit" in error_str or "exceeded your current request limit" in error_str

                    if retry < max_retries - 1:
                        if is_rate_limit:
                            logger.warning(f"API请求限流，{retry_delay}秒后重试 ({retry+1}/{max_retries})")
                        else:
                            logger.warning(f"API请求失败，{retry_delay}秒后重试 ({retry+1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        if is_rate_limit:
                            logger.error(f"API请求限流，重试失败: {e}")
                        else:
                            logger.error(f"API请求失败，重试失败: {e}")
                        raise

            # 解析模型返回结果
            txt = resp.completion_text.strip()
            logger.debug(f"模型原始返回结果: {txt}")

            # 处理可能的Markdown代码块
            import re
            code_block_pattern = re.compile(r"```(json)?\s*(.*?)\s*```", re.DOTALL)
            match = code_block_pattern.search(txt)
            if match:
                txt = match.group(2).strip()

            result = json.loads(txt)

            # 提取分类结果
            category = result.get("category", categories[0] if categories else "happy")  # 默认使用配置的第一个分类
            tags = result.get("tags", [])
            desc = result.get("description", "")
            emotion = category

            # 确保分类结果在指定的分类列表中
            if categories and category not in categories:
                # 如果分类不在列表中，使用第一个分类作为默认值
                category = categories[0] if categories else "happy"
                emotion = category
                logger.warning(f"模型返回的分类{result.get('category')}不在配置的分类列表中，使用默认分类{category}")

            logger.debug(f"图片分类结果: category={category}, tags={tags}, desc={desc}, emotion={emotion}")

            # 缓存分类结果
            if h and self.cache_service:
                self.cache_service.set("desc_cache", h, desc, persist=True)
                self.cache_service.set("image_cache", h, (category, tags, desc, emotion), persist=True)
                logger.debug(f"缓存分类结果: {h}")

            return category, tags, desc, emotion
        except Exception as e:
            logger.error(f"图片分类失败: {e}", exc_info=True)
            fallback = categories[0] if categories else "其它"
            return fallback, [], "", fallback

    async def filter_image(self, event: AstrMessageEvent | None, file_path: str, filtration_prompt: str, content_filtration: bool) -> bool:
        """过滤图片内容。

        Args:
            event: 消息事件对象
            file_path: 图片文件路径
            filtration_prompt: 过滤提示词
            content_filtration: 是否启用内容过滤

        Returns:
            是否通过过滤
        """
        return await self._filter_image(event, file_path, filtration_prompt, content_filtration)

    async def process_image(self, event: AstrMessageEvent | None, file_path: str, is_temp: bool = False, idx: dict | None = None,
                          categories: list[str] = None, emoji_only: bool = False, content_filtration: bool = False,
                          filtration_prompt: str = "", backend_tag: str = "") -> tuple[bool, dict | None]:
        """统一处理图片的方法，包括过滤、分类、存储和索引更新。

        Args:
            event: 消息事件对象
            file_path: 图片文件路径
            is_temp: 是否为临时文件
            idx: 可选的索引字典
            categories: 分类列表
            emoji_only: 是否仅处理表情包
            content_filtration: 是否启用内容过滤
            filtration_prompt: 过滤提示词
            backend_tag: 后端标签

        Returns:
            (成功与否, 更新后的索引字典)
        """
        try:
            logger.debug(f"开始处理图片: {file_path}, is_temp: {is_temp}, emoji_only: {emoji_only}")

            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"处理图片时文件不存在: {file_path}")
                if is_temp:
                    await self._safe_remove_file(file_path)
                return False, idx

            # 确保categories是一个列表
            if categories is None:
                categories = []

            # 先将图片保存到raw目录（不指定分类）
            raw_stored_path = await self._store_image(file_path)
            logger.debug(f"图片已保存到raw目录: {raw_stored_path}")

            # 内容过滤（使用raw目录的路径）
            ok = await self._filter_image(event, raw_stored_path, filtration_prompt, content_filtration)
            if not ok:
                logger.debug(f"图片内容过滤未通过: {raw_stored_path}")
                if is_temp:
                    await self._safe_remove_file(file_path)
                # 删除已保存的raw文件
                await self._safe_remove_file(raw_stored_path)
                return False, idx

            # 图片分类（使用raw目录的路径）
            cat, tags, desc, emotion = await self.classify_image(event, raw_stored_path, emoji_only, categories, backend_tag)
            logger.debug(f"图片分类结果: category={cat}, tags={tags}, desc={desc}, emotion={emotion}")

            # 如果分类为"非表情包"且emoji_only为true，跳过存储
            if (cat == "非表情包" or emotion == "非表情包") and emoji_only:
                logger.debug(f"图片非表情包且仅处理表情包模式开启，跳过存储: {raw_stored_path}")
                if is_temp:
                    await self._safe_remove_file(file_path)
                # 删除已保存的raw文件
                await self._safe_remove_file(raw_stored_path)
                return False, idx

            # 确定最终分类 - 在classify_image中已经确保了cat在categories列表中
            final_category = cat if categories else None
            logger.debug(f"最终分类: {final_category}")

            # 如果有有效分类，将图片复制到分类目录
            if final_category:
                await self._store_image(raw_stored_path, final_category)
                logger.debug(f"图片已保存到分类目录: {final_category}")

            # 更新索引（始终使用raw目录的路径）
            # 如果没有提供索引，则创建新的
            if idx is None:
                idx = {}

            # 使用raw目录的路径作为索引键
            final_stored_path = raw_stored_path

            idx[final_stored_path] = {
                "category": cat,
                "tags": tags,
                "backend_tag": backend_tag,
                "created_at": int(asyncio.get_event_loop().time()),
                "usage_count": 0,
                "desc": desc,
                "emotion": emotion,
            }
            logger.debug(f"索引更新成功: {final_stored_path}")

            # 删除源文件（如果是临时文件）
            if is_temp and file_path != raw_stored_path:
                await self._safe_remove_file(file_path)

            return True, idx
        except Exception as e:
            logger.error(f"处理图片失败: {e}", exc_info=True)
            if is_temp:
                await self._safe_remove_file(file_path)
            return False, idx

    def update_config(self, categories: list[str], content_filtration: bool, filtration_prompt: str, vision_provider_id: str, emoji_only: bool):
        """更新图片处理器的配置。

        Args:
            categories: 分类列表
            content_filtration: 是否启用内容过滤
            filtration_prompt: 过滤提示词
            vision_provider_id: 视觉模型提供商ID
            emoji_only: 是否仅处理表情包
        """
        self.vision_provider_id = vision_provider_id

    def initialize(self):
        """初始化图片处理器。"""
        pass

    def cleanup(self):
        """清理资源。"""
        pass



