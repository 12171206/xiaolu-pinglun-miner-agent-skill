---
name: feishu-video-topic-miner
description: Collect public comments and matching evidence screenshots from user-supplied video links, filter comments that independently support content topics, generate evidence-backed topic ideas for a stated niche, and sync categorized records to a fixed Feishu Base. Use for comment mining, audience-question topic generation, screenshot-topic matching, or Feishu topic-library sync.
---

# 飞书视频评论选题

把用户提供的赛道和视频链接转成可追溯选题库。每条正式选题都要能回查评论原文、原始截图、来源链接和证据哈希。

## 输入与固定规则

最低输入是赛道、目标受众和至少一个用户有权访问的视频链接。首次运行或连接失效时，阅读 [references/feishu-onboarding.md](references/feishu-onboarding.md) 并逐步引导用户配置；安装到其他 AI 客户端时阅读 [references/install.md](references/install.md)。

- 默认不限制评论条数或滚动轮数，以连续多轮无新增作为停止条件。
- 同一个固定飞书多维表格长期复用；同赛道写同一张数据表，不同赛道在该多维表格中新建同结构数据表。
- 只有用户明确提供新的飞书目标链接时才更换目标。
- 正式选题、评论原文和匹配截图必须位于同一行。

## 低 Token 工作流

1. 运行 `scripts/configure.py --show` 读取固定配置。缺失时启动首次配置引导。
2. 阅读 [references/collection.md](references/collection.md)，运行 `scripts/capture_comments.py --screenshot-mode none` 采集完整评论文字。遇到登录、验证码、风控或付费墙时让用户亲自处理，不绕过访问控制。
3. 运行 `scripts/prefilter_comments.py` 本地去重并排除确定无效内容。只把其生成的紧凑候选 JSON 交给模型，不把完整网页、截图或重复元数据送入上下文。
4. 阅读 [references/topic-method.md](references/topic-method.md)。一次批量审核全部候选，输出紧凑的 `selection-plan.json`；只有脱离视频也能看懂具体问题、痛点、选择或误区的评论入选。
5. 用 `scripts/build_selection.py` 把审核计划与原始评论合并。随后仅对入选 ID 运行第二轮截图：`--screenshot-mode selected --selected-ids selected-comments.json`。
6. 用 `scripts/build_evidence_map.py` 校验评论 ID、截图路径和 SHA-256。依赖父评论的回复必须把必要上下文截入同一张图，否则淘汰。
7. 模型一次批量生成紧凑的标题覆盖映射；平台、链接、ID、时间、哈希、固定结构等字段由 `scripts/prepare_topic_bundle.py` 本地生成。不要逐条调用模型，也不要让模型逐张识图；只有证据映射存在疑问时才查看截图。
8. 本地生成 `topic-report.md`、`selected-comments.json`、`selected-evidence.json`、`topic-bundle.json` 和证据目录。
9. 用户授权同步后，阅读 [references/feishu.md](references/feishu.md)，运行 `scripts/feishu_bitable.py`。按批次 ID 去重，只上传正式选题使用的截图。
10. 回读验收总评论数、入选数、截图数、题图匹配、赛道表和记录 ID。文字与截图均写入成功后才能报告“已同步飞书”。

## 质量底线

- 评论只保留原意；模型知识和视频正文不能伪装成评论区声音。
- “这个怎么办”“已经中招”“我也是”等缺少讨论对象的评论不生成选题。
- 标题、钩子和核心命题中的事实必须由同一行截图直接支持；金额、关系、行为、诉讼状态和结果不能补写。
- “爆款”仅表示传播潜力假设，不承诺播放量。
- 采集不到的字段留空；不声称抓取全部评论，除非有可验证的完整遍历记录。
- 原始证据只进入用户授权位置，外发报告默认匿名化。
