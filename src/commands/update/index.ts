/**
 * Update command module - 主入口
 *
 * 该模块提供 Trellis 更新功能的主入口函数。
 * 通过组合多个子模块实现完整的更新流程。
 *
 * 子模块分工:
 * - types.ts - 类型定义
 * - file-utils.ts - 文件操作工具
 * - backup-manager.ts - 备份管理
 * - template-collector.ts - 模板收集
 * - change-analyzer.ts - 变更分析
 * - conflict-resolver.ts - 冲突解决
 * - migration-executor.ts - 迁移执行
 * - version-manager.ts - 版本管理
 *
 * @module commands/update
 * @copyright Copyright (c) 2024 Trellis. All rights reserved.
 */

import fs from "node:fs";
import path from "node:path";
import chalk from "chalk";
import inquirer from "inquirer";

import { DIR_NAMES } from "../../constants/paths.js";
import {
  getMigrationsForVersion,
  getAllMigrations,
  getMigrationMetadata,
} from "../../migrations/index.js";
import { loadHashes, updateHashes } from "../../utils/template-hash.js";
import { compareVersions } from "../../utils/compare-versions.js";
import { PATHS } from "../../constants/paths.js";

// 导入子模块
import type { UpdateOptions } from "./types.js";
import { createFullBackup } from "./backup-manager.js";
import { collectTemplateFiles } from "./template-collector.js";
import { analyzeChanges, printChangeSummary } from "./change-analyzer.js";
import {
  promptConflictResolution,
  createApplyToAllState,
} from "./conflict-resolver.js";
import {
  classifyMigrations,
  printMigrationSummary,
  executeMigrations,
  printMigrationResult,
} from "./migration-executor.js";
import {
  updateVersionFile,
  getInstalledVersion,
  getLatestNpmVersion,
  CLI_VERSION,
  CLI_PACKAGE_NAME,
} from "./version-manager.js";

// 重新导出类型供外部使用
export type { UpdateOptions } from "./types.js";

// =============================================================================
// 主更新函数
// =============================================================================

/**
 * 主更新命令
 *
 * 执行完整的 Trellis 更新流程：
 * 1. 版本检查和比较
 * 2. 迁移分析
 * 3. 变更分析
 * 4. 用户确认
 * 5. 备份创建
 * 6. 迁移执行
 * 7. 文件更新
 * 8. 哈希更新
 * 9. 任务创建（如有破坏性变更）
 *
 * @param options - 更新选项
 */
