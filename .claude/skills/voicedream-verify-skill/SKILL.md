# Skill: voicedream-verify-skill

## Description
After making changes to the voicedream project, always run typecheck and lint verification to ensure code quality before proceeding or considering the task complete.

## Triggers
- User makes changes to voicedream project files
- User says 'continua' or similar after voicedream changes
- User requests deployment or push of voicedream changes
- Any modification to voicedream source code

## Workflow
1. After making any changes to voicedream project:
   - Run typecheck: `npm run typecheck` or equivalent TypeScript compilation check
   - Run lint: `npm run lint` or equivalent ESLint check
   - Wait for both to complete successfully (exit code 0)
   - Only then consider the changes ready for next steps
2. If typecheck or lint fails:
   - Fix the reported issues before proceeding
   - Re-run verification until both pass
3. Provide explicit status updates:
   - "Typecheck passed"
   - "Lint passed" 
   - "Both typecheck and lint verification completed successfully"
4. Never skip verification even if user says 'continua' or seems eager to proceed

## Anti-patterns
- Considering changes complete without running typecheck and lint
- Skipping verification to save time
- Assuming changes are correct without validation
- Proceeding to next steps when verification fails

## Context
This skill captures the user's explicit preference for running typecheck and lint verification after any voicedream project changes to ensure code quality, based on repeated patterns in the conversation where the user emphasized this verification step.
