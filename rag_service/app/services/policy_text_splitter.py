"""中文优化分句器 + Parent-Child 双层分块策略 (EduRAG 版本)

Parent-Child Chunking:
  - 父块(Parent): 1200字符, 作为LLM输入的上下文单位（保留完整语义）
  - 子块(Child):  300字符, 作为检索匹配的最小单位（提高命中精度）
  - 检索时命中子块 → 按 parent_id 去重 → 返回父块内容 → CrossEncoder 重排序

中文递归分句器（从 EduRAG 迁移）:
  - 分隔符优先级: 段落 > 换行 > 中文句尾 > 英文句尾 > 分号 > 逗号
  - 保留分隔符在chunk末尾，保持语义完整性
"""
import re
import logging
import hashlib
from typing import List, Optional, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _split_text_with_regex(text: str, separator: str, keep_separator: bool) -> List[str]:
    """按正则分隔符拆分文本，可选择保留分隔符"""
    if separator:
        if keep_separator:
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
    """中文递归分句器"""

    def __init__(
        self,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
        is_separator_regex: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(keep_separator=keep_separator, **kwargs)
        self._separators = separators or [
            "\n\n",             # 段落分隔
            "\n",               # 换行
            "。|！|？",         # 中文句子结尾
            r"\.\s|\!\s|\?\s",  # 英文句子结尾（后跟空格）
            "；|;\s",           # 分号
            "，|,\s"            # 逗号
        ]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """递归拆分核心逻辑"""
        final_chunks = []
        separator = separators[-1]
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

        _good_splits = []
        _sep = "" if self._keep_separator else separator
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, _sep)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, _sep)
            final_chunks.extend(merged_text)

        return [
            re.sub(r"\n{2,}", "\n", chunk.strip())
            for chunk in final_chunks
            if chunk.strip() != ""
        ]


class PolicyParentChildSplitter:
    """Parent-Child 双层分块器

    子块(300字)用于检索匹配，父块(1200字)作为LLM上下文。
    检索命中子块 → parent_id 去重 → 返回父块内容。
    """

    def __init__(self, parent_chunk_size: int = 1200, child_chunk_size: int = 300,
                 chunk_overlap: int = 50):
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.chunk_overlap = chunk_overlap

        # 父块用较大的拆分器
        self._parent_splitter = ChineseRecursiveTextSplitter(
            keep_separator=True,
            is_separator_regex=True,
            chunk_size=parent_chunk_size,
            chunk_overlap=chunk_overlap,
        )
        # 子块用较小的拆分器
        self._child_splitter = ChineseRecursiveTextSplitter(
            keep_separator=True,
            is_separator_regex=True,
            chunk_size=child_chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """将文档列表先拆父块，再拆子块，子块带 parent_id"""
        all_child_docs = []

        for doc in documents:
            parent_text = doc.page_content
            parent_chunks = self._parent_splitter.split_text(parent_text)

            for p_idx, parent_chunk in enumerate(parent_chunks):
                parent_id = f"{doc.metadata.get('doc_id', '')}_{hashlib.md5(parent_chunk.encode()).hexdigest()[:8]}"
                child_chunks = self._child_splitter.split_text(parent_chunk)

                for c_idx, child_chunk in enumerate(child_chunks):
                    child_doc = Document(
                        page_content=child_chunk,
                        metadata={
                            **doc.metadata,
                            "parent_id": parent_id,
                            "parent_content": parent_chunk,
                            "child_index": c_idx,
                            "parent_index": p_idx,
                        },
                    )
                    all_child_docs.append(child_doc)

        logger.info(f"Parent-Child 分块: {len(parent_chunks)} 父块 → {len(all_child_docs)} 子块")
        return all_child_docs