export async function update(options: UpdateOptions): Promise<void> {
  const cwd = process.cwd();

  // ========================================
  // 1. 检查 Trellis 是否已初始化
  // ========================================
  if (!fs.existsSync(path.join(cwd, DIR_NAMES.WORKFLOW))) {
    console.log(chalk.red("Error: Trellis not initialized in this directory."));
    console.log(chalk.gray("Run 'trellis init' first."));
    return;
  }

  console.log(chalk.cyan("\nTrellis Update"));
  console.log(chalk.cyan("══════════════\n"));

  // ========================================
  // 2. 版本检查
  // ========================================
  const projectVersion = getInstalledVersion(cwd);
  const cliVersion = CLI_VERSION;
  const latestNpmVersion = await getLatestNpmVersion();

  // 版本比较
  const cliVsProject = compareVersions(cliVersion, projectVersion);
  const cliVsNpm = latestNpmVersion
    ? compareVersions(cliVersion, latestNpmVersion)
    : 0;

  // 显示版本信息
  console.log(`Project version: ${chalk.white(projectVersion)}`);
  console.log(`CLI version:     ${chalk.white(cliVersion)}`);
  if (latestNpmVersion) {
    console.log(`Latest on npm:   ${chalk.white(latestNpmVersion)}`);
  } else {
    console.log(chalk.gray("Latest on npm:   (unable to fetch)"));
  }
  console.log("");

  // 检查 CLI 是否过时
  if (cliVsNpm < 0 && latestNpmVersion) {
    console.log(
      chalk.yellow(
        `⚠️  Your CLI (${cliVersion}) is behind npm (${latestNpmVersion}).`,
      ),
    );
    console.log(chalk.yellow(`   Run: npm install -g ${CLI_PACKAGE_NAME}\n`));
  }

  // 检查降级情况
  if (cliVsProject < 0) {
    console.log(
      chalk.red(
        `❌ Cannot update: CLI version (${cliVersion}) < project version (${projectVersion})`,
      ),
    );
    console.log(chalk.red(`   This would DOWNGRADE your project!\n`));

    if (!options.allowDowngrade) {
      console.log(chalk.gray("Solutions:"));
      console.log(
        chalk.gray(`  1. Update your CLI: npm install -g ${CLI_PACKAGE_NAME}`),
      );
      console.log(
        chalk.gray(`  2. Force downgrade: trellis update --allow-downgrade\n`),
      );
      return;
    }

    console.log(
      chalk.yellow(
        "⚠️  --allow-downgrade flag set. Proceeding with downgrade...\n",
      ),
    );
  }

  // ========================================
  // 3. 加载哈希追踪数据
  // ========================================
  const hashes = loadHashes(cwd);
  const isFirstHashTracking = Object.keys(hashes).length === 0;

  // 处理未知版本 - 跳过迁移但继续模板更新
  const isUnknownVersion = projectVersion === "unknown";
  if (isUnknownVersion) {
    console.log(
      chalk.yellow("⚠️  No version file found. Skipping migrations."),
    );
    console.log(chalk.gray("   Template updates will still be applied."));
    console.log(
      chalk.gray(
        "   If your project used old file paths, you may need to rename them manually.\n",
      ),
    );
  }

  // ========================================
  // 4. 收集模板文件
  // ========================================
  const templates = collectTemplateFiles(cwd);

  // ========================================
  // 5. 检查待处理迁移
  // ========================================
  let pendingMigrations = isUnknownVersion
    ? []
    : getMigrationsForVersion(projectVersion, cliVersion);

  // 检查孤立迁移 - 源文件存在但版本显示不应迁移
  const allMigrations = getAllMigrations();
  const orphanedMigrations = allMigrations.filter((item) => {
    if (item.type !== "rename" && item.type !== "rename-dir") return false;
    if (!item.from || !item.to) return false;

    const oldPath = path.join(cwd, item.from);
    const newPath = path.join(cwd, item.to);

    const sourceExists = fs.existsSync(oldPath);
    const targetExists = fs.existsSync(newPath);
    const alreadyPending = pendingMigrations.some(
      (m) => m.from === item.from && m.to === item.to,
    );

    return sourceExists && !targetExists && !alreadyPending;
  });

  if (orphanedMigrations.length > 0) {
    console.log(
      chalk.yellow("⚠️  Detected incomplete migrations from previous updates:"),
    );
    for (const item of orphanedMigrations) {
      console.log(chalk.yellow(`    ${item.from} → ${item.to}`));
    }
    console.log("");
    pendingMigrations = [...pendingMigrations, ...orphanedMigrations];
  }

  const hasMigrations = pendingMigrations.length > 0;

  // ========================================
  // 6. 迁移分类和分析
  // ========================================
  let classifiedMigrations = null;

  if (hasMigrations) {
    console.log(chalk.cyan("Analyzing migrations...\n"));

    classifiedMigrations = classifyMigrations(
      pendingMigrations,
      cwd,
      hashes,
      templates,
    );

    printMigrationSummary(classifiedMigrations);

    // 显示 --migrate 提示
    if (!options.migrate) {
      const autoCount = classifiedMigrations.auto.length;
      const confirmCount = classifiedMigrations.confirm.length;

      if (autoCount > 0 || confirmCount > 0) {
        console.log(
          chalk.gray(
            `Tip: Use --migrate to apply migrations (prompts for modified files).`,
          ),
        );
        if (confirmCount > 0) {
          console.log(
            chalk.gray(
              `     Use --migrate -f to force all, or --migrate -s to skip modified.\n`,
            ),
          );
        } else {
          console.log("");
        }
      }
    }
  }

  // ========================================
  // 7. 变更分析
  // ========================================
  const changes = analyzeChanges(cwd, hashes, templates);
  printChangeSummary(changes);

  // 首次哈希追踪提示
  if (isFirstHashTracking && changes.changedFiles.length > 0) {
    console.log(chalk.cyan("ℹ️  First update with hash tracking enabled."));
    console.log(
      chalk.gray(
        "   Changed files shown above may not be actual user modifications.",
      ),
    );
    console.log(
      chalk.gray(
        "   After this update, hash tracking will accurately detect changes.\n",
      ),
    );
  }

  // ========================================
  // 8. 检查是否有操作需要执行
  // ========================================
  const isUpgrade = cliVsProject > 0;
  const isDowngrade = cliVsProject < 0;
  const isSameVersion = cliVsProject === 0;

  const hasPendingMigrations =
    options.migrate &&
    classifiedMigrations &&
    (classifiedMigrations.auto.length > 0 ||
      classifiedMigrations.confirm.length > 0);

  if (
    changes.newFiles.length === 0 &&
    changes.autoUpdateFiles.length === 0 &&
    changes.changedFiles.length === 0 &&
    !hasPendingMigrations
  ) {
    if (isSameVersion) {
      console.log(chalk.green("✓ Already up to date!"));
    } else if (isUpgrade) {
      console.log(
        chalk.green(
          `✓ No file changes needed for ${projectVersion} → ${cliVersion}`,
        ),
      );
    }
    return;
  }

  // ========================================
  // 9. 显示操作类型
  // ========================================
  if (isUpgrade) {
    console.log(
      chalk.green(`This will UPGRADE: ${projectVersion} → ${cliVersion}\n`),
    );
  } else if (isDowngrade) {
    console.log(
      chalk.red(`⚠️  This will DOWNGRADE: ${projectVersion} → ${cliVersion}\n`),
    );
  }

  // ========================================
  // 10. 破坏性变更警告
  // ========================================
  if (cliVsProject > 0 && projectVersion !== "unknown") {
    const preConfirmMetadata = getMigrationMetadata(projectVersion, cliVersion);
    if (preConfirmMetadata.breaking) {
      console.log(chalk.cyan("═".repeat(60)));
      console.log(
        chalk.bgRed.white.bold(" ⚠️  BREAKING CHANGES ") +
          chalk.red.bold(" Review the changes above carefully!"),
      );
      if (preConfirmMetadata.changelog.length > 0) {
        console.log("");
        console.log(chalk.white(preConfirmMetadata.changelog[0]));
      }
      if (preConfirmMetadata.recommendMigrate && !options.migrate) {
        console.log("");
        console.log(
          chalk.bgGreen.black.bold(" 💡 RECOMMENDED ") +
            chalk.green.bold(" Run with --migrate to complete the migration"),
        );
      }
      console.log(chalk.cyan("═".repeat(60)));
      console.log("");
    }
  }

  // ========================================
  // 11. Dry run 模式
  // ========================================
  if (options.dryRun) {
    console.log(chalk.gray("[Dry run] No changes made."));
    return;
  }

  // ========================================
  // 12. 用户确认
  // ========================================
  const { proceed } = await inquirer.prompt<{ proceed: boolean }>([
    {
      type: "confirm",
      name: "proceed",
      message: "Proceed?",
      default: true,
    },
  ]);

  if (!proceed) {
    console.log(chalk.yellow("Update cancelled."));
    return;
  }

  // ========================================
  // 13. 创建完整备份
  // ========================================
  const backupDir = createFullBackup(cwd);

  if (backupDir) {
    console.log(
      chalk.gray(`\nBackup created: ${path.relative(cwd, backupDir)}/`),
    );
  }

  // ========================================
  // 14. 执行迁移
  // ========================================
  if (options.migrate && classifiedMigrations) {
    const migrationResult = await executeMigrations(classifiedMigrations, cwd, {
      force: options.force,
      skipAll: options.skipAll,
    });
    printMigrationResult(migrationResult);

    // 硬编码: 重命名 traces-*.md 为 journal-*.md
    // 原因: 迁移系统只支持固定路径重命名，不支持模式匹配
    const workspaceDir = path.join(cwd, PATHS.WORKSPACE);
    if (fs.existsSync(workspaceDir)) {
      let journalRenamed = 0;
      const devDirs = fs.readdirSync(workspaceDir);
      for (const dev of devDirs) {
        const devPath = path.join(workspaceDir, dev);
        if (!fs.statSync(devPath).isDirectory()) continue;

        const files = fs.readdirSync(devPath);
        for (const file of files) {
          if (file.startsWith("traces-") && file.endsWith(".md")) {
            const oldPath = path.join(devPath, file);
            const newFile = file.replace("traces-", "journal-");
            const newPath = path.join(devPath, newFile);
            fs.renameSync(oldPath, newPath);
            journalRenamed++;
          }
        }
      }
      if (journalRenamed > 0) {
        console.log(
          chalk.cyan(`Renamed ${journalRenamed} traces file(s) to journal`),
        );
      }
    }
  }

  // ========================================
  // 15. 执行文件更新
  // ========================================
  let added = 0;
  let autoUpdated = 0;
  let updated = 0;
  let skipped = 0;
  let createdNew = 0;

  // 添加新文件
  if (changes.newFiles.length > 0) {
    console.log(chalk.blue("\nAdding new files..."));
    for (const file of changes.newFiles) {
      const dir = path.dirname(file.path);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(file.path, file.newContent);

      // 设置脚本可执行权限
      if (
        file.relativePath.endsWith(".sh") ||
        file.relativePath.endsWith(".py")
      ) {
        fs.chmodSync(file.path, "755");
      }

      console.log(chalk.green(`  + ${file.relativePath}`));
      added++;
    }
  }

  // 自动更新文件（模板已更新，用户未修改）
  if (changes.autoUpdateFiles.length > 0) {
    console.log(chalk.blue("\nAuto-updating template files..."));
    for (const file of changes.autoUpdateFiles) {
      fs.writeFileSync(file.path, file.newContent);

      if (
        file.relativePath.endsWith(".sh") ||
        file.relativePath.endsWith(".py")
      ) {
        fs.chmodSync(file.path, "755");
      }

      console.log(chalk.cyan(`  ↑ ${file.relativePath}`));
      autoUpdated++;
    }
  }

  // 处理冲突文件
  if (changes.changedFiles.length > 0) {
    console.log(chalk.blue("\n--- Resolving conflicts ---\n"));

    const applyToAll = createApplyToAllState();

    for (const file of changes.changedFiles) {
      const action = await promptConflictResolution(file, options, applyToAll);

      if (action === "overwrite") {
        fs.writeFileSync(file.path, file.newContent);
        if (
          file.relativePath.endsWith(".sh") ||
          file.relativePath.endsWith(".py")
        ) {
          fs.chmodSync(file.path, "755");
        }
        console.log(chalk.yellow(`  ✓ Overwritten: ${file.relativePath}`));
        updated++;
      } else if (action === "create-new") {
        const newPath = file.path + ".new";
        fs.writeFileSync(newPath, file.newContent);
        console.log(chalk.blue(`  ✓ Created: ${file.relativePath}.new`));
        createdNew++;
      } else {
        console.log(chalk.gray(`  ○ Skipped: ${file.relativePath}`));
        skipped++;
      }
    }
  }

  // ========================================
  // 16. 更新版本文件
  // ========================================
  updateVersionFile(cwd);

  // ========================================
  // 17. 更新模板哈希
  // ========================================
  const filesToHash = new Map<string, string>();
  for (const file of changes.newFiles) {
    filesToHash.set(file.relativePath, file.newContent);
  }
  for (const file of changes.autoUpdateFiles) {
    filesToHash.set(file.relativePath, file.newContent);
  }
  for (const file of changes.changedFiles) {
    const fullPath = path.join(cwd, file.relativePath);
    if (fs.existsSync(fullPath)) {
      const content = fs.readFileSync(fullPath, "utf-8");
      if (content === file.newContent) {
        filesToHash.set(file.relativePath, file.newContent);
      }
    }
  }
  if (filesToHash.size > 0) {
    updateHashes(cwd, filesToHash);
  }

  // ========================================
  // 18. 打印摘要
  // ========================================
  console.log(chalk.cyan("\n--- Summary ---\n"));
  if (added > 0) {
    console.log(`  Added: ${added} file(s)`);
  }
  if (autoUpdated > 0) {
    console.log(`  Auto-updated: ${autoUpdated} file(s)`);
  }
  if (updated > 0) {
    console.log(`  Updated: ${updated} file(s)`);
  }
  if (skipped > 0) {
    console.log(`  Skipped: ${skipped} file(s)`);
  }
  if (createdNew > 0) {
    console.log(`  Created .new copies: ${createdNew} file(s)`);
  }
  if (backupDir) {
    console.log(`  Backup: ${path.relative(cwd, backupDir)}/`);
  }

  const actionWord = isDowngrade ? "Downgrade" : "Update";
  console.log(
    chalk.green(
      `\n✅ ${actionWord} complete! (${projectVersion} → ${cliVersion})`,
    ),
  );

  if (createdNew > 0) {
    console.log(
      chalk.gray(
        "\nTip: Review .new files and merge changes manually if needed.",
      ),
    );
  }

  // ========================================
  // 19. 创建迁移任务（如有破坏性变更）
  // ========================================
  if (cliVsProject > 0 && projectVersion !== "unknown") {
    const metadata = getMigrationMetadata(projectVersion, cliVersion);

    if (metadata.breaking && metadata.migrationGuides.length > 0) {
      const today = new Date();
      const monthDay = `${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
      const taskSlug = `migrate-to-${cliVersion}`;
      const taskDirName = `${monthDay}-${taskSlug}`;
      const tasksDir = path.join(cwd, DIR_NAMES.WORKFLOW, DIR_NAMES.TASKS);
      const taskDir = path.join(tasksDir, taskDirName);

      if (!fs.existsSync(taskDir)) {
        fs.mkdirSync(taskDir, { recursive: true });

        // 获取当前开发者
        const developerFile = path.join(cwd, DIR_NAMES.WORKFLOW, ".developer");
        let currentDeveloper = "unknown";
        if (fs.existsSync(developerFile)) {
          currentDeveloper = fs.readFileSync(developerFile, "utf-8").trim();
        }

        // 构建 task.json
        const taskTitle = `Migrate to v${cliVersion}`;
        const todayStr = today.toISOString().split("T")[0];
        const taskJson = {
          title: taskTitle,
          description: `Breaking change migration from v${projectVersion} to v${cliVersion}`,
          status: "planning",
          dev_type: null,
          scope: "migration",
          priority: "P1",
          creator: "trellis-update",
          assignee: currentDeveloper,
          createdAt: todayStr,
          completedAt: null,
          branch: null,
          base_branch: null,
          worktree_path: null,
          current_phase: 0,
          next_action: [
            { phase: 1, action: "review-guide" },
            { phase: 2, action: "update-files" },
            { phase: 3, action: "run-migrate" },
            { phase: 4, action: "test" },
          ],
          commit: null,
          pr_url: null,
          subtasks: [],
        };

        fs.writeFileSync(
          path.join(taskDir, "task.json"),
          JSON.stringify(taskJson, null, 2),
        );

        // 构建 PRD 内容
        let prdContent = `# Migration Task: Upgrade to v${cliVersion}\n\n`;
        prdContent += `**Created**: ${todayStr}\n`;
        prdContent += `**From Version**: ${projectVersion}\n`;
        prdContent += `**To Version**: ${cliVersion}\n`;
        prdContent += `**Assignee**: ${currentDeveloper}\n\n`;
        prdContent += `## Status\n\n- [ ] Review migration guide\n- [ ] Update custom files\n- [ ] Run \`trellis update --migrate\`\n- [ ] Test workflows\n\n`;

        for (const {
          version,
          guide,
          aiInstructions,
        } of metadata.migrationGuides) {
          prdContent += `---\n\n## v${version} Migration Guide\n\n`;
          prdContent += guide;
          prdContent += "\n\n";

          if (aiInstructions) {
            prdContent += `### AI Assistant Instructions\n\n`;
            prdContent += `When helping with this migration:\n\n`;
            prdContent += aiInstructions;
            prdContent += "\n\n";
          }
        }

        fs.writeFileSync(path.join(taskDir, "prd.md"), prdContent);

        console.log("");
        console.log(chalk.bgCyan.black.bold(" 📋 MIGRATION TASK CREATED "));
        console.log(
          chalk.cyan(
            `A task has been created to help you complete the migration:`,
          ),
        );
        console.log(
          chalk.white(
            `   ${DIR_NAMES.WORKFLOW}/${DIR_NAMES.TASKS}/${taskDirName}/`,
          ),
        );
        console.log("");
        console.log(
          chalk.gray(
            "Use AI to help: Ask Claude/Cursor to read the task and fix your custom files.",
          ),
        );
      }
    }
  }

  // ========================================
  // 20. 显示最终破坏性变更警告
  // ========================================
  if (cliVsProject > 0 && projectVersion !== "unknown") {
    const finalMetadata = getMigrationMetadata(projectVersion, cliVersion);

    if (finalMetadata.breaking || finalMetadata.changelog.length > 0) {
      console.log("");
      console.log(chalk.cyan("═".repeat(60)));

      if (finalMetadata.breaking) {
        console.log(
          chalk.bgRed.white.bold(" ⚠️  BREAKING CHANGES ") +
            chalk.red.bold(" This update contains breaking changes!"),
        );
        console.log("");
      }

      if (finalMetadata.changelog.length > 0) {
        console.log(chalk.cyan.bold("📋 What's Changed:"));
        for (const entry of finalMetadata.changelog) {
          console.log(chalk.white(`   ${entry}`));
        }
        console.log("");
      }

      if (finalMetadata.recommendMigrate && !options.migrate) {
        console.log(
          chalk.bgGreen.black.bold(" 💡 RECOMMENDED ") +
            chalk.green.bold(" Run with --migrate to complete the migration"),
        );
        console.log(
          chalk.gray("   This will remove legacy files and apply all changes."),
        );
        console.log("");
      }

      console.log(chalk.cyan("═".repeat(60)));
    }
  }
}
