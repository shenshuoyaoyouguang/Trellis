/**
 * 迁移执行模块
 *
 * 提供迁移分类、排序、执行和结果打印功能。
 * 处理文件重命名、删除等迁移操作，支持自动迁移和用户确认模式。
 *
 * @module migration-executor
 */

import fs from "node:fs";
import path from "node:path";
import chalk from "chalk";
import inquirer from "inquirer";

import type {
  MigrationItem,
  ClassifiedMigrations,
  MigrationResult,
  MigrationAction,
  TemplateHashes,
} from "../../types/migration.js";
import {
  loadHashes,
  saveHashes,
  renameHash,
  removeHash,
  isTemplateModified,
} from "../../utils/template-hash.js";
import {
  removeDirectoryRecursive,
  isDirectorySafeToReplace,
  isFileSafeToReplace,
  cleanupEmptyDirs,
} from "./file-utils.js";

// ============================================================================
// 迁移分类
// ============================================================================

/**
 * 根据文件状态和用户修改情况分类迁移
 *
 * 将迁移项分为四类：
 * - auto: 未修改的文件，可以自动迁移
 * - confirm: 用户修改过的文件，需要确认
 * - conflict: 源文件和目标文件都存在，产生冲突
 * - skip: 源文件不存在，无需处理
 *
 * @param migrations - 迁移项列表
 * @param cwd - 项目根目录
 * @param hashes - 存储的模板哈希映射
 * @param templates - 模板内容映射（相对路径 -> 内容）
 * @returns 分类后的迁移结果
 *
 * @example
 * ```ts
 * const classified = classifyMigrations(migrations, cwd, hashes, templates);
 * console.log(`Auto: ${classified.auto.length}, Confirm: ${classified.confirm.length}`);
 * ```
 */
export function classifyMigrations(
  migrations: MigrationItem[],
  cwd: string,
  hashes: TemplateHashes,
  templates: Map<string, string>,
): ClassifiedMigrations {
  const result: ClassifiedMigrations = {
    auto: [],
    confirm: [],
    conflict: [],
    skip: [],
  };

  for (const item of migrations) {
    const oldPath = path.join(cwd, item.from);
    const oldExists = fs.existsSync(oldPath);

    if (!oldExists) {
      // 源文件不存在，无需迁移
      result.skip.push(item);
      continue;
    }

    if (item.type === "rename" && item.to) {
      const newPath = path.join(cwd, item.to);
      const newExists = fs.existsSync(newPath);

      if (newExists) {
        // 源和目标都存在 - 检查目标是否匹配模板（可安全覆盖）
        if (isFileSafeToReplace(cwd, item.to, templates)) {
          // 目标文件只是模板内容 - 可安全删除后重命名
          result.auto.push(item);
        } else {
          // 目标文件有用户内容 - 冲突
          result.conflict.push(item);
        }
      } else if (isTemplateModified(cwd, item.from, hashes)) {
        // 用户修改过文件 - 需要确认
        result.confirm.push(item);
      } else {
        // 未修改的模板 - 可自动迁移
        result.auto.push(item);
      }
    } else if (item.type === "rename-dir" && item.to) {
      const newPath = path.join(cwd, item.to);
      const newExists = fs.existsSync(newPath);

      if (newExists) {
        // 目标存在 - 检查是否只包含未修改的模板文件
        if (isDirectorySafeToReplace(cwd, item.to, hashes, templates)) {
          // 可安全删除目标后重命名
          result.auto.push(item);
        } else {
          // 目标有用户修改 - 冲突
          result.conflict.push(item);
        }
      } else {
        // 目录重命名 - 始终自动执行（包含用户文件）
        result.auto.push(item);
      }
    } else if (item.type === "delete") {
      if (isTemplateModified(cwd, item.from, hashes)) {
        // 用户修改过 - 删除前需要确认
        result.confirm.push(item);
      } else {
        // 未修改 - 可自动删除
        result.auto.push(item);
      }
    }
  }

  return result;
}

