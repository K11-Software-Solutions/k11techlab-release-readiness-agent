# Changelog

## 0.2.0 (15 November 2026)

- **Performance evidence:** new `perf-evidence` sub-agent runs a load test with [k11 Performance QA](https://github.com/K11-Software-Solutions/k11techlab-performance-qa-mcp) (your API flows as traffic) and compares it with the baseline from main.
- Seven K11 servers bundled; the plan triggers a load test for database and performance-sensitive changes (needs Release Gate 0.3.0).

## 0.1.0 (13 November 2026)

- First release: `/release-readiness:check`, four evidence sub-agents, six K11 servers, deterministic verdict from the Release Gate.
