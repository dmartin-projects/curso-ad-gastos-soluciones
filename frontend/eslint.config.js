// @ts-check
const eslint = require('@eslint/js');
const { defineConfig } = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');
const boundaries = require('eslint-plugin-boundaries');

/**
 * Las capas del frontend (módulo 80). Cada carpeta es un "element" de eslint-plugin-boundaries; `feature` y `page`
 * se capturan de la ruta para poder decir "de SU feature".
 */
const ELEMENTOS = [
  { type: 'testing', pattern: 'src/app/testing' },
  { type: 'page', pattern: 'src/app/features/*/pages/*', capture: ['feature', 'page'] },
  { type: 'component', pattern: 'src/app/features/*/components', capture: ['feature'] },
  { type: 'service', pattern: 'src/app/features/*/services', capture: ['feature'] },
  { type: 'interfaces', pattern: 'src/app/features/*/interfaces', capture: ['feature'] },
  { type: 'feature', pattern: 'src/app/features/*', capture: ['feature'] }, // <feature>.routes.ts
  { type: 'core-api', pattern: 'src/app/core/api' },
  { type: 'core', pattern: 'src/app/core' },
  { type: 'shared-utils', pattern: 'src/app/shared/utils' },
  { type: 'shared-interfaces', pattern: 'src/app/shared/interfaces' },
  { type: 'shared', pattern: 'src/app/shared' },
  { type: 'app', pattern: 'src/app' }, // app.ts, app.config.ts, app.routes.ts
];

const MISMA = { feature: '{{from.element.captured.feature}}' };
const SHARED = ['shared', 'shared-utils', 'shared-interfaces'];

/** Quién puede importar a quién. Lo que no está aquí, está prohibido (default: 'disallow'). */
const REGLAS = [
  { from: 'app', to: [{ type: ['app', 'core', 'core-api', ...SHARED, 'feature', 'page'] }] },
  {
    from: 'feature',
    to: [{ type: ['page', 'service'], captured: MISMA }, { type: ['core', 'core-api'] }],
  },
  {
    from: 'page',
    to: [
      { type: 'page', captured: { ...MISMA, page: '{{from.element.captured.page}}' } }, // su carpeta
      { type: ['component', 'service', 'interfaces'], captured: MISMA },
      { type: ['core', 'core-api', ...SHARED] },
    ],
  },
  {
    from: 'component',
    to: [{ type: ['component', 'interfaces'], captured: MISMA }, { type: SHARED }],
  },
  {
    from: 'service',
    to: [
      { type: ['service', 'interfaces'], captured: MISMA },
      { type: ['core', 'core-api', 'shared-utils', 'shared-interfaces'] },
    ],
  },
  {
    from: 'interfaces',
    to: [{ type: 'interfaces', captured: MISMA }, { type: ['core-api', 'shared-interfaces'] }],
  },
  { from: 'core', to: [{ type: ['core', 'core-api', ...SHARED] }] },
  { from: 'core-api', to: [{ type: 'core-api' }] },
  { from: 'shared', to: [{ type: SHARED }] },
  { from: 'shared-utils', to: [{ type: ['shared-utils', 'shared-interfaces'] }] },
  { from: 'shared-interfaces', to: [{ type: 'shared-interfaces' }] },
  { from: 'testing', to: [{ type: ['testing', 'core', 'core-api', ...SHARED] }] },
];

module.exports = defineConfig([
  { ignores: ['src/app/core/api/esquema.ts'] }, // lo genera openapi-typescript
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      tseslint.configs.recommended,
      tseslint.configs.stylistic,
      angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      '@angular-eslint/directive-selector': [
        'error',
        { type: 'attribute', prefix: 'app', style: 'camelCase' },
      ],
      '@angular-eslint/component-selector': [
        'error',
        { type: 'element', prefix: 'app', style: 'kebab-case' },
      ],
      // los query params llegan como inputs (withComponentInputBinding): su nombre lo pone la URL
      '@angular-eslint/no-input-rename': ['error', { allowedNames: ['error_social', 'q'] }],
    },
  },
  {
    files: ['**/*.html'],
    extends: [angular.configs.templateRecommended, angular.configs.templateAccessibility],
    rules: {},
  },
  // ── Fronteras entre features, core y shared ──
  {
    files: ['src/app/**/*.ts'],
    plugins: { boundaries },
    settings: {
      'import/resolver': { node: { extensions: ['.ts'] } },
      'boundaries/elements': ELEMENTOS,
      'boundaries/files': [{ category: 'spec', pattern: '**/*.spec.ts' }],
    },
    rules: {
      'boundaries/no-unknown-files': 'error', // cada archivo, en una capa conocida
      'boundaries/no-unknown-dependencies': 'error', // y solo importa archivos de capas conocidas
      'boundaries/dependencies': [
        'error',
        {
          default: 'disallow',
          message:
            '{{from.element.types}}{{#if from.element.captured.feature}} «{{from.element.captured.feature}}»{{/if}} ' +
            'no puede importar {{to.element.types}}{{#if to.element.captured.feature}} «{{to.element.captured.feature}}»{{/if}} ' +
            '(reglas de dependencia del módulo 80)',
          policies: [
            { allow: { to: { module: { origin: ['external', 'core'] } } } }, // npm y Node
            ...REGLAS.map(({ from, to }) => ({
              from: { element: { type: from } },
              allow: { to: to.map((elemento) => ({ element: elemento })) },
            })),
            // un test mira su pieza por dentro: su feature entera, core, shared y testing/
            {
              from: { file: { categories: 'spec' } },
              allow: {
                to: [
                  { element: { captured: MISMA } },
                  { element: { type: ['core', 'core-api', 'testing', ...SHARED] } },
                ],
              },
            },
          ],
        },
      ],
    },
  },
  // ── HTTP solo en los services de cada feature y en core ──
  {
    files: ['src/app/**/*.ts'],
    ignores: [
      'src/app/features/*/services/**',
      'src/app/core/**',
      'src/app/testing/**',
      'src/app/app.config.ts', // provideHttpClient y los interceptores: la composición de la app
      '**/*.spec.ts',
    ],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@angular/common/http',
              message:
                'HTTP solo en features/<feature>/services/ y en core/: pide los datos al service de tu feature.',
            },
          ],
        },
      ],
    },
  },
]);
