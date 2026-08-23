#!/usr/bin/env python3
"""每日 AI 简报数据更新脚本。

使用 Python 标准库抓取中文 RSS，并通过 yfinance（不可用时自动降级）更新股票行情。
当外部数据源不可用时保留上一次有效数据，避免线上页面被空数据覆盖。
"""

from __future__ import annotations

import html
import json
import os
import re
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "data.json"
USER_AGENT = "Mozilla/5.0 (compatible; DailyBrief/2.0; +https://github.com/lkk-A/daily-brief)"

AI_IMAGES = [
    "assets/images/ai-news-1.svg",
    "assets/images/ai-news-2.svg",
    "assets/images/ai-news-3.svg",
]
ECONOMY_IMAGES = [
    "assets/images/economy-1.svg",
    "assets/images/economy-2.svg",
]


def fetch_url(url: str, timeout: int = 15) -> str:
    """下载 UTF-8 文本，失败时返回空字符串。"""
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # 网络源偶发失败不应中断整次更新
        print(f"获取失败：{url}（{exc}）")
        return ""


def clean_text(value: str | None, limit: int = 6000) -> str:
    """去除 RSS 中的 HTML，并把实体编码还原成可读文字。"""
    text = html.unescape(value or "")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


class ParagraphParser(HTMLParser):
    """在正文提取库失败时，从 HTML 中收集可读段落。"""

    def __init__(self) -> None:
        super().__init__()
        self.in_paragraph = False
        self.current: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "p":
            self.in_paragraph = True
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.in_paragraph:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "p" and self.in_paragraph:
            paragraph = clean_text("".join(self.current), 500)
            if len(paragraph) >= 25:
                self.paragraphs.append(paragraph)
            self.in_paragraph = False
            self.current = []


def contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))


def child_text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    """读取 RSS/Atom 子节点，不依赖命名空间前缀。"""
    for child in node.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names and child.text:
            return child.text.strip()
    return ""


def get_source(node: ElementTree.Element) -> tuple[str, str]:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].lower() == "source":
            return clean_text(child.text, 40) or "综合资讯", (child.attrib.get("url") or "").strip()
    return "综合资讯", ""


def parse_rss(xml_text: str, max_items: int = 10) -> list[dict]:
    """按 item/entry 解析 RSS，跳过频道标题与非中文条目。"""
    if not xml_text:
        return []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        print(f"RSS 解析失败：{exc}")
        return []

    nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    items: list[dict] = []
    for node in nodes:
        title = clean_text(child_text(node, ("title",)), 120)
        if not title or not contains_chinese(title):
            continue

        description = clean_text(child_text(node, ("description", "summary", "content")), 600)
        if not contains_chinese(description):
            description = "点击查看这条资讯的中文详情与原始报道。"

        link = child_text(node, ("link",))
        if not link:
            for child in node.iter():
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break

        source, source_url = get_source(node)
        suffix = f" - {source}"
        if title.endswith(suffix):
            title = title[:-len(suffix)].strip()
        published = child_text(node, ("pubdate", "published", "updated"))
        time_label = "今日"
        if published:
            try:
                published_at = parsedate_to_datetime(published).astimezone(CST)
                time_label = published_at.strftime("%m月%d日")
            except (TypeError, ValueError, OverflowError):
                pass

        items.append(
            {
                "title": title,
                "summary": description,
                "content": description,
                "source": source,
                "time": time_label,
                "link": link.strip(),
                "source_url": source_url,
                "impact": "",
            }
        )
        if len(items) >= max_items:
            break
    return items


def is_direct_article_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return hostname not in {"news.google.com", "google.com", "www.google.com"}


def resolve_original_url(item: dict) -> str:
    """把 Google News 聚合链接还原成媒体文章链接。"""
    link = item.get("link", "")
    if is_direct_article_url(link):
        return link
    if "news.google.com" in link:
        try:
            from googlenewsdecoder import gnewsdecoder

            result = gnewsdecoder(link)
            decoded = result.get("decoded_url", "") if result.get("status") else ""
            if is_direct_article_url(decoded):
                return decoded
            print(f"原文链接解析失败：{item.get('title', '')}（{result.get('message', '未知原因')}）")
        except Exception as exc:
            print(f"原文链接解析异常：{item.get('title', '')}（{exc}）")
    return ""


