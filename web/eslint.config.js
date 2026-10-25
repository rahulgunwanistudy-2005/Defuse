import js from '@eslint/js';
import ts from 'typescript-eslint';

export default ts.config(
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    languageOptions: { globals: { window: 'readonly', document: 'readonly', EventSource: 'readonly', fetch: 'readonly', setTimeout: 'readonly', clearTimeout: 'readonly', console: 'readonly' } },
    rules: { '@typescript-eslint/no-explicit-any': 'off' }
  },
  { ignores: ['.svelte-kit/', 'build/', 'node_modules/'] }
);
