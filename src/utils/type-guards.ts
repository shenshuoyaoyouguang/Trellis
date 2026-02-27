/**
 * Type guard utilities for safe type checking and parsing
 * Provides runtime type validation for CLI options and other dynamic inputs
 */

/**
 * Check if a value is a boolean or undefined
 */
export function isBooleanOrUndefined(
  value: unknown,
): value is boolean | undefined {
  return value === undefined || typeof value === "boolean";
}

/**
 * Check if a value is a string or undefined
 */
export function isStringOrUndefined(
  value: unknown,
): value is string | undefined {
  return value === undefined || typeof value === "string";
}

/**
 * Safely get a boolean option value with default
 *
 * @param options - Options object
 * @param key - Key to retrieve
 * @param defaultValue - Default value if key is missing or not boolean
 * @returns Boolean value
 */
export function getBooleanOption(
  options: Record<string, unknown>,
  key: string,
  defaultValue = false,
): boolean {
  const value = options[key];
  if (typeof value === "boolean") {
    return value;
  }
  return defaultValue;
}

/**
 * Safely get a string option value with default
 *
 * @param options - Options object
 * @param key - Key to retrieve
 * @param defaultValue - Default value if key is missing or not string
 * @returns String value
 */
export function getStringOption(
  options: Record<string, unknown>,
  key: string,
  defaultValue = "",
): string {
  const value = options[key];
  if (typeof value === "string") {
    return value;
  }
  return defaultValue;
}

/**
 * Init command options interface
 */
export interface InitOptions {
  cursor: boolean;
  claude: boolean;
  iflow: boolean;
  opencode: boolean;
  codex: boolean;
  kilo: boolean;
  kiro: boolean;
  yes: boolean;
  user: string;
  force: boolean;
  skipExisting: boolean;
  template: string;
  overwrite: boolean;
  append: boolean;
}

/**
 * Parse and validate init command options
 *
 * @param options - Raw options from Commander.js
 * @returns Typed InitOptions object
 */
export function parseInitOptions(
  options: Record<string, unknown>,
): InitOptions {
  return {
    cursor: getBooleanOption(options, "cursor"),
    claude: getBooleanOption(options, "claude"),
    iflow: getBooleanOption(options, "iflow"),
    opencode: getBooleanOption(options, "opencode"),
    codex: getBooleanOption(options, "codex"),
    kilo: getBooleanOption(options, "kilo"),
    kiro: getBooleanOption(options, "kiro"),
    yes: getBooleanOption(options, "yes"),
    user: getStringOption(options, "user"),
    force: getBooleanOption(options, "force"),
    skipExisting: getBooleanOption(options, "skipExisting"),
    template: getStringOption(options, "template"),
    overwrite: getBooleanOption(options, "overwrite"),
    append: getBooleanOption(options, "append"),
  };
}

/**
 * Update command options interface
 */
export interface UpdateOptions {
  dryRun: boolean;
  force: boolean;
  skipAll: boolean;
  createNew: boolean;
  allowDowngrade: boolean;
  migrate: boolean;
}

/**
 * Parse and validate update command options
 *
 * @param options - Raw options from Commander.js
 * @returns Typed UpdateOptions object
 */
export function parseUpdateOptions(
  options: Record<string, unknown>,
): UpdateOptions {
  return {
    dryRun: getBooleanOption(options, "dryRun"),
    force: getBooleanOption(options, "force"),
    skipAll: getBooleanOption(options, "skipAll"),
    createNew: getBooleanOption(options, "createNew"),
    allowDowngrade: getBooleanOption(options, "allowDowngrade"),
    migrate: getBooleanOption(options, "migrate"),
  };
}

/**
 * Assert that a value is not null or undefined
 *
 * @param value - Value to check
 * @param message - Error message if assertion fails
 * @throws Error if value is null or undefined
 */
export function assertDefined<T>(
  value: T | null | undefined,
  message = "Value is required",
): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(message);
  }
}

/**
 * Type guard for checking if value is a non-empty string
 */
export function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

/**
 * Type guard for checking if value is a plain object
 */
export function isPlainObject(
  value: unknown,
): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