def extract_article_text(url: str) -> str:
    """优先提取文章正文；失败时从 meta 与段落标签中降级提取。"""
    if not is_direct_article_url(url):
        return ""
    raw_html = ""
    try:
        import trafilatura

        raw_html = trafilatura.fetch_url(url) or ""
        if raw_html:
            extracted = trafilatura.extract(
                raw_html,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
                deduplicate=True,
            )
            text = clean_text(extracted, 6000)
            if len(text) >= 120:
                return text
    except Exception as exc:
        print(f"正文提取库处理失败：{url}（{exc}）")

    raw_html = raw_html or fetch_url(url, timeout=20)
    if not raw_html:
        return ""

    descriptions = re.findall(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)',
        raw_html,
        flags=re.I,
    )
    parser = ParagraphParser()
    try:
        parser.feed(raw_html)
    except Exception:
        pass
    parts = [clean_text(value, 500) for value in descriptions] + parser.paragraphs
    return clean_text("。".join(part for part in parts if contains_chinese(part)), 6000)


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    cleaned: list[str] = []
    seen: set[str] = set()
    noise = ("责任编辑", "版权所有", "打开微信", "扫码", "登录", "免责声明", "相关阅读")
    for sentence in sentences:
        sentence = clean_text(sentence, 260).strip(" -—|·")
        normalized = re.sub(r"\W+", "", sentence)
        if len(sentence) < 25 or len(sentence) > 250 or any(word in sentence for word in noise):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(sentence)
    return cleaned


def build_detailed_digest(item: dict, article_text: str) -> tuple[str, str]:
    """生成可读的详细要点，不整篇转载受版权保护的报道。"""
    feed_description = item.get("summary", "")
    candidates = split_sentences(article_text)
    if feed_description and feed_description != item.get("title"):
        candidates = split_sentences(feed_description) + candidates

    selected: list[str] = []
    for sentence in candidates:
        if item.get("title", "") in sentence and len(sentence) <= len(item.get("title", "")) + 20:
            continue
        if any(sentence[:24] in existing or existing[:24] in sentence for existing in selected):
            continue
        selected.append(sentence)
        if len("".join(selected)) >= 650 or len(selected) >= 7:
            break

    if not selected:
        summary = f"{item.get('source', '媒体')}发布了这则报道，主题为“{item.get('title', '')}”。当前页面正文未能自动提取，建议进入发布方文章页核对完整信息。"
        content = (
            f"报道主题：{item.get('title', '')}\n\n"
            f"发布来源：{item.get('source', '媒体')}\n\n"
            "当前媒体页面未能自动提取出足够正文，因此这里不根据标题臆测事实、数据或结论。"
            "请通过下方发布方链接阅读完整报道，重点核对事件背景、时间、相关主体、原始数据、引用来源、论证过程与上下文。"
        )
        return summary, content

    summary_parts: list[str] = []
    for sentence in selected:
        summary_parts.append(sentence)
        if len("".join(summary_parts)) >= 120 or len(summary_parts) >= 2:
            break
    summary = clean_text("".join(summary_parts), 220)
    bullets = "\n\n".join(f"• {sentence}" for sentence in selected)
    content = (
        f"核心要点\n\n{bullets}\n\n"
        "说明：以上内容由系统从发布方页面自动整理，仅概括报道要点；完整论证、数据和上下文请查看原文。"
    )
    return summary, content


def enrich_news(items: list[dict], limit: int) -> list[dict]:
    print(f"解析 {len(items)} 条新闻的发布方链接与正文……")
    enriched: list[dict] = []
    for item in items:
        direct_url = resolve_original_url(item)
        if not is_direct_article_url(direct_url):
            print(f"跳过未取得发布方直链的新闻：{item.get('title', '')}")
            continue
        item["link"] = direct_url
        article_text = extract_article_text(direct_url)
        item["summary"], item["content"] = build_detailed_digest(item, article_text)
        item.pop("source_url", None)
        enriched.append(item)
        if len(enriched) >= limit:
            break
    return enriched


def google_news_feed(query: str) -> str:
    encoded = quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def unique_by_title(items: list[dict], limit: int) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        normalized = re.sub(r"\s+", "", item["title"]).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def get_ai_news() -> list[dict]:
    print("获取中文 AI 新闻……")
    queries = ["人工智能 大模型 科技", "AI 应用 机器人 芯片"]
    news: list[dict] = []
    for query in queries:
        news.extend(parse_rss(fetch_url(google_news_feed(query)), 10))
    news = enrich_news(unique_by_title(news, 16), 8)
    for index, item in enumerate(news):
        item["image"] = AI_IMAGES[index % len(AI_IMAGES)]
    return news


def get_economy_news() -> list[dict]:
    print("获取中文经济新闻……")
    queries = ["全球经济 财经 市场", "中国经济 外贸 市场"]
    news: list[dict] = []
    for query in queries:
        news.extend(parse_rss(fetch_url(google_news_feed(query)), 8))
    news = enrich_news(unique_by_title(news, 12), 6)
    for index, item in enumerate(news):
        item["image"] = ECONOMY_IMAGES[index % len(ECONOMY_IMAGES)]
    return news


