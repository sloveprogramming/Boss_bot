"""中文优化分句器 + Parent-Child 双层分块策略

Parent-Child Chunking:
  - 父块(Parent): 1200字符, 作为LLM输入的上下文单位（保留完整语义）
  - 子块(Child):  300字符, 作为检索匹配的最小单位（提高命中精度）
  - 检索时命中子块 → 按 parent_id 去重 → 返回父块内容 → CrossEncoder 重排序

中文递归分句器:
  - 分隔符优先级: \n\n > \n > 。|！|？ > ；|;\s > ，|,\s
  - 保留分隔符在chunk末尾，保持语义完整性
"""
import re
import logging
from typing import List, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _split_text_with_regex_from_end(
    text: str, separator: str, keep_separator: bool
) -> List[str]:
    """带保留分隔符的正则分割"""
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
    """针对中文优化的递归分句器

    分隔符优先级（从高到低）：
      段落:  \n\n
      行:    \n
      句:    。|！|？
      分句:  ；|;
      短语:  ，|,
    """

    def __init__(
        self,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
        is_separator_regex: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(keep_separator=keep_separator, **kwargs)
        self._separators = separators or [
            "\n\n",
            "\n",
            "。|！|？",
            r"\.\s|\!\s|\?\s",
            "；|;\s",
            "，|,\s",
        ]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """重写递归分割逻辑，优化中文分句"""
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
        splits = _split_text_with_regex_from_end(text, _separator, self._keep_separator)

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

        return [re.sub(r"\n{2,}", "\n", chunk.strip()) for chunk in final_chunks if chunk.strip() != ""]


class PolicyParentChildSplitter:
    """企业制度文档的 Parent-Child 双层分块器

    使用流程:
        splitter = PolicyParentChildSplitter()
        chunks = splitter.split_documents(documents)
        # 返回的 chunks 是子块，每个子块携带 parent_id 和 parent_content 元数据
    """

    def __init__(
        self,
        parent_chunk_size: int = 1200,
        child_chunk_size: int = 300,
        chunk_overlap: int = 50,
    ):
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.chunk_overlap = chunk_overlap

        # 通用中文分句器
        self.parent_splitter = ChineseRecursiveTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=chunk_overlap,
            keep_separator=True,
        )
        self.child_splitter = ChineseRecursiveTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=chunk_overlap // 2,
            keep_separator=True,
        )

        logger.info(
            f"PolicyParentChildSplitter 初始化: "
            f"parent={parent_chunk_size}, child={child_chunk_size}, overlap={chunk_overlap}"
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """将文档列表分割为子块列表（携带父块信息）

        Args:
            documents: 原始文档列表（每个文档应含 metadata.title/category）

        Returns:
            子块列表，每个子块包含 parent_id, parent_content 元数据
        """
        child_chunks = []

        for i, doc in enumerate(documents):
            # 1) 切分成父块
            parent_docs = self.parent_splitter.split_documents([doc])

            for j, parent_doc in enumerate(parent_docs):
                parent_id = f"doc_{i}_parent_{j}"
                parent_content = parent_doc.page_content

                # 2) 父块切分成子块
                sub_chunks = self.child_splitter.split_documents([parent_doc])

                for k, sub_chunk in enumerate(sub_chunks):
                    # 子块携带父块信息
                    sub_chunk.metadata["parent_id"] = parent_id
                    sub_chunk.metadata["parent_content"] = parent_content
                    sub_chunk.metadata["id"] = f"{parent_id}_child_{k}"

                    # 保留原始文档元数据
                    for key in ("title", "category", "doc_id", "source"):
                        if key in doc.metadata and key not in sub_chunk.metadata:
                            sub_chunk.metadata[key] = doc.metadata[key]

                    child_chunks.append(sub_chunk)

        logger.info(
            f"双层分块完成: {len(documents)} 文档 → {len(child_chunks)} 子块"
        )
        return child_chunks

    def split_text(self, text: str, metadata: dict = None) -> List[Document]:
        """直接分割文本（方便测试用）

        Args:
            text: 原始文本
            metadata: 元数据

        Returns:
            子块列表
        """
        metadata = metadata or {}
        doc = Document(page_content=text, metadata=metadata)
        return self.split_documents([doc])


if __name__ == "__main__":
    # 测试中文分句器
    splitter = ChineseRecursiveTextSplitter(chunk_size=150, chunk_overlap=10)
    test_text = """第一章 总则

第一条 为规范公司员工考勤管理，维护正常工作秩序，根据国家相关法律法规，结合公司实际情况，制定本制度。

第二条 本制度适用于公司全体正式员工、试用期员工及实习生。

第三条 人力资源部负责考勤制度的执行和监督，各部门负责人负责本部门员工的考勤管理。

第二章 考勤规定

第四条 工作时间为周一至周五，上午9:00-12:00，下午13:00-18:00。
午休时间为12:00-13:00。

第五条 员工应按时上下班，不得迟到、早退。迟到或早退30分钟以内的，按次扣罚50元；超过30分钟的，按旷工半天处理。"""
    chunks = splitter.split_text(test_text)
    for i, chunk in enumerate(chunks):
        print(f"\n--- Chunk {i} (len={len(chunk)}) ---")
        print(chunk[:100])
