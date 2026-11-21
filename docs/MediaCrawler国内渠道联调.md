# 抖音与小红书获客功能测试

工作台读取 MediaCrawler 数据 WebUI 已有的 JSON 导出，支持抖音作品、小红书笔记和两者的评论。也可直接导入同格式的文件。工作台的关键词查询面向已导入记录，页面另有平台站内搜索链接。上游搜索与采集由独立 MediaCrawler 环境管理。版本核对使用 [上游提交 09ed1ec](https://github.com/NanmiCoder/MediaCrawler/tree/09ed1ec62d885dab422a53de999f52ac0bd4966b)，该项目采用[非商业学习使用许可证](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)。真实企业获客使用上游软件前须取得作者书面商用授权，同时确认平台授权范围。

## 三分钟测试

1. 登录工作台，进入「国内线索」，展开「接入 MediaCrawler 数据」，点击「载入测试样例」。首次新增四条，再次加载显示四条重复。样例有独立标识和去重空间。
2. 选择「求购」，可看到维修厂求购 WVA 29087 和车队评论询价。搜索「重卡刹车片」也能找到所属作品讨论该产品的评论；切换「供应推广」可看到厂家直销。产品线索可来自所属作品，购买意愿取自评论本身。原文可供销售复核。
3. 导入自己的数据时选择平台和 JSON 文件。抖音需要 `aweme_id`，小红书需要 `note_id`，评论还需要 `comment_id` 和 `content`。作品读取 `title`、`desc`，时间支持秒或毫秒。保留平台、作品或评论 ID、原文、检索词和发布时间；未保存用户主页、昵称、平台登录信息。原作品链接由平台和作品 ID 构成，部分原帖需在平台内登录查看。
4. 销售核实公开求购方的企业名称后点「核实并建档」，可选填所在市场，采购权限初始为待核实。同一平台同一作品或评论重导会更新内容，保留已关联的档案。当前销售只核实了账号发言时，可以继续让该线索留在列表里。

## 连接已有的 MediaCrawler WebUI

在上游选择 JSON 作为导出格式，确定其 HTTP 地址。可先在运行工作台 API 的网络环境访问 `GET /api/data/files?file_type=json`，应返回 `files` 数组。连接器识别上游作品及评论文件，例如 `douyin/json/search_contents_日期.json`、`xhs/json/search_comments_日期.json`。列表为空时检查导出格式和上游数据目录。

| 部署方式 | MEDIACRAWLER_URL 示例 |
|---|---|
| 两个进程都在宿主机，上游监听 8091 | `http://127.0.0.1:8091` |
| 工作台用 Docker Desktop，上游在宿主机 8091 且容器可达 | `http://host.docker.internal:8091` |
| 两个服务在同一 Docker 网络，上游服务名 mediacrawler | `http://mediacrawler:8080` |

Compose 将地址写进工作台根目录的 `.env`，执行 `docker compose up -d --build`。直接运行 Python 时在启动服务前设置环境变量。通过已有可信网络连接 WebUI。工作台仅调用两个读取接口，无需填写个人 Cookie。

进入「国内线索」点击「读取 WebUI 文件列表」，选择文件并「同步所选文件」。读取完整文件，包括默认预览的前 100 条之外的记录。每文件最多 4 MiB、5000 条，超限会报错。重复同步会返回新增、更新、重复和跳过数。时间缺失会保留为空。没有记录时页面展示空结果；连接出错时展示上游错误提示。

无法识别作品 ID、缺少正文、或正文超过 12000 字符的行计入「跳过」；其他有效行仍可导入。

## 将自有账号评论转为来信

在 `MEDIACRAWLER_OWN_POSTS` 填入企业确认拥有的作品，使用逗号分隔，例如 `dy:实际作品ID,xhs:实际笔记ID`。重启 API 后，此类作品下的真实导入评论会出现「确认是客户来信」。销售核实后，收件箱保存评论原文、原始时间、渠道、原作品地址，再次操作仍指向同一询盘。每条独立评论单独进入收件箱，确认同一次采购后可使用已有的询盘合并功能。

## 工作台 API 和验收

所有接口沿用工作台登录会话，写请求沿用浏览器写入校验。

| 接口 | 用途 |
|---|---|
| `GET /api/domestic/files` | 查询上游可同步文件 |
| `POST /api/domestic/sync` | 使用文件清单返回的 `path` 同步 |
| `POST /api/domestic/import` | 提交 `platform`（dy、xhs）和 JSON 原文字符串 `document` |
| `GET /api/domestic/signals` | 按平台、意图、关键词分页查询 |
| `POST /api/domestic/signals/{id}/adopt` | 传入已核实企业名称和可选国家或地区，建档或关联 |
| `POST /api/domestic/signals/{id}/inquiry` | 确认自有作品的评论并写入收件箱 |
| `POST /api/domestic/examples` | 在启用模拟器时载入标记样例 |

运行 `python -m scripts.goal` 验证项目。拥有上游源码时，可另外运行 `python -m tests.mediacrawler_interop 上游源码目录`。它加载上游原版数据路由，在回环地址临时启动，使用独立数据库和合成的导出文件验证跨 HTTP 同步、筛选及来信转换。
