import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";
export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.mjs"],
    languageOptions: {globals: globals.node},
  },
  {ignores: ["node_modules", "coverage", "dist"]},
  {rules: {"@typescript-eslint/no-explicit-any": "error"}},
];
