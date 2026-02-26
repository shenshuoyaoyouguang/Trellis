/**
 * 文件操作工具模块
 *
 * 提供安全的文件操作功能，包括递归收集文件、安全替换检查、目录清理等。
 *
 * @module file-utils
 */

import fs from "node:fs";
import path from "node:path";

import { isManagedPath, isManagedRootDir } from "../../configurators/index.js";
import type { TemplateHashes } from "../../types/migration.js";
import { isTemplateModified } from "../../utils/template-hash.js";
import type { FileBackup, BackupOptions } from "./types.js";

/**
 * 默认备份目录名
 */
const DEFAULT_BACKUP_DIR = ".backup";

// ============================================================================
// 文件收集与递归操作
// ============================================================================

/**
 * 递归收集目录下所有文件
 *
 * 遍历指定目录及其子目录，返回所有文件的绝对路径列表。
 * 用于备份、迁移等需要批量处理文件的场景。
 *
 * @param dirPath - 要扫描的目录路径
 * @returns 文件绝对路径数组，目录不存在时返回空数组
 *
 * @example
 * ```ts
 * const files = collectAllFiles('/project/.trellis/scripts');
 * // 返回: ['/project/.trellis/scripts/__init__.py', ...]
 * ```
 */
export function collectAllFiles(dirPath: string): string[] {
  if (!fs.existsSync(dirPath)) return [];

  const files: string[] = [];
  const entries = fs.readdirSync(dirPath, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectAllFiles(fullPath));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }

  return files;
}

/**
 * 递归删除目录
 *
 * 安全地删除整个目录树，包括所有子目录和文件。
 * 如果目录不存在，则静默返回。
 *
 * @param dirPath - 要删除的目录路径
 *
 * @example
 * ```ts
 * removeDirectoryRecursive('/tmp/old-backup');
 * ```
 */
export function removeDirectoryRecursive(dirPath: string): void {
  if (!fs.existsSync(dirPath)) return;
  fs.rmSync(dirPath, { recursive: true, force: true });
}

// ============================================================================
// 安全替换检查
// ============================================================================

/**
 * 检查目录是否可安全替换
 *
 * 判断目录是否仅包含未修改的模板文件，用于决定是否可以安全删除或覆盖。
 * 安全条件（满足任一即可）：
 * - 所有文件都被跟踪且未修改
 * - 所有文件内容与当前模板匹配（即使未跟踪）
 *
 * @param cwd - 项目根目录
 * @param dirRelativePath - 相对于项目根目录的目录路径
 * @param hashes - 存储的模板哈希映射
 * @param templates - 模板内容映射（相对路径 -> 内容）
 * @returns 如果目录可安全替换则返回 true
 *
 * @example
 * ```ts
 * const isSafe = isDirectorySafeToReplace(
 *   cwd,
 *   '.claude/commands',
 *   storedHashes,
 *   templateMap
 * );
 * ```
 */
export function isDirectorySafeToReplace(
  cwd: string,
  dirRelativePath: string,
  hashes: TemplateHashes,
  templates: Map<string, string>,
): boolean {
  const dirFullPath = path.join(cwd, dirRelativePath);
  if (!fs.existsSync(dirFullPath)) return true;

  const files = collectAllFiles(dirFullPath);
  if (files.length === 0) return true; // 空目录是安全的

  for (const fullPath of files) {
    const relativePath = path.relative(cwd, fullPath);
    const storedHash = hashes[relativePath];
    const templateContent = templates.get(relativePath);

    // 检查文件是否匹配模板内容（处理未跟踪的文件）
    if (templateContent) {
      const currentContent = fs.readFileSync(fullPath, "utf-8");
      if (currentContent === templateContent) {
        // 文件匹配模板 - 安全
        continue;
      }
    }

    // 检查文件是否被跟踪且未修改
    if (storedHash && !isTemplateModified(cwd, relativePath, hashes)) {
      // 已跟踪且未修改 - 安全
      continue;
    }

    // 文件是用户创建或修改的 - 不安全
    return false;
  }

  return true;
}

/**
 * 检查文件是否可安全覆盖
 *
 * 判断文件内容是否与模板内容匹配，用于决定是否可以安全覆盖。
 *
 * @param cwd - 项目根目录
 * @param relativePath - 相对于项目根目录的文件路径
 * @param templates - 模板内容映射（相对路径 -> 内容）
 * @returns 如果文件可安全覆盖则返回 true
 *
 * @example
 * ```ts
 * const isSafe = isFileSafeToReplace(
 *   cwd,
 *   '.claude/settings.json',
 *   templateMap
 * );
 * ```
 */
export function isFileSafeToReplace(
  cwd: string,
  relativePath: string,
  templates: Map<string, string>,
): boolean {
  const fullPath = path.join(cwd, relativePath);
  if (!fs.existsSync(fullPath)) return true;

  const templateContent = templates.get(relativePath);
  if (!templateContent) return false; // 不是模板文件

  const currentContent = fs.readFileSync(fullPath, "utf-8");
  return currentContent === templateContent;
}

// ============================================================================
// 空目录清理
// ============================================================================

/**
 * 清理文件迁移后的空目录
 *
 * 递归移除空父目录，直到遇到非空目录或管理根目录。
 * 具有安全保护：不会删除管理路径之外的目录，也不会删除管理根目录本身。
 *
 * @param cwd - 项目根目录
 * @param dirPath - 相对于项目根目录的起始目录路径
 *
 * @example
 * ```ts
 * // 删除文件后清理空目录
 * fs.unlinkSync(someFile);
 * cleanupEmptyDirs(cwd, path.dirname(relativeFilePath));
 * ```
 */
