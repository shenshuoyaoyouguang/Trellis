/**
 * Input sanitization and validation utilities
 * Provides safe input handling to prevent security vulnerabilities
 */

import path from "node:path";

/**
 * Pattern for safe name input (alphanumeric, underscore, hyphen only)
 */
const SAFE_NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

/**
 * Maximum allowed length for name inputs
 */
const MAX_NAME_LENGTH = 64;

/**
 * Sanitization error class
 */
export class SanitizationError extends Error {
  constructor(
    message: string,
    public readonly field: string,
    public readonly value: string,
  ) {
    super(message);
    this.name = "SanitizationError";
  }
}

/**
 * Validation result type
 */
export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Validate and sanitize a name input
 * Only allows alphanumeric characters, underscores, and hyphens
 *
 * @param input - The input string to validate
 * @param fieldName - Name of the field for error messages
 * @returns Sanitized input string
 * @throws SanitizationError if input contains invalid characters
 */
export function sanitizeName(input: string, fieldName = "name"): string {
  // Trim whitespace
  const trimmed = input.trim();

  // Check for empty input
  if (trimmed.length === 0) {
    throw new SanitizationError(
      `${fieldName} cannot be empty`,
      fieldName,
      input,
    );
  }

  // Length validation
  if (trimmed.length > MAX_NAME_LENGTH) {
    throw new SanitizationError(
      `${fieldName} exceeds maximum length (${MAX_NAME_LENGTH} characters)`,
      fieldName,
      input,
    );
  }

  // Character whitelist validation
  if (!SAFE_NAME_PATTERN.test(trimmed)) {
    throw new SanitizationError(
      `${fieldName} contains invalid characters. Only letters, numbers, underscores, and hyphens are allowed.`,
      fieldName,
      input,
    );
  }

  return trimmed;
}

/**
 * Validate a name without throwing (returns result object)
 *
 * @param input - The input string to validate
 * @param fieldName - Name of the field for error messages
 * @returns Validation result with success status and optional error message
 */
export function validateName(
  input: string,
  fieldName = "name",
): ValidationResult {
  try {
    sanitizeName(input, fieldName);
    return { valid: true };
  } catch (error) {
    if (error instanceof SanitizationError) {
      return { valid: false, error: error.message };
    }
    return { valid: false, error: "Unknown validation error" };
  }
}

/**
 * Escape a string for safe use in shell commands
 * Uses single quotes and escapes internal single quotes
 *
 * @param arg - The argument to escape
 * @returns Shell-escaped string
 */
export function escapeShellArg(arg: string): string {
  // Use single quotes to prevent shell interpretation
  // Escape any single quotes in the argument
  return `'${arg.replace(/'/g, "'\\''")}'`;
}

/**
 * Check if a path is safe (no directory traversal)
 *
 * @param inputPath - The path to check
 * @returns True if the path is safe
 */
export function isPathSafe(inputPath: string): boolean {
  // Normalize path separators first (Windows -> Unix style)
  const normalized = inputPath.replace(/\\/g, "/");

  // Check for directory traversal attempts AFTER normalization
  if (normalized.includes("..") || normalized.includes("~")) {
    return false;
  }

  // Check for absolute paths using normalized path
  if (path.isAbsolute(normalized)) {
    return false;
  }

  return true;
}
