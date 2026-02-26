/**
 * 变更分析模块
 *
 * 负责分析文件变更、打印变更摘要等核心功能。
 * 使用哈希追踪来区分：
 * - 用户未修改 + 模板相同 = 跳过
 * - 用户未修改 + 模板更新 = 自动更新
 * - 用户已修改 = 需要确认
 */

import fs from "node:fs";
import path from "node:path";
import chalk from "chalk";

import { DIR_NAMES } from "../../constants/paths.js";
import { computeHash } from "../../utils/template-hash.js";
import type { FileChange, ChangeAnalysis } from "./types.js";

/**
 * 受保护路径列表 - 这些路径永远不会被修改
 * 包含真正的用户数据目录
 *
 * 注意: frontend/backend spec 目录已移除 - 它们应该在缺失时创建，
 * 现有文件通过基于哈希的修改追踪进行保护
 */
export const PROTECTED_PATHS = [
  `${DIR_NAMES.WORKFLOW}/${DIR_NAMES.WORKSPACE}`, // workspace/
  `${DIR_NAMES.WORKFLOW}/${DIR_NAMES.TASKS}`, // tasks/
  `${DIR_NAMES.WORKFLOW}/.developer`,
  `${DIR_NAMES.WORKFLOW}/.current-task`,
];

/**
 * 模板哈希映射类型
 * 键为相对路径，值为内容哈希值
 */
export type TemplateHashes = Record<string, string>;

/**
 * 分析当前文件与模板之间的变更
 *
 * 使用哈希追踪来区分：
 * - 用户未修改 + 模板相同 = unchangedFiles (跳过)
 * - 用户未修改 + 模板更新 = autoUpdateFiles (自动更新)
 * - 用户已修改 = changedFiles (需要确认)
 *
 * @param cwd - 当前工作目录
 * @param hashes - 已存储的模板哈希映射
 * @param templates - 模板文件映射 (相对路径 -> 内容)
 * @returns 变更分析结果
 */
export function analyzeChanges(
  cwd: string,
  hashes: TemplateHashes,
  templates: Map<string, string>,
): ChangeAnalysis {
  const result: ChangeAnalysis = {
    newFiles: [],
    unchangedFiles: [],
    autoUpdateFiles: [],
    changedFiles: [],
    protectedPaths: PROTECTED_PATHS,
  };

  for (const [relativePath, newContent] of templates) {
    const fullPath = path.join(cwd, relativePath);
    const exists = fs.existsSync(fullPath);

    const change: FileChange = {
      path: fullPath,
      relativePath,
      newContent,
      status: "new",
    };

    if (!exists) {
      // 文件不存在 - 标记为新文件
      change.status = "new";
      result.newFiles.push(change);
    } else {
      const existingContent = fs.readFileSync(fullPath, "utf-8");
      if (existingContent === newContent) {
        // 内容与模板相同 - 已是最新
        change.status = "unchanged";
        result.unchangedFiles.push(change);
      } else {
        // 内容不同 - 检查是用户修改还是模板更新
        const storedHash = hashes[relativePath];
        const currentHash = computeHash(existingContent);

        if (storedHash && storedHash === currentHash) {
          // 哈希匹配已存储的哈希 - 用户未修改，模板已更新
          // 可以安全地自动更新
          change.status = "changed";
          result.autoUpdateFiles.push(change);
        } else {
          // 哈希不同（或无存储哈希）- 用户已修改文件
          // 需要确认
          change.status = "changed";
          result.changedFiles.push(change);
        }
      }
    }
  }

  return result;
}

/**
 * 打印变更摘要
 *
 * 以彩色格式输出变更分析结果，包括：
 * - 新文件（绿色）
 * - 自动更新文件（青色）
 * - 未变更文件（灰色）
 * - 需要确认的文件（黄色）
 * - 受保护的用户数据（灰色）
 *
 * @param changes - 变更分析结果
 */
export function printChangeSummary(changes: ChangeAnalysis): void {
  console.log("\nScanning for changes...\n");

  // 打印新文件
  if (changes.newFiles.length > 0) {
    console.log(chalk.green("  New files (will add):"));
    for (const file of changes.newFiles) {
      console.log(chalk.green(`    + ${file.relativePath}`));
    }
    console.log("");
  }

  // 打印自动更新文件（模板已更新，用户未修改）
  if (changes.autoUpdateFiles.length > 0) {
    console.log(chalk.cyan("  Template updated (will auto-update):"));
    for (const file of changes.autoUpdateFiles) {
      console.log(chalk.cyan(`    ↑ ${file.relativePath}`));
    }
    console.log("");
  }

  // 打印未变更文件（最多显示5个）
  if (changes.unchangedFiles.length > 0) {
    console.log(chalk.gray("  Unchanged files (will skip):"));
    for (const file of changes.unchangedFiles.slice(0, 5)) {
      console.log(chalk.gray(`    ○ ${file.relativePath}`));
    }
    if (changes.unchangedFiles.length > 5) {
      console.log(
        chalk.gray(`    ... and ${changes.unchangedFiles.length - 5} more`),
      );
    }
    console.log("");
  }

  // 打印需要用户确认的文件（用户已修改）
  if (changes.changedFiles.length > 0) {
    console.log(chalk.yellow("  Modified by you (need your decision):"));
    for (const file of changes.changedFiles) {
      console.log(chalk.yellow(`    ? ${file.relativePath}`));
    }
    console.log("");
  }

  // 仅显示实际存在的受保护路径
  const existingProtectedPaths = changes.protectedPaths.filter((p) => {
    const fullPath = path.join(process.cwd(), p);
    return fs.existsSync(fullPath);
  });

  if (existingProtectedPaths.length > 0) {
    console.log(chalk.gray("  User data (preserved):"));
    for (const protectedPath of existingProtectedPaths) {
      console.log(chalk.gray(`    ○ ${protectedPath}/`));
    }
    console.log("");
  }
}
