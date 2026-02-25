# /trellis:hive-status

> 查看蜂巢并发代理模式的当前状态，包括工蜂进度、巢室状态、共识分数。

---

## 功能说明

此命令将显示：

1. **蜂巢整体状态** - 激活状态、运行时间
2. **工蜂状态** - 每只工蜂的进度和当前任务
3. **巢室状态** - 各巢室的完成情况和依赖关系
4. **雄蜂验证** - 共识分数和验证结果
5. **信息素痕迹** - 最近的事件日志

---

## 使用方式

```
/trellis:hive-status [--detail]
```

**参数**:
- `--detail` (可选): 显示详细信息，包括信息素痕迹

---

## 执行步骤

### Step 1: 读取信息素状态

```bash
python3 .trellis/scripts/hive/pheromone.py status
```

### Step 2: 读取巢室状态

```bash
python3 .trellis/scripts/hive/cell_manager.py list
```

### Step 3: 检查阻塞

```bash
python3 .trellis/scripts/hive/pheromone.py worker --blocked
```

### Step 4: 检查共识

```bash
python3 .trellis/scripts/hive/drone_validator.py consensus
```

---

## 输出格式

### 标准输出

```markdown
## 🐝 蜂巢状态报告

**蜂巢ID**: hive-2026-02-25-001
**状态**: 🟢 活跃
**运行时间**: 15 分钟

---

### 📊 整体进度

```
████████░░░░░░░░░░░░░░░░░░░░░░░░░░ 25%
```

| 指标 | 数值 |
|------|------|
| 总巢室 | 4 |
| 已完成 | 1 |
| 进行中 | 2 |
| 等待中 | 1 |
| 活跃工蜂 | 2 |

---

### 👷 工蜂状态

| 工蜂ID | 巢室 | 状态 | 进度 | 最后更新 |
|--------|------|------|------|----------|
| worker-001 | cell-auth | ✅ 完成 | 100% | 2分钟前 |
| worker-002 | cell-api | 🔄 实现中 | 60% | 刚刚 |
| worker-003 | cell-ui | ⏳ 等待 | 0% | - |

---

### 📦 巢室状态

| 巢室 | 描述 | 状态 | 工蜂 | 依赖 |
|------|------|------|------|------|
| cell-auth | 认证模块 | ✅ 完成 | worker-001 | - |
| cell-api | API路由 | 🔄 进行中 | worker-002 | cell-auth |
| cell-ui | 登录界面 | ⏳ 等待 | - | cell-api |
| cell-tests | 测试用例 | ⏳ 等待 | - | cell-api |

---

### 🐝 雄蜂验证

| 巢室 | 共识分数 | 状态 | 问题 |
|------|----------|------|------|
| cell-auth | 95 | ✅ 共识达成 | 无 |

---

### ⚠️ 警告

无阻塞或超时

---

### 📋 下一步行动

1. 等待 cell-api 完成
2. 派遣 worker-003 到 cell-ui
3. 监控 worker-002 进度
```

### 详细输出 (--detail)

```markdown
## 🐝 蜂巢状态报告 (详细)

... (标准输出内容)

---

### 📜 信息素痕迹 (最近 10 条)

| 时间 | 类型 | 来源 | 内容 |
|------|------|------|------|
| 10:30:00 | progress | worker-002 | cell-api 进度 60% |
| 10:28:00 | completion | worker-001 | cell-auth 完成 |
| 10:25:00 | progress | worker-001 | cell-auth 进度 80% |
| 10:20:00 | progress | worker-001 | cell-auth 进度 40% |
| 10:15:00 | alert | queen | 蜂巢激活 |

---

### 📁 巢室详情

#### cell-auth

```json
{
  "id": "cell-auth",
  "status": "completed",
  "inputs": ["spec/auth.md"],
  "outputs": ["src/auth/*.ts"],
  "assigned_worker": "worker-001",
  "created_at": "2026-02-25T10:15:00Z",
  "completed_at": "2026-02-25T10:28:00Z"
}
```
```

---

## 状态图标说明

| 图标 | 含义 |
|------|------|
| 🟢 | 活跃/正常 |
| 🟡 | 等待/暂停 |
| 🔴 | 阻塞/错误 |
| ⚪ | 非活跃 |
| ✅ | 完成 |
| 🔄 | 进行中 |
| ⏳ | 等待 |
| ❌ | 失败 |

---

## 告警类型

### 阻塞警告

```markdown
⚠️ 阻塞检测

worker-003 被阻塞
- 阻塞来源: worker-002 (cell-api)
- 原因: 等待 API 接口定义

建议: 优先完成 cell-api 以解除阻塞
```

### 超时警告

```markdown
⚠️ 超时检测

worker-001 已超时 (>300秒无响应)
- 巢室: cell-auth
- 最后更新: 10分钟前

建议: 检查 worktree 状态或重新派遣
```

---

## 使用场景

1. **进度监控**: 了解任务执行进度
2. **问题诊断**: 发现阻塞或超时问题
3. **决策支持**: 确定下一步行动
4. **报告生成**: 导出状态报告

---

## 后续操作

- `/trellis:hive-activate` - 激活蜂巢
- `/trellis:hive-halt` - 暂停蜂群作业
