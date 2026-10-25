# 飞书视频评论选题 Agent Skill

一个遵循开放 Agent Skills 格式的跨 AI Skill：从用户提供的视频链接采集公开评论，筛选可独立支撑内容选题的评论，只给入选评论截图，并把评论原文、截图和选题写入固定飞书多维表格。

## 主要特性

- 支持 Codex、Claude Code、Cursor、Gemini CLI、GitHub Copilot 等能够读取 `SKILL.md` 并运行本地脚本的 Agent；
- 抖音、小红书、B 站、YouTube、快手和通用网页采集适配；
- 默认不设评论数量上限，以连续无新增为自然停止条件；
- 本地预筛、批量 AI 审核、只截入选评论，降低 Token 消耗；
- 评论 ID、原图和选题一一对应，截图哈希可复核；
- 固定一个飞书多维表格，同赛道复用同一数据表，新赛道自动创建相同的 18 字段表；
- 首次使用时由 Agent 引导完成飞书应用、权限、凭证、目标表和连接测试。

## 三步完成安装

先安装 [Python 3.10+](https://www.python.org/downloads/) 和 [Git](https://git-scm.com/downloads)，再打开 PowerShell 或终端执行以下命令。

### 第一步：下载 Skill

```bash
git clone https://github.com/12171206/feishu-video-topic-miner-agent-skill.git
cd feishu-video-topic-miner-agent-skill
```

不使用 Git 也可以点击仓库右上角 `Code → Download ZIP`，解压后在该文件夹中打开终端。

### 第二步：安装运行依赖

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

这两行只安装运行依赖，还没有把 Skill 安装进 AI 软件。

### 第三步：安装到你的 AI 软件

选择下面一条命令执行：

| AI 软件 | 安装命令 |
|---|---|
| Codex | `python scripts/install_skill.py --agent codex` |
| Claude Code | `python scripts/install_skill.py --agent claude` |
| Cursor | `python scripts/install_skill.py --agent cursor` |
| Gemini CLI | `python scripts/install_skill.py --agent gemini` |
| GitHub Copilot | `python scripts/install_skill.py --agent copilot` |
| 其他 Agent Skills 客户端 | `python scripts/install_skill.py --agent agents` |

安装成功后重新启动对应的 AI 软件，然后对它说：

> 使用 feishu-video-topic-miner，帮我连接飞书多维表格并检查配置。

安装助手会自动复制到对应客户端的用户级技能目录。若客户端使用自定义目录，可运行：

```bash
python scripts/install_skill.py --agent agents --target-dir "你的技能目录"
```

更详细的目录说明和更新方式见 [`references/install.md`](references/install.md)。

## 首次使用

对 Agent 说：

> 使用 feishu-video-topic-miner，帮我连接一个固定飞书多维表格。我的赛道是……

Agent 应读取 `references/feishu-onboarding.md`，逐步引导你创建应用、开通权限、授权目标表、安全保存凭证并测试连接。

## 使用方式

配置完成后，直接提供赛道和视频链接：

> 赛道是恋爱纠纷法律科普，请采集这个小红书链接的评论，筛选能独立成为选题的评论，保留匹配原图并同步飞书：`<链接>`

如果下一条链接仍属于同一赛道，会继续写入同一张赛道数据表；若赛道改变，会在同一个多维表格中新建一张相同结构的数据表。

## 安全

- 仓库不包含任何 App Secret、Access Token、Cookie、浏览器登录资料、评论截图或用户数据；
- Windows 默认用当前用户 DPAPI 加密保存飞书 Secret；macOS/Linux 推荐使用环境变量或系统密钥管理器；
- 不要提交 `.env`、`credentials.json`、浏览器 profile 或运行产物；
- 不绕过登录、验证码、平台风控或访问限制。

## 低 Token 设计

浏览器采集、确定性排除、去重、元数据补全、截图哈希和飞书写入全部由本地脚本完成。模型只读取紧凑候选评论并批量输出筛选计划与少量创作字段，避免逐评论调用和逐图识别。
