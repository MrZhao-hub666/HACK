# 抖音与小红书获客功能测试

工作台可以发起抖音作品、小红书笔记和评论的实时采集，也支持导入已有 JSON。上游搜索与采集由独立 MediaCrawler 环境管理。版本核对使用 [上游提交 09ed1ec](https://github.com/NanmiCoder/MediaCrawler/tree/09ed1ec62d885dab422a53de999f52ac0bd4966b)，该项目采用[非商业学习使用许可证](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)。真实企业获客使用上游软件前须取得作者书面商用授权，同时确认平台授权范围。

## 载入样例和本地导出

在部署目录运行以下命令，将四条带标记的演示记录写入工作台数据库。启用 `ENABLE_SIMULATOR=1` 时可执行，重复运行会显示四条重复。

```sh
docker compose exec -T api python -m src.api.domestic examples
```

这些样例仅供本地索引接口测试。实时界面只显示真实导入的作品和评论。产品线索可来自作品，购买意愿取自评论。销售核实公开求购方的企业名称后，可点「核实并建档」，采购权限初始为待核实。

部署者也可从本机导入 UTF-8 JSON。传 `dy` 表示抖音，`xhs` 表示小红书。以下是在 Docker 部署目录执行的两种方式。

```sh
docker compose exec -T api python -m src.api.domestic import dy - < export.json
```

```powershell
Get-Content -Raw -Encoding utf8 .\export.json | docker compose exec -T api python -m src.api.domestic import dy -
```

直接运行 Python 部署时，在使用相同 `DB_PATH` 的终端执行 `python -m src.api.domestic import dy export.json`。抖音行需要 `aweme_id`，小红书需要 `note_id`，评论还需要 `comment_id` 和 `content`。作品读取 `title`、`desc`，时间支持秒或毫秒。索引保存平台、外部 ID、原文、检索词和发布时间。原作品链接由平台和作品 ID 构成，部分原帖需在平台内登录查看。重复导入会更新记录并保留已关联的档案。

## 连接已有的 MediaCrawler WebUI

「搜索线索」按钮使用工作台采集服务。使用 MediaCrawler 虚拟环境中的 Python，从工作台项目目录启动服务。例如 Windows 本地联调：

```powershell
& 'D:\Program\MediaCrawler\.venv\Scripts\python.exe' -m scripts.mediacrawler_bridge 'D:\Program\MediaCrawler' --port 8092
```

Compose 的 `MEDIACRAWLER_URL` 指向 `http://host.docker.internal:8092`。服务监听本机地址，两平台顺序采集，每次各查一页。出现登录提示时在采集电脑上的浏览器扫码。采集结束后页面自动导入成功的平台，按所选意图显示本次结果。批次数据存放在 MediaCrawler 安装目录的 `.workbench-searches`，旧导出仍可通过原有命令导入。

在上游选择 JSON 作为导出格式，确定其 HTTP 地址。可先在运行工作台 API 的网络环境访问 `GET /api/data/files?file_type=json`，应返回 `files` 数组。连接器识别上游作品及评论文件，例如 `douyin/json/search_contents_日期.json`、`xhs/json/search_comments_日期.json`。列表为空时检查导出格式和上游数据目录。

| 部署方式 | MEDIACRAWLER_URL 示例 |
|---|---|
| 两个进程都在宿主机，上游监听 8091 | `http://127.0.0.1:8091` |
| 工作台用 Docker Desktop，上游在宿主机 8091 且容器可达 | `http://host.docker.internal:8091` |
| 两个服务在同一 Docker 网络，上游服务名 mediacrawler | `http://mediacrawler:8080` |

将地址写进 Compose 部署目录的 `.env`，执行 `docker compose up -d --build`。直接运行 Python 时在启动服务前设置环境变量。通过已有可信网络连接本机采集服务。抖音和小红书的登录态由独立浏览器保存。

用部署端命令列出并同步已有导出，第二条命令的参数取自第一条命令输出的 `path`。

```sh
docker compose exec -T api python -m src.api.domestic list
docker compose exec -T api python -m src.api.domestic sync douyin/json/search_contents_日期.json
```

同步读取完整文件，覆盖默认预览的前 100 条之后的记录。每文件最多 4 MiB、5000 条。命令输出新增、更新、重复和跳过数。配置缺失、连接错误和文件超限会返回错误并退出。时间缺失保留为空。无法识别作品 ID、缺少正文或正文超过 12000 字符的行计入「跳过」，其他有效行仍可导入。

## 将自有账号评论转为来信

在 `MEDIACRAWLER_OWN_POSTS` 填入企业确认拥有的作品，使用逗号分隔，例如 `dy:实际作品ID,xhs:实际笔记ID`。重启 API 后，此类作品下的真实导入评论会出现「确认是客户来信」。销售核实后，收件箱保存评论原文、原始时间、渠道、原作品地址，再次操作仍指向同一询盘。每条独立评论单独进入收件箱，确认同一次采购后可使用已有的询盘合并功能。

## 工作台 API 和验收

销售业务接口沿用工作台登录会话，写请求沿用浏览器写入校验。

| 接口 | 用途 |
|---|---|
| `POST /api/domestic/searches` | 使用请求 ID 和关键词发起实时采集 |
| `GET /api/domestic/searches/{id}` | 查看各平台的采集状态 |
| `POST /api/domestic/searches/{id}/import` | 导入已完成批次，重复调用返回原导入数 |
| `GET /api/domestic/signals` | 按批次、平台、意图、关键词分页查询 |
| `POST /api/domestic/signals/{id}/adopt` | 传入已核实企业名称和可选国家或地区，建档或关联 |
| `POST /api/domestic/signals/{id}/inquiry` | 确认自有作品的评论并写入收件箱 |

运行 `python -m scripts.goal` 验证项目。拥有上游源码时，可另外运行 `python -m tests.mediacrawler_interop 上游源码目录`。它加载上游原版数据路由，在回环地址临时启动，使用独立数据库和合成的导出文件验证跨 HTTP 同步、筛选及来信转换。
