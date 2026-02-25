# /trellis:hive-halt

> 暂停蜂巢并发代理模式，停止所有工蜂作业并保存当前状态。

---

## 功能说明

此命令将：

1. **发送停止信号** - 通知所有工蜂停止当前工作
2. **保存信息素状态** - 记录当前进度，便于恢复
3. **清理 worktree** - 可选清理临时 worktree
4. **生成中断报告** - 记录停止原因和当前状态

---

## 使用方式

```
/trellis:hive-halt [--cleanup] [--reason "原因"]
```

**参数**:
- `--cleanup` (可选): 清理所有 worktree 和临时文件
- `--reason "原因"` (可选): 停止原因说明

---

## 执行步骤

### Step 1: 检查蜂巢状态

```bash
python3 .trellis/scripts/hive/pheromone.py status
```

### Step 2: 发送停止信号

```python
# 更新信息素状态为 "halting"
# 工蜂检测到状态变化后会自动停止
python3 .trellis/scripts/hive/pheromone.py halt
```

### Step 3: 等待工蜂响应

```python
# 等待所有工蜂确认停止
# 最多等待 30 秒
```

### Step 4: 清理资源 (可选)

```bash
if [ "$CLEANUP" = true ]; then
    python3 .trellis/scripts/hive/cell_manager.py cleanup --all
fi
```

### Step 5: 生成报告

```markdown
# 蜂巢中断报告
...
```

---

## 输出格式

### 标准输出

```markdown
## 🐝 蜂巢暂停

**状态**: 🟡 暂停中
**原因**: 用户请求

---

### 停止进度

| 工蜂 | 状态 | 操作 |
|------|------|------|
| worker-001 | ✅ 已停止 | 保存进度 |
| worker-002 | ✅ 已停止 | 保存进度 |
| worker-003 | ⏳ 等待中 | - |

---

### 保存的状态

| 巢室 | 进度 | 状态 |
|------|------|------|
| cell-auth | 100% | 完成 |
| cell-api | 60% | 暂停 |
| cell-ui | 0% | 未开始 |

---

### 资源状态

- Worktrees: 保留 (使用 --cleanup 清理)
- 信息素文件: 已保存
- 上下文文件: 已保存

---

### 恢复方式

要恢复蜂群作业，运行:
```
/trellis:hive-activate
```

蜂后会自动从保存的状态恢复。
```

### 带 --cleanup 的输出

```markdown
## 🐝 蜂巢暂停并清理

**状态**: ⚪ 非活跃
**原因**: 用户请求 + 清理

---

### 清理进度

| 资源 | 状态 |
|------|------|
| worktree-cell-auth | 🗑️ 已删除 |
| worktree-cell-api | 🗑️ 已删除 |
| worktree-cell-ui | 🗑️ 已删除 |
| pheromone.json | 🗑️ 已删除 |
| cells/ | 🗑️ 已删除 |

---

### 已保存的报告

中断报告已保存到: .iflow/hive-audit/halt-report-2026-02-25.json

---

### 重新开始

要重新启动蜂巢，运行:
```
/trellis:hive-activate
```

注意: 清理后需要重新分解任务。
```

---

## 使用场景

### 临时暂停

```
/trellis:hive-halt
```

适用于：
- 临时离开，稍后恢复
- 需要检查中间结果
- 等待外部依赖

### 完全清理

```
/trellis:hive-halt --cleanup
```

适用于：
- 任务已完成或取消
- 需要释放资源
- 切换到其他任务

### 带原因记录

```
/trellis:hive-halt --reason "需要等待设计稿确认"
```

适用于：
- 被外部因素阻塞
- 需要人工决策
- 文档记录

---

## 恢复机制

### 自动恢复

重新激活蜂巢时，蜂后会：

1. 读取信息素文件（如果存在）
2. 检查保存的进度
3. 恢复未完成的巢室
4. 继续调度工蜂

### 手动恢复

如果需要从特定状态恢复：

```bash
# 查看保存的状态
cat .trellis/pheromone.json

# 手动恢复特定巢室
python3 .trellis/scripts/hive/cell_manager.py resume <cell-id>
```

---

## 注意事项

1. **未完成的代码**: 暂停时未提交的代码会保留在 worktree 中
2. **清理警告**: `--cleanup` 会删除所有 worktree，无法恢复
3. **中断报告**: 自动保存到 `.iflow/hive-audit/`

---

## 错误处理

### 工蜂无响应

```markdown
⚠️ 部分工蜂未响应

| 工蜂 | 状态 |
|------|------|
| worker-002 | ❌ 超时 |

建议操作:
1. 检查进程状态
2. 手动终止进程
3. 使用 --cleanup 强制清理
```

### 蜂巢未激活

```markdown
⚠️ 蜂巢未激活

当前状态: inactive

无需暂停操作。
```
