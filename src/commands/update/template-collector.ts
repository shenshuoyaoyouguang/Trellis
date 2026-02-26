/**
 * @fileoverview 模板收集器模块
 *
 * 负责收集所有需要被 update 命令管理的模板文件。
 * 仅收集已配置平台（已有目录）的模板。
 *
 * @module commands/update/template-collector
 * @copyright Copyright (c) 2024 Trellis. All rights reserved.
 */

import { PATHS, DIR_NAMES } from "../../constants/paths.js";
import {
  getConfiguredPlatforms,
  collectPlatformTemplates,
} from "../../configurators/index.js";

// Import templates for comparison
import {
  // Python scripts - package init
  scriptsInit,
  // Python scripts - common
  commonInit,
  commonPaths,
  commonDeveloper,
  commonGitContext,
  commonWorktree,
  commonTaskQueue,
  commonTaskUtils,
  commonPhase,
  commonRegistry,
  commonCliAdapter,
  // Python scripts - multi_agent
  multiAgentInit,
  multiAgentStart,
  multiAgentCleanup,
  multiAgentStatus,
  multiAgentCreatePr,
  multiAgentPlan,
  // Python scripts - main
  getDeveloperScript,
  initDeveloperScript,
  taskScript,
  getContextScript,
  addSessionScript,
  createBootstrapScript,
  // Configuration
  worktreeYamlTemplate,
  workflowMdTemplate,
  gitignoreTemplate,
} from "../../templates/trellis/index.js";

import {
  guidesIndexContent,
  guidesCrossLayerThinkingGuideContent,
  guidesCodeReuseThinkingGuideContent,
  // Backend structure (multi-doc)
  backendIndexContent,
  backendDirectoryStructureContent,
  backendDatabaseGuidelinesContent,
  backendLoggingGuidelinesContent,
  backendQualityGuidelinesContent,
  backendErrorHandlingContent,
  // Frontend structure (multi-doc)
  frontendIndexContent,
  frontendDirectoryStructureContent,
  frontendTypeSafetyContent,
  frontendHookGuidelinesContent,
  frontendComponentGuidelinesContent,
  frontendQualityGuidelinesContent,
  frontendStateManagementContent,
  // Workspace
  workspaceIndexContent,
} from "../../templates/markdown/index.js";

/**
 * 收集所有需要被 update 命令管理的模板文件
 *
 * 该函数会扫描项目中已配置的平台（如 .claude、.cursor 等），
 * 并收集相应的模板文件。仅收集已存在目录的平台模板，
 * 避免为未配置的平台创建不必要的文件。
 *
 * 收集的模板类型包括：
 * - Python 脚本文件（scripts/ 目录）
 * - 配置文件（worktree.yaml、.gitignore 等）
 * - 规范文档（spec/guides、spec/backend、spec/frontend）
 * - 工作区文件（workspace/index.md）
 * - 平台特定模板（根据已配置平台动态添加）
 *
 * @param cwd - 项目根目录路径
 * @returns Map<string, string> - 相对路径到模板内容的映射
 *
 * @example
 * ```typescript
 * const templates = collectTemplateFiles('/path/to/project');
 * for (const [relativePath, content] of templates) {
 *   console.log(`${relativePath}: ${content.length} bytes`);
 * }
 * ```
 */
