"""RAG 系统评测脚本（基于 RAGAS 框架）

评估维度：
  - faithfulness(忠实度): 答案是否基于检索到的上下文，无幻觉
  - answer_relevancy(答案相关度): 答案是否与问题相关
  - context_precision(上下文精确度): 检索结果是否精确命中问题所需信息
  - context_recall(上下文召回率): 检索结果是否覆盖回答问题所需的所有信息

使用方法：
  1. 准备评测数据: scripts/rag_evaluate_data.json
     [
       {"question": "年假几天？", "answer": "...", "contexts": ["..."], "ground_truth": "..."},
       ...
     ]
  2. 运行: python scripts/rag_eval.py
"""
import json
import os
import sys
import asyncio
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rag_eval")

# 加入项目根目录到 sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./recruit.db")


def load_test_data(data_path: str = None) -> list:
    """加载评测数据集

    Expected JSON format:
    [
        {
            "question": "年假有几天？",
            "ground_truth": "根据公司制度，正式员工每年享有5天年假。",
        }
    ]
    """
    if data_path is None:
        data_path = os.path.join(_current_dir, "rag_evaluate_data.json")

    if not os.path.exists(data_path):
        logger.warning(f"评测数据文件不存在: {data_path}")
        logger.info("生成示例评测数据...")
        sample_data = [
            {
                "question": "公司年假有几天？",
                "ground_truth": "根据公司制度，正式员工每年享有5天带薪年假，工龄每增加一年年假增加1天，上限15天。",
            },
            {
                "question": "请假流程是什么？",
                "ground_truth": "员工请假需提前在OA系统提交申请，1-3天由部门主管审批，3天以上需总监审批。",
            },
            {
                "question": "加班有加班费吗？",
                "ground_truth": "工作日加班按工资的150%支付，休息日加班按200%支付，法定节假日按300%支付。",
            },
            {
                "question": "报销流程怎么走？",
                "ground_truth": "报销需填写报销单并附发票，经部门负责人审批后提交财务部，一般在15个工作日内到账。",
            },
            {
                "question": "试用期多久？",
                "ground_truth": "劳动合同期限3个月以上不满1年的，试用期不超过1个月；1年以上不满3年的，试用期不超过2个月；3年以上固定期限和无固定期限的，试用期不超过6个月。",
            },
        ]
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=2)
        logger.info(f"已生成示例评测数据: {data_path}")
        return sample_data

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"加载评测数据: {len(data)} 条")
    return data


async def run_single_eval(question: str, ground_truth: str) -> dict:
    """对单条问题进行RAG检索 + LLM回答，返回结果

    结果格式（RAGAS 输入格式）：
        {"question", "answer", "contexts": [...], "ground_truth"}
    """
    from app.services.policy_rag import policy_rag_agent
    from app.agents.prompts import POLICY_AGENT_PROMPT, POLICY_AGENT_SYSTEM
    from app.agents.llm_client import llm_client
    from app.database import async_session_factory

    async with async_session_factory() as db:
        # 1) RAG 检索
        retrieved = await policy_rag_agent.query(question, db=db)
        contexts = [r["content"] for r in retrieved] if retrieved else []

        # 2) 构建 LLM 上下文
        if contexts:
            chunks_text = "\n\n---\n\n".join(
                f"[来源: {r['title']}]\n{r['content']}" for r in retrieved
            )
        else:
            chunks_text = "暂无相关文档。"

        # 3) 调用 LLM 生成回答
        prompt = POLICY_AGENT_PROMPT.format(
            retrieved_chunks=chunks_text,
            user_question=question,
        )
        answer = await llm_client.chat(
            system=POLICY_AGENT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )

    return {
        "question": question,
        "answer": answer,
        "contexts": contexts,
        "ground_truth": ground_truth,
    }


async def evaluate_all(data: list, output_path: str = None) -> dict:
    """批量评测

    Args:
        data: 评测数据集 [{"question": ..., "ground_truth": ...}, ...]
        output_path: 结果输出路径（可选）

    Returns:
        各维度的平均得分 {"faithfulness": float, ...}
    """
    logger.info(f"开始批量评测 {len(data)} 条数据...")

    # 1) 逐条执行 RAG 检索+生成
    eval_results = []
    for i, item in enumerate(data):
        logger.info(f"[{i + 1}/{len(data)}] 评测: {item['question'][:50]}...")
        result = await run_single_eval(item["question"], item.get("ground_truth", ""))
        eval_results.append(result)

    # 2) 检查是否有 contexts（如果 Milvus 为空则跳过 RAGAS）
    has_contexts = any(r["contexts"] for r in eval_results)
    if not has_contexts:
        logger.warning("所有评测数据的 contexts 均为空（Milvus 中可能无数据），跳过 RAGAS 评分")
        return {"faithfulness": 0, "answer_relevancy": 0, "context_precision": 0, "context_recall": 0}

    # 3) 使用 RAGAS 评估
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )

        eval_dataset = Dataset.from_dict({
            "question": [r["question"] for r in eval_results],
            "answer": [r["answer"] for r in eval_results],
            "contexts": [r["contexts"] for r in eval_results],
            "ground_truth": [r["ground_truth"] for r in eval_results],
        })

        result = evaluate(
            dataset=eval_dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
        )
        result_dict = {k: float(v) for k, v in result.items()}
    except ImportError as e:
        logger.error(f"RAGAS 或 datasets 未安装: {e}")
        logger.info("降级输出为 0 分，请安装: pip install ragas datasets")
        result_dict = {"faithfulness": 0.0, "answer_relevancy": 0.0,
                        "context_precision": 0.0, "context_recall": 0.0}
    except Exception as e:
        logger.error(f"RAGAS 评测执行失败: {e}")
        result_dict = {"faithfulness": 0.0, "answer_relevancy": 0.0,
                        "context_precision": 0.0, "context_recall": 0.0}

    # 4) 输出结果
    print("\n" + "=" * 60)
    print("RAGAS 评测结果")
    print("=" * 60)
    for metric, score in result_dict.items():
        stars = "⭐" * int(score * 5)
        print(f"  {metric:25s} {score:.4f}  {stars}")
    print("=" * 60)

    # 5) 保存结果
    if output_path:
        output = {
            "timestamp": datetime.now().isoformat(),
            "metrics": result_dict,
            "evaluated_count": len(eval_results),
            "details": eval_results,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info(f"评测结果已保存: {output_path}")

    return result_dict


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="RAG 系统评测工具")
    parser.add_argument("--data", type=str, default=None, help="评测数据 JSON 路径")
    parser.add_argument("--output", type=str, default=None, help="结果输出路径（默认打印到控制台）")
    args = parser.parse_args()

    # 加载评测数据
    data = load_test_data(args.data)
    if not data:
        logger.error("无评测数据")
        return

    # 执行评测
    result = asyncio.run(evaluate_all(data, output_path=args.output))


if __name__ == "__main__":
    main()