def default_ai_news() -> list[dict]:
    """首次部署且新闻源不可用时使用的中文状态内容。"""
    return [
        {"title": "中文 AI 新闻源正在等待下一次自动更新", "summary": "本次抓取未获得足够的中文资讯，系统会在下一次定时任务中自动重试。", "content": "为了避免把英文标题或损坏的 RSS 内容发布到页面，本次更新使用中文兜底内容。", "source": "系统状态", "time": "今日", "link": "", "impact": ""},
        {"title": "每日简报已启用中文内容校验", "summary": "只有包含中文标题且格式完整的新闻条目才会进入线上数据。", "content": "数据更新完成后会自动验证中文标题、新闻数量和图片字段，验证失败时不会提交损坏数据。", "source": "系统状态", "time": "今日", "link": "", "impact": ""},
        {"title": "AI 新闻卡片现已支持本地图片", "summary": "新闻插图存放在仓库中，外部图片不可用时也能正常显示。", "content": "页面为每条 AI 新闻分配本地插图，并为所有外部图片提供统一的加载失败占位图。", "source": "系统状态", "time": "今日", "link": "", "impact": ""},
    ]


def default_economy_news() -> list[dict]:
    return [
        {"title": "中文经济新闻源正在等待下一次自动更新", "summary": "外部资讯源暂时不可用，系统会在下一次定时任务中自动重试。", "content": "为保证页面保持中文，本次没有发布来源异常的英文内容。", "source": "系统状态", "time": "今日", "link": "", "impact": ""},
        {"title": "全球经济栏目已启用内容格式校验", "summary": "异常标题、频道名称和 HTML 残片会在发布前被过滤。", "content": "更新脚本现在按 RSS 新闻条目解析内容，不再把频道标题误识别为新闻。", "source": "系统状态", "time": "今日", "link": "", "impact": ""},
        {"title": "线上数据更新保留最近一次有效中文内容", "summary": "短暂的网络故障不会再清空栏目或覆盖成英文。", "content": "当抓取失败时，系统优先保留最近一次通过中文校验的数据。", "source": "系统状态", "time": "今日", "link": "", "impact": ""},
    ]


def choose_chinese_news(fetched: list[dict], previous: list[dict], fallback: list[dict], images: list[str]) -> list[dict]:
    """依次选择新数据、有效历史数据和中文兜底内容。"""
    def valid(items: list[dict]) -> list[dict]:
        return [
            item for item in items
            if contains_chinese(item.get("title", ""))
            and (
                item.get("source") == "系统状态"
                or (
                    len(item.get("summary", "")) >= 40
                    and len(item.get("content", "")) >= 100
                    and is_direct_article_url(item.get("link", ""))
                )
            )
        ]

    selected = valid(fetched)
    if len(selected) < 3:
        selected = valid(previous)
    if len(selected) < 3:
        selected = fallback
    for index, item in enumerate(selected):
        item["image"] = item.get("image") or images[index % len(images)]
        if not contains_chinese(item.get("summary", "")):
            item["summary"] = "点击查看这条资讯的中文详情与原始报道。"
        if not contains_chinese(item.get("content", "")):
            item["content"] = item["summary"]
    return selected


