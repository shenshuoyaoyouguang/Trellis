/**
 * Type definitions for the update command
 *
 * This module contains all type definitions used by the update command
 * and its sub-modules.
 */

/**
 * Options for the update command
 */
export interface UpdateOptions {
  /** Preview changes without applying them */
  dryRun?: boolean;
  /** Overwrite all changed files without asking */
  force?: boolean;
  /** Skip all changed files without asking */
  skipAll?: boolean;
  /** Create .new copies for all changed files */
  createNew?: boolean;
  /** Allow downgrading to an older version */
  allowDowngrade?: boolean;
  /** Apply pending file migrations (renames/deletions) */
  migrate?: boolean;
}

/**
 * Represents a file change detected during update
 */
export interface FileChange {
  /** Absolute path to the file */
  path: string;
  /** Path relative to the project root */
  relativePath: string;
  /** New content from template */
  newContent: string;
  /** Status of the file change */
  status: "new" | "unchanged" | "changed";
}

/**
 * Analysis result of file changes
 */
export interface ChangeAnalysis {
  /** Files that don't exist yet */
  newFiles: FileChange[];
  /** Files that match the template exactly */
  unchangedFiles: FileChange[];
  /** Template updated, user didn't modify - safe to auto-update */
  autoUpdateFiles: FileChange[];
  /** User modified, needs confirmation */
  changedFiles: FileChange[];
  /** Paths that should never be modified */
  protectedPaths: string[];
}

/**
 * Action to take for a file conflict
 */
export type ConflictAction = "overwrite" | "skip" | "create-new";

/**
 * Result of applying a single conflict action
 */
export interface ConflictResult {
  /** The action that was taken */
  action: ConflictAction;
  /** Path to the affected file */
  path: string;
  /** Whether the action succeeded */
  success: boolean;
  /** Optional message about the result */
  message?: string;
}

/**
 * Summary of all update operations
 */
export interface UpdateSummary {
  /** Total number of files processed */
  totalFiles: number;
  /** Number of new files created */
  newFiles: number;
  /** Number of files updated */
  updatedFiles: number;
  /** Number of files skipped */
  skippedFiles: number;
  /** Number of .new files created */
  newCopies: number;
  /** Whether this was a dry run */
  dryRun: boolean;
}

/**
 * Backup information for a file
 */
export interface FileBackup {
  /** Original path of the file */
  originalPath: string;
  /** Path to the backup file */
  backupPath: string;
  /** Timestamp of the backup */
  timestamp: string;
}

/**
 * Migration classification result
 */
export interface MigrationClassification {
  /** Migrations that can be auto-applied */
  auto: import("../../types/migration.js").MigrationItem[];
  /** Migrations that need user confirmation */
  manual: import("../../types/migration.js").MigrationItem[];
  /** Migrations that have conflicts */
  conflicts: import("../../types/migration.js").MigrationItem[];
}

/**
 * Version comparison result
 */
export type VersionComparison = "newer" | "older" | "same";

/**
 * Options for backup operations
 */
export interface BackupOptions {
  /** Directory to store backups */
  backupDir?: string;
  /** Maximum number of backups to keep */
  maxBackups?: number;
  /** Whether to include timestamps in backup names */
  includeTimestamp?: boolean;
}
