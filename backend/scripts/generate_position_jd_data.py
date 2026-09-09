"""从「在招岗位说明书汇总.docx」生成 services/position_jd_data.py 的 SEED_JDS 常量

背景：简历分析要自动套用「对应岗位的岗位 JD」，这里的 11 条内置默认数据
一字不差取自 HR 维护的在招岗位说明书汇总文档，本脚本负责把 docx 拆成
「每岗位一份：岗位职责 + 任职要求」的可维护常量，commit 进仓库。

什么时候用：
  - 首次入库：生成 SEED_JDS 后提交；
  - 后续 HR 更新了汇总文档：重跑本脚本再 diff 提交（已在库中手工改过的
    岗位记录不会被覆盖，只有重新播种缺失的岗位才会用这里的内容）。

使用方法（项目根目录，用 boos_bot venv 的 python）:
    python backend/scripts/generate_position_jd_data.py
    python backend/scripts/generate_position_jd_data.py --docx "D:/xxx.docx"
    python backend/scripts/generate_position_jd_data.py --out D:/out.py   # 只生成不落库目录
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path

DOCX_DEFAULT = r"C:/Users/Lenovo/Desktop/文档/相关文档/在招岗位JD/在招岗位说明书/在招岗位说明书汇总.docx"

# docx 内岗位标题形如 "1. 采购主管"。注意区别于职责条目 "1、xxx" 与 "3.1 xxx"：
#   \d+\.\s+ 要求数字后是「点+空白」，职责条目是顿号「、」，3.1 后是数字 1 不是空白。
_HEADER_RE = re.compile(r"^(\d{1,2})\.\s+(.+)$")

# ── 每个岗位的「分类 + 匹配别名」。岗位名取自 docx（含括号备注），
#    别名用于兼容 HR/AI 识别时填写的各种写法（顿号分隔，匹配用最长命中）。
POSITION_META = {
    "采购主管": {
        "category": "采购供应链",
        "aliases": "采购经理，采购主管（坚果），坚果采购",
    },
    "城市经理（安徽）": {
        "category": "销售",
        "aliases": "城市经理，区域经理，安徽城市经理，区域销售经理",
    },
    "大宗贸易销售（坚果原料）": {
        "category": "销售",
        "aliases": "大宗贸易销售，大宗贸易，坚果原料销售，原料贸易销售",
    },
    "电商运营经理": {
        "category": "运营",
        "aliases": "电商经理，电商运营，坚果电商运营",
    },
    "俄语外贸业务员": {
        "category": "销售",
        "aliases": "外贸业务员，俄语业务员，俄语外贸，外贸销售，俄语外贸销售",
    },
    "食品研发工程师（烘焙）": {
        "category": "研发",
        "aliases": "食品研发工程师，食品研发，烘焙研发工程师，烘焙研发，坚果酱研发",
    },
    "市场主管": {
        "category": "市场",
        "aliases": "市场经理，市场营销主管，市场推广主管",
    },
    "视频号商务BD": {
        "category": "市场",
        "aliases": "视频号BD，视频号商务，商务BD，达人BD，直播BD",
    },
    "销售内勤": {
        "category": "职能",
        "aliases": "销售助理，销售支持，商务内勤，销售文员",
    },
    "英语翻译（总秘）": {
        "category": "职能",
        "aliases": "英语翻译，英文翻译，总经理秘书，总裁秘书，总秘",
    },
    "资深电商运营专员": {
        "category": "运营",
        "aliases": "电商运营专员，资深电商运营，京东运营",
    },
}


def _clean(text: str) -> str:
    return text.strip()


def _split_roles(doc):
    """按 "N. 岗位名" 标题切出每个岗位的原始段落（不含该岗位后续标题）。"""
    paras = [(p.text.strip(), (p.style.name if p.style else "")) for p in doc.paragraphs]
    roles = []          # [{num, position, paras:[(text,style)]}]
    current = None
    for text, _style in paras:
        if not text:
            continue
        m = _HEADER_RE.match(text)
        if m:
            if current is not None:
                roles.append(current)
            current = {
                "num": int(m.group(1)),
                "position": _clean(m.group(2)),
                "paras": [],
            }
            continue
        if current is not None:
            current["paras"].append(text)
    if current is not None:
        roles.append(current)
    roles.sort(key=lambda r: r["num"])
    return roles


def _collect_salary(doc) -> dict:
    """读 docx 末尾 11 张「岗位名称 | 薪资」表，得到 {岗位名: 薪资}。"""
    out = {}
    for tb in doc.tables:
        for row in tb.rows:
            cells = [c.text.strip() for c in row.cells]
            if not cells or cells[0] in ("", "岗位名称"):
                continue
            name = cells[0]
            sal = cells[1] if len(cells) > 1 else "面议"
            if name:
                out[name] = sal or "面议"
    return out


def _section_text(role) -> dict:
    """把岗位段落切到 岗位职责 / 任职要求 两节，返回 {responsibilities, requirements}。"""
    resp, req = [], []
    mode = None
    for text in role["paras"]:
        if text == "岗位职责":
            mode = "resp"
            continue
        if text == "任职要求":
            mode = "req"
            continue
        if mode == "resp":
            resp.append(text)
        elif mode == "req":
            req.append(text)
    return {
        "responsibilities": "\n".join(resp).strip(),
        "requirements": "\n".join(req).strip(),
    }


def parse_docx(docx_path: str) -> list:
    from docx import Document

    doc = Document(docx_path)
    roles = _split_roles(doc)
    salary_by_name = _collect_salary(doc)

    items = []
    for role in roles:
        body = _section_text(role)
        meta = POSITION_META.get(role["position"], {"category": "other", "aliases": ""})
        items.append({
            "position": role["position"],
            "aliases": meta.get("aliases", ""),
            "category": meta.get("category", "other"),
            "responsibilities": body["responsibilities"],
            "requirements": body["requirements"],
            "salary": salary_by_name.get(role["position"], "面议"),
        })
    return items


def render(items: list) -> str:
    """渲染成 position_jd_data.py 的源码文本。"""
    header = (
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════════════\n"
        "# 【小白导读】内置岗位 JD 默认数据（唯一事实来源）——由\n"
        "#   scripts/generate_position_jd_data.py 从《在招岗位说明书汇总.docx》\n"
        "#   生成，共 %d 个在招岗位。岗位职责/任职要求一字不差取自文档，\n"
        "#   页面上的改动存在 position_jds 表（本文件只在新库播种缺失时使用）。\n"
        "#   以后 HR 更新汇总文档后重跑生成脚本再提交即可。\n"
        "# ═══════════════════════════════════════════════════════════════\n"
        "SEED_JDS = "
    ) % len(items)
    body = json.dumps(items, ensure_ascii=False, indent=2)
    return header + body + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", default=DOCX_DEFAULT, help="汇总 docx 路径")
    ap.add_argument("--out", default="", help="输出文件；缺省写到 src/app/services/position_jd_data.py")
    ap.add_argument("--stdout", action="store_true", help="只打印到标准输出（调试用）")
    args = ap.parse_args()

    src_path = Path(args.docx)
    if not src_path.exists():
        sys.exit(f"找不到 docx: {src_path}")

    items = parse_docx(str(src_path))
    text = render(items)

    if args.stdout:
        sys.stdout.buffer.write(text.encode("utf-8"))
        return

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "src" / "app" / "services" / "position_jd_data.py"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(out_path), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"OK 岗位数={len(items)} 已写入 {out_path}")


if __name__ == "__main__":
    main()
