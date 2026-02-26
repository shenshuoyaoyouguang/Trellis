/**
 * Conflict resolution module for the update command
 *
 * 处理文件冲突的交互式解决方案，提供多种选项供用户选择：
 * - 覆盖现有文件
 * - 跳过（保留用户版本）
 * - 创建 .new 副本
 * - 批量应用到所有文件
 *
 * @module conflict-resolver
 */

import inquirer from "inquirer";
import type { FileChange, UpdateOptions, ConflictAction } from "./types.js";

/**
 * 用于跟踪批量操作状态的对象
 * 当用户选择"应用到所有"时，后续文件将自动应用相同操作
 */
export interface ApplyToAllState {
  /** 当前应用的批量操作，null 表示未设置 */
  action: ConflictAction | null;
}

/**
 * 交互式冲突解决提示
 *
 * 当检测到文件与模板不同时，提示用户选择处理方式。
 * 支持单文件操作和批量应用到所有文件。
 *
 * @param file - 发生冲突的文件信息
 * @param options - 更新命令的选项
 * @param applyToAll - 批量操作状态对象（会被修改）
 * @returns 用户选择的冲突处理动作
 *
 * @example
 * ```typescript
 * const applyToAll = { action: null };
 * for (const file of changedFiles) {
 *   const action = await promptConflictResolution(file, options, applyToAll);
 *   // 处理动作...
 * }
 * ```
 */
export async function promptConflictResolution(
  file: FileChange,
  options: UpdateOptions,
  applyToAll: ApplyToAllState,
): Promise<ConflictAction> {
  // 如果已设置批量操作，直接使用
  if (applyToAll.action) {
    return applyToAll.action;
  }

  // 检查命令行选项
  if (options.force) {
    return "overwrite";
  }
  if (options.skipAll) {
    return "skip";
  }
  if (options.createNew) {
    return "create-new";
  }

  // 交互式提示
  const { action } = await inquirer.prompt<{ action: string }>([
    {
      type: "list",
      name: "action",
      message: `${file.relativePath} has changes.`,
      choices: [
        {
          name: "[1] Overwrite - Replace with new version",
          value: "overwrite",
        },
        { name: "[2] Skip - Keep your current version", value: "skip" },
        {
          name: "[3] Create copy - Save new version as .new",
          value: "create-new",
        },
        { name: "[a] Apply Overwrite to all", value: "overwrite-all" },
        { name: "[s] Apply Skip to all", value: "skip-all" },
        { name: "[n] Apply Create copy to all", value: "create-new-all" },
      ],
      default: "skip",
    },
  ]);

  // 处理"应用到所有"选项
  if (action === "overwrite-all") {
    applyToAll.action = "overwrite";
    return "overwrite";
  }
  if (action === "skip-all") {
    applyToAll.action = "skip";
    return "skip";
  }
  if (action === "create-new-all") {
    applyToAll.action = "create-new";
    return "create-new";
  }

  return action as ConflictAction;
}

/**
 * 创建初始的批量操作状态
 *
 * @returns 初始状态对象（action 为 null）
 */
export function createApplyToAllState(): ApplyToAllState {
  return { action: null };
}
