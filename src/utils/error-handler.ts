/**
 * Unified error handling utilities
 * Provides consistent error handling across the application
 */

import chalk from "chalk";

/**
 * Error severity levels
 */
export type ErrorSeverity = "critical" | "warning" | "info" | "silent";

/**
 * Error context information
 */
export interface ErrorContext {
  /** Name of the operation that failed */
  operation: string;
  /** Severity level determining how the error is handled */
  severity: ErrorSeverity;
  /** Optional fallback function to execute on non-critical errors */
  fallback?: () => void;
  /** Optional user-friendly message */
  userMessage?: string;
  /** Optional additional context for debugging */
  details?: Record<string, unknown>;
}

/**
 * Application error class with context
 */
export class AppError extends Error {
  constructor(
    message: string,
    public readonly context?: ErrorContext,
    public readonly cause?: Error,
  ) {
    super(message);
    this.name = "AppError";
  }
}

/**
 * Handle an error based on its severity
 *
 * @param error - The error to handle
 * @param context - Context information for error handling
 */
export function handleError(error: unknown, context: ErrorContext): void {
  const { operation, severity, fallback, userMessage, details } = context;
  const errorMessage = error instanceof Error ? error.message : String(error);

  switch (severity) {
    case "critical":
      // Critical errors: log details and re-throw
      console.error(chalk.red(`\n❌ ${operation} failed: ${errorMessage}`));
      if (userMessage) {
        console.error(chalk.gray(`   ${userMessage}`));
      }
      if (details) {
        console.error(chalk.gray(`   Details: ${JSON.stringify(details)}`));
      }
      throw error;

    case "warning":
      // Warnings: display message but continue
      console.warn(chalk.yellow(`\n⚠️  ${operation} warning: ${errorMessage}`));
      if (userMessage) {
        console.warn(chalk.gray(`   ${userMessage}`));
      }
      fallback?.();
      break;

    case "info":
      // Info: just log the message
      console.log(chalk.gray(`ℹ️  ${operation}: ${errorMessage}`));
      if (userMessage) {
        console.log(chalk.gray(`   ${userMessage}`));
      }
      break;

    case "silent":
      // Silent: no output (for known edge cases)
      break;
  }
}

/**
 * Wrap an async operation with automatic error handling
 *
 * @param operation - Name of the operation
 * @param fn - Async function to execute
 * @param context - Error context (without operation)
 * @returns Result of fn or undefined on error
 */
export async function withErrorHandling<T>(
  operation: string,
  fn: () => Promise<T>,
  context: Omit<ErrorContext, "operation">,
): Promise<T | undefined> {
  try {
    return await fn();
  } catch (error) {
    handleError(error, { ...context, operation });
    return undefined;
  }
}

/**
 * Wrap a sync operation with automatic error handling
 *
 * @param operation - Name of the operation
 * @param fn - Sync function to execute
 * @param context - Error context (without operation)
 * @returns Result of fn or undefined on error
 */
export function withSyncErrorHandling<T>(
  operation: string,
  fn: () => T,
  context: Omit<ErrorContext, "operation">,
): T | undefined {
  try {
    return fn();
  } catch (error) {
    handleError(error, { ...context, operation });
    return undefined;
  }
}

/**
 * Log an error with full stack trace (for debugging)
 *
 * @param error - Error to log
 * @param context - Optional context
 */
export function logError(error: unknown, context?: string): void {
  if (error instanceof Error) {
    console.error(chalk.red(`\n[DEBUG] ${context ?? "Error"}:`));
    console.error(chalk.red(error.stack ?? error.message));
  } else {
    console.error(
      chalk.red(`\n[DEBUG] ${context ?? "Error"}: ${String(error)}`),
    );
  }
}

/**
 * Create a user-friendly error message from an unknown error
 *
 * @param error - Unknown error
 * @returns User-friendly message string
 */
export function formatErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "An unknown error occurred";
}
