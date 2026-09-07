"""搜索引擎抓取 —— 无 API key 的网页搜索（供 JD 全网参考等场景）

设计原则：
- 只做"搜索"，不含 LLM；纯函数可独立单测（给 RSS/HTML 定串即可断言解析）。
- provider 按 settings.JD_REF_SEARCH_PROVIDERS（逗号分隔）顺序尝试，首个返回非空即停；
  全部失败返回 []（调用方降级，不抛异常）。
- 实测结论：Bing(Bing RSS/b_algo HTML)/百度/360 对无 cookie 无头客户端反爬
  （Bing 返回干扰百科、百度 wappass、360 qcaptcha）；搜狗普通 HTML 可正常抓。
  因此默认 provider 为 sogou，Bing RSS 作可选兜底。
"""
import html as _html
import ipaddress
import logging
import re
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class SearchResult:
    """一条搜索命中结果"""
    title: str
    url: str
    snippet: str = ""
    page_text: str = ""          # 仅当 JD_REF_FETCH_PAGE_BODY=True 抓取正文后填充
    provider: str = ""


def build_bing_url(base: str, query: str, limit: int, rss: bool) -> str:
    """构造 Bing 搜索结果 URL。

    rss=True 时带 format=rss（返回 XML，解析最稳）；否则返回普通 HTML 结果页。
    """
    params = {"q": query, "mkt": "zh-CN", "setlang": "zh-cn", "ensearch": "0"}
    if rss:
        params["format"] = "rss"
        params["count"] = str(max(1, min(limit, 20)))
    return f"{base}/search?{urlencode(params)}"


def build_sogou_url(query: str) -> str:
    """构造搜狗搜索结果 URL（普通 HTML 页）"""
    return f"https://www.sogou.com/web?{urlencode({'query': query})}"


def _clean(raw: str) -> str:
    """去掉 HTML 标签 → 反转义 → 压缩空白"""
    text = _TAG_RE.sub("", raw or "")
    return _WS_RE.sub(" ", _html.unescape(text)).strip()


def _parse_rss(xml_text: str) -> list[dict]:
    """解析 Bing RSS（兼容命名空间：按 tag 后缀匹配，不依赖前缀）"""
    items: list[dict] = []
    root = ET.fromstring(xml_text)
    for item in root.iter():
        if not item.tag.endswith("item"):
            continue
        title = link = desc = ""
        for child in item:
            tag = child.tag
            if tag.endswith("title"):
                title = _clean(child.text or "")
            elif tag.endswith("link"):
                link = (child.text or "").strip()
            elif tag.endswith("description"):
                desc = _clean(child.text or "")
        if title or link:
            items.append({"title": title, "url": link, "snippet": desc[:300]})
    return items


def _parse_b_algo_html(html_text: str) -> list[dict]:
    """解析 Bing 普通 HTML 的 <li class="b_algo"> 结果块（正则宽匹配，容错）"""
    items: list[dict] = []
    pattern = re.compile(
        r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>',
        re.S | re.I,
    )
    for m in pattern.finditer(html_text):
        block = m.group(1)
        link = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S | re.I)
        if not link:
            continue
        title = _clean(link.group(2))
        if not title:
            continue
        p = re.search(r"<p[^>]*>(.*?)</p>", block, re.S | re.I)
        snippet = _clean(p.group(1)) if p else ""
        items.append({"title": title, "url": link.group(1), "snippet": snippet[:300]})
    return items


def _parse_sogou_html(html_text: str) -> list[dict]:
    """解析搜狗普通 HTML 的 <div class="vrwrap"> 结果容器

    结构（实测）：h3.vr-title > a(相对 /link?url= 跳转) + 摘要 p 位于 text-layout 内。
    标题/摘要里的 <em><!--red_beg-->命中词高亮</em> 会被 _clean 一并清除。
    """
    items: list[dict] = []
    positions = [m.end() for m in re.finditer(r'<div class="vrwrap">', html_text, re.I)]
    for idx, start in enumerate(positions):
        end = positions[idx + 1] if idx + 1 < len(positions) else min(start + 6000, len(html_text))
        chunk = html_text[start:end]

        h3a = re.search(
            r'<h3[^>]*class="[^"]*vr-title[^"]*"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            chunk, re.S | re.I,
        )
        if not h3a:
            continue
        title = _clean(h3a.group(2))
        if not title:
            continue

        href = h3a.group(1).strip()
        if not href.startswith(("http://", "https://")):
            href = "https://www.sogou.com" + href if href.startswith("/") else href

        tl = re.search(r'<div class="text-layout[^"]*"[^>]*>(.*?)</div>', chunk, re.S | re.I)
        snippet = _clean(tl.group(1)) if tl else ""
        items.append({"title": title, "url": href, "snippet": snippet[:300]})
    return items


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    """按 url 去重、仅保留 http(s) 链接"""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        url = (r.url or "").strip()
        if not url or not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(r)
    return out


