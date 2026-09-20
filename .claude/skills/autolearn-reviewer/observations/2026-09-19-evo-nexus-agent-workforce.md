# Observation: EvoNexus Agent Workforce Configuration Issues

## Context
During investigation of user request to make Omni Nexus proactive with agent workforce, discovered systemic configuration issues preventing proper goal-driven agent operation.

## Key Findings

### 1. Goal Planner Disabled
- The `goal-planner` heartbeat (responsible for decomposing Goals → Tickets) is disabled (`enabled: false`)
- Despite having `goal_created` wake trigger, lacks `interval` trigger for periodic sweeps
- Results in 5 existing Goals remaining in `decomposition_state: None` (never decomposed)
- **User Preference**: Goals should automatically derive tickets via goal-planner for agent assignment

### 2. Autopilot Heartbeats Mostly Disabled
- Of 16 `autopilot-*` agent workers, only 4 enabled: bolt-executor, hawk-debugger, oath-verifier, sage-strategy
- Critical agents like compass-planner, dex-data, mako-marketing disabled (`enabled: 0`)
- **User Expectation**: Agents should process assigned tickets when orchestrator dispatches them
- **Note**: Orchestrator bypasses `enabled` check when dispatching, but disabled state indicates configuration neglect

### 3. Configuration/Documentation Divergence
- `goal-planner` agent documentation specifies wake_triggers: `[goal_created, interval, manual]`
- Actual YAML configuration: `wake_triggers: [goal_created, manual]` (missing `interval`)
- **Pattern**: Documentation describes intended periodic behavior but implementation lacks interval trigger

### 4. Magneto/Telegram Integration Gap
- User controls/workflow via Magneto (Telegram bot) on WhatsApp
- Reports/notifications not arriving consistently in WhatsApp channel
- **User Need**: Reliable communication channel for agent status reports and control

## Root Cause
System configured for manual/intervention-driven operation rather than proactive autonomous workflow:
- Goal decomposition requires manual trigger (goal-planner disabled/sweep missing)
- Agent workers disabled by default
- No automatic periodic goal review/sweep mechanism

## Recommended Fixes
1. Enable `goal-planner` heartbeat and add `interval` trigger for periodic sweeps
2. Enable appropriate `autopilot-*` heartbeats for core agent workforce
3. Align agent documentation with actual configuration (or vice versa)
4. Verify Magneto/Telegram bot connectivity and message formatting for WhatsApp delivery

## Token-Efficiency Insight
Investigation revealed that understanding the heartbeat/dispatcher/orchestrator flow required examining multiple interconnected components:
- Scheduler configuration
- Heartbeat dispatcher/runner logic  
- Nexus orchestrator ticket processing
- Agent-specific autopilot definitions
- Database state of goals/tickets/heartbeats
Future sessions can shortcut this discovery by examining these specific components in order when diagnosing agent inactivity.

