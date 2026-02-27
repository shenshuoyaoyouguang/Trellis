# Trellis 完整教程

> AI 的能力像藤蔓一样生长——充满活力但四处蔓延。Trellis 提供结构，引导它沿着规范的路径前进。

---

## 目录

- [第一部分：快速入门](#第一部分快速入门)
  - [1.1 Trellis 是什么](#11-trellis-是什么)
  - [1.2 安装与初始化](#12-安装与初始化)
  - [1.3 第一个开发任务](#13-第一个开发任务)
- [第二部分：核心概念](#第二部分核心概念)
  - [2.1 规范系统](#21-规范系统)
  - [2.2 会话追踪系统](#22-会话追踪系统)
  - [2.3 Agent 系统](#23-agent-系统)
  - [2.4 Hook 自动化机制](#24-hook-自动化机制)
  - [2.5 多 Agent 并行管道](#25-多-agent-并行管道)
- [第三部分：日常工作流](#第三部分日常工作流)
  - [3.1 单会话开发流程](#31-单会话开发流程)
  - [3.2 Slash 命令速查](#32-slash-命令速查)
  - [3.3 开发规范管理](#33-开发规范管理)
  - [3.4 会话记录与追踪](#34-会话记录与追踪)
- [第四部分：实战案例集](#第四部分实战案例集)
  - [4.1 案例1：简单 Bug 修复](#41-案例1简单-bug-修复)
  - [4.2 案例2：前端组件开发](#42-案例2前端组件开发)
  - [4.3 案例3：后端 API 实现](#43-案例3后端-api-实现)
  - [4.4 案例4：多 Agent 并行开发](#44-案例4多-agent-并行开发)
- [第五部分：配置项参考](#第五部分配置项参考)
  - [5.1 worktree.yaml 配置详解](#51-worktreeyaml-配置详解)
  - [5.2 task.json 结构说明](#52-taskjson-结构说明)
  - [5.3 JSONL 上下文文件](#53-jsonl-上下文文件)
  - [5.4 settings.json Hook 配置](#54-settingsjson-hook-配置)
- [第六部分：Hook 开发指南](#第六部分hook-开发指南)
  - [6.1 Hook 系统架构](#61-hook-系统架构)
  - [6.2 PreToolUse Hook 开发](#62-pretooluse-hook-开发)
  - [6.3 SubagentStop Hook 开发](#63-subagentstop-hook-开发)
  - [6.4 自定义 Hook 最佳实践](#64-自定义-hook-最佳实践)
- [附录](#附录)
  - [A. 命令速查表](#a-命令速查表)
  - [B. 文件结构速查](#b-文件结构速查)
  - [C. 常见问题解答](#c-常见问题解答)

---

# 第一部分：快速入门

## 1.1 Trellis 是什么

Trellis 是一个 **All-in-one AI 框架和工具集**，专为 Claude Code、Cursor、iFlow、Codex 和 Kiro Code 等 AI 编程工具设计。

### 解决什么问题

| 问题 | Trellis 的方案 |
|------|----------------|
| **AI 缺乏项目背景** | 规范持久存储在 `.trellis/spec/`，会话记录在 `.trellis/workspace/` |
| **开发规范写了但不遵守** | 规范按需加载，通过 Hook 自动注入到 Agent 上下文 |
| **工作流程靠人盯着** | Slash Command 封装完整工作流，自动化执行 |
| **多 Agent 并行的门槛高** | `/trellis:parallel` 一键启动，Git Worktree 物理隔离 |

### 核心价值

```
一次编写规范 → 全团队共享 → AI 自动遵守 → 持续改进
```

- **自动注入**：规范和工作流自动注入到每次对话中
- **自动更新规范库**：最佳实践存储在自动更新的规范文件中
- **并行会话**：在独立 worktree 中运行多个 AI Agent
- **团队同步**：一人编写规范，全员受益
- **会话持久化**：工作痕迹保存在仓库中，跨会话记忆

---

## 1.2 安装与初始化

### 安装

```bash
npm install -g @mindfoldhq/trellis@latest
```

### 初始化项目

```bash
# 交互式初始化
trellis init

# 使用默认值快速初始化
trellis init -y -u your-name

# 仅配置 Claude Code
trellis init --claude -y

# 仅配置 Cursor
trellis init --cursor -y
```

### 初始化选项说明

| 选项 | 说明 |
|------|------|
| `--cursor` | 仅包含 Cursor 命令 |
| `--claude` | 仅包含 Claude Code 命令 |
| `-y, --yes` | 跳过提示，使用默认值 |
| `-u, --user <name>` | 使用指定名称初始化开发者身份 |
| `-f, --force` | 覆盖现有文件，不询问 |
| `-s, --skip-existing` | 跳过现有文件，不询问 |

### 初始化后的目录结构

```
your-project/
├── AGENTS.md                    # 轻量级 AI 指令
├── .trellis/                    # 工作流和规范中心
│   ├── workflow.md              # 开发流程指南
│   ├── worktree.yaml            # 多 Agent 流水线配置
│   ├── spec/                    # 开发规范
│   ├── workspace/               # 会话记录
│   ├── tasks/                   # 任务管理
│   └── scripts/                 # 自动化脚本
├── .claude/                     # Claude Code 专用配置
│   ├── commands/                # Slash Commands
│   ├── agents/                  # Agent 定义
│   └── hooks/                   # Hook 脚本
└── .cursor/                     # Cursor 专用配置
    └── commands/                # Slash Commands
```

---

## 1.3 第一个开发任务

### 最小化工作流

```
/trellis:start → 说需求 → /trellis:finish-work → git commit → /trellis:record-session
```

### 详细步骤

**步骤 1：启动会话**

```
/trellis:start
```

AI 会自动：
1. 读取 `.trellis/workflow.md` 了解工作流
2. 执行 `get_context.py` 获取当前状态
3. 读取 `.trellis/spec/` 规范索引
4. 报告就绪状态，询问任务

**步骤 2：描述需求**

```
修复用户登录页面的空指针异常
```

**步骤 3：AI 执行开发**

- AI 判断任务类型（简单修复）
- 直接修改代码
- 提醒你执行 `/trellis:finish-work`

**步骤 4：完成检查**

```
/trellis:finish-work
```

AI 会执行：
- 代码质量检查（lint、typecheck）
- 文档同步检查
- 跨层验证

**步骤 5：人工提交**

```bash
git add .
git commit -m "fix(auth): 修复登录页面空指针异常"
```

**步骤 6：记录会话**

```
/trellis:record-session
```

---

# 第二部分：核心概念

## 2.1 规范系统

规范系统是 Trellis 的核心知识库，存储项目的开发规范和最佳实践。

### 目录结构

```
.trellis/spec/
├── shared/                      # 跨项目通用规范
│   └── index.md
├── frontend/                    # 前端开发规范
│   ├── index.md                 # 前端规范入口
│   ├── directory-structure.md   # 目录结构约定
│   ├── component-guidelines.md  # 组件设计规范
│   ├── hook-guidelines.md       # Hook 使用规范
│   ├── state-management.md      # 状态管理规范
│   ├── quality-guidelines.md    # 代码质量标准
│   └── type-safety.md           # 类型安全规范
├── backend/                     # 后端开发规范
│   ├── index.md                 # 后端规范入口
│   ├── directory-structure.md   # 目录结构约定
│   ├── database-guidelines.md   # 数据库规范
│   ├── error-handling.md        # 错误处理策略
│   ├── quality-guidelines.md    # 代码质量标准
│   └── logging-guidelines.md    # 日志规范
└── guides/                      # 思考指南
    ├── index.md                 # 指南入口
    ├── cross-layer-thinking-guide.md   # 跨层开发思考清单
    └── code-reuse-thinking-guide.md    # 代码复用思考清单
```

### 核心理念

1. **规范越清晰，AI 执行效果越好**
2. **每次发现问题就更新规范，形成持续改进循环**
3. **Thinking Guides 捕捉隐性知识，防止"想不到的问题"**

### 按需加载机制

```
开发任务类型
    │
    ├── 前端任务 → 注入 frontend/*.md
    ├── 后端任务 → 注入 backend/*.md
    ├── 跨层任务 → 注入 guides/cross-layer-*.md
    └── 代码复用 → 注入 guides/code-reuse-*.md
```

### Thinking Guides 触发条件

| 指南 | 触发条件 |
|------|---------|
| cross-layer-thinking-guide | Feature 涉及 3+ 层、数据格式在层间变化、多个消费者需要同一数据 |
| code-reuse-thinking-guide | 类似代码已存在、同一模式重复 3+ 次、需要在多处添加字段 |

---

## 2.2 会话追踪系统

会话追踪系统记录所有 AI Agent 的工作历史，支持多开发者协作。

### 目录结构

```
.trellis/workspace/
├── index.md                     # 活跃开发者列表
└── {developer}/                 # 每个开发者的目录
    ├── index.md                 # 个人会话索引
    ├── journal-N.md             # 会话记录（每文件最多 2000 行）
    └── features/                # Feature 目录
        ├── {day}-{name}/        # 活跃 Feature
        │   ├── task.json        # Feature 元数据
        │   ├── prd.md           # 需求文档
        │   ├── info.md          # 技术设计（可选）
        │   ├── implement.jsonl  # Implement Agent 上下文配置
        │   ├── check.jsonl      # Check Agent 上下文配置
        │   └── debug.jsonl      # Debug Agent 上下文配置
        └── archive/             # 已归档 Feature
```

### Feature 目录详解

每个 Feature 是一个独立的工作单元，包含完整的上下文配置：

**task.json** - Feature 元数据：

```json
{
  "id": "user-auth",
  "name": "user-auth",
  "title": "用户认证功能",
  "status": "in_progress",
  "dev_type": "backend",
  "priority": "P1",
  "branch": "feature/user-auth",
  "base_branch": "main",
  "current_phase": 1,
  "next_action": [
    {"phase": 1, "action": "implement"},
    {"phase": 2, "action": "check"},
    {"phase": 3, "action": "finish"},
    {"phase": 4, "action": "create-pr"}
  ]
}
```

**JSONL 文件** - 上下文配置：

```jsonl
{"file": ".trellis/spec/backend/index.md", "reason": "后端开发规范"}
{"file": "src/api/auth.ts", "reason": "现有认证模式参考"}
{"file": "src/middleware/", "type": "directory", "reason": "中间件模式参考"}
```

### 可追溯性

- **jsonl 文件**：记录用了哪些规范文件、参考了哪些代码、原因是什么
- **journal 文件**：记录每次会话的日期、Feature、工作摘要、主要改动、Git 提交

---

## 2.3 Agent 系统

Trellis 定义了 6 个专门的 Agent，各司其职：

### Agent 职责分工

| Agent | 职责 | 特点 |
|-------|------|------|
| **Plan** | 评估需求有效性、配置 Feature 目录 | 可以拒绝不清晰的需求 |
| **Research** | 搜索代码和文档 | 只读不修改，禁止建议/批评 |
| **Dispatch** | 多代理管道主调度器 | 纯分发者，不读取规范 |
| **Implement** | 按规范实现功能 | 禁止 git commit |
| **Check** | 检查代码并自行修复 | 受 Ralph Loop 控制 |
| **Debug** | 深度分析和修复问题 | 仅在 Check 失败时调用 |

### Agent 调用关系

```
用户请求 → dispatch(调度)
              │
              ├── plan(需求评估) → 可拒绝不清晰需求
              │       │
              │       └── research(代码分析)
              │
              ├── implement(代码实现) ← Hook 注入 spec 上下文
              │
              ├── check(质量检查) ← Ralph Loop 强制验证
              │
              ├── debug(问题修复) ← 如 check 失败
              │
              └── finish → create-pr(创建 PR)
```

### Agent 工具权限

| Agent | Read | Write/Edit | Bash | Git Commit |
|-------|------|------------|------|------------|
| dispatch | ✓ | ✗ | ✓ | ✗ |
| plan | ✓ | ✗ | ✓ | ✗ |
| research | ✓ | ✗ | ✗ | ✗ |
| implement | ✓ | ✓ | ✓ | **禁止** |
| check | ✓ | ✓ | ✓ | **禁止** |
| debug | ✓ | ✓ | ✓ | **禁止** |

---

## 2.4 Hook 自动化机制

Trellis 通过 Hook 实现工作流自动化，让 AI 按照预定流程执行。

### 上下文分阶段注入

**问题**：上下文过多会导致 AI 分心、混淆、冲突——称为**上下文腐烂**。

**解决方案**：分阶段注入

```
Plan/Research Agent 提前分析需求
         ↓
将相关文件路径写入 *.jsonl
         ↓
Hook 在调用每个 Agent 时，只注入该阶段需要的文件
         ↓
每个 Agent 收到精准的上下文，专注当前任务
```

| 阶段 | 注入内容 | 排除内容 |
|------|---------|---------|
| Implement | 需求 + 实现相关的规范和代码 | 检查规范 |
| Check | 检查规范 + 代码质量标准 | 实现细节 |
| Finish | 提交检查清单 + 需求 | 完整的检查规范 |

### Hook 文件

| Hook | 触发时机 | 功能 |
|------|---------|------|
| `inject-subagent-context.py` | PreToolUse (Task 调用前) | 注入上下文到子 Agent |
| `ralph-loop.py` | SubagentStop (Check Agent 停止时) | 质量控制循环 |

### Ralph Loop 质量控制

```
Check Agent 尝试停止
        ↓
  Ralph Loop 触发
        ↓
   有 verify 配置？
   ├─ 是 → 执行验证命令
   │       ├─ 全部通过 → 允许停止
   │       └─ 有失败 → 阻止停止，继续修复
   └─ 否 → 检查完成标记
           ├─ 标记齐全 → 允许停止
           └─ 缺少标记 → 阻止停止
```

**最多循环 5 次**（防止无限循环）

---

## 2.5 多 Agent 并行管道

多 Agent 并行管道使用 Git Worktree 实现物理隔离，让多个 Agent 同时工作。

### 与单会话的区别

| 维度 | 单会话 (`/trellis:start`) | 并行管道 (`/trellis:parallel`) |
|------|--------------------------|-------------------------------|
| 执行位置 | 主仓库单进程 | 主仓库 + Worktree 多进程 |
| Git 管理 | 当前分支直接开发 | 创建独立 Worktree 和分支 |
| 适用场景 | 简单任务、快速实现 | 复杂功能、多模块、需要隔离 |

### 流水线阶段

```
┌─────────────────────────────────────────────────────────────┐
│ Plan 阶段（主仓库）                                          │
├─────────────────────────────────────────────────────────────┤
│ 1. Plan Agent 评估需求                                       │
│ 2. Research Agent 分析代码库                                 │
│ 3. 创建 Feature 目录（task.json、prd.md、*.jsonl）           │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ Worktree 创建（主仓库 → Worktree）                           │
├─────────────────────────────────────────────────────────────┤
│ 1. 创建 Git Worktree                                         │
│ 2. 复制环境变量文件                                          │
│ 3. 运行初始化命令                                            │
│ 4. 启动 Dispatch Agent                                       │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ Implement → Check → Finish → Create-PR                      │
│ （在 Worktree 中执行）                                        │
└─────────────────────────────────────────────────────────────┘
```

### Worktree 配置

编辑 `.trellis/worktree.yaml`：

```yaml
# Worktree 存储目录
worktree_dir: ../trellis-worktrees

# 需要复制的文件
copy:
  - .env
  - .trellis/.developer

# 创建后运行的命令
post_create:
  - pnpm install --frozen-lockfile

# Check Agent 验证命令
verify:
  - pnpm lint
  - pnpm typecheck
```

---

# 第三部分：日常工作流

## 3.1 单会话开发流程

### Claude Code 工作流

**简单任务**：

```
/trellis:start → 说需求 → /trellis:finish-work → 提交 → /trellis:record-session
```

**复杂功能**（多 Agent 流水线）：

```
/trellis:parallel → 说需求 → （自动执行完整流水线）→ /trellis:record-session
```

### Cursor 工作流

Cursor 不支持 Hook 自动化，需要手动触发各阶段：

```
/trellis:start
    ↓
说需求
    ↓
/trellis:before-frontend-dev  或  /trellis:before-backend-dev
    ↓
AI 实现功能
    ↓
/trellis:check-frontend  或  /trellis:check-backend
    ↓
/trellis:finish-work
    ↓
git commit
    ↓
/trellis:record-session
```

### 任务分类决策

| 类型 | 判断标准 | 处理方式 |
|------|---------|---------|
| **问题咨询** | 询问代码、架构、工作原理 | 直接回答 |
| **简单修复** | 错别字、注释、单行改动 | 直接修改 → `/trellis:finish-work` |
| **开发任务** | 修改逻辑、添加功能、修复 bug、多文件 | **Feature Workflow** |

> **如有疑虑，使用 Feature Workflow** —— 规范是被注入到 Agent 的，不是靠"记忆"。

---

## 3.2 Slash 命令速查

### 核心命令

| 命令 | 用途 | 触发时机 |
|------|------|---------|
| `/trellis:start` | 会话初始化 | 开始开发时 |
| `/trellis:parallel` | 多 Agent 流水线 | 复杂功能开发 |
| `/trellis:finish-work` | 提交前检查 | 准备提交时 |
| `/trellis:record-session` | 记录会话 | 提交完成后 |

### 开发前命令

| 命令 | 用途 |
|------|------|
| `/trellis:before-frontend-dev` | 注入前端规范到上下文 |
| `/trellis:before-backend-dev` | 注入后端规范到上下文 |

### 检查命令

| 命令 | 用途 |
|------|------|
| `/trellis:check-frontend` | 前端代码质量检查 |
| `/trellis:check-backend` | 后端代码质量检查 |
| `/trellis:check-cross-layer` | 跨层一致性检查 |

### 辅助命令

| 命令 | 用途 |
|------|------|
| `/trellis:onboard` | 新用户入门引导 |
| `/trellis:brainstorm` | 需求发现和澄清 |
| `/trellis:break-loop` | Bug 深度分析 |
| `/trellis:update-spec` | 更新代码规范文档 |
| `/trellis:create-command` | 创建新的 Slash Command |
| `/trellis:integrate-skill` | 提取 skill 集成到项目规范 |

---

## 3.3 开发规范管理

### 规范更新循环

```
AI 按规范执行 → 发现问题 → 更新 .trellis/spec/ → 下次执行更好 → 规范越用越好
```

### 更新规范的时机

- 新模式被发现
- Bug 修复揭示了缺失的指导
- 新约定被建立
- 团队共识发生变化

### 使用 `/trellis:update-spec`

```
/trellis:update-spec
```

AI 会：
1. 分析最近的代码变更
2. 识别新的模式或约定
3. 更新对应的规范文件
4. 更新 index.md 索引

### 团队规范共享

规范文件存储在 `.trellis/spec/`，可以通过 Git 提交共享给团队：

```bash
git add .trellis/spec/
git commit -m "docs: 更新后端错误处理规范"
git push
```

---

## 3.4 会话记录与追踪

### 记录会话

提交代码后：

```
/trellis:record-session
```

或手动执行脚本：

```bash
python3 ./.trellis/scripts/add_session.py \
  --title "实现用户认证功能" \
  --commit "abc1234"
```

### 会话记录内容

每次会话记录包含：
- 日期和时间
- Feature 名称
- 工作摘要
- 主要改动文件
- Git 提交信息
- 测试情况
- 下一步计划

### 任务管理

```bash
# 列出活跃任务
python3 ./.trellis/scripts/task.py list

# 创建新任务
python3 ./.trellis/scripts/task.py create "用户认证功能" --priority P1

# 归档完成的任务
python3 ./.trellis/scripts/task.py archive user-auth

# 列出归档任务
python3 ./.trellis/scripts/task.py list-archive 2024-01
```

---

# 第四部分：实战案例集

## 4.1 案例1：简单 Bug 修复

### 场景

修复用户登录页面的空指针异常。

### 完整流程

**步骤 1：启动会话**

```
用户: /trellis:start
```

**AI 响应**：

```
我已获取项目上下文：
- 当前分支：main
- 开发者：john
- 活跃任务：无
- 最近提交：fix: 修复样式问题

请告诉我你需要完成什么任务？
```

**步骤 2：描述需求**

```
用户: 修复用户登录页面的空指针异常，当用户名为空时会导致崩溃
```

**AI 判断**：

```
这是一个简单修复任务（单文件改动）。

我将直接修复，不需要创建 Feature 目录。
```

**步骤 3：AI 执行修复**

```
我来分析并修复这个问题：

1. 定位问题代码：src/pages/LoginPage.tsx:45
2. 问题原因：未检查 user.username 是否存在
3. 修复方案：添加空值检查

已修改文件：
- src/pages/LoginPage.tsx
```

**步骤 4：完成检查**

```
用户: /trellis:finish-work
```

**AI 执行检查清单**：

```
正在执行 Pre-Commit Checklist...

✓ Lint 检查通过
✓ TypeCheck 通过
✓ 无 console.log 残留
✓ 无 any 类型

代码已准备好提交。
请执行 git commit 后使用 /trellis:record-session 记录会话。
```

**步骤 5：人工提交**

```bash
git add .
git commit -m "fix(auth): 修复登录页面空指针异常"
```

**步骤 6：记录会话**

```
用户: /trellis:record-session
```

---

## 4.2 案例2：前端组件开发

### 场景

创建一个用户列表组件，包含搜索、分页功能。

### 完整流程

**步骤 1：启动会话**

```
用户: /trellis:start
```

**步骤 2：描述需求**

```
用户: 创建用户列表组件，需要支持搜索和分页功能
```

**AI 判断**：

```
这是一个前端开发任务，需要创建新组件。
我将使用 Feature Workflow 确保规范被正确注入。
```

**步骤 3：注入前端规范**

```
用户: /trellis:before-frontend-dev
```

**AI 响应**：

```
我已阅读前端开发规范：
- 组件规范：使用函数式组件、Props 接口定义
- 状态管理：使用 React Query 处理服务端状态
- 类型安全：避免 any，使用严格类型

现在开始实现组件...
```

**步骤 4：AI 实现功能**

```
正在创建用户列表组件...

创建文件：
- src/components/UserList/index.tsx      # 组件主文件
- src/components/UserList/types.ts       # 类型定义
- src/components/UserList/hooks.ts       # 自定义 Hook
- src/components/UserList/UserList.test.tsx  # 测试文件

修改文件：
- src/api/users.ts                       # 添加 API 函数
```

**步骤 5：前端检查**

```
用户: /trellis:check-frontend
```

**AI 执行检查**：

```
正在检查前端代码...

检查项目：
✓ 组件规范遵循
✓ Hook 规范遵循
✓ 类型安全
✓ Props 验证
✓ 无硬编码字符串

发现 1 个问题：
- UserList.tsx:32 - 建议添加 useCallback 优化

正在修复...
✓ 已优化渲染性能
```

**步骤 6：完成检查**

```
用户: /trellis:finish-work
```

**步骤 7：提交和记录**

```bash
git add .
git commit -m "feat(ui): 添加用户列表组件"
```

```
用户: /trellis:record-session
```

---

## 4.3 案例3：后端 API 实现

### 场景

实现用户注册 API，包含邮箱验证。

### 完整流程

**步骤 1：启动会话并描述需求**

```
用户: /trellis:start

用户: 实现用户注册 API，需要验证邮箱格式、检查用户名唯一性、发送验证邮件
```

**步骤 2：注入后端规范**

```
用户: /trellis:before-backend-dev
```

**AI 响应**：

```
我已阅读后端开发规范：
- API 规范：RESTful 风格、统一响应格式
- 数据库规范：使用事务、参数化查询
- 错误处理：统一错误码、详细日志

现在开始实现 API...
```

**步骤 3：AI 实现功能**

```
正在创建用户注册 API...

创建文件：
- src/api/routes/auth.ts              # 注册路由
- src/services/auth/register.ts       # 注册服务
- src/services/email/verification.ts  # 邮件服务
- src/validators/auth.ts              # 请求验证

修改文件：
- src/db/schema/users.ts              # 用户表结构
- src/types/api/auth.ts               # 类型定义
```

**步骤 4：后端检查**

```
用户: /trellis:check-backend
```

**AI 执行检查**：

```
正在检查后端代码...

检查项目：
✓ API 规范遵循
✓ 数据库事务处理
✓ 错误处理完整
✓ 日志记录规范
✓ 输入验证

发现 2 个问题：
- auth.ts:45 - 密码未加密
- register.ts:78 - 缺少事务回滚

正在修复...
✓ 已添加 bcrypt 加密
✓ 已添加事务回滚处理
```

**步骤 5：跨层检查**

```
用户: /trellis:check-cross-layer
```

**AI 执行检查**：

```
正在执行跨层检查...

检查维度：
✓ API 响应格式与前端类型一致
✓ 数据库字段与 API 返回字段对应
✓ 错误码在前端有对应处理

全部通过！
```

**步骤 6：完成并提交**

```
用户: /trellis:finish-work
```

```bash
git add .
git commit -m "feat(api): 实现用户注册 API"
```

---

## 4.4 案例4：多 Agent 并行开发

### 场景

实现完整的用户认证功能，包括前后端。

### 完整流程

**步骤 1：启动并行管道**

```
用户: /trellis:parallel

用户: 实现完整的用户认证功能：
- 前端：登录页面、注册页面、登出功能
- 后端：登录 API、注册 API、JWT 验证中间件
- 数据库：用户表、会话表
```

**Plan Agent 阶段**（自动执行）：

```
Plan Agent 正在评估需求...

需求评估：
✓ 需求清晰，可以执行

正在调用 Research Agent 分析代码库...

发现相关代码：
- 现有中间件模式：src/middleware/auth.ts
- 数据库配置：src/db/config.ts
- API 路由结构：src/api/routes/

创建 Feature 目录：
- .trellis/tasks/02-27-user-auth/
  ├── task.json
  ├── prd.md
  ├── implement.jsonl
  └── check.jsonl
```

**Worktree 创建**（自动执行）：

```
正在创建 Worktree...

1. 创建目录：../trellis-worktrees/feature/user-auth
2. 创建分支：feature/user-auth
3. 复制环境文件：.env, .trellis/.developer
4. 运行初始化：pnpm install --frozen-lockfile
5. 启动 Dispatch Agent
```

**Implement Agent 阶段**（在 Worktree 中执行）：

```
Implement Agent 正在实现功能...

注入上下文：
- .trellis/spec/frontend/index.md
- .trellis/spec/backend/index.md
- prd.md（需求文档）

创建文件（前端）：
- src/pages/LoginPage.tsx
- src/pages/RegisterPage.tsx
- src/components/AuthForm.tsx
- src/hooks/useAuth.ts

创建文件（后端）：
- src/api/routes/auth.ts
- src/services/auth/login.ts
- src/services/auth/register.ts
- src/middleware/jwt.ts

创建文件（数据库）：
- src/db/schema/users.ts
- src/db/schema/sessions.ts
- migrations/002_add_sessions.ts

运行 lint... ✓ 通过
运行 typecheck... ✓ 通过
```

**Check Agent 阶段**（在 Worktree 中执行）：

```
Check Agent 正在检查代码...

注入上下文：
- .trellis/spec/shared/quality.md
- finish-work.md

检查结果：
- 前端规范：✓ 通过
- 后端规范：✓ 通过
- 类型安全：✓ 通过

Ralph Loop 验证：
运行 pnpm lint... ✓ 通过
运行 pnpm typecheck... ✓ 通过

全部验证通过！
```

**Create-PR 阶段**（自动执行）：

```
正在创建 PR...

1. git add -A（排除 agent-traces）
2. git commit -m "feat(auth): 实现用户认证功能"
3. git push origin feature/user-auth
4. gh pr create --draft --base main

PR 已创建：https://github.com/xxx/pull/123
```

**步骤 2：人工测试和合并**

```bash
# 在主仓库查看 Worktree 状态
python3 ./.trellis/scripts/multi_agent/status.py

# 测试通过后合并 PR
gh pr merge 123 --squash

# 清理 Worktree
python3 ./.trellis/scripts/multi_agent/cleanup.py user-auth
```

**步骤 3：记录会话**

```
用户: /trellis:record-session
```

---

# 第五部分：配置项参考

## 5.1 worktree.yaml 配置详解

Worktree 配置文件用于多 Agent 并行管道。

### 完整配置示例

```yaml
# .trellis/worktree.yaml

#-------------------------------------------------------------------------------
# 路径配置
#-------------------------------------------------------------------------------

# Worktree 存储目录（相对于项目根目录）
worktree_dir: ../trellis-worktrees

#-------------------------------------------------------------------------------
# 文件复制
#-------------------------------------------------------------------------------

# 需要复制到每个 Worktree 的文件
# 这些文件包含敏感信息或需要独立配置
copy:
  # 环境变量文件
  - .env
  - .env.local
  # 开发者身份
  - .trellis/.developer

#-------------------------------------------------------------------------------
# 创建后钩子
#-------------------------------------------------------------------------------

# Worktree 创建后运行的命令
# 在 Worktree 目录中执行，按顺序执行，失败则中止
post_create:
  # 安装依赖（根据包管理器选择）
  - pnpm install --frozen-lockfile
  # 其他初始化命令
  # - npm run db:migrate

#-------------------------------------------------------------------------------
# Check Agent 验证命令（Ralph Loop）
#-------------------------------------------------------------------------------

# Check Agent 结束前必须通过的验证命令
# 如果配置，Ralph Loop 会执行这些命令，全部通过才允许结束
# 如果不配置，则信任 Agent 的完成标记
verify:
  - pnpm lint
  - pnpm typecheck
  # - pnpm test
```

### 配置项说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `worktree_dir` | string | 是 | Worktree 存储目录，相对于项目根目录 |
| `copy` | string[] | 否 | 需要复制的文件列表 |
| `post_create` | string[] | 否 | 创建后运行的命令列表 |
| `verify` | string[] | 否 | Check Agent 验证命令列表 |

---

## 5.2 task.json 结构说明

Feature 任务元数据文件。

### 完整字段说明

```json
{
  "id": "user-auth",
  "name": "user-auth",
  "title": "用户认证功能",
  "description": "实现完整的用户认证系统",
  "status": "in_progress",
  "dev_type": "fullstack",
  "scope": "auth",
  "priority": "P1",
  "creator": "john",
  "assignee": "john",
  "createdAt": "2024-02-27",
  "completedAt": null,
  "branch": "feature/user-auth",
  "base_branch": "main",
  "worktree_path": "../trellis-worktrees/feature/user-auth",
  "current_phase": 1,
  "next_action": [
    {"phase": 1, "action": "implement"},
    {"phase": 2, "action": "check"},
    {"phase": 3, "action": "finish"},
    {"phase": 4, "action": "create-pr"}
  ],
  "commit": null,
  "pr_url": null,
  "subtasks": [],
  "relatedFiles": [],
  "notes": "",
  "review_status": "none",
  "reviewer": null,
  "reviewed_at": null,
  "review_comments": []
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 任务唯一标识 |
| `name` | string | 任务名称（用于命令行） |
| `title` | string | 任务标题 |
| `description` | string | 任务描述 |
| `status` | string | 状态：`planning`/`in_progress`/`review`/`completed`/`rejected` |
| `dev_type` | string | 开发类型：`frontend`/`backend`/`fullstack`/`test`/`docs` |
| `scope` | string | PR 作用域（用于 PR 标题） |
| `priority` | string | 优先级：`P0`/`P1`/`P2`/`P3` |
| `creator` | string | 创建者 |
| `assignee` | string | 负责人 |
| `createdAt` | string | 创建日期 |
| `completedAt` | string | 完成日期 |
| `branch` | string | Git 分支名 |
| `base_branch` | string | PR 目标分支 |
| `worktree_path` | string | Worktree 路径 |
| `current_phase` | number | 当前阶段 |
| `next_action` | array | 下一步行动列表 |
| `commit` | string | 提交哈希 |
| `pr_url` | string | PR 链接 |
| `review_status` | string | 审核状态：`none`/`pending`/`approved`/`changes_requested` |

---

## 5.3 JSONL 上下文文件

JSONL 文件定义每个 Agent 需要读取的规范和代码文件。

### 文件类型

| 文件 | 用途 |
|------|------|
| `implement.jsonl` | Implement Agent 上下文 |
| `check.jsonl` | Check Agent 上下文 |
| `debug.jsonl` | Debug Agent 上下文 |
| `research.jsonl` | Research Agent 上下文（可选） |

### 条目格式

**文件条目**：

```jsonl
{"file": ".trellis/spec/backend/index.md", "reason": "后端开发规范"}
{"file": "src/api/auth.ts", "reason": "现有认证模式参考"}
```

**目录条目**：

```jsonl
{"file": "src/middleware/", "type": "directory", "reason": "中间件模式参考"}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | string | 是 | 文件或目录路径 |
| `type` | string | 否 | 类型：`file`（默认）/`directory` |
| `reason` | string | 是 | 引用原因（用于生成完成标记） |

### 管理命令

```bash
# 初始化上下文文件
python3 ./.trellis/scripts/task.py init-context <dir> <dev_type>

# 添加上下文条目
python3 ./.trellis/scripts/task.py add-context <dir> <jsonl> <path> [reason]

# 列出上下文条目
python3 ./.trellis/scripts/task.py list-context <dir>

# 验证上下文文件
python3 ./.trellis/scripts/task.py validate <dir>
```

---

## 5.4 settings.json Hook 配置

Claude Code 的 Hook 配置文件。

### 完整配置示例

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ./.claude/hooks/session-start.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Task",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ./.claude/hooks/inject-subagent-context.py"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "Task",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ./.claude/hooks/ralph-loop.py"
          }
        ]
      }
    ]
  }
}
```

### Hook 事件说明

| 事件 | 触发时机 | 用途 |
|------|---------|------|
| `SessionStart` | 会话开始时 | 注入初始上下文 |
| `PreToolUse` | 工具调用前 | 修改工具输入 |
| `SubagentStop` | 子 Agent 停止时 | 控制循环行为 |

---

# 第六部分：Hook 开发指南

## 6.1 Hook 系统架构

### 触发时机

```
用户输入 → SessionStart Hook → AI 处理 → PreToolUse Hook → 工具执行 → SubagentStop Hook → AI 继续
```

### 输入输出格式

**输入**（stdin）：

```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Task",
  "tool_input": {
    "subagent_type": "implement",
    "prompt": "实现用户认证功能"
  },
  "cwd": "/path/to/repo"
}
```

**输出**（stdout）：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "updatedInput": {
      "subagent_type": "implement",
      "prompt": "修改后的 prompt..."
    }
  }
}
```

### 开发环境

- 语言：Python 3.12+
- 编码：UTF-8
- 输出：JSON 到 stdout
- 错误：stderr（不影响主流程）

---

## 6.2 PreToolUse Hook 开发

### 功能

在 Task 工具调用前，注入上下文到子 Agent。

### 核心逻辑

```python
def main():
    # 1. 读取输入
    input_data = json.load(sys.stdin)
    
    # 2. 检查是否是 Task 工具
    if input_data.get("tool_name") != "Task":
        sys.exit(0)  # 不处理，放行
    
    # 3. 获取 Agent 类型
    subagent_type = input_data["tool_input"].get("subagent_type")
    
    # 4. 获取当前任务目录
    task_dir = get_current_task(repo_root)
    
    # 5. 读取对应的 JSONL 文件
    context = read_jsonl_entries(repo_root, f"{task_dir}/{subagent_type}.jsonl")
    
    # 6. 构建新的 prompt
    original_prompt = input_data["tool_input"]["prompt"]
    new_prompt = build_prompt(original_prompt, context)
    
    # 7. 返回修改后的输入
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {
                **input_data["tool_input"],
                "prompt": new_prompt
            }
        }
    }
    print(json.dumps(output))
```

### 关键函数

**读取 JSONL 文件**：

```python
def read_jsonl_entries(base_path: str, jsonl_path: str) -> list:
    results = []
    with open(jsonl_path, "r") as f:
        for line in f:
            item = json.loads(line)
            file_path = item.get("file")
            entry_type = item.get("type", "file")
            
            if entry_type == "directory":
                # 读取目录下所有 .md 文件
                results.extend(read_directory_contents(base_path, file_path))
            else:
                # 读取单个文件
                content = read_file_content(base_path, file_path)
                results.append((file_path, content))
    return results
```

**构建 prompt**：

```python
def build_implement_prompt(original_prompt: str, context: str) -> str:
    return f"""# Implement Agent Task

## Your Context

{context}

---

## Your Task

{original_prompt}

---

## Workflow

1. Understand specs - All dev specs are injected above
2. Understand requirements - Read requirements document
3. Implement feature - Follow specs and design
4. Self-check - Ensure code quality

## Constraints

- Do NOT execute git commit
- Follow all dev specs
- Report modified/created files"""
```

---

## 6.3 SubagentStop Hook 开发

### 功能

控制 Check Agent 的停止行为，确保代码质量。

### 核心逻辑

```python
def main():
    # 1. 读取输入
    input_data = json.load(sys.stdin)
    
    # 2. 检查是否是 Check Agent
    if input_data.get("subagent_type") != "check":
        sys.exit(0)  # 不处理，放行
    
    # 3. 检查迭代次数
    state = load_state(repo_root)
    current_iteration = state.get("iteration", 0) + 1
    
    if current_iteration >= MAX_ITERATIONS:
        # 达到最大迭代，允许停止
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)
    
    # 4. 执行验证
    verify_commands = get_verify_commands(repo_root)
    
    if verify_commands:
        # 程序化验证
        passed, message = run_verify_commands(repo_root, verify_commands)
        if passed:
            print(json.dumps({"decision": "allow"}))
        else:
            print(json.dumps({
                "decision": "block",
                "reason": f"验证失败：{message}"
            }))
    else:
        # 完成标记验证
        markers = get_completion_markers(repo_root, task_dir)
        all_complete, missing = check_completion(agent_output, markers)
        if all_complete:
            print(json.dumps({"decision": "allow"}))
        else:
            print(json.dumps({
                "decision": "block",
                "reason": f"缺少标记：{missing}"
            }))
```

### 验证方式

**方式 1：程序化验证**（推荐）

```yaml
# worktree.yaml
verify:
  - pnpm lint
  - pnpm typecheck
```

**方式 2：完成标记验证**

```jsonl
// check.jsonl
{"file": "...", "reason": "TypeCheck"}
{"file": "...", "reason": "Lint"}
```

生成标记：`TYPECHECK_FINISH`、`LINT_FINISH`

Agent 必须在输出中包含这些标记才能停止。

---

## 6.4 自定义 Hook 最佳实践

### 开发原则

1. **快速失败**：遇到错误立即 `sys.exit(0)`，不影响主流程
2. **幂等性**：多次执行结果相同
3. **最小依赖**：只使用 Python 标准库
4. **UTF-8 编码**：Windows 兼容

### 调试技巧

```python
import sys

# 调试输出写入 stderr（不影响 stdout JSON）
print("Debug info", file=sys.stderr)

# 保存输入用于调试
with open("/tmp/hook_input.json", "w") as f:
    f.write(json.dumps(input_data))
```

### 错误处理

```python
def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # 解析失败，放行
    
    try:
        # 业务逻辑
        pass
    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)  # 错误时放行，不阻塞主流程
```

### Windows 兼容

```python
import sys
import io

# 强制 UTF-8 输出
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    elif hasattr(sys.stdout, "detach"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.detach(), 
            encoding="utf-8"
        )
```

---

# 附录

## A. 命令速查表

### CLI 命令

| 命令 | 说明 |
|------|------|
| `trellis init` | 初始化项目 |
| `trellis init -y -u <name>` | 快速初始化 |
| `trellis update` | 更新配置 |
| `trellis update --dry-run` | 预览更新 |

### Slash 命令

| 命令 | 说明 |
|------|------|
| `/trellis:start` | 会话初始化 |
| `/trellis:parallel` | 多 Agent 流水线 |
| `/trellis:finish-work` | 提交前检查 |
| `/trellis:record-session` | 记录会话 |
| `/trellis:before-frontend-dev` | 前端规范注入 |
| `/trellis:before-backend-dev` | 后端规范注入 |
| `/trellis:check-frontend` | 前端检查 |
| `/trellis:check-backend` | 后端检查 |
| `/trellis:check-cross-layer` | 跨层检查 |
| `/trellis:break-loop` | Bug 分析 |
| `/trellis:update-spec` | 更新规范 |

### 脚本命令

| 命令 | 说明 |
|------|------|
| `task.py create "<title>"` | 创建任务 |
| `task.py list` | 列出任务 |
| `task.py archive <name>` | 归档任务 |
| `task.py init-context <dir> <type>` | 初始化上下文 |
| `task.py add-context <dir> <file> <path>` | 添加上下文 |
| `get_context.py` | 获取会话上下文 |
| `add_session.py --title "..." --commit "..."` | 记录会话 |

---

## B. 文件结构速查

### 核心目录

```
.trellis/
├── workflow.md              # 开发流程指南
├── worktree.yaml            # 并行管道配置
├── .developer               # 开发者身份
├── .current-task            # 当前任务
├── spec/                    # 开发规范
│   ├── frontend/            # 前端规范
│   ├── backend/             # 后端规范
│   └── guides/              # 思考指南
├── workspace/               # 会话记录
│   └── {developer}/
│       ├── index.md         # 索引
│       └── journal-N.md     # 日志
└── tasks/                   # 任务目录
    └── {MM-DD-slug}/
        ├── task.json        # 元数据
        ├── prd.md           # 需求
        └── *.jsonl          # 上下文
```

### Claude Code 目录

```
.claude/
├── settings.json            # Hook 配置
├── commands/trellis/        # Slash 命令
├── agents/                  # Agent 定义
└── hooks/                   # Hook 脚本
    ├── session-start.py
    ├── inject-subagent-context.py
    └── ralph-loop.py
```

---

## C. 常见问题解答

### Q: Hook 不生效怎么办？

**检查步骤**：

1. 确认 `.claude/settings.json` 配置正确
2. 确认 Hook 脚本有执行权限
3. 检查 Python 版本（需要 3.12+）
4. 查看 Claude Code 日志

### Q: Worktree 创建失败？

**常见原因**：

1. 分支名已存在
2. `worktree_dir` 路径无写入权限
3. `post_create` 命令执行失败

**解决方案**：

```bash
# 手动清理 Worktree
git worktree list
git worktree remove <path>

# 重新创建
python3 ./.trellis/scripts/multi_agent/start.py <task-dir>
```

### Q: Ralph Loop 无限循环？

**原因**：

1. 验证命令持续失败
2. 完成标记未正确输出

**解决方案**：

1. 检查 `worktree.yaml` 的 `verify` 命令是否正确
2. 查看 `.trellis/.ralph-state.json` 状态
3. 手动删除状态文件重置

### Q: 如何自定义 Agent？

1. 创建 `.claude/agents/my-agent.md`
2. 定义 Agent prompt 和约束
3. 在 Dispatch Agent 中添加调用逻辑

### Q: 如何添加新的 Slash Command？

```
/trellis:create-command
```

或手动创建：

1. 创建 `.claude/commands/trellis/my-command.md`
2. 编写命令 prompt
3. 重启 Claude Code

---

## 拓展阅读

- [用 Kubernetes 的方式来理解 Trellis](use-k8s-to-know-trellis-zh.md)
- [上下文开销分析](context-overhead-zh.md)
- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