// ============================================================================
// 迁移摘要打印
// ============================================================================

/**
 * 打印迁移摘要
 *
 * 按类别显示迁移项：
 * - 绿色：自动迁移项
 * - 黄色：需要确认的项
 * - 红色：冲突项
 * - 灰色：跳过的项
 *
 * @param classified - 分类后的迁移结果
 *
 * @example
 * ```ts
 * printMigrationSummary(classified);
 * // 输出:
 * // ✓ Auto-migrate (unmodified):
 * //   old/path → new/path
 * // ...
 * ```
 */
export function printMigrationSummary(classified: ClassifiedMigrations): void {
  const total =
    classified.auto.length +
    classified.confirm.length +
    classified.conflict.length +
    classified.skip.length;

  if (total === 0) {
    console.log(chalk.gray("  No migrations to apply.\n"));
    return;
  }

  if (classified.auto.length > 0) {
    console.log(chalk.green("  ✓ Auto-migrate (unmodified):"));
    for (const item of classified.auto) {
      if (item.type === "rename") {
        console.log(chalk.green(`    ${item.from} → ${item.to}`));
      } else if (item.type === "rename-dir") {
        console.log(chalk.green(`    [dir] ${item.from}/ → ${item.to}/`));
      } else {
        console.log(chalk.green(`    ✕ ${item.from}`));
      }
    }
    console.log("");
  }

  if (classified.confirm.length > 0) {
    console.log(chalk.yellow("  ⚠ Requires confirmation (modified by user):"));
    for (const item of classified.confirm) {
      if (item.type === "rename") {
        console.log(chalk.yellow(`    ${item.from} → ${item.to}`));
      } else {
        console.log(chalk.yellow(`    ✕ ${item.from}`));
      }
    }
    console.log("");
  }

  if (classified.conflict.length > 0) {
    console.log(chalk.red("  ⊘ Conflict (both old and new exist):"));
    for (const item of classified.conflict) {
      if (item.type === "rename-dir") {
        console.log(chalk.red(`    [dir] ${item.from}/ ↔ ${item.to}/`));
      } else {
        console.log(chalk.red(`    ${item.from} ↔ ${item.to}`));
      }
    }
    console.log(
      chalk.gray(
        "    → Resolve manually: merge or delete one, then re-run update",
      ),
    );
    console.log("");
  }

  if (classified.skip.length > 0) {
    console.log(chalk.gray("  ○ Skipping (old file not found):"));
    for (const item of classified.skip.slice(0, 3)) {
      console.log(chalk.gray(`    ${item.from}`));
    }
    if (classified.skip.length > 3) {
      console.log(chalk.gray(`    ... and ${classified.skip.length - 3} more`));
    }
    console.log("");
  }
}

// ============================================================================
// 用户交互
// ============================================================================

/**
 * 提示用户选择迁移动作
 *
 * 对于用户修改过的文件，提供三个选项：
 * - 重命名/删除（强制执行）
 * - 备份后执行
 * - 跳过此迁移
 *
 * @param item - 迁移项
 * @returns 用户选择的动作
 *
 * @example
 * ```ts
 * const action = await promptMigrationAction(item);
 * if (action === 'skip') {
 *   console.log('User chose to skip');
 * }
 * ```
 */
export async function promptMigrationAction(
  item: MigrationItem,
): Promise<MigrationAction> {
  const action =
    item.type === "rename"
      ? `${item.from} → ${item.to}`
      : `Delete ${item.from}`;

  const { choice } = await inquirer.prompt<{ choice: MigrationAction }>([
    {
      type: "list",
      name: "choice",
      message: `${action}\nThis file has been modified. What would you like to do?`,
      choices: [
        {
          name:
            item.type === "rename" ? "[r] Rename anyway" : "[d] Delete anyway",
          value: "rename" as MigrationAction,
        },
        {
          name: "[b] Backup original, then proceed",
          value: "backup-rename" as MigrationAction,
        },
        {
          name: "[s] Skip this migration",
          value: "skip" as MigrationAction,
        },
      ],
      default: "skip",
    },
  ]);

  return choice;
}