export function cleanupEmptyDirs(cwd: string, dirPath: string): void {
  const fullPath = path.join(cwd, dirPath);

  // 安全保护：不删除管理路径之外的目录
  if (!isManagedPath(dirPath)) {
    return;
  }

  // 安全保护：永远不删除管理根目录本身（如 .claude, .trellis）
  if (isManagedRootDir(dirPath)) {
    return;
  }

  // 检查目录是否存在且为空
  if (!fs.existsSync(fullPath)) return;

  try {
    const stat = fs.statSync(fullPath);
    if (!stat.isDirectory()) return;

    const contents = fs.readdirSync(fullPath);
    if (contents.length === 0) {
      fs.rmdirSync(fullPath);
      // 递归检查父目录（但在根目录处停止）
      const parent = path.dirname(dirPath);
      if (parent !== "." && parent !== dirPath && !isManagedRootDir(parent)) {
        cleanupEmptyDirs(cwd, parent);
      }
    }
  } catch {
    // 忽略错误（权限问题等）
  }
}

// ============================================================================
// 备份操作
// ============================================================================

/**
 * 创建文件备份
 *
 * @param filePath - 要备份的文件路径
 * @param cwd - 项目根目录
 * @param options - 备份选项
 * @returns 备份信息，文件不存在时返回 null
 */
export function createBackup(
  filePath: string,
  cwd: string,
  options: BackupOptions = {},
): FileBackup | null {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupDir = options.backupDir ?? path.join(cwd, DEFAULT_BACKUP_DIR);
  const relativePath = path.relative(cwd, filePath);
  const backupFileName = options.includeTimestamp
    ? `${relativePath.replace(/[\\/]/g, "_")}.${timestamp}`
    : relativePath.replace(/[\\/]/g, "_");
  const backupPath = path.join(backupDir, backupFileName);

  // 确保备份目录存在
  fs.mkdirSync(path.dirname(backupPath), { recursive: true });

  // 复制文件到备份位置
  fs.copyFileSync(filePath, backupPath);

  return {
    originalPath: filePath,
    backupPath,
    timestamp,
  };
}

/**
 * 从备份恢复文件
 *
 * @param backup - 备份信息
 * @returns 恢复成功返回 true
 */
export function restoreFromBackup(backup: FileBackup): boolean {
  try {
    if (!fs.existsSync(backup.backupPath)) {
      return false;
    }
    fs.copyFileSync(backup.backupPath, backup.originalPath);
    return true;
  } catch {
    return false;
  }
}

/**
 * 清理旧备份，仅保留最近的几个
 *
 * @param cwd - 项目根目录
 * @param maxBackups - 每个文件保留的最大备份数
 */
export function cleanupOldBackups(cwd: string, maxBackups = 5): void {
  const backupDir = path.join(cwd, DEFAULT_BACKUP_DIR);

  if (!fs.existsSync(backupDir)) {
    return;
  }

  // 按原始文件分组备份
  const backups = new Map<string, string[]>();

  const files = fs.readdirSync(backupDir, { recursive: true });
  for (const file of files) {
    const filePath = file.toString();
    const fullPath = path.join(backupDir, filePath);

    if (fs.statSync(fullPath).isFile()) {
      // 提取基础名称（不含时间戳）
      const baseName = filePath.replace(/\.\d{4}-\d{2}-\d{2}T.+$/, "");
      const existing = backups.get(baseName);
      if (existing) {
        existing.push(fullPath);
      } else {
        backups.set(baseName, [fullPath]);
      }
    }
  }

  // 移除旧备份
  for (const [, backupPaths] of backups) {
    if (backupPaths.length > maxBackups) {
      // 按修改时间排序（最旧的在前）
      backupPaths.sort((a, b) => {
        const statA = fs.statSync(a);
        const statB = fs.statSync(b);
        return statA.mtimeMs - statB.mtimeMs;
      });

      // 移除最旧的备份
      const toRemove = backupPaths.slice(0, backupPaths.length - maxBackups);
      for (const removePath of toRemove) {
        fs.unlinkSync(removePath);
      }
    }
  }
}

// ============================================================================
// 通用文件操作
// ============================================================================

/**
 * 安全写入文件，自动创建父目录
 *
 * @param filePath - 写入路径
 * @param content - 写入内容
 */
export function safeWriteFile(filePath: string, content: string): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(filePath, content);
}

/**
 * 检查目录是否为空
 *
 * @param dirPath - 目录路径
 * @returns 目录为空或不存在时返回 true
 */
export function isDirectoryEmpty(dirPath: string): boolean {
  if (!fs.existsSync(dirPath)) {
    return true;
  }
  const files = fs.readdirSync(dirPath);
  return files.length === 0;
}

/**
 * 如果目录为空则删除
 *
 * @param dirPath - 目录路径
 * @returns 目录被删除时返回 true
 */
export function removeEmptyDirectory(dirPath: string): boolean {
  if (isDirectoryEmpty(dirPath)) {
    fs.rmdirSync(dirPath);
    return true;
  }
  return false;
}

/**
 * 递归移除空的父目录
 *
 * @param cwd - 项目根目录
 * @param dirPath - 起始目录路径
 */
export function cleanupEmptyParentDirs(cwd: string, dirPath: string): void {
  let currentPath = dirPath;

  while (currentPath !== cwd) {
    if (!removeEmptyDirectory(currentPath)) {
      break;
    }
    currentPath = path.dirname(currentPath);
  }
}
