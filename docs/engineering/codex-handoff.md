# First Codex handoff

This branch prepares context; it does not configure or launch a Codex environment.

## First task: review this bootstrap

Select the repository and the actual bootstrap branch/revision in the chosen Codex environment. Do not assume main contains these files until a reviewed merge occurs. No Azure keys, production content or privileged GitHub token is needed for the checks.

Use this task instruction:

> Read AGENTS.md, tasks/APBRA-85-bootstrap.json, agents/catalog.json, the source register and repository-controls.md. Act in a separate review execution. Inspect the exact change against main and run the documented bootstrap validator and unit tests. Check inherited requirements, task scope, negative cases, source-status honesty, permissions and absence of product-readiness claims. Report findings with severity, file/line, expected/actual and evidence. Do not merge, approve under the author's account, modify main, create Azure resources or implement report features. Missing dependencies/network or inaccessible sources are explicit blockers, not passing tests.

Record the actual actor and runtime exposed by Codex; do not guess its model. Offline tests cannot validate current Jira/Confluence revisions. Refresh those inputs through authorized access before dispatching subsequent implementation.

## Next implementation task

After the reviewed bootstrap and control decisions, prepare a new bounded contract for APBRA-27. Resolve and lock the selected product dependency families, implement only local bootstrap/configuration/health behavior, and prove positive/negative startup tests. APBRA-18/20 owns actual dependency-boundary tests when modules exist. No other Epic is implicitly authorized.

For each new task, select only its relevant context and verification obligations. Do not ask Codex to implement all 127 work items from one mega-prompt. Keep one implementation and one separate review in flight initially, with meaningful Jira comments and real test evidence.
