
You are an expert in TypeScript, Angular, and scalable web application development. You write functional, maintainable, performant, and accessible code following Angular and TypeScript best practices.

**IMPORTANT**: Always reference `CONTEXT.md` for project-specific details, current state, and session history before making changes. This file contains essential context about the DIY Craftsmanship Assistant application.

## TypeScript Best Practices

- Use strict type checking
- Prefer type inference when the type is obvious
- Avoid the `any` type; use `unknown` when type is uncertain

## Angular Best Practices

- Always use standalone components over NgModules
- Must NOT set `standalone: true` inside Angular decorators. It's the default in Angular v20+.
- Use signals for state management
- Implement lazy loading for feature routes
- Do NOT use the `@HostBinding` and `@HostListener` decorators. Put host bindings inside the `host` object of the `@Component` or `@Directive` decorator instead
- Use `NgOptimizedImage` for all static images.
  - `NgOptimizedImage` does not work for inline base64 images.

## Accessibility Requirements

- It MUST pass all AXE checks.
- It MUST follow all WCAG AA minimums, including focus management, color contrast, and ARIA attributes.

### Components

- Keep components small and focused on a single responsibility
- Use `input()` and `output()` functions instead of decorators
- Use `computed()` for derived state
- Set `changeDetection: ChangeDetectionStrategy.OnPush` in `@Component` decorator
- Prefer inline templates for small components
- Prefer Reactive forms instead of Template-driven ones
- Do NOT use `ngClass`, use `class` bindings instead
- Do NOT use `ngStyle`, use `style` bindings instead
- When using external templates/styles, use paths relative to the component TS file.

## State Management

- Use signals for local component state
- Use `computed()` for derived state
- Keep state transformations pure and predictable
- Do NOT use `mutate` on signals, use `update` or `set` instead

## Templates

- Keep templates simple and avoid complex logic
- Use native control flow (`@if`, `@for`, `@switch`) instead of `*ngIf`, `*ngFor`, `*ngSwitch`
- Use the async pipe to handle observables
- Do not assume globals like (`new Date()`) are available.

## Services

- Design services around a single responsibility
- Use the `providedIn: 'root'` option for singleton services
- Use the `inject()` function instead of constructor injection

## Token Optimization Guidelines

**Priority: Correctness First, Efficiency Second**

To minimize token usage while maintaining task accuracy:

1. **Read Files Efficiently**:
   - Read entire files in one operation rather than multiple partial reads
   - Batch parallel reads for context gathering (AGENTS.md + CONTEXT.md together)
   - Use grep_search with targeted patterns for large files instead of reading all content

2. **Reference CONTEXT.md First**:
   - Always consult CONTEXT.md before making changes to understand current state
   - This prevents redundant exploration and ensures changes align with established patterns
   - Review the "Recent Fixes" and "Latest Updates" sections to avoid repeating work

3. **Use Multi-Replace Operations**:
   - Apply multiple independent edits simultaneously with multi_replace_string_in_file
   - This consolidates tool calls and reduces overhead compared to sequential edits

4. **Minimize Exploration**:
   - Use semantic_search for understanding codebase patterns, not for simple file location
   - Avoid running commands to explore structure when file listings exist
   - Keep related changes in a single batch when possible

5. **Task-First Approach**:
   - Break complex requests into clear steps tracked in todo list
   - Complete full implementation before stopping, even if it requires multiple tool calls
   - Avoid half-measures: if a task requires CSS, HTML, and TypeScript changes, do all three

6. **Documentation Updates**:
   - Update CONTEXT.md incrementally as changes are made
   - Record what was changed and why, not just what the final state is
   - This provides future reference without needing to re-read implementation files
