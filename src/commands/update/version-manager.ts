/**
 * 版本管理模块
 *
 * 提供版本文件的读取、更新和 npm 注册表查询功能。
 * 用于跟踪已安装版本和检查可用更新。
 *
 * @module version-manager
 */

import fs from "node:fs";
import path from "node:path";

import { DIR_NAMES } from "../../constants/paths.js";
import { VERSION, PACKAGE_NAME } from "../../constants/version.js";

// =============================================================================
// 版本文件操作
// =============================================================================

/**
 * 更新版本文件
 *
 * 将当前 CLI 版本写入项目的版本文件。
 * 版本文件位于 .trellis/.version
 *
 * @param cwd - 项目根目录
 *
 * @example
 * ```ts
 * updateVersionFile('/project');
 * // 将 CLI 版本写入 /project/.trellis/.version
 * ```
 */
export function updateVersionFile(cwd: string): void {
  const versionPath = path.join(cwd, DIR_NAMES.WORKFLOW, ".version");
  fs.writeFileSync(versionPath, VERSION);
}

/**
 * 获取已安装版本
 *
 * 读取项目的版本文件，返回当前安装的版本号。
 * 如果版本文件不存在，返回 "unknown"。
 *
 * @param cwd - 项目根目录
 * @returns 版本字符串，如 "1.0.0" 或 "unknown"
 *
 * @example
 * ```ts
 * const version = getInstalledVersion('/project');
 * console.log(`Installed: ${version}`);
 * ```
 */
export function getInstalledVersion(cwd: string): string {
  const versionPath = path.join(cwd, DIR_NAMES.WORKFLOW, ".version");
  if (fs.existsSync(versionPath)) {
    return fs.readFileSync(versionPath, "utf-8").trim();
  }
  return "unknown";
}

// =============================================================================
// NPM 注册表查询
// =============================================================================

/**
 * 从 npm 注册表获取最新版本
 *
 * 异步查询 npmjs.org 获取包的最新发布版本。
 * 用于检查是否有可用更新。
 *
 * @returns 最新版本字符串，查询失败返回 null
 *
 * @example
 * ```ts
 * const latest = await getLatestNpmVersion();
 * if (latest && latest !== currentVersion) {
 *   console.log(`New version available: ${latest}`);
 * }
 * ```
 */
export async function getLatestNpmVersion(): Promise<string | null> {
  try {
    const response = await fetch(
      `https://registry.npmjs.org/${PACKAGE_NAME}/latest`,
    );
    if (!response.ok) {
      return null;
    }
    const data = (await response.json()) as { version?: string };
    return data.version ?? null;
  } catch {
    return null;
  }
}

// =============================================================================
// 版本常量导出
// =============================================================================

/**
 * 当前 CLI 版本
 */
export const CLI_VERSION = VERSION;

/**
 * 包名称
 */
export const CLI_PACKAGE_NAME = PACKAGE_NAME;
