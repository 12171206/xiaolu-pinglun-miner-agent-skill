# 安装到不同 AI 客户端

仅在安装、迁移或排查 Skill 发现问题时阅读。

## 运行条件

- AI 客户端能读取本地 `SKILL.md`；
- Agent 拥有用户授权的本地文件、命令行和浏览器能力；
- Python 3.10+；
- `playwright`、`requests` 以及 Chromium 浏览器运行时；
- 访问飞书时具备正常网络连接。

仓库根目录本身就是 Skill 目录。复制时保留 `SKILL.md`、`scripts/`、`references/` 和可选的 `agents/`。

## 常见目录

- Codex：`~/.codex/skills/feishu-video-topic-miner/`
- Claude Code：`~/.claude/skills/feishu-video-topic-miner/`
- Cursor：`~/.cursor/skills/feishu-video-topic-miner/`
- Gemini CLI：`~/.gemini/skills/feishu-video-topic-miner/`；也可使用 `.agents/skills/`
- GitHub Copilot：`~/.copilot/skills/feishu-video-topic-miner/`
- 其他兼容 Agent Skills 的客户端：优先放入 `~/.agents/skills/` 或该客户端文档指定的位置

也可运行：

```bash
python scripts/install_skill.py --agent codex
python scripts/install_skill.py --agent claude
python scripts/install_skill.py --agent cursor
python scripts/install_skill.py --agent gemini
python scripts/install_skill.py --agent copilot
python scripts/install_skill.py --agent agents
```

## 安装依赖与验证

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts/doctor.py
```

重启客户端或重新加载 Skills。然后让 Agent 列出可用技能，确认能看到 `feishu-video-topic-miner`。

## 不原生支持 Agent Skills 的软件

将整个仓库放入该软件允许访问的工作区，并在其项目说明中加入：

> 当用户请求采集视频评论、保留证据截图、生成选题或同步飞书时，先完整阅读 `feishu-video-topic-miner/SKILL.md`，再按其中条件读取 references 并运行 scripts。

这类兼容模式依赖客户端是否能读文件、执行 Python 和控制已授权浏览器。仅能聊天而不能执行本地工具的软件，只能使用筛选与选题方法，不能自动采集或写入飞书。
