# Skill: continua-progress-skill

## Description
When user gives brief imperatives like 'continua' to proceed with a task, provide explicit progress updates about what specific verification/validation steps have been completed before asking for approval to proceed to the next phase.

## Triggers
- User says 'continua', 'continua com next move', 'retry', or similar brief imperatives to proceed
- User expresses frustration about perceived delays ('ainda nao apareceu nada')
- User wants thorough completion of current task before moving to next planned item

## Workflow
1. When user says 'continua' or similar:
   - Give a brief recap of established state
   - Pick the single next concrete safe step that can actually be executed
   - Execute it (e.g. build+lint validation, next migration, next sub-step)
   - Report completion of that specific step with evidence/commands
   - Ask for approval to proceed to the next phase
2. For multi-step processes (push+deploy, approval workflows):
   - Provide explicit status updates after each major step
   - Examples: 'lint check passed', 'committed locally', 'waiting for approval to push', 'push done', 'CI built', 'VPS updated'
3. Never re-ask for direction when user says 'continua' - instead execute the next logical step

## Examples
- User: "continua"
  Agent: "Recap: [state]. Next step: [action]. Executing now..."
  [After completion]: "[Step] completed. Ready for next phase. Continua?"

- User: "ainda nao apareceu nada"
  Agent: "Here's what has been completed so far: [list completed steps with timestamps/evidence]"

## Anti-patterns
- Re-asking for clarification or direction when user says 'continua'
- Not providing explicit progress updates during multi-step processes
- Moving to next phase without completing and verifying current step
- Assuming user wants theoretical discussion instead of concrete action

## Context
This skill captures the user's preference for explicit, step-by-step progress reporting when they use brief imperatives to continue work, reducing perception of delays and ensuring thorough completion before moving forward.
