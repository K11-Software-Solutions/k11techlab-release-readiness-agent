---
name: check
description: Decide whether the current branch can be released. Plans which checks the change needs, gathers evidence in parallel (UI tests with self-healing, API contract, API functional tests, LLM red-team), gets a deterministic verdict from the K11 Release Gate, and explains it. Use before merging or tagging a release.
argument-hint: "[base ref, default origin/main] [release label]"
---

# Release readiness check

You are coordinating a release-readiness check for this repository. The **Release Gate decides**; you plan, gather evidence, and explain. Never change, soften or second-guess the verdict.

Input: $ARGUMENTS (optional base git ref, default `origin/main`; optional release label)

## 1. Plan

Call the release-gate `plan_checks` tool with the base ref. It returns which kinds of evidence this change needs (`ui_heal`, `contract`, `api_tests`, `llm`), the changed files that triggered each, and the tool that produces it. Show the user the plan in one short table: kind, needed or skipped, and why.

If `plan_checks` fails because the base ref doesn't exist, ask which branch to compare with.

## 2. Confirm before anything touches an environment

API functional tests and LLM red-teaming send requests to running systems. Before starting them:
- call api-functional-qa `list_environments` and tell the user which environment will be used and whether it allows writes;
- for the LLM red-team, confirm the target file and that the user owns or is authorised to test that system.

Never point any check at production. If the only configured environment is production-like, stop that check and say so.

## 3. Gather evidence in parallel

For every needed kind, start its sub-agent at the same time (one Agent call each, in a single message):

| Kind | Sub-agent |
|---|---|
| `ui_heal` | `release-readiness:ui-evidence` |
| `contract` | `release-readiness:api-contract-evidence` |
| `api_tests` | `release-readiness:api-functional-evidence` |
| `llm` | `release-readiness:llm-evidence` |

Give each the base ref, the environment or target the user confirmed, and the evidence path from the release policy (`collect_evidence` shows the patterns; the defaults are `.qa-mcp/heal-report/heal-report.json`, `.qa-mcp/contract-report/contract-report.json`, `.qa-mcp/api-test-report/api-test-report.json`, `llm-assure-report/assessment.json`). Each sub-agent writes its report there and returns a short summary. Skip kinds that aren't needed.

## 4. Decide

Call release-gate `evaluate_release` with the label and the same base ref. Report the verdict exactly as returned:

- **ship**
- **ship with conditions**: list each condition and who must meet it
- **needs a person**: name the approvers from the result
- **block**: list each blocker

## 5. Explain and suggest

For each blocker, give what failed, the evidence file, and the smallest change that would clear it. Use the sub-agents' summaries and the investigative tools where helpful (for example `heal_locator` candidates, `assess_impact` details, or `call_api` to reproduce a failing request). **Ask before changing any code or tests**, and never weaken a test or a policy rule to change the verdict.

List what wasn't tested, and say plainly that untested is not the same as passing.

Finish with the path to `.qa-mcp/release-gate/release-decision.md`.
