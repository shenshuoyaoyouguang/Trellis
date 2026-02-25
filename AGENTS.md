<!-- TRELLIS:START -->
# Trellis 项目指南

> 本文档为 AI 助手提供项目上下文，由 `trellis update` 命令自动维护

---

## 项目概述

**Trellis** 是一站式 AI Coding 框架，支持 Claude Code、Cursor、OpenCode、iFlow CLI、Codex、Kilo CLI、Kiro Code 等多种 AI 编码工具。

**核心价值**：

| 功能 | 解决什么问题 |
|------|-------------|
| **自动注入** | 规范和工作流自动注入每次对话，写一次永久生效 |
| **自更新规范库** | 最佳实践存在 `.trellis/spec/` 中，用得越多 AI 越懂项目 |
| **并行会话** | `/trellis:parallel` 支持多 Agent 并行开发，各自独立 worktree |
| **团队共享** | 团队共享规范，一人写好规范拉高全员 AI Coding 水平 |
| **会话持久化** | 工作记录持久化到 `.trellis/workspace/`，跨会话记住上下文 |

---

## 支持的平台

| 平台 | CLI 标志 | 配置目录 | 默认选中 | Python Hooks |
|------|----------|----------|----------|--------------|
| Claude Code | `--claude` | `.claude/` | 是 | 是 |
| Cursor | `--cursor` | `.cursor/` | 是 | 否 |
| OpenCode | `--opencode` | `.opencode/` | 否 | 否 |
| iFlow CLI | `--iflow` | `.iflow/` | 否 | 是 |
| Codex | `--codex` | `.agents/skills/` | 否 | 否 |
| Kilo CLI | `--kilo` | `.kilocode/` | 否 | 否 |
| Kiro Code | `--kiro` | `.kiro/skills/` | 否 | 否 |

---

## 项目结构

```
Trellis/
├── bin/trellis.js           # CLI 入口脚本
├── src/                     # TypeScript 源码
│   ├── cli/index.ts         # CLI 核心逻辑
│   ├── commands/            # 命令实现 (init, update)
│   ├── configurators/       # 平台配置器
│   ├── templates/           # 模板文件
│   ├── types/               # 类型定义
│   └── utils/               # 工具函数
├── test/                    # 测试文件
├── docs/                    # 文档
├── .trellis/                # 核心工作目录
│   ├── workflow.md          # 工作流指南
│   ├── scripts/             # Python 工具脚本
│   │   ├── task.py          # 任务管理
│   │   ├── get_context.py   # 获取上下文
│   │   └── multi_agent/     # 多代理流水线
│   ├── spec/                # 开发规范 [!] 必读
│   │   ├── frontend/        # 前端规范
│   │   ├── backend/         # 后端规范
│   │   └── guides/          # 思维指南
│   ├── tasks/               # 任务目录
│   └── workspace/           # 开发者工作空间
├── .claude/                 # Claude Code 配置
│   ├── agents/              # Agent 定义
│   ├── commands/            # 斜杠命令
│   └── hooks/               # Hook 脚本
├── .cursor/commands/        # Cursor 斜杠命令
└── .opencode/               # OpenCode 配置
```

---

## 开发命令

### 构建 & 开发

```bash
pnpm build          # TypeScript 编译 + 复制模板
pnpm dev            # 开发模式（监听编译）
pnpm start          # 运行 CLI
```

### 测试

```bash
pnpm test           # 运行测试
pnpm test:watch     # 测试监听模式
pnpm test:coverage  # 测试覆盖率报告
```

### 代码规范

```bash
pnpm lint           # ESLint 检查
pnpm lint:fix       # ESLint 自动修复
pnpm lint:all       # 同时检查 JS/TS 和 Python
pnpm format         # Prettier 格式化
pnpm typecheck      # TypeScript 类型检查
```

### 发布

```bash
pnpm release        # 发布补丁版本
pnpm release:minor  # 发布次版本
pnpm release:major  # 发布主版本
pnpm release:rc     # 发布 RC 版本
```

---

## 开发约定

### TypeScript 配置

- **严格模式**：启用 `strict: true`
- **目标**：ES2022
- **模块**：NodeNext
- **禁止 `any` 类型**：ESLint 强制要求显式类型

### 代码风格

- **Prettier**：双引号、分号、2空格缩进、尾逗号
- **ESLint**：继承 TypeScript 严格规则，强制显式返回类型

### 提交规范

遵循 **Conventional Commits**：

```
type(scope): description
```

**类型**：`feat` | `fix` | `docs` | `refactor` | `test` | `chore` | `perf` | `ci`

### 重要限制

- [!] **AI 禁止执行 `git commit`** — 由人工提交
- 会话记录单文件最多 **2000 行**
- 开发前**必须**阅读 `.trellis/spec/` 相关规范

---

## 斜杠命令参考

### 会话管理

| 命令 | 用途 |
|------|------|
| `/trellis:start` | 开始新会话，初始化开发者身份，加载上下文 |
| `/trellis:record-session` | 记录当前会话到 journal 文件 |
| `/trellis:finish-work` | 完成检查清单 |

### 开发流程

| 命令 | 用途 |
|------|------|
| `/trellis:parallel` | 启动并行开发，多个 Agent 在独立 worktree 工作 |
| `/trellis:before-frontend-dev` | 前端开发前准备 |
| `/trellis:before-backend-dev` | 后端开发前准备 |
| `/trellis:check-frontend` | 前端代码检查 |
| `/trellis:check-backend` | 后端代码检查 |
| `/trellis:check-cross-layer` | 跨层特性检查 |
| `/trellis:break-loop` | 调试后深度分析 |

### 工具命令

| 命令 | 用途 |
|------|------|
| `/trellis:onboard` | 项目入职指南 |
| `/trellis:update-spec` | 更新规范文档 |
| `/trellis:create-command` | 创建自定义斜杠命令 |
| `/trellis:integrate-skill` | 集成新的 skill |

---

## 工作流指南

### 快速开始

```bash
# 1. 初始化开发者身份（首次）
python3 ./.trellis/scripts/init_developer.py <your-name>

# 2. 获取完整上下文
python3 ./.trellis/scripts/get_context.py

# 3. 查看活跃任务
python3 ./.trellis/scripts/task.py list
```

### 开发流程

1. **开始会话** → `/trellis:start`
2. **阅读规范** → 阅读 `.trellis/spec/` 相关文档
3. **开发任务** → 按规范实现
4. **检查代码** → `/trellis:check-frontend` 或 `/trellis:check-backend`
5. **完成工作** → `/trellis:finish-work`
6. **记录会话** → `/trellis:record-session`

### 任务管理

```bash
# 创建任务
python3 ./.trellis/scripts/task.py create "<title>" --slug <name>

# 列出活跃任务
python3 ./.trellis/scripts/task.py list

# 归档任务
python3 ./.trellis/scripts/task.py archive <name>
```

### 必读文档

| 任务类型 | 必读文档 |
|----------|----------|
| 前端工作 | `.trellis/spec/frontend/index.md` |
| 后端工作 | `.trellis/spec/backend/index.md` |
| 跨层特性 | `.trellis/spec/guides/cross-layer-thinking-guide.md` |

---

## 进一步阅读

- [完整使用指南](docs/guide.md) — 系统架构、工作流详解
- [开发工作流](.trellis/workflow.md) — 详细开发流程
- [贡献指南](CONTRIBUTING.md) — 如何贡献代码

<!-- TRELLIS:END -->