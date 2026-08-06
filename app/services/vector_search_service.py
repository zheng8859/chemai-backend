"""Vector search service — ChromaDB-powered similarity search for historical exams.

三层检索策略 (25号 §七.4):
  1. 关键词匹配 — 知识点重叠度 + 难度匹配优先排序
  2. ChromaDB 向量检索 — embedding 语义相似度精筛
  3. 联网搜索兜底 — MiMo enable_search (仅 keyword_count < 3 时触发)

当前实现: 层1 + 层2。层3 待 LLM router 就绪后接入。
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.question_bank import HistoricalExam
from ..config import CHROMA_DB_PATH, CHROMA_COLLECTION, DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# ChromaDB client (lazy init)
# ═══════════════════════════════════════════════

_chroma_client = None
_collection = None


def _get_collection():
    """Lazy-init ChromaDB collection. Returns None if unavailable."""
    global _chroma_client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
        _collection = _chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB connected: %s/%s", CHROMA_DB_PATH, CHROMA_COLLECTION)
        return _collection
    except Exception as e:
        logger.warning("ChromaDB unavailable, falling back to keyword-only: %s", e)
        return None


# ═══════════════════════════════════════════════
# Embedding
# ═══════════════════════════════════════════════

def _build_embed_text(question: HistoricalExam) -> str:
    """构建嵌入文本 (25号 §八.2: _build_embed_text)."""
    parts = [
        f"考点: {'、'.join(question.knowledge_point_tags or [])}。",
        f"题型: {question.question_type or '未知'}。",
        f"难度: {question.difficulty or 'medium'}。",
        f"来源: {question.source} {question.year} {question.question_number}。",
        f"题目: {(question.content or '')[:500]}。",
        f"答案: {question.answer or ''}",
    ]
    return "".join(parts)


def _get_embedding(text: str) -> Optional[list[float]]:
    """调用 dashscope text-embedding-v3 获取 1024 维向量。"""
    if not DASHSCOPE_API_KEY:
        logger.debug("No DASHSCOPE_API_KEY set, using fallback embedding")
        return _fallback_embedding(text)
    try:
        import dashscope
        from dashscope import TextEmbedding
        resp = TextEmbedding.call(
            model="text-embedding-v3",
            api_key=DASHSCOPE_API_KEY,
            input=text,
        )
        if resp.status_code == 200 and resp.output:
            return resp.output.get("embeddings", [None])[0].get("embedding")
        logger.warning("Embedding API returned status=%s", resp.status_code)
        return _fallback_embedding(text)
    except ImportError:
        logger.debug("dashscope not installed, using fallback embedding")
        return _fallback_embedding(text)
    except Exception as e:
        logger.warning("Embedding call failed: %s", e)
        return _fallback_embedding(text)


def _fallback_embedding(text: str, dims: int = 1024) -> list[float]:
    """MD5 哈希伪向量 — 仅测试环境可用 (25号 §八.1 回退方案)."""
    import hashlib
    hash_bytes = hashlib.md5(text.encode("utf-8")).digest()
    vec = []
    for i in range(dims):
        b = hash_bytes[i % len(hash_bytes)]
        vec.append((b / 255.0) * 2 - 1)
    return vec


# ═══════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════

class VectorSearchService:
    """向量检索服务 — 两层搜索：关键词初筛 → 向量精筛."""

    @staticmethod
    async def search_similar(
        db: AsyncSession,
        knowledge_points: list[str],
        difficulty: str = "",
        limit: int = 5,
    ) -> list[HistoricalExam]:
        """搜索与给定知识点+难度最相似的真题。

        Args:
            db: 数据库会话
            knowledge_points: 目标知识点列表
            difficulty: 难度筛选 (可选)
            limit: 返回数量上限

        Returns:
            按相似度排序的 HistoricalExam 列表
        """
        # ── Layer 1: keyword match ──
        candidates = await _keyword_match(db, knowledge_points, difficulty)
        if not candidates:
            return []

        # ── Layer 2: vector search ──
        return await _vector_rerank(candidates, knowledge_points, limit)


async def _keyword_match(
    db: AsyncSession,
    knowledge_points: list[str],
    difficulty: str = "",
) -> list[HistoricalExam]:
    """Layer 1: 知识点重叠度 + 难度匹配排序 (25号 §八.3 第一层)."""
    query = select(HistoricalExam)
    if difficulty:
        query = query.where(HistoricalExam.difficulty == difficulty)
    query = query.order_by(HistoricalExam.year.desc()).limit(50)
    result = await db.execute(query)
    exams = result.scalars().all()

    if not exams or not knowledge_points:
        return list(exams)

    # Score by knowledge point overlap
    kp_set = set(knowledge_points)
    scored = []
    for exam in exams:
        exam_kps = set(exam.knowledge_point_tags or [])
        overlap = len(kp_set & exam_kps)
        exact_match = 2 if any(kp in exam_kps for kp in knowledge_points) else 0
        diff_match = 1 if difficulty and exam.difficulty == difficulty else 0
        score = overlap + exact_match + diff_match
        if score > 0:
            scored.append((score, exam))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for _, ex in scored[:20]]  # Top-20 candidates


async def _vector_rerank(
    candidates: list[HistoricalExam],
    knowledge_points: list[str],
    limit: int = 5,
) -> list[HistoricalExam]:
    """Layer 2: ChromaDB 向量检索精筛 (25号 §八.3 第二层).

    Falls back to keyword-only when ChromaDB is unavailable.
    """
    coll = _get_collection()
    if coll is None:
        # Fallback: keyword-only
        return candidates[:limit]

    try:
        # Get embeddings for candidates
        texts = [_build_embed_text(e) for e in candidates]
        embeddings = []
        for text in texts:
            emb = _get_embedding(text)
            if emb:
                embeddings.append(emb)
            else:
                embeddings.append(_fallback_embedding(text))

        # Query ChromaDB with first candidate's embedding as query
        query_text = f"考点: {'、'.join(knowledge_points)}。"
        query_emb = _get_embedding(query_text) or _fallback_embedding(query_text)

        results = coll.query(
            query_embeddings=[query_emb],
            n_results=min(limit * 2, len(embeddings)),
        )

        # Map results back to candidates
        if results and results.get("ids") and results["ids"][0]:
            result_ids = results["ids"][0]
            result_distances = results.get("distances", [[0]*len(result_ids)])[0]

            # Build exam_id → best distance map
            # Stored IDs: historical_{exam_id}::kp-{N} → extract exam_id
            dist_map = {}
            for rid, rd in zip(result_ids, result_distances):
                exam_id_str = rid.split("::")[0].replace("historical_", "")
                try:
                    eid = int(exam_id_str)
                    if eid not in dist_map or rd < dist_map[eid]:
                        dist_map[eid] = rd
                except ValueError:
                    continue

            # Re-rank candidates by vector similarity
            reranked = []
            for exam in candidates:
                distance = dist_map.get(exam.id, 1.0)
                similarity = 1.0 - distance
                reranked.append((similarity, exam))

            reranked.sort(key=lambda x: x[0], reverse=True)
            return [ex for _, ex in reranked[:limit]]

    except Exception as e:
        logger.warning("Vector rerank failed, falling back to keyword: %s", e)

    return candidates[:limit]


# ═══════════════════════════════════════════════
# Index build (startup check)
# ═══════════════════════════════════════════════

async def check_and_rebuild_index(db: AsyncSession) -> dict:
    """启动时检查索引状态，维度不匹配则清空重建。

    Returns:
        {"status": "ok"/"rebuilt", "count": N}
    """
    coll = _get_collection()
    if coll is None:
        return {"status": "unavailable", "count": 0}

    try:
        existing = coll.count()
        if existing == 0:
            return await build_index(db, coll, mode="replace")

        # Check one existing vector's dimension
        sample = coll.get(limit=1, include=["embeddings"])
        if sample and sample.get("embeddings") and sample["embeddings"]:
            existing_dim = len(sample["embeddings"][0])
            expected_dim = 1024
            if existing_dim != expected_dim:
                logger.warning(
                    "Vector dimension mismatch: existing=%d, expected=%d. Rebuilding.",
                    existing_dim, expected_dim,
                )
                return await build_index(db, coll, mode="replace")

        # Check count vs database
        result = await db.execute(select(HistoricalExam))
        total = len(result.scalars().all())
        expected = total * 3  # ~3 knowledge points per exam
        if existing < expected * 0.5:
            logger.info("Index count low (%d < %d), rebuilding.", existing, expected)
            return await build_index(db, coll, mode="replace")

        return {"status": "ok", "count": existing}
    except Exception as e:
        logger.warning("Index check failed: %s", e)
        return {"status": "check_failed", "count": 0}


async def build_index(
    db: AsyncSession,
    coll=None,
    mode: str = "append",
) -> dict:
    """构建/重建全量向量索引 (25号 §八.4)."""
    if coll is None:
        coll = _get_collection()
    if coll is None:
        return {"status": "unavailable", "count": 0}

    result = await db.execute(select(HistoricalExam))
    exams = result.scalars().all()

    if mode == "replace":
        try:
            coll.delete(where={})
        except Exception:
            pass

    ids, embeddings, metadatas = [], [], []
    for exam in exams:
        kps = exam.knowledge_point_tags or []
        for i, kp in enumerate(kps[:5]):  # Max 5 KPs per question
            chroma_id = f"historical_{exam.id}::kp-{i}"
            text = _build_embed_text(exam)
            emb = _get_embedding(text) or _fallback_embedding(text)
            ids.append(chroma_id)
            embeddings.append(emb)
            metadatas.append({
                "exam_id": exam.id,
                "knowledge_point": kp,
                "source": exam.source or "",
                "year": exam.year or 0,
            })

    if ids:
        try:
            coll.add(ids=ids, embeddings=embeddings, metadatas=metadatas)
        except Exception as e:
            logger.warning("Index write failed: %s", e)
            return {"status": "write_failed", "count": 0}

    logger.info("Vector index built: %d vectors for %d exams", len(ids), len(exams))
    return {"status": "ok", "count": len(ids)}
