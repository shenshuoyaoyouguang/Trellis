# Review - 审批任务

审批人审查任务并做出决定：批准、拒绝或要求修改。

**时机**: 收到审批请求后

---

## 审批前检查

### 1. 查看任务详情

```bash
# 查看任务状态
python3 ./.trellis/scripts/task.py review-status <task-dir>

# 查看任务配置
cat <task-dir>/task.json

# 查看需求文档
cat <task-dir>/prd.md
```

### 2. 查看代码变更

```bash
# 查看文件变更
git diff --name-only

# 查看具体变更
git diff
```

### 3. 运行验证

```bash
# 代码检查
pnpm lint
pnpm type-check

# 运行测试
pnpm test
```

---

## 审批操作

### 批准任务

```bash
python3 ./.trellis/scripts/task.py review <task-dir> --approve

# 带评论批准
python3 ./.trellis/scripts/task.py review <task-dir> --approve --comment "代码质量良好，功能完整"
```

**效果**:
- `review_status` 设为 `approved`
- `status` 设为 `completed`
- 记录审批人和审批时间

### 拒绝任务

```bash
python3 ./.trellis/scripts/task.py review <task-dir> --reject --comment "不符合需求规范"
```

**效果**:
- `review_status` 设为 `rejected`
- `status` 设为 `rejected`

### 要求修改

```bash
python3 ./.trellis/scripts/task.py review <task-dir> --request-changes --comment "需要添加错误处理"
```

**效果**:
- `review_status` 设为 `changes_requested`
- `status` 设为 `in_progress`
- 开发者需要修改后重新请求审批

---

## 添加审批评论

可以在审批时添加评论，也可以单独添加：

```bash
# 添加评论
python3 ./.trellis/scripts/task.py add-review-comment <task-dir> "建议优化循环逻辑"

# 关联到具体文件
python3 ./.trellis/scripts/task.py add-review-comment <task-dir> "这里有内存泄漏风险" --file src/auth.ts --line 42
```

---

## 审批清单

### 代码质量

- [ ] 代码风格符合规范
- [ ] 无明显的性能问题
- [ ] 无安全漏洞风险
- [ ] 错误处理完善

### 功能完整性

- [ ] 实现了需求中的所有功能
- [ ] 边界情况处理正确
- [ ] 用户交互流畅

### 测试覆盖

- [ ] 单元测试覆盖关键逻辑
- [ ] 集成测试通过
- [ ] 手动测试通过

### 文档完整

- [ ] API 文档已更新
- [ ] 类型定义已更新
- [ ] 规范文档已更新（如有新模式）

---

## 审批决策矩阵

| 代码质量 | 功能完整 | 测试覆盖 | 建议操作 |
|----------|----------|----------|----------|
| ✅ | ✅ | ✅ | 批准 |
| ✅ | ✅ | ⚠️ | 要求修改（补充测试）|
| ✅ | ⚠️ | ✅ | 要求修改 |
| ⚠️ | ✅ | ✅ | 要求修改 |
| ❌ | - | - | 拒绝或要求大幅修改 |

---

## 相关命令

- `/trellis:request-review` - 请求审批
- `/trellis:review-status` - 查看审批状态
