/**
 * Backup Manager - 备份管理模块
 *
 * 负责创建和管理更新前的文件备份。
 * 所有备份操作都旨在保护用户数据，防止更新过程中数据丢失。
 *
 * 主要功能：
 * - 创建时间戳命名的备份目录
 * - 备份所有受管目录的文件
 * - 排除用户数据目录（workspace、tasks等）
 */

import fs from "node:fs";
import path from "node:path";

import { DIR_NAMES } from "../../constants/paths.js";
import { ALL_MANAGED_DIRS } from "../../configurators/index.js";
import { collectAllFiles } from "./file-utils.js";

// =============================================================================
// 常量定义
// =============================================================================

/**
 * 需要备份的目录列表
 *
 * 派生自平台注册表，包含所有受管目录。
 * 包括 .trellis 目录和所有平台配置目录。
 */
export const BACKUP_DIRS = ALL_MANAGED_DIRS;

/**
 * 备份排除模式
 *
 * 这些路径模式匹配的文件将不会包含在备份中。
 * 主要排除用户数据和临时文件，避免备份膨胀。
 */
export const BACKUP_EXCLUDE_PATTERNS = [
  ".backup-", // 之前的备份目录
  "/workspace/", // 开发者工作区（用户数据）
  "/tasks/", // 任务数据（用户数据）
  "/backlog/", // 待办事项数据（用户数据）
  "/agent-traces/", // 代理追踪数据（用户数据，旧名称）
];

// =============================================================================
// 工具函数
// =============================================================================

/**
 * 检查路径是否应该从备份中排除
 *
 * @param relativePath - 相对于项目根目录的路径
 * @returns 如果路径匹配排除模式则返回 true
 *
 * @example
 * shouldExcludeFromBackup(".trellis/workspace/task.md") // true
 * shouldExcludeFromBackup(".trellis/scripts/init.py") // false
 */
export function shouldExcludeFromBackup(relativePath: string): boolean {
  for (const pattern of BACKUP_EXCLUDE_PATTERNS) {
    if (relativePath.includes(pattern)) {
      return true;
    }
  }
  return false;
}

/**
 * 创建带时间戳的备份目录路径
 *
 * 路径格式: {cwd}/.trellis/.backup-{timestamp}
 * 时间戳格式: YYYY-MM-DDTHH-MM-SS
 *
 * @param cwd - 项目根目录
 * @returns 备份目录的完整路径
 *
 * @example
 * createBackupDirPath("/project") // "/project/.trellis/.backup-2024-01-15T10-30-00"
 */
export function createBackupDirPath(cwd: string): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return path.join(cwd, DIR_NAMES.WORKFLOW, `.backup-${timestamp}`);
}

/**
 * 备份单个文件到备份目录
 *
 * 将源文件复制到备份目录中，保持原有目录结构。
 * 如果源文件不存在，则不执行任何操作。
 *
 * @param cwd - 项目根目录
 * @param backupDir - 备份目录路径
 * @param relativePath - 相对于项目根目录的文件路径
 *
 * @example
 * backupFile("/project", "/project/.trellis/.backup-xxx", ".trellis/scripts/init.py")
 * // 将 init.py 复制到备份目录
 */
export function backupFile(
  cwd: string,
  backupDir: string,
  relativePath: string,
): void {
  const srcPath = path.join(cwd, relativePath);
  if (!fs.existsSync(srcPath)) return;

  const backupPath = path.join(backupDir, relativePath);
  fs.mkdirSync(path.dirname(backupPath), { recursive: true });
  fs.copyFileSync(srcPath, backupPath);
}

/**
 * 创建所有受管目录的完整备份快照
 *
 * 遍历所有受管目录（BACKUP_DIRS），将文件复制到时间戳备份目录。
 * 排除用户数据目录（workspace、tasks、backlog等）。
 *
 * 备份范围：
 * - .trellis/ 目录（排除用户数据）
 * - 所有平台配置目录（.claude、.cursor等）
 *
 * @param cwd - 项目根目录
 * @returns 备份目录路径，如果没有文件需要备份则返回 null
 *
 * @example
 * const backupDir = createFullBackup("/project")
 * if (backupDir) {
 *   console.log(`备份已创建: ${backupDir}`)
 * }
 */
export function createFullBackup(cwd: string): string | null {
  const backupDir = createBackupDirPath(cwd);
  let hasFiles = false;

  for (const dir of BACKUP_DIRS) {
    const dirPath = path.join(cwd, dir);
    if (!fs.existsSync(dirPath)) continue;

    const files = collectAllFiles(dirPath);
    for (const fullPath of files) {
      const relativePath = path.relative(cwd, fullPath);

      // 跳过排除的路径
      if (shouldExcludeFromBackup(relativePath)) continue;

      // 创建备份
      if (!hasFiles) {
        fs.mkdirSync(backupDir, { recursive: true });
        hasFiles = true;
      }
      backupFile(cwd, backupDir, relativePath);
    }
  }

  return hasFiles ? backupDir : null;
}
