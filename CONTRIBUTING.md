# Contributing

This project values reliability, deterministic installs, and clear UX. Use the prompts and process below to keep changes consistent and “legendary.”

## Legendary prompt set (copy/paste)

### 1) Legendary upgrade
```
Make it legendary. Optimize for reliability, clarity, and zero-surprise defaults.
List tradeoffs and the smallest safe changes first.
```

### 2) Full review pass
```
Do a full pass: README + code + tests. Fix correctness first, then UX/docs.
Run tests after changes and summarize risks.
```

### 3) Test + docs discipline
```
Rebuild tests for updated scope/spec, run them, then update README and cheatsheet.
```

### 4) Release + Homebrew cycle
```
Complete the full release cycle:
1) run tests
2) commit + push
3) create release
4) update tap + SHA
5) brew upgrade locally
6) verify with brew info
```

### 5) Homebrew vendoring
```
Move to Homebrew vendored resources. Generate resource blocks, update formula,
and verify brew install. Call out optional deps explicitly.
```

### 6) Web UI hardening
```
Harden the web UI: validate inputs, prevent non-interactive failures,
and add clear user feedback. Keep it local-only safe by default.
```

### 7) Documentation audit
```
Review README for accuracy, missing info, and drift from actual behavior.
Update to match install paths and runtime requirements.
```

## Canonical process

### A) Plan
1) Define the goal and decision points.
2) Choose the minimal safe option.
3) Outline the change list and test scope.

### B) Implement
1) Update code and tests.
2) Update README/cheatsheet.
3) Run tests and capture results.

### C) Release + distribution
1) Bump version.
2) Commit + push.
3) Create release.
4) Update Homebrew tap + SHA.
5) `brew upgrade cbc-radio-cli`.
6) Verify with `brew info cbc-radio-cli`.

### D) Post-release verification
1) Smoke test CLI.
2) Smoke test web UI.
3) Confirm install guidance still matches behavior.
