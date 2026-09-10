## What does this change?

<!-- A sentence or two. Link the issue it closes, e.g. "Closes #12". -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Accessibility improvement
- [ ] Documentation
- [ ] Refactor / maintenance

## Checklist

- [ ] `ruff check .` passes
- [ ] `ruff format .` leaves no changes
- [ ] `pytest` passes
- [ ] New behaviour has tests
- [ ] `CHANGELOG.md` has an entry under `Unreleased` (user-visible changes only)

## If this touches the GUI

- [ ] `python tools/screenshot.py` runs clean
- [ ] Every new control is reachable with Tab and activates with Enter or Space
- [ ] New colours clear WCAG AA in both palettes, with the ratio noted in `theme.py`
- [ ] Checked at 160% text scale - nothing clipped or overlapping

## If this touches a conversion pipeline

- [ ] Output was opened and visually or audibly verified, not just size-checked
- [ ] Existing files are still never overwritten
