# 每日AI简报

一个每天自动更新的 AI 资讯 + 股票 + 经济 + 外贸 + 变现案例 简报应用。

## 功能

- 🤖 **AI要闻**：每天 5-10 条最新 AI 动态，含影响分析
- 📈 **AI股票**：AI 概念股实时排名，含分析
- 🌍 **全球经济**：每天 5 条重要经济新闻
- 📦 **外贸热款**：5 个当前外贸热销产品
- 🎬 **AI变现爆款**：3-4 个 AI 赚钱爆款视频案例
- ⭐ **收藏功能**：收藏感兴趣的内容
- 🌙 **深色模式**：支持深浅主题切换
- 📅 **每日打卡**：记录连续学习天数
- 📖 **专业名词解释**：点击术语查看解释

## 自动更新

通过 GitHub Actions 每天北京时间 8:15 自动获取最新数据并更新。

- AI 新闻：Google News RSS
- 股票数据：yfinance（实时股价）
- 经济新闻：BBC / Google News RSS
- 外贸热款 & AI爆款：维护的热门数据（定期更新）

## 部署到 GitHub Pages

1. Fork 或上传本仓库到 GitHub
2. 仓库 Settings → Pages → Source 选 `main` 分支 → Save
3. 等待部署完成，访问 `https://你的用户名.github.io/仓库名/`
4. GitHub Actions 会每天自动更新数据

## 打包成手机 APP

用 Android Studio 创建 WebView 项目，加载你的 GitHub Pages 网址：

```java
webView.loadUrl("https://你的用户名.github.io/daily-brief/");
```

详细步骤见项目说明。

## 项目结构

```
├── index.html              # 主页面
├── data/
│   └── data.json           # 数据文件（每天自动更新）
├── scripts/
│   └── update_data.py      # 数据更新脚本
└── .github/workflows/
    └── update.yml          # GitHub Actions 定时任务
```
