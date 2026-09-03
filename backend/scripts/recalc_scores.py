"""全量重算历史评分 — v2 评分体系"权重改了历史分数跟着变"的执行入口

原理：每个候选人的维度分（skill/experience/stability）已经落在
resume.match_analysis.dimension_scores，总分只是维度分 × 权重的派生值。
改权重后跑本脚本，全量历史分数秒级对齐新口径，不调一次 LLM。

使用方法（项目根目录）:
    python backend/scripts/recalc_scores.py                # 预览：只显示会怎么变，不写库
    python backend/scripts/recalc_scores.py --apply        # 真正写库
    python backend/scripts/recalc_scores.py --category 销售 --apply
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.workflow.scoring import compute_overall, extract_dimension_scores, get_weights


async def recalc(apply: bool, category: str | None) -> None:
    weights = get_weights(category)
    print(f"使用权重: {weights}"
          f"（来源: {'类别 ' + category if category else '默认'}）")
    print(f"模式: {'写库' if apply else '预览（加 --apply 生效）'}")
    print("-" * 60)

    async with async_session_factory() as db:
        from app.models import Candidate, Resume
        result = await db.execute(select(Resume).order_by(Resume.candidate_id))
        resumes = result.scalars().all()

        changed, skipped_incomplete, skipped_missing = 0, 0, 0
        for resume in resumes:
            ma = resume.match_analysis or {}
            dims_raw = ma.get("dimension_scores")
            if not dims_raw:
                skipped_missing += 1
                continue

            # 恢复 None 语义（JSON 里可能存成 null）
            dimension_scores = {
                "skill": dims_raw.get("skill"),
                "experience": dims_raw.get("experience"),
                "stability": dims_raw.get("stability"),
            }
            scoring = compute_overall(dimension_scores, weights)

            if scoring["overall"] is None:
                skipped_incomplete += 1
                continue

            old = ma.get("overall_score")
            new = scoring["overall"]
            if old is not None and abs(float(old) - new) < 0.05:
                continue  # 分数没变

            candidate_id = resume.candidate_id
            print(f"  候选人 {candidate_id}: {old} → {new} "
                  f"(source={scoring['source']})")

            if apply:
                from datetime import datetime
                ma["overall_score"] = new
                ma["score_source"] = scoring["source"]
                ma["weights_used"] = scoring["weights_used"]
                ma["recalc_at"] = datetime.utcnow().isoformat()
                resume.match_analysis = ma
                # 同步候选人表的总分
                cand = await db.get(Candidate, candidate_id)
                if cand:
                    cand.match_score = new
                changed += 1

        if apply:
            await db.commit()

    print("-" * 60)
    print(f"完成: 更新 {changed} 条 | 维度分缺失跳过 {skipped_incomplete} 条 | "
          f"无维度分记录 {skipped_missing} 条")
    if not apply and changed:
        print("这是预览结果，加 --apply 真正写库")


def main():
    parser = argparse.ArgumentParser(description="全量重算历史评分")
    parser.add_argument("--apply", action="store_true", help="真正写库（缺省只预览）")
    parser.add_argument("--category", default=None, help="只重算指定岗位类别（用该类别权重）")
    args = parser.parse_args()
    asyncio.run(recalc(apply=args.apply, category=args.category))


if __name__ == "__main__":
    main()
