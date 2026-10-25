# 飞书同步

仅在用户要求写入飞书时阅读本文件。

首次接入、凭证缺失或更换固定目标时，先完整阅读 [feishu-onboarding.md](feishu-onboarding.md)。

## 连接顺序

1. 优先使用已授权的飞书连接器。
2. 固定目标为多维表格时使用 `scripts/feishu_bitable.py`；普通文档使用 `scripts/feishu_doc.py`。
3. 缺少权限或凭证时保留本地交付，只让用户在本机安全输入密钥。

## 开放平台准备

用户需要在飞书开放平台创建企业自建应用。多维表格接入至少启用：

- “查看、评论、编辑和管理多维表格”；
- 固定链接为 `/wiki/` 时，再启用“查看知识空间节点信息”或同等知识库只读权限；
- 上传评论截图所需的云文档素材上传权限。

权限开通后，在目标多维表格右上角菜单的“添加文档应用”中添加该应用并授予可管理权限。应用必须先拥有至少一项多维表格 API 权限，才能被搜索到。

凭证优先用下面的命令在本机交互保存：

```bash
python <skill>/scripts/feishu_credentials.py --save --app-id <APP_ID>
```

Windows 使用当前用户 DPAPI 加密，命令参数和日志都不包含 App Secret。macOS/Linux 使用环境变量或系统密钥管理器映射的 `FEISHU_APP_ID` 与 `FEISHU_APP_SECRET`；`FEISHU_ACCESS_TOKEN` 可覆盖两者。脚本使用 `https://accounts.feishu.cn/oauth/v3/token` 获取令牌。已在聊天、截图或日志中暴露的 App Secret 视为失效，先重置再保存。

## 多维表格配置与同步

首次使用把非敏感配置保存在本机状态目录。多维表格本身固定，但不固定到某一张数据表；每个赛道使用一张独立数据表：

```bash
python <skill>/scripts/configure.py --bitable "<固定飞书多维表格URL>" --track "<主赛道>" --comments-per-video 0
```

先只读测试连接，再按赛道创建或复用数据表并补齐字段：

```bash
python <skill>/scripts/feishu_bitable.py --test-connection
python <skill>/scripts/feishu_bitable.py --ensure-track-table --track "<赛道>"
```

结构化写入包中的每个 topic 至少包含 `topic_id`、`title`、`comment_text`、`evidence_fit` 和非空 `images`。建议同时包含 `track`、`category`、`viral_reason`、`hook`、`outline`、`source_platform`、`source_url`、`video_title`、`comment_id` 与 `collected_at`。

```bash
python <skill>/scripts/feishu_bitable.py --bundle "<run-dir>/topic-bundle.json" --run-key "<本批次唯一哈希>"
```

连接器只创建缺少的数据表、字段和新记录，不删除字段、数据表或记录。赛道名对应数据表名；首次接入且只有一张空白默认表时，将其重命名为主赛道，后续新赛道一律新建独立数据表。每张赛道表使用相同的 18 个字段，主字段为“选题标题”。一个写入包即使包含多个赛道，也会自动拆分写入对应数据表。每个正式选题一行，原评论截图与该选题位于同一行。

## 普通文档同步

仅当固定目标是飞书普通文档时使用：

```bash
python <skill>/scripts/feishu_doc.py --topic-bundle "<run-dir>/topic-bundle.json" --run-key "<本批次唯一哈希>"
```

## 验收

- 返回正确的 app token、table ID 和记录 ID；
- 每个赛道命中独立数据表，新赛道表的 18 个字段与既有赛道表一致；
- 一行一题，截图附件、评论原文、选题标题与选题依据齐全；
- 同一 `批次ID:选题ID` 重试不重复入库；
- 抽查至少 5 条选题，标题事实能由同一行截图直接支持；不足 5 条时全查。

任何一步失败都保留本地产物和错误码；重试前先检查已写入记录。
