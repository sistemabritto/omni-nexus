# Learning: Workspace Lock Deadlock Root Cause

## Context
During troubleshooting of system-wide failures ("tudo falha"), investigation revealed the root cause was a persistent workspace lock file causing all operations to report "workspace busy".

## Key Insight
The lock file `workspace/.locks/orchestrator-bash.lock` was being held by process ID 131, which turned out to be the main Flask app process (`app.py`) itself—not an orphaned subprocess. This created a deadlock situation where:

1. The Flask app spawns subprocesses for operations (like bolt-executor)
2. These subprocesses inherit file descriptors including the lock file descriptor
3. When a subprocess is killed by timeout (e.g., 280s limit), the child process dies
4. However, the parent Flask app's inherited file descriptor to the lock remains open
5. Since file locks (flocks) are only released when ALL file descriptors to that inode are closed, the lock persists indefinitely
6. The parent Flask app continues to hold the inherited lock file descriptor, causing all subsequent operations to fail with "workspace busy"

## Root Cause Analysis
- **Not a stuck orphan**: The lock holder is the legitimate Flask app process
- **Inheritance issue**: File descriptor inheritance creates persistent lock ownership
- **Timeout interaction**: Process timeouts kill children but don't close inherited FDs in parents
- **Systemic effect**: One timed-out operation can permanently lock the entire workspace until the Flask app restarts

## Solution Implications
To fix this issue:
1. Avoid passing lock file descriptors to subprocesses that might timeout
2. Implement proper lock handling in subprocess spawning code
3. Consider using lock files with automatic cleanup mechanisms (e.g., lockd, flock with timeout)
4. Ensure subprocesses close inherited file descriptors they don't need
5. Consider restarting the Flask app as recovery mechanism when lock is detected as held by app.py

## Verification Approach
- Check who holds the lock using `lsof workspace/.locks/orchestrator-bash.lock`
- Verify lock-holding bug against heartbeat logs
- Monitor for patterns where lock holder is the Flask app PID after timeouts

This learning explains why simply removing the lock file didn't provide a permanent fix—the root cause was the Flask app itself maintaining an open file descriptor to the lock through inheritance.
