# MediaCrawler 维护记录

2026 年 11 月 21 日核查。根据“抖音、小红书、爬虫学习”三个线索，本次核查选用 NanmiCoder/MediaCrawler。它是第三方学习项目。[项目主页](https://github.com/NanmiCoder/MediaCrawler)

## 更新频率

按北京时间选取截至 11 月 20 日的 90 个完整自然日。通过 GitHub Commits API 分别查询整个主分支和 `media_platform/douyin` 目录。使用提交者时间，包含合并和文档提交，每个自然日有至少一次提交即算一个活跃日。目录口径只覆盖直接涉及该路径的记录。[主分支记录](https://api.github.com/repos/NanmiCoder/MediaCrawler/commits?sha=09ed1ec62d885dab422a53de999f52ac0bd4966b&since=2026-08-22T16:00:00Z&until=2026-11-20T15:59:59Z&per_page=100) · [抖音目录记录](https://api.github.com/repos/NanmiCoder/MediaCrawler/commits?sha=09ed1ec62d885dab422a53de999f52ac0bd4966b&path=media_platform%2Fdouyin&since=2026-08-22T16:00:00Z&until=2026-11-20T15:59:59Z&per_page=100)

| 统计区间（2026 年） | 主分支提交 | 主分支活跃日 | 抖音目录提交 | 抖音目录活跃日 |
|---|---:|---:|---:|---:|
| 8 月 23 日至 9 月 21 日 | 11 | 4 | 3 | 3 |
| 9 月 22 日至 10 月 21 日 | 11 | 8 | 1 | 1 |
| 10 月 22 日至 11 月 20 日 | 23 | 8 | 3 | 3 |
| 合计 | 45 | 20 | 7 | 7 |

主分支相邻活跃日的间隔中位数为 2 天，最长为 12 天。核查时主分支最新提交发生在 11 月 17 日，内容是更新 README。[最新提交](https://github.com/NanmiCoder/MediaCrawler/commit/09ed1ec62d885dab422a53de999f52ac0bd4966b)

抖音目录的更新集中在 9 月 17、18、19 日，10 月 10 日和 11 月 3、5、8 日。相邻活跃日最长间隔 24 天。11 月 8 日合并了抖音图文作品链接解析修复。GitHub Releases 页截至核查时没有正式发布记录。[相关改动](https://github.com/NanmiCoder/MediaCrawler/pull/998) · [Releases](https://github.com/NanmiCoder/MediaCrawler/releases)

## 与冠英项目的关系

仓库采用《非商业学习使用许可证 1.1》，用于企业商业获客需要先获得版权所有者书面同意。本次核查只统计维护活动。提交次数无法证明检索、评论接口的实时可用性。[许可证](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)
