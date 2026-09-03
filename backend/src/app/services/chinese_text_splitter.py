"""中文递归分句器 — 从 EduRAG 项目迁移

分隔符优先级（从大到小）：
  1. 段落分隔 (双换行)
  2. 换行
  3. 中文句子结尾 (。！？)
  4. 英文句子结尾（后跟空格）
  5. 分号
  6. 逗号

特性：
  - keep_separator=True  保留分隔符在 chunks 末尾，保持语义完整
  - 递归拆分  优先用大分隔符，不够再降级
  - 合并短块  小于 chunk_size 的合并，避免碎片
"""
import re
from typing import List, Optional, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)


def _split_text_with_regex(text: str, separator: str, keep_separator: bool) -> List[str]:
    """按正则分隔符拆分文本，可选择保留分隔符"""
    if separator:
        if keep_separator:
            # 括号保留分隔符在原位置
            _splits = re.split(f"({separator})", text)
            splits = ["".join(i) for i in zip(_splits[0::2], _splits[1::2])]
            if len(_splits) % 2 == 1:
                splits += _splits[-1:]
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [s for s in splits if s != ""]


class ChineseRecursiveTextSplitter(RecursiveCharacterTextSplitter):
    """中文优化递归分句器

    继承 langchain 的 RecursiveCharacterTextSplitter，
    使用中文专属分隔符序列逐级拆分。

    Args:
        chunk_size: 目标块大小（字符数）
        chunk_overlap: 块间重叠字符数
        keep_separator: 是否保留分隔符
    """

    def __init__(
        self,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
        is_separator_regex: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(keep_separator=keep_separator, **kwargs)
        # 中文专属分隔符序列（从大到小）
        self._separators = separators or [
            "\n\n",           # 段落分隔
            "\n",             # 换行
            "。|！|？",       # 中文句子结尾
            r"\.\s|\!\s|\?\s",  # 英文句子结尾（后跟空格）
            "；|;\s",         # 分号
            "，|,\s"          # 逗号
        ]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """递归拆分核心逻辑"""
        final_chunks = []

        # 找到当前文本最适合的分隔符
        separator = separators[-1]  # 默认用最小分隔符
        new_separators = []
        for i, _s in enumerate(separators):
            _separator = _s if self._is_separator_regex else re.escape(_s)
            if _s == "":
                separator = _s
                break
            if re.search(_separator, text):
                separator = _s
                new_separators = separators[i + 1:]
                break

        _separator = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex(text, _separator, self._keep_separator)

        # 处理拆分结果：短块合并，长块继续递归拆分
        _good_splits = []
        _separator = "" if self._keep_separator else separator
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, _separator)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)

        if _good_splits:
            merged_text = self._merge_splits(_good_splits, _separator)
            final_chunks.extend(merged_text)

        # 清理多余换行
        return [
            re.sub(r"\n{2,}", "\n", chunk.strip())
            for chunk in final_chunks
            if chunk.strip() != ""
        ]


def create_chinese_splitter(chunk_size: int = 300, chunk_overlap: int = 50) -> ChineseRecursiveTextSplitter:
    """工厂函数：创建中文分句器实例"""
    return ChineseRecursiveTextSplitter(
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
