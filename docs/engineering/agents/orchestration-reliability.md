# Orchestration Reliability

Use this guidance when a goal run coordinates work through subagents.

## Failure Mode

Recent goal runs have stopped while the coordinator was waiting on subagents. The goal records stayed `active`, with no token budget and no completed or blocked status. The session logs ended immediately after `wait_agent` calls with long timeouts, which means the coordinator did not receive the wait result and resume.

Treat this as a tool-session reliability risk, not a product or repository blocker.

## Coordinator Rules

- Do not use one long `wait_agent` call as the only coordination point.
- Poll subagents in short intervals, normally 60-120 seconds.
- Keep polling until every dispatched subagent has a terminal result, has been explicitly closed, or has been replaced by a new checkpointed dispatch. A timed-out poll is not a stopping condition.
- Do not send a final handoff while any checkpointed subagent is still running unless the user explicitly pauses the run.
- After every subagent dispatch, write a compact checkpoint into the active roadmap before waiting:
  - agent id
  - workstream and pass
  - expected ownership boundary
  - dispatch timestamp
  - next coordinator action
- After every returned subagent result, update the same checkpoint with:
  - status
  - changed files
  - verification
  - unresolved blockers
  - next pass needed
- If a wait call does not return, a later coordinator must resume from the roadmap checkpoints and visible git state, not from memory.
- After a coordinator resume, first try `resume_agent` for checkpointed agent ids before replacing them. If resumed handles repeatedly time out without status, record them as stale in the roadmap and dispatch a replacement agent with a new checkpoint.
- If the platform supports direct status nudges, ask long-running subagents for a compact status before another wait.
- Never leave the only source of orchestration state inside the coordinator context window.

## Practical Loop

1. Dispatch one workstream agent.
2. Immediately checkpoint the dispatch in the active roadmap.
3. Poll with short waits until a terminal result returns.
4. On return, checkpoint the result.
5. Dispatch the next pass or next independent stream only after the roadmap reflects the current state.

This keeps goal runs resumable even if the coordinator session is interrupted at the subagent wait boundary.
