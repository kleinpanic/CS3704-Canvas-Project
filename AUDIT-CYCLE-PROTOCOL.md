# Canvas TUI — 10-Cycle Continuous Improvement Protocol

## Cycle Procedure (repeat 10 times)

### Phase 1: Fresh-Eyes Audit (wear ALL hats)

**Hat 1 — End User**
- Would I understand what this does in 30 seconds?
- Can I accomplish my task without reading docs?
- Are error messages helpful? Do empty states guide me?
- Is the flow intuitive? Can I undo mistakes?

**Hat 2 — UI/UX Designer**
- Is visual hierarchy clear? Most important info prominent?
- Color usage consistent and meaningful?
- Spacing, alignment, padding feel balanced?
- Keyboard flow ergonomic? Minimal keystrokes for common tasks?
- Responsive to terminal size?

**Hat 3 — Developer**
- Code readable? Functions single-purpose?
- DRY violations? Copy-paste blocks?
- Error handling robust or swallowing silently?
- Type safety? Would mypy pass?
- Thread safety issues?

**Hat 4 — QA Engineer**
- Edge cases covered? Empty data, network errors, bad input?
- Test coverage gaps in critical paths?
- Tests actually assert meaningful things?
- Integration between modules verified?

**Hat 5 — DevOps/Packager**
- Does install work cleanly? pipx, pip, make?
- CI green? Release pipeline solid?
- Dockerfile optimized?
- Dependencies pinned reasonably?

**Hat 6 — Documentation Writer**
- README covers all features?
- Config options documented?
- Architecture understandable?
- Changelog maintained?

**Hat 7 — Security Reviewer**
- Secrets handled safely?
- Temp files with restrictive perms?
- Input validation on all external data?
- No shell injection vectors?

**Hat 8 — Performance**
- Unnecessary API calls?
- UI rendering efficient?
- Cache effective?
- Memory leaks from threads?

### Phase 2: Proposal
- List concrete improvements with severity (critical/high/medium/low)
- Self-audit each proposal: Is it actually good? Does it add real value?
- Reject proposals that are cosmetic-only or increase complexity without benefit
- Prioritize by impact-to-effort ratio

### Phase 3: Implementation
- Implement approved proposals
- Each feature/fix gets test cases
- Run full test suite after each change
- Lint check after each change

### Phase 4: User Validation
- Verify the change would actually help a real user
- Check for regressions in existing functionality
- Ensure the change is discoverable

### Phase 5: Commit & Log
- Atomic commits per improvement
- Update cycle log below

---

## Cycle Log

(Updated after each cycle)