# ===== 相关性闸门 =====
# 实测 Bing 对无 cookie 无头客户端会"bot 降级"：返回查询首字的百科/知乎无关结果
# （如搜"电商运营经理…"返回"电（物理现象）"）。用"查询连续 2+ 汉字的二元组"做判据，
# 命中标题/摘要才保留 —— 无关百科不包含"电商/运营/招聘/职责"这类二元组，自然被滤掉。

_CJK_RUN_RE = re.compile(r"[一-鿿]{2,}")


def _query_grams(query: str) -> set[str]:
    """抽取查询里连续中文字段落的二元组集合"""
    grams: set[str] = set()
    for run in _CJK_RUN_RE.findall(query or ""):
        for i in range(len(run) - 1):
            grams.add(run[i : i + 2])
    return grams


def _filter_irrelevant(results: list[SearchResult], query: str) -> list[SearchResult]:
    """丢弃与查询无二元组重合的结果（反爬降级/跑题防护）；查询无语料时全量放行"""
    grams = _query_grams(query)
    if not grams:
        return results
    kept = [
        r
        for r in results
        if any(g in (r.title or "") + " " + (r.snippet or "") for g in grams)
    ]
    if kept and len(kept) < len(results):
        logger.debug("相关性过滤: %d → %d (query=%s)", len(results), len(kept), query)
    return kept


async def _fetch(url: str, client: httpx.AsyncClient) -> str:
    resp = await client.get(url, headers=_HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


async def search_web(
    query: str,
    limit: int = 8,
    providers: list[str] | None = None,
) -> list[SearchResult]:
    """按优先级依次尝试 provider；全部失败返回 []（不抛异常，调用方降级）"""
    limit = max(1, min(limit, 20))
    names = providers or [
        p.strip()
        for p in settings.JD_REF_SEARCH_PROVIDERS.split(",")
        if p.strip()
    ]
    for name in names:
        try:
            results = await _search_one(name, query, limit)
        except Exception as e:
            logger.warning("搜索 provider=%s 失败（尝试下一个）: %s", name, e)
            continue
        if results:
            return results
    logger.warning("全部搜索 provider 失败或结果为空: query=%s", query)
    return []


async def _search_one(name: str, query: str, limit: int) -> list[SearchResult]:
    """单 provider 抓取 + 重试 + 解析去重"""
    if name == "sogou":
        url = build_sogou_url(query)
    elif name in ("bing_cn", "bing_cn_html"):
        rss = name == "bing_cn"
        url = build_bing_url(settings.JD_REF_BING_BASE, query, limit, rss=rss)
    else:
        raise ValueError(f"未知搜索 provider: {name}")

    last_err: Exception | None = None
    for attempt in range(settings.JD_REF_SEARCH_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.JD_REF_SEARCH_TIMEOUT) as client:
                text = await _fetch(url, client)
            if name == "sogou":
                parsed = _parse_sogou_html(text)
            elif name == "bing_cn":
                parsed = _parse_rss(text)
            else:
                parsed = _parse_b_algo_html(text)
            results = [
                SearchResult(
                    title=i["title"],
                    url=i["url"],
                    snippet=i["snippet"],
                    provider=name,
                )
                for i in parsed
            ]
            # 相关性闸门：滤掉反爬降级/跑题结果；过滤后为空 → search_web 会继续尝试下一 provider
            return _dedupe(_filter_irrelevant(results, query))[:limit]
        except Exception as e:  # 网络错误 / 解析失败 / 非 200 —— 重试或抛给上层切 provider
            last_err = e
            if attempt < settings.JD_REF_SEARCH_RETRIES:
                continue
    raise last_err or RuntimeError(f"provider {name} 失败")


# ===== 可选：抓取结果页正文（实验性，默认关闭）=====

def _is_safe_target(url: str) -> bool:
    """SSRF 防护：仅允许公网 http(s) 目标（host 不解析到内网/保留段）"""
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        ip = socket.gethostbyname(host)          # 阻塞式 DNS；仅 JD_REF_FETCH_PAGE_BODY 开启时使用
        addr = ipaddress.ip_address(ip)
        return not (
            addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified
        )
    except Exception:
        return False


async def enrich_with_page_text(results: list[SearchResult], limit: int | None = None) -> None:
    """可选：抓取前 N 条结果的正文纯文本（去 script/style），填充到 page_text

    仅当 JD_REF_FETCH_PAGE_BODY=True 由编排层调用；任何单条失败只记 debug 并跳过。
    """
    count = 0
    async with httpx.AsyncClient(
        timeout=settings.JD_REF_FETCH_TIMEOUT,
        follow_redirects=True,
    ) as client:
        for r in results:
            if limit is not None and count >= limit:
                break
            if not _is_safe_target(r.url):
                continue
            try:
                resp = await client.get(r.url, headers=_HEADERS)
                resp.raise_for_status()
                body = re.sub(
                    r"<script.*?</script>|<style.*?</style>",
                    " ",
                    resp.text,
                    flags=re.S | re.I,
                )
                r.page_text = _clean(body)[:4000]
                count += 1
            except Exception as e:
                logger.debug("抓取正文失败 url=%s: %s", r.url, e)