export function collectTemplateFiles(cwd: string): Map<string, string> {
  const files = new Map<string, string>();
  const platforms = getConfiguredPlatforms(cwd);

  // ========================================
  // Python scripts - package init
  // ========================================
  files.set(`${PATHS.SCRIPTS}/__init__.py`, scriptsInit);

  // ========================================
  // Python scripts - common
  // ========================================
  files.set(`${PATHS.SCRIPTS}/common/__init__.py`, commonInit);
  files.set(`${PATHS.SCRIPTS}/common/paths.py`, commonPaths);
  files.set(`${PATHS.SCRIPTS}/common/developer.py`, commonDeveloper);
  files.set(`${PATHS.SCRIPTS}/common/git_context.py`, commonGitContext);
  files.set(`${PATHS.SCRIPTS}/common/worktree.py`, commonWorktree);
  files.set(`${PATHS.SCRIPTS}/common/task_queue.py`, commonTaskQueue);
  files.set(`${PATHS.SCRIPTS}/common/task_utils.py`, commonTaskUtils);
  files.set(`${PATHS.SCRIPTS}/common/phase.py`, commonPhase);
  files.set(`${PATHS.SCRIPTS}/common/registry.py`, commonRegistry);
  files.set(`${PATHS.SCRIPTS}/common/cli_adapter.py`, commonCliAdapter);

  // ========================================
  // Python scripts - multi_agent
  // ========================================
  files.set(`${PATHS.SCRIPTS}/multi_agent/__init__.py`, multiAgentInit);
  files.set(`${PATHS.SCRIPTS}/multi_agent/start.py`, multiAgentStart);
  files.set(`${PATHS.SCRIPTS}/multi_agent/cleanup.py`, multiAgentCleanup);
  files.set(`${PATHS.SCRIPTS}/multi_agent/status.py`, multiAgentStatus);
  files.set(`${PATHS.SCRIPTS}/multi_agent/create_pr.py`, multiAgentCreatePr);
  files.set(`${PATHS.SCRIPTS}/multi_agent/plan.py`, multiAgentPlan);

  // ========================================
  // Python scripts - main
  // ========================================
  files.set(`${PATHS.SCRIPTS}/init_developer.py`, initDeveloperScript);
  files.set(`${PATHS.SCRIPTS}/get_developer.py`, getDeveloperScript);
  files.set(`${PATHS.SCRIPTS}/task.py`, taskScript);
  files.set(`${PATHS.SCRIPTS}/get_context.py`, getContextScript);
  files.set(`${PATHS.SCRIPTS}/add_session.py`, addSessionScript);
  files.set(`${PATHS.SCRIPTS}/create_bootstrap.py`, createBootstrapScript);

  // ========================================
  // Configuration
  // ========================================
  files.set(`${DIR_NAMES.WORKFLOW}/worktree.yaml`, worktreeYamlTemplate);
  files.set(`${DIR_NAMES.WORKFLOW}/.gitignore`, gitignoreTemplate);
  files.set(PATHS.WORKFLOW_GUIDE_FILE, workflowMdTemplate);

  // ========================================
  // Workspace index (template file, not user data)
  // ========================================
  files.set(`${PATHS.WORKSPACE}/index.md`, workspaceIndexContent);

  // ========================================
  // Spec - guides
  // ========================================
  files.set(`${PATHS.SPEC}/guides/index.md`, guidesIndexContent);
  files.set(
    `${PATHS.SPEC}/guides/cross-layer-thinking-guide.md`,
    guidesCrossLayerThinkingGuideContent,
  );
  files.set(
    `${PATHS.SPEC}/guides/code-reuse-thinking-guide.md`,
    guidesCodeReuseThinkingGuideContent,
  );

  // ========================================
  // Spec - backend (created if missing, protected by hash tracking if modified)
  // ========================================
  files.set(`${PATHS.SPEC}/backend/index.md`, backendIndexContent);
  files.set(
    `${PATHS.SPEC}/backend/directory-structure.md`,
    backendDirectoryStructureContent,
  );
  files.set(
    `${PATHS.SPEC}/backend/database-guidelines.md`,
    backendDatabaseGuidelinesContent,
  );
  files.set(
    `${PATHS.SPEC}/backend/logging-guidelines.md`,
    backendLoggingGuidelinesContent,
  );
  files.set(
    `${PATHS.SPEC}/backend/quality-guidelines.md`,
    backendQualityGuidelinesContent,
  );
  files.set(
    `${PATHS.SPEC}/backend/error-handling.md`,
    backendErrorHandlingContent,
  );

  // ========================================
  // Spec - frontend (created if missing, protected by hash tracking if modified)
  // ========================================
  files.set(`${PATHS.SPEC}/frontend/index.md`, frontendIndexContent);
  files.set(
    `${PATHS.SPEC}/frontend/directory-structure.md`,
    frontendDirectoryStructureContent,
  );
  files.set(`${PATHS.SPEC}/frontend/type-safety.md`, frontendTypeSafetyContent);
  files.set(
    `${PATHS.SPEC}/frontend/hook-guidelines.md`,
    frontendHookGuidelinesContent,
  );
  files.set(
    `${PATHS.SPEC}/frontend/component-guidelines.md`,
    frontendComponentGuidelinesContent,
  );
  files.set(
    `${PATHS.SPEC}/frontend/quality-guidelines.md`,
    frontendQualityGuidelinesContent,
  );
  files.set(
    `${PATHS.SPEC}/frontend/state-management.md`,
    frontendStateManagementContent,
  );

  // ========================================
  // Platform-specific templates (only for configured platforms)
  // ========================================
  for (const platformId of platforms) {
    const platformFiles = collectPlatformTemplates(platformId);
    if (platformFiles) {
      for (const [filePath, content] of platformFiles) {
        files.set(filePath, content);
      }
    }
  }

  return files;
}
