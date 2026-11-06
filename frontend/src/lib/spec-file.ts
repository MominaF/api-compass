const MAX_SPEC_BYTES = 5 * 1024 * 1024;

export const SPEC_FILE_TYPES = ".json,.yaml,.yml";

/** Catches files the API would reject, before uploading them. Returns the problem, if any. */
export function specFileError(file: File): string | null {
  if (!/\.(json|ya?ml)$/i.test(file.name)) return "Upload a .json, .yaml or .yml file.";
  if (file.size > MAX_SPEC_BYTES) return "The file is larger than the 5 MB limit.";
  if (file.size === 0) return "The file is empty.";
  return null;
}
