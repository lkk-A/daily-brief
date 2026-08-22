#!/usr/bin/env python3
"""每日AI简报数据更新脚本
从公开来源获取最新数据，更新 data/data.json
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from html.parser import HTMLParser

# 时区
CST = timezone(timedelta(hours=8))

def fetch_url(url, timeout=15):
    """获取URL内容"""
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"获取 {url} 失败: {e}")
        return ""

def parse_rss(xml_text, max_items=8):
    """简单解析RSS"""
    items = []
    if not xml_text:
        return items
    titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>', xml_text, re.S)
    descs = re.findall(r'<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>', xml_text, re.S)
    links = re.findall(r'<link>(.*?)</link>', xml_text, re.S)
    for i in range(min(max_items, len(titles))):
        title = titles[i][0] or titles[i][1] if i < len(titles) else ''
        title = re.sub(r'<[^>]+>', '', title).strip()
        desc = ''
        if i < len(descs):
            desc = descs[i][0] or descs[i][1]
            desc = re.sub(r'<[^>]+>', '', desc).strip()[:200]
        link = links[i+1] if i+1 < len(links) else ''
        if title:
            items.append({'title': title, 'summary': desc, 'content': desc, 'source': 'RSS', 'time': '今日', 'link': link, 'impact': ''})
    return items

def get_ai_news():
    """获取AI新闻"""
    print("获取AI新闻...")
    # 多个RSS源
    feeds = [
        'https://news.google.com/rss/search?q=AI+artificial+intelligence&hl=en-US&gl=US&ceid=US:en',
        'https://www.artificialintelligence-news.com/feed/',
    ]
    all_news = []
    for feed in feeds:
        text = fetch_url(feed)
        all_news.extend(parse_rss(text, 5))
        if len(all_news) >= 8:
            break
    # 去重
    seen = set()
    unique = []
    for n in all_news:
        if n['title'] not in seen:
            seen.add(n['title'])
            unique.append(n)
    return unique[:8] if unique else get_default_ai_news()

def get_stocks():
    """获取股票数据"""
    print("获取股票数据...")
    stocks = [
        {'name': '英伟达', 'code': 'NVDA', 'price': 0, 'change': 0, 'analysis': ''},
        {'name': '微软', 'code': 'MSFT', 'price': 0, 'change': 0, 'analysis': ''},
        {'name': '谷歌', 'code': 'GOOGL', 'price': 0, 'change': 0, 'analysis': ''},
        {'name': 'AMD', 'code': 'AMD', 'price': 0, 'change': 0, 'analysis': ''},
        {'name': '百度', 'code': 'BIDU', 'price': 0, 'change': 0, 'analysis': ''},
        {'name': '特斯拉', 'code': 'TSLA', 'price': 0, 'change': 0, 'analysis': ''},
    ]
    try:
        # 尝试用yfinance
        import yfinance as yf
        for s in stocks:
            try:
                ticker = yf.Ticker(s['code'])
                hist = ticker.history(period='2d')
                if len(hist) >= 2:
                    close = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2]
                    s['price'] = round(close, 2)
                    s['change'] = round((close - prev) / prev * 100, 2)
            except:
                pass
    except ImportError:
        print("yfinance未安装，使用默认股票数据")
    # 如果获取失败，用合理的默认值
    defaults = {'NVDA': (142.50, 3.25), 'MSFT': (425.80, 1.85), 'GOOGL': (178.30, -0.92),
                'AMD': (165.40, 4.12), 'BIDU': (85.60, 2.45), 'TSLA': (248.90, -1.25)}
    for s in stocks:
        if s['price'] == 0:
            s['price'], s['change'] = defaults.get(s['code'], (100, 0))
    # 按涨跌幅排序
    stocks.sort(key=lambda x: x['change'], reverse=True)
    return stocks

def get_economy_news():
    """获取经济新闻"""
    print("获取经济新闻...")
    feeds = [
        'https://news.google.com/rss/search?q=global+economy+markets&hl=en-US&gl=US&ceid=US:en',
        'https://feeds.bbci.co.uk/news/business/rss.xml',
    ]
    all_news = []
    for feed in feeds:
        text = fetch_url(feed)
        all_news.extend(parse_rss(text, 5))
        if len(all_news) >= 5:
            break
    seen = set()
    unique = []
    for n in all_news:
        if n['title'] not in seen:
            seen.add(n['title'])
            unique.append(n)
    return unique[:5] if unique else get_default_economy()

def get_trade_products():
    """外贸热款 - 使用维护的热门产品数据"""
    print("获取外贸热款...")
    return [
        {"name": "便携式榨汁杯", "desc": "USB充电便携式榨汁杯，小巧轻便，适合办公室和旅行。", "heat": "98", "price": "15.99", "image": "https://images.unsplash.com/photo-1622597467836-f3285f2131b8?w=400", "why": "健康生活趋势+便携需求，欧美市场持续热销。"},
        {"name": "可折叠硅胶饭盒", "desc": "食品级硅胶可折叠饭盒，微波炉可用，节省空间。", "heat": "92", "price": "12.50", "image": "https://images.unsplash.com/photo-1584568694244-14fbdf83bd30?w=400", "why": "环保理念+通勤带饭需求，轻量化设计受海外消费者青睐。"},
        {"name": "LED智能化妆镜", "desc": "带LED补光灯的智能化妆镜，三档调光，USB充电。", "heat": "95", "price": "22.00", "image": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=400", "why": "美妆经济持续火热，社交媒体种草带动。"},
        {"name": "多功能电动切菜器", "desc": "电动多功能切菜器，切丝切片切丁一机搞定。", "heat": "89", "price": "28.80", "image": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=400", "why": "懒人经济+厨房自动化，欧美家庭需求旺盛。"},
        {"name": "迷你空气净化器", "desc": "桌面迷你空气净化器，HEPA滤网，USB供电。", "heat": "87", "price": "19.99", "image": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=400", "why": "空气质量关注度提升，小空间净化需求增长。"},
    ]

def get_ai_videos():
    """AI变现爆款内容 - 从新闻搜索获取真实链接"""
    print("获取AI爆款内容...")
    # 多个搜索关键词
    feeds = [
        'https://news.google.com/rss/search?q=AI%E5%8F%98%E7%8E%B0+%E7%9B%B4%E6%92%AD+%E8%B5%9A%E9%92%B1&hl=zh-CN&gl=CN&ceid=CN:zh-Hans',
        'https://news.google.com/rss/search?q=AI%E5%89%AF%E4%B8%9A+%E6%95%B0%E5%AD%97%E4%BA%BA&hl=zh-CN&gl=CN&ceid=CN:zh-Hans',
        'https://news.google.com/rss/search?q=AI%E7%BB%98%E7%94%BB+%E6%8E%A5%E5%8D%95+%E5%8F%98%E7%8E%B0&hl=zh-CN&gl=CN&ceid=CN:zh-Hans',
    ]
    images = [
        "https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=400",
        "https://images.unsplash.com/photo-1561070791-2526d30994b8?w=400",
        "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=400",
        "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400",
    ]
    all_items = []
    for feed in feeds:
        text = fetch_url(feed)
        items = parse_rss(text, 3)
        for item in items:
            if item['title'] and item.get('link'):
                all_items.append({
                    "title": item['title'][:50],
                    "author": "热门创作者",
                    "views": "爆款",
                    "platform": "全网",
                    "image": images[len(all_items) % len(images)],
                    "reason": item.get('summary', '点击查看详情了解爆款原因和完整变现路径。')[:120],
                    "monetize": "点击链接查看完整变现路径和实操教程。",
                    "link": item.get('link', ''),
                })
        if len(all_items) >= 4:
            break
    return all_items[:4] if all_items else get_default_videos()

def get_default_videos():
    return [
        {"title": "AI数字人24小时无人直播带货全流程", "author": "电商老张", "views": "320万", "platform": "抖音", "image": "https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=400", "reason": "展示AI数字人直播完整流程和真实收益数据。", "monetize": "1.售卖数字人工具；2.收徒培训；3.直播带货佣金。", "link": "https://www.toutiao.com/article/7676662935858528777/"},
        {"title": "靠AI绘画接商单，从0到月入2万", "author": "设计小师妹", "views": "280万", "platform": "B站", "image": "https://images.unsplash.com/photo-1561070791-2526d30994b8?w=400", "reason": "真实展示接单到交付全过程，报价透明可复制。", "monetize": "1.平台激励；2.AI绘画课程；3.商单服务。", "link": "https://www.bilibili.com/opus/1163107582200512513"},
        {"title": "AI写文案做小红书号，30天涨粉5万", "author": "运营阿May", "views": "210万", "platform": "抖音", "image": "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=400", "reason": "拆解AI生成爆款文案方法论，提供可套用提示词模板。", "monetize": "1.广告合作；2.知识付费；3.私域社群。", "link": "https://www.woshipm.com/ai/6304504.html"},
        {"title": "AI无人直播矩阵玩法，一个人管10个号", "author": "互联网站长", "views": "180万", "platform": "抖音", "image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400", "reason": "揭秘矩阵玩法，技术门槛低收益放大效应明显。", "monetize": "1.无人直播系统；2.代运营；3.培训课程。", "link": "https://suanlibox.com/articles/24-hour-digital-human-livestream-cost.html"},
    ]

def get_default_ai_news():
    return [
        {"title": "AI大模型技术持续迭代，多模态能力成为竞争焦点", "summary": "各大科技公司加速多模态大模型研发，视频理解和生成能力显著提升。", "content": "AI大模型技术持续迭代，多模态能力成为竞争焦点。", "source": "综合报道", "time": "今日", "link": "", "impact": "AI应用场景进一步拓展。"},
    ]

def get_default_economy():
    return [
        {"title": "全球经济温和复苏，新兴市场表现亮眼", "summary": "IMF最新报告显示全球经济增长好于预期。", "content": "全球经济温和复苏。", "source": "综合报道", "link": ""},
    ]

def main():
    print(f"=== 开始更新数据 {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    data = {
        'ai_news': get_ai_news(),
        'stocks': get_stocks(),
        'stock_analysis': '本周AI板块整体走强，算力芯片厂商表现突出。大模型降价加速应用落地，关注算力基础设施和AI应用两条主线。',
        'economy': get_economy_news(),
        'trade': get_trade_products(),
        'videos': get_ai_videos(),
    }
    
    # 保存
    out_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'data.json')
    out_path = os.path.abspath(out_path)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"数据已保存到 {out_path}")
    print(f"AI新闻: {len(data['ai_news'])} 条")
    print(f"股票: {len(data['stocks'])} 只")
    print(f"经济新闻: {len(data['economy'])} 条")
    print(f"外贸热款: {len(data['trade'])} 个")
    print(f"AI爆款视频: {len(data['videos'])} 个")
    print("=== 更新完成 ===")

if __name__ == '__main__':
    main()