def get_quote(code: str) -> tuple[float, float] | None:
    """通过 Yahoo Finance 图表接口读取最近两个交易日收盘价。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(code)}?range=5d&interval=1d"
    raw = fetch_url(url)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        closes = payload["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        valid = [float(value) for value in closes if value is not None]
        if len(valid) < 2:
            return None
        previous, current = valid[-2], valid[-1]
        return round(current, 2), round((current - previous) / previous * 100, 2)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def get_stocks(previous: list[dict]) -> list[dict]:
    print("获取股票行情……")
    companies = [
        ("英伟达", "NVDA"),
        ("微软", "MSFT"),
        ("谷歌", "GOOGL"),
        ("AMD", "AMD"),
        ("百度", "BIDU"),
        ("特斯拉", "TSLA"),
    ]
    old_by_code = {item.get("code"): item for item in previous}
    stocks = []
    yfinance_module = None
    try:
        import yfinance as yfinance_module
    except ImportError:
        pass
    for name, code in companies:
        quote_data = None
        if yfinance_module:
            try:
                history = yfinance_module.Ticker(code).history(period="5d")
                if len(history) >= 2:
                    previous_close = float(history["Close"].iloc[-2])
                    current_close = float(history["Close"].iloc[-1])
                    quote_data = round(current_close, 2), round((current_close - previous_close) / previous_close * 100, 2)
            except Exception as exc:
                print(f"yfinance 获取 {code} 失败：{exc}")
        if not quote_data:
            quote_data = get_quote(code)
        if quote_data:
            price, change = quote_data
        else:
            old = old_by_code.get(code, {})
            price = old.get("price", 0)
            change = old.get("change", 0)
        stocks.append({"name": name, "code": code, "price": price, "change": change, "analysis": ""})
    stocks.sort(key=lambda item: item["change"], reverse=True)
    return stocks


def get_trade_products() -> list[dict]:
    return [
        {"name": "便携式榨汁杯", "desc": "USB 充电便携式榨汁杯，小巧轻便，适合办公室和旅行。", "heat": "98", "price": "15.99", "image": "https://images.unsplash.com/photo-1622597467836-f3285f2131b8?w=800&auto=format&fit=crop&q=80", "why": "健康生活趋势与便携需求叠加，欧美市场持续热销。"},
        {"name": "可折叠硅胶饭盒", "desc": "食品级硅胶可折叠饭盒，可用于微波炉并能节省收纳空间。", "heat": "92", "price": "12.50", "image": "https://images.unsplash.com/photo-1584568694244-14fbdf83bd30?w=800&auto=format&fit=crop&q=80", "why": "环保理念和通勤带饭需求增长，轻量化设计更容易传播。"},
        {"name": "LED 智能化妆镜", "desc": "三档调光、USB 充电的桌面化妆镜，适合居家与旅行。", "heat": "95", "price": "22.00", "image": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=800&auto=format&fit=crop&q=80", "why": "美妆内容持续热门，产品展示直观，适合短视频种草。"},
        {"name": "多功能电动切菜器", "desc": "切丝、切片和切丁一机完成，适合快节奏家庭厨房。", "heat": "89", "price": "28.80", "image": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=800&auto=format&fit=crop&q=80", "why": "厨房自动化需求增长，功能演示具有较强的视觉传播效果。"},
        {"name": "迷你空气净化器", "desc": "采用 HEPA 滤网并支持 USB 供电，适合办公桌和卧室。", "heat": "87", "price": "19.99", "image": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=800&auto=format&fit=crop&q=80", "why": "消费者更关注小空间空气质量，桌面产品容易形成刚需。"},
    ]


def get_ai_videos() -> list[dict]:
    return [
        {"title": "AI 数字人 24 小时无人直播带货全流程", "author": "电商案例", "views": "热门", "platform": "全网", "image": "https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=800&auto=format&fit=crop&q=80", "reason": "完整展示数字人直播的搭建方式、运营流程和成本结构。", "monetize": "数字人工具、培训服务、直播佣金与企业代运营。", "link": "https://www.toutiao.com/article/7676662935858528777/"},
        {"title": "AI 绘画接单：从作品集到客户交付", "author": "设计案例", "views": "热门", "platform": "B站", "image": "assets/images/video-creator.svg", "reason": "把接单、报价、沟通和交付拆成了适合新手执行的步骤。", "monetize": "商单服务、课程、素材包与平台创作激励。", "link": "https://www.bilibili.com/opus/1163107582200512513"},
        {"title": "用 AI 写小红书内容的 30 天运营方法", "author": "运营案例", "views": "热门", "platform": "小红书", "image": "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=800&auto=format&fit=crop&q=80", "reason": "从选题、文案到复盘形成可重复执行的内容工作流。", "monetize": "广告合作、知识付费、社群和工具推广。", "link": "https://www.woshipm.com/ai/6304504.html"},
        {"title": "一个人管理多个 AI 直播账号的矩阵方法", "author": "直播案例", "views": "热门", "platform": "全网", "image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&auto=format&fit=crop&q=80", "reason": "重点介绍多账号排期、内容复用和数据复盘的规模化方法。", "monetize": "直播系统、代运营、培训课程与流量服务。", "link": "https://suanlibox.com/articles/24-hour-digital-human-livestream-cost.html"},
    ]


def load_previous_data() -> dict:
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    started_at = datetime.now(CST)
    print(f"=== 开始更新 {started_at:%Y-%m-%d %H:%M:%S} ===")
    previous = load_previous_data()

    ai_news = choose_chinese_news(get_ai_news(), previous.get("ai_news", []), default_ai_news(), AI_IMAGES)
    economy = choose_chinese_news(get_economy_news(), previous.get("economy", []), default_economy_news(), ECONOMY_IMAGES)

    data = {
        "last_updated": started_at.isoformat(timespec="seconds"),
        "ai_news": ai_news,
        "stocks": get_stocks(previous.get("stocks", [])),
        "stock_analysis": "AI 板块波动较大，页面行情仅供信息参考，不构成投资建议。建议同时关注算力基础设施、模型能力和实际应用落地。",
        "economy": economy,
        "trade": get_trade_products(),
        "videos": get_ai_videos(),
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = DATA_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, DATA_PATH)

    print(f"数据已保存：{DATA_PATH}")
    print(f"AI 新闻 {len(ai_news)} 条，经济新闻 {len(economy)} 条，股票 {len(data['stocks'])} 只")
    print("=== 更新完成 ===")


if __name__ == "__main__":
    main()