// ============================================================================
// 迁移排序
// ============================================================================

/**
 * 为安全执行顺序排序迁移项
 *
 * 排序规则：
 * - 路径更深的 rename-dir 优先（处理嵌套目录）
 * - rename-dir 在 rename/delete 之前（目录优先）
 *
 * @param migrations - 迁移项列表
 * @returns 排序后的迁移项列表
 *
 * @example
 * ```ts
 * const sorted = sortMigrationsForExecution(migrations);
 * // 先处理深层目录，再处理文件
 * ```
 */
export function sortMigrationsForExecution(
  migrations: MigrationItem[],
): MigrationItem[] {
  return [...migrations].sort((a, b) => {
    // rename-dir 按路径深度排序（更深的优先）
    if (a.type === "rename-dir" && b.type === "rename-dir") {
      const aDepth = a.from.split("/").length;
      const bDepth = b.from.split("/").length;
      return bDepth - aDepth; // 更深的路径优先
    }
    // rename-dir 在 rename/delete 之前（目录优先）
    if (a.type === "rename-dir" && b.type !== "rename-dir") return -1;
    if (a.type !== "rename-dir" && b.type === "rename-dir") return 1;
    return 0;
  });
}

// ============================================================================
// 迁移执行
// ============================================================================

/**
 * 执行分类后的迁移
 *
 * 执行流程：
 * 1. 自动迁移（未修改的文件）
 * 2. 需确认的迁移（已修改的文件）
 * 3. 统计跳过和冲突数量
 *
 * @param classified - 分类后的迁移结果
 * @param cwd - 项目根目录
 * @param options - 执行选项
 * @param options.force - 强制迁移已修改文件，不询问
 * @param options.skipAll - 跳过所有已修改文件
 * @returns 迁移执行结果
 *
 * @example
 * ```ts
 * const result = await executeMigrations(classified, cwd, { force: false });
 * console.log(`Renamed: ${result.renamed}, Deleted: ${result.deleted}`);
 * ```
 */
