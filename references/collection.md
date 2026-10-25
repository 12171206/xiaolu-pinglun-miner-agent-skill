# 评论采集与留证

仅在实际处理视频链接时阅读本文件。

## 采集优先级

1. 平台官方 API 或用户提供的合法导出文件；
2. 用户已登录并能正常查看的浏览器页面；
3. 用户手工导出的评论与截图。

页面可见不等于允许高频自动化。使用温和滚动，并以连续多轮无新增评论作为遍历完成条件；不破解签名、不复用偷取的 Cookie、不绕过验证码或访问控制。平台阻止自动采集时，保存诊断信息并转为用户导出流程。

## 浏览器采集

`capture_comments.py` 使用独立浏览器资料目录保存登录会话，不读取用户日常浏览器资料。首次需要登录时，运行可见浏览器模式，让用户亲自完成登录；不要要求用户把密码或验证码发给代理。

采用两轮流程：第一轮读取评论文字但不截图；完成选题价值筛选后，第二轮只截图 `selected-comments.json` 中的入选评论。这样不会把无效评论全部截图或上传飞书。

常用命令：

```powershell
python <skill>/scripts/capture_comments.py "<video-url>" --out "<run-dir>/sources/video-01" --headful --screenshot-mode none
```

若内置平台选择器失效，先检查页面中一条完整评论的稳定容器，再传入覆盖选择器：

```powershell
python <skill>/scripts/capture_comments.py "<video-url>" --out "<run-dir>/sources/video-01" --comment-selector "<css>" --content-selector "<css>" --author-selector "<css>"
```

选择器必须指向一条完整评论，不要用只包含正文的叶子节点，否则作者、时间和点赞数无法与正文稳定关联。若评论位于 iframe 或关闭的 shadow DOM，改用可操作该上下文的浏览器工具，并保持相同输出结构。

## 人工验证后继续

若平台在自动化浏览器中断开连接或展示滑块，使用由用户亲自操作的独立普通浏览器。启动一个带调试端口的 Edge 和专用资料目录，打开目标视频；用户完成验证并展开评论后，采集器连接当前页面，不重复导航：

```powershell
Start-Process -FilePath "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ArgumentList @("--remote-debugging-port=9223", "--user-data-dir=<dedicated-profile>", "<video-url>")
python <skill>/scripts/capture_comments.py "<video-url>" --out "<run-dir>/sources/video-01" --cdp-url "http://127.0.0.1:9223" --use-current-page --screenshot-mode none
```

调试端口仅绑定本机地址；采集完成后关闭该专用 Edge。验证码、登录和风险确认由用户完成，代理不代答也不绕过。

筛选完成后，对每个视频重新运行并只截入选评论：

```powershell
python <skill>/scripts/capture_comments.py "<video-url>" --out "<run-dir>/sources/video-01-selected" --selected-ids "<run-dir>/selected-comments.json" --screenshot-mode selected
```

`selected-comments.json` 可以是评论 ID 数组，也可以是含 `comment_id` 的对象数组。第二轮输出中的 `selected_for_topic` 为 `true`，且应有截图路径和校验值。目标评论若使用“这个、这种、同样的问题”等指代，截图必须同时包含被指代的父评论；采集器无法稳定截取父子上下文时，将该评论从入选清单移除。

## 样本策略

- 默认不限制评论条数和滚动轮数，持续温和滚动，直到连续 5 轮没有新增评论。`--max-comments` 和 `--max-scrolls` 仅用于用户明确要求抽样或诊断时的可选限制；值为 `0` 表示不限。
- 有“热门/最新”排序时，各采集一批并在 `sample_mode` 中标记。无法切换排序时记录 `visible_order`。
- 回复可作为独立记录，但必须保留父评论 ID；无法稳定关联时，在 `raw_text` 中保留整块并标记 `thread_unparsed`。
- 对同一视频的短链和落地页做规范化，避免重复采集。

## 证据结构

每行 `comments.jsonl` 是一个对象：

```json
{
  "comment_id": "稳定哈希",
  "author": "页面显示昵称，可空",
  "content": "评论正文",
  "published_at": "页面显示时间，可空",
  "like_count_raw": "页面显示点赞数，可空",
  "raw_text": "评论容器完整可见文本",
  "source_url": "视频规范链接",
  "platform": "youtube|bilibili|douyin|xiaohongshu|kuaishou|generic",
  "sample_mode": "visible_order|top|latest",
  "screenshot": "screenshots/comment-0001.png",
  "screenshot_sha256": "十六进制校验值",
  "collected_at": "ISO 8601 时间"
}
```

`manifest.json` 至少记录请求 URL、最终 URL、平台、采集时间、采集上限、实际唯一评论数、截图成功数、使用的选择器、滚动轮数、警告和失败原因。

## 采集验收

- 随机抽查至少 5 条入选评论的结构化正文与截图一致；不足 5 条时全查。
- 每个被选题引用的评论必须有来源 URL 和可读截图。
- 未入选评论只保留文字研究数据，默认不截图、不上传飞书。
- 页面噪声、菜单文字和视频字幕不得误收为评论。
- 失败链接仍写进总报告，包括失败阶段和是否需要用户登录。
