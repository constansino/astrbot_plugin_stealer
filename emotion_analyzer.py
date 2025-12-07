import json
import re
from pathlib import Path

from astrbot.api import (
    logger,
)
from astrbot.api.event import AstrMessageEvent

# 标准的相对导入


class EmotionAnalyzer:
    """情绪分析服务类，负责文本情绪的提取和分类。"""



    # 缓存最大大小
    _CACHE_MAX_SIZE = 1000

    def __init__(self, categories: list[str], context=None):
        """初始化情绪分析器。"""
        self._categories = categories
        self._context = context  # 保存上下文对象
        self._EMOTION_MAPPING: dict[str, str] = {}  # 情绪类别映射
        self._text_cache: dict[str, str] = {}  # 文本情绪分类缓存

        # 加载情绪映射
        self._load_emotion_mapping()

    def _load_emotion_mapping(self):
        """加载情绪映射文件。"""
        mapping_file_path = Path(__file__).parent / "emotion_mapping.json"
        try:
            with open(mapping_file_path, encoding="utf-8") as f:
                self._EMOTION_MAPPING = json.load(f)
        except Exception as e:
            logger.error(f"加载情绪映射文件失败: {e}")
            # 加载失败时使用空映射作为降级方案
            self._EMOTION_MAPPING = {}

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

    def _extract_emotions_from_text(self, text: str) -> list[str]:
        """从文本中提取情绪类别。

        Args:
            text: 要分析的文本

        Returns:
            提取到的情绪类别列表
        """
        if not text:
            return []

        # 首先尝试通过&&emotion&&格式提取情绪
        if "&&" in text:
            pattern = r"&&([^&]+?)&&"
            emotions = re.findall(pattern, text)
            if emotions:
                mapped_emotions = []
                for emotion in emotions:
                    norm = self._normalize_category(emotion.strip())
                    if norm:
                        mapped_emotions.append(norm)
                return mapped_emotions

        # 直接检查文本是否匹配已知情绪词
        norm_text = text.strip()
        if norm_text in self._EMOTION_MAPPING:
            mapped = self._EMOTION_MAPPING[norm_text]
            if mapped in self._categories:
                return [mapped]

        # 检查文本是否包含英文情绪词
        if norm_text in self._categories:
            return [norm_text]

        # 检查中文情绪词
        cleaned_text = text.strip().lower()
        # 按长度降序排列中文情绪词，确保优先匹配更长的词汇
        sorted_cn_emotions = sorted(self._EMOTION_MAPPING.keys(), key=len, reverse=True)

        found_emotions = []
        for cn_emotion in sorted_cn_emotions:
            if cn_emotion.lower() in cleaned_text:
                positions = [m.start() for m in re.finditer(re.escape(cn_emotion.lower()), cleaned_text)]
                # 只考虑不在括号内的匹配
                external_positions = [pos for pos in positions if not self._is_in_parentheses(cleaned_text, pos)]
                if external_positions:
                    en_emotion = self._EMOTION_MAPPING[cn_emotion]
                    if en_emotion not in found_emotions and en_emotion in self._categories:
                        found_emotions.append(en_emotion)

        return found_emotions

    def _normalize_category(self, category: str | None) -> str:
        """将模型返回的情绪类别规范化到内部英文标签。

        - 将中文情绪词映射为英文标签
        - 兼容旧配置中的“搞怪/其它”等泛用标签
        - 对常见同义词做映射
        """
        if not category:
            return self._categories[0]  # 默认使用第一个分类
        text = str(category).strip()

        if text in self._categories:
            return text

        # 旧分类兼容
        if text == "搞怪":
            # 搞怪类通常是调皮/夸张，可映射到 smirk / happy
            return "smirk" if "smirk" in self._categories else "happy"
        if text in {"其它", "其他", "其他表情", "其他情绪"}:
            return self._categories[0]  # 移除"neutral"后，默认使用第一个分类

        # 同义词 / 近义词映射（中文与英文别名）
        if text in self._EMOTION_MAPPING and self._EMOTION_MAPPING[text] in self._categories:
            return self._EMOTION_MAPPING[text]

        # 通过包含关系粗略匹配
        for key, val in self._EMOTION_MAPPING.items():
            if key in text and val in self._categories:
                return val

        return self._categories[0]  # 默认使用第一个分类



    async def extract_emotions_from_text(self, event: AstrMessageEvent | None, text: str) -> tuple[list[str], str]:
        """从文本中提取情绪关键词。

        支持的形式：
        - 形如 &&开心&& 的显式标记
        - 直接出现的类别关键词（如“开心”“害羞”“哭泣”等），按出现顺序去重

        返回：
        - 提取到的情绪列表
        - 清理掉情绪标记和情绪词后的文本

        优化出处：参考 astrbot_plugin_meme_manager 插件的 resp 方法实现
        """
        if not text:
            return [], text

        res: list[str] = []
        seen: set[str] = set()
        cleaned_text = str(text)
        valid_categories = set(self._categories)

        # 1. 处理显式包裹标记：&&情绪&&
        hex_pattern = r"&&([^&]+?)&&"
        matches = list(re.finditer(hex_pattern, cleaned_text))

        # 收集所有匹配项，避免索引偏移问题
        temp_replacements = []
        for match in matches:
            original = match.group(0)
            emotion = match.group(1).strip()
            norm_cat = self._normalize_category(emotion)

            if norm_cat and norm_cat in valid_categories:
                temp_replacements.append((original, norm_cat))
            else:
                temp_replacements.append((original, ""))  # 非法或未知情绪静默移除

        # 保持原始顺序替换
        for original, emotion in temp_replacements:
            cleaned_text = cleaned_text.replace(original, "", 1)
            if emotion and emotion not in seen:
                seen.add(emotion)
                res.append(emotion)

        # 2. 处理直接出现的英文情绪词（直接匹配分类）
        for cat in self._categories:
            if cat in seen:
                continue

            # 使用边界匹配确保是完整单词
            pattern = rf"\b{re.escape(cat)}\b"
            matches = list(re.finditer(pattern, cleaned_text, re.IGNORECASE))

            # 检查是否有括号外的匹配
            has_external_match = False
            for match in matches:
                if not self._is_in_parentheses(cleaned_text, match.start()):
                    has_external_match = True
                    break

            if has_external_match:
                seen.add(cat)
                res.append(cat)

                # 注意：不再移除英文情绪词，保留原始文本的完整性
                # 只提取情绪，不修改文本内容

        # 3. 处理直接出现的中文情绪词（使用统一的EMOTION_MAPPING）
        # 按长度排序，优先处理长的情绪词
        sorted_cn_emotions = sorted(self._EMOTION_MAPPING.keys(), key=len, reverse=True)

        for cn_emotion in sorted_cn_emotions:
            en_emotion = self._EMOTION_MAPPING[cn_emotion]
            if en_emotion in valid_categories and en_emotion not in seen:
                positions = []
                start = 0

                # 收集所有匹配位置
                while True:
                    pos = cleaned_text.find(cn_emotion, start)
                    if pos == -1:
                        break
                    positions.append(pos)
                    start = pos + 1

                # 检查是否有括号外的匹配
                external_positions = [pos for pos in positions if not self._is_in_parentheses(cleaned_text, pos)]

                if external_positions:
                    seen.add(en_emotion)
                    res.append(en_emotion)

                    # 注意：不再移除中文情绪词，保留原始文本的完整性
                    # 只提取情绪，不修改文本内容

        # 清理多余的空格
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()



        return res, cleaned_text

    def _clean_cache(self, cache: dict) -> None:
        """清理缓存，保持在最大大小以下。

        Args:
            cache: 要清理的缓存字典
        """
        if len(cache) > self._CACHE_MAX_SIZE:
            keys_to_keep = list(cache.keys())[-self._CACHE_MAX_SIZE:]
            items_to_keep = {k: cache[k] for k in keys_to_keep}
            cache.clear()
            cache.update(items_to_keep)

    def get_emotions_from_text(self, text: str) -> list[str]:
        """从文本中获取情绪类别。

        Args:
            text: 要分析的文本

        Returns:
            提取到的情绪类别列表
        """
        return self._extract_emotions_from_text(text)

    def analyze_text(self, event: AstrMessageEvent, text: str) -> str:
        """分析文本情绪的统一接口。

        从文本中提取情绪。

        Args:
            event: 消息事件
            text: 要分析的文本

        Returns:
            情绪类别，如果分析失败则返回空字符串
        """
        # 从文本中提取情绪
        extracted_emotions = self._extract_emotions_from_text(text)
        if extracted_emotions:
            # 返回第一个找到的情绪
            return extracted_emotions[0]

        return ""

    def get_emotion_mapping(self) -> dict[str, str]:
        """获取情绪映射。

        Returns:
            情绪映射字典
        """
        return self._EMOTION_MAPPING

    def update_config(self, categories: list[str], context=None):
        """更新配置。

        Args:
            categories: 情绪类别列表
            context: 上下文对象
        """
        self._categories = categories
        if context:
            self._context = context

    def cleanup(self):
        """清理资源。"""
        pass
