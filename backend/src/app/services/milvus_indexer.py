"""轻量文档索引 — 同步写入 Milvus（避免 asyncio 循环冲突）"""
import hashlib
import logging

logger = logging.getLogger(__name__)


def index_document_sync(doc_id: int) -> int:
    """同步拆块写入 Milvus — 从 MySQL 读文档 → 拆块 → 写入向量库"""
    import pymysql
    from app.config import settings
    from pymilvus import MilvusClient, DataType

    # 1. 读 MySQL 文档
    db_url = settings.DATABASE_URL
    # 解析 mysql+aiomysql://user:pass@host:port/db?params
    url = db_url.replace("mysql+aiomysql://", "")
    user_pass, rest = url.split("@")
    user, password = user_pass.split(":")
    host_port, db_name = rest.split("/")
    host = host_port.split(":")[0]
    port = int(host_port.split(":")[1]) if ":" in host_port else 3306
    db_name = db_name.split("?")[0]

    conn = pymysql.connect(host=host, user=user, password=password,
                           database=db_name, port=port, charset="utf8mb4")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, title, category, content FROM policy_documents WHERE id = %s",
                (doc_id,)
            )
            row = cursor.fetchone()
        if not row:
            return 0

        doc_title = row[1] or ""
        doc_category = row[2] or ""
        content = (row[3] or "")[:50000]
    finally:
        conn.close()

    if not content:
        return 0

    # 2. 用中文递归分句器拆块
    from app.services.chinese_text_splitter import create_chinese_splitter

    splitter = create_chinese_splitter(chunk_size=300, chunk_overlap=50)
    chunks = splitter.split_text(content)

    if not chunks:
        return 0

    # 3. 写入 Milvus
    client = MilvusClient(
        uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}",
    )

    collection_name = "policy_docs_v2"
    if not client.has_collection(collection_name):
        schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=100)
        schema.add_field("text", DataType.VARCHAR, max_length=65535)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=768)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=100)
        schema.add_field("parent_content", DataType.VARCHAR, max_length=65535)
        schema.add_field("title", DataType.VARCHAR, max_length=500)
        schema.add_field("category", DataType.VARCHAR, max_length=100)
        schema.add_field("doc_id", DataType.INT64)
        idx = client.prepare_index_params()
        idx.add_index("dense_vector", "",  # AUTOINDEX
                      metric_type="COSINE")
        client.create_collection(collection_name, schema=schema, index_params=idx)
        client.load_collection(collection_name)

    data = []
    for i, chunk in enumerate(chunks):
        text_hash = hashlib.md5(chunk.encode("utf-8")).hexdigest()
        data.append({
            "id": f"doc{doc_id}_{text_hash[:16]}",
            "text": chunk,
            "dense_vector": [0.0] * 768,
            "parent_id": f"doc_{doc_id}",
            "parent_content": chunk,
            "title": doc_title,
            "category": doc_category,
            "doc_id": doc_id,
        })

    client.upsert(collection_name=collection_name, data=data)

    # 4. 更新 MySQL
    conn2 = pymysql.connect(host=host, user=user, password=password,
                            database=db_name, port=port, charset="utf8mb4")
    try:
        with conn2.cursor() as cursor:
            cursor.execute(
                "UPDATE policy_documents SET chunk_count = %s, `indexed` = 1 WHERE id = %s",
                (len(chunks), doc_id)
            )
        conn2.commit()
    finally:
        conn2.close()

    logger.info(f"索引完成: doc_id={doc_id}, chunks={len(chunks)}")
    return len(chunks)
