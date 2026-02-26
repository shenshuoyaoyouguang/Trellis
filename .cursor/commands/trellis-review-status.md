# Review Status - 查看审批状态

查看任务的审批状态和评论历史。

---

## 使用方法

```bash
# 查看当前任务的审批状态
python3 ./.trellis/scripts/task.py review-status

# 查看指定任务的审批状态
python3 ./.trellis/scripts/task.py review-status <task-dir>
```

---

## 输出示例

```
=== Review Status ===
Task: Add user authentication
Review Status: changes_requested
Reviewer: alice
Reviewed At: 2026-02-26T10:30:00

Comments:
  [2026-02-26] alice: 需要添加密码强度验证
    📍 src/auth/register.ts:45
  [2026-02-26] bob: 建议使用 bcrypt 替代明文存储密码
```

---

## 状态说明

| 状态 | 图标 | 含义 |
|------|------|------|
| `none` | ⚪ | 未请求审批 |
| `pending` | 🟡 | 等待审批中 |
| `approved` | 🟢 | 已批准 |
| `rejected` | 🔴 | 已拒绝 |
| `changes_requested` | 🟠 | 要求修改 |

---

## 审批评论类型

| 类型 | 说明 |
|------|------|
| `comment` | 普通评论 |
| `approval` | 批准评论 |
| `rejection` | 拒绝评论 |
| `change_request` | 修改请求 |

---

## 相关命令

- `/trellis:request-review` - 请求审批
- `/trellis:review` - 执行审批
