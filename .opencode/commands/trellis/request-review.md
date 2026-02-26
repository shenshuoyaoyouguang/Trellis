# Request Review - 请求审批

请求审批人对当前任务进行审查。

**时机**: 任务开发完成，通过自测后，需要人工审批

---

## 工作流程

### Step 1: 确认当前任务

```bash
# 检查当前任务
python3 ./.trellis/scripts/task.py list --mine --status in_progress
```

### Step 2: 确认代码已就绪

- [ ] 所有代码变更已提交到暂存区
- [ ] lint 和 typecheck 通过
- [ ] 测试通过
- [ ] 相关文档已更新

### Step 3: 请求审批

```bash
# 请求审批（使用当前任务）
python3 ./.trellis/scripts/task.py request-review

# 指定审批人
python3 ./.trellis/scripts/task.py request-review --reviewer <name>

# 指定任务目录
python3 ./.trellis/scripts/task.py request-review <task-dir> --reviewer <name>
```

### Step 4: 通知审批人

审批请求提交后，请通知指定的审批人进行审查。

---

## 审批状态说明

| 状态 | 含义 |
|------|------|
| `none` | 未请求审批 |
| `pending` | 等待审批 |
| `approved` | 已批准 |
| `rejected` | 已拒绝 |
| `changes_requested` | 要求修改 |

---

## 审批流程图

```
开发完成 → request-review → pending
                                   ↓
                          review --approve → completed
                                   ↓
                          review --reject → rejected
                                   ↓
                          review --request-changes → in_progress（返回修改）
```

---

## 相关命令

- `/trellis:review` - 执行审批
- `/trellis:review-status` - 查看审批状态