export async function executeMigrations(
  classified: ClassifiedMigrations,
  cwd: string,
  options: { force?: boolean; skipAll?: boolean },
): Promise<MigrationResult> {
  const result: MigrationResult = {
    renamed: 0,
    deleted: 0,
    skipped: 0,
    conflicts: classified.conflict.length,
  };

  // 按安全执行顺序排序迁移
  const sortedAuto = sortMigrationsForExecution(classified.auto);

  // 1. 执行自动迁移（未修改的文件和目录）
  for (const item of sortedAuto) {
    if (item.type === "rename" && item.to) {
      const oldPath = path.join(cwd, item.from);
      const newPath = path.join(cwd, item.to);

      // 确保目标目录存在
      fs.mkdirSync(path.dirname(newPath), { recursive: true });
      fs.renameSync(oldPath, newPath);

      // 更新哈希跟踪
      renameHash(cwd, item.from, item.to);

      // 如果是脚本文件，设置为可执行
      if (item.to.endsWith(".sh") || item.to.endsWith(".py")) {
        fs.chmodSync(newPath, "755");
      }

      // 清理空的源目录
      cleanupEmptyDirs(cwd, path.dirname(item.from));

      result.renamed++;
    } else if (item.type === "rename-dir" && item.to) {
      const oldPath = path.join(cwd, item.from);
      const newPath = path.join(cwd, item.to);

      // 如果目标存在（已检查可安全替换）
      // 先删除后再重命名
      if (fs.existsSync(newPath)) {
        removeDirectoryRecursive(newPath);
      }

      // 确保父目录存在
      fs.mkdirSync(path.dirname(newPath), { recursive: true });

      // 重命名整个目录（包含所有用户文件）
      fs.renameSync(oldPath, newPath);

      // 批量更新目录内所有文件的哈希跟踪
      const hashes = loadHashes(cwd);
      const oldPrefix = item.from.endsWith("/") ? item.from : item.from + "/";
      const newPrefix = item.to.endsWith("/") ? item.to : item.to + "/";

      const updatedHashes: TemplateHashes = {};
      for (const [hashPath, hashValue] of Object.entries(hashes)) {
        if (hashPath.startsWith(oldPrefix)) {
          // 重命名路径：旧前缀 -> 新前缀
          const newHashPath = newPrefix + hashPath.slice(oldPrefix.length);
          updatedHashes[newHashPath] = hashValue;
        } else if (hashPath.startsWith(newPrefix)) {
          // 跳过已删除目标目录中的旧哈希
          // （它们将被重命名的源文件替换）
          continue;
        } else {
          // 保持不变
          updatedHashes[hashPath] = hashValue;
        }
      }
      saveHashes(cwd, updatedHashes);

      result.renamed++;
    } else if (item.type === "delete") {
      const filePath = path.join(cwd, item.from);
      fs.unlinkSync(filePath);

      // 从哈希跟踪中移除
      removeHash(cwd, item.from);

      // 清理空目录
      cleanupEmptyDirs(cwd, path.dirname(item.from));

      result.deleted++;
    }
  }

  // 2. 处理需要确认的迁移（已修改的文件）
  // 注意：所有文件在执行前已通过 createMigrationBackup 备份
  for (const item of classified.confirm) {
    let action: MigrationAction;

    if (options.force) {
      // 强制模式：直接执行（已备份）
      action = "rename";
    } else if (options.skipAll) {
      // 跳过模式：跳过所有已修改文件
      action = "skip";
    } else {
      // 默认：交互式提示
      action = await promptMigrationAction(item);
    }

    if (action === "skip") {
      result.skipped++;
      continue;
    }

    // 对于 backup-rename，直接执行（备份已完成）
    // 执行重命名或删除
    if (item.type === "rename" && item.to) {
      const oldPath = path.join(cwd, item.from);
      const newPath = path.join(cwd, item.to);

      fs.mkdirSync(path.dirname(newPath), { recursive: true });
      fs.renameSync(oldPath, newPath);
      renameHash(cwd, item.from, item.to);

      if (item.to.endsWith(".sh") || item.to.endsWith(".py")) {
        fs.chmodSync(newPath, "755");
      }

      // 清理空的源目录
      cleanupEmptyDirs(cwd, path.dirname(item.from));

      result.renamed++;
    } else if (item.type === "delete") {
      const filePath = path.join(cwd, item.from);
      fs.unlinkSync(filePath);
      removeHash(cwd, item.from);

      // 清理空目录
      cleanupEmptyDirs(cwd, path.dirname(item.from));

      result.deleted++;
    }
  }

  // 3. 跳过计数已跟踪（源文件不存在）
  result.skipped += classified.skip.length;

  return result;
}

// ============================================================================
// 结果打印
// ============================================================================

/**
 * 打印迁移结果摘要
 *
 * 显示重命名、删除、跳过和冲突的数量统计。
 *
 * @param result - 迁移执行结果
 *
 * @example
 * ```ts
 * printMigrationResult({ renamed: 3, deleted: 1, skipped: 2, conflicts: 0 });
 * // 输出: Migration complete: 3 renamed, 1 deleted, 2 skipped
 * ```
 */
export function printMigrationResult(result: MigrationResult): void {
  const parts: string[] = [];

  if (result.renamed > 0) {
    parts.push(`${result.renamed} renamed`);
  }
  if (result.deleted > 0) {
    parts.push(`${result.deleted} deleted`);
  }
  if (result.skipped > 0) {
    parts.push(`${result.skipped} skipped`);
  }
  if (result.conflicts > 0) {
    parts.push(
      `${result.conflicts} conflict${result.conflicts > 1 ? "s" : ""}`,
    );
  }

  if (parts.length > 0) {
    console.log(chalk.cyan(`Migration complete: ${parts.join(", ")}`));
  }
}
