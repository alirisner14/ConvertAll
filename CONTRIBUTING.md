# Contributing to ConvertAll

Thanks for taking the time. Bug reports, accessibility feedback and pull
requests are all welcome.

## Getting set up

```bash
git clone https://github.com/alirisner14/ConvertAll.git
cd ConvertAll
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
source .venv/bin/activate           # macOS / Linux
pip install -r requirements.txt -r requirements-dev.txt
```

Run the app with `python -m convertall`, or press <kbd>F5</kbd> in VS Code.

## Before you open a pull request

```bash
ruff check .        # lint - must pass
ruff format .       # formatting - must be clean
pytest              # tests - must pass
```

CI runs exactly these three on Windows, macOS and Linux. If you touched the
GUI, also run `python tools/screenshot.py` - it builds every panel, switches
palettes and text scales, and fails on any exception, so it doubles as a GUI
smoke test.

## How the project is organised

The rule that matters: **`convertall/core/` never imports the GUI.**

Every pipeline is a plain function that takes paths, returns a `TaskResult`, and
can be tested without a display. The GUI's only job is to collect a file list
and some options, hand them to `JobRunner`, and render what comes back. If you
find yourself wanting to import `tkinter` inside `core/`, that is a sign the
logic belongs in the panel instead.

| Where | What belongs there |
| --- | --- |
| `convertall/core/` | Conversion, tracing, splitting, compression |
| `convertall/app.py` | Window, tool panels, event loop |
| `convertall/widgets.py` | Reusable accessible controls |
| `convertall/theme.py` | Palettes and the type scale |
| `convertall/jobs.py` | Threading and the event queue |
| `tools/` | Developer scripts, not shipped behaviour |

## Adding a new tool

1. Write the pipeline in `convertall/core/` as a function taking
   `(src: Path, out_dir: Path, ..., log=None) -> TaskResult`.
2. Add tests for it in `tests/`.
3. Subclass `ToolPanel` in `app.py`, set the class attributes (`key`, `title`,
   `description`, `accepted`, `action_text`), implement `build_options` and
   `make_job`, and append it to `PANELS`.

The sidebar, shortcuts, file handling, output folder, progress and logging all
come from the base class - you should not need to touch them.

## Accessibility requirements

These are not optional; a pull request that regresses them will not be merged.

- **Contrast.** Body text must clear WCAG AA (4.5:1) against its background in
  both palettes. Add new colours to `theme.py` with the measured ratio in a
  comment, the way the existing entries do.
- **Keyboard.** Every new control must be reachable with Tab and activatable
  with Enter or Space. Use `AccessibleButton`, `option_menu` and `checkbox`
  from `widgets.py` and you get this for free.
- **Focus is not hover.** Keep the cyan focus ring visually distinct from the
  amber hover state.
- **No tooltips for essential information.** Use a visible help line - pass
  `hint=` to `ToolPanel.row()`.
- **Text scaling.** Check your panel at 160% (`Ctrl` + `+` five times). Nothing
  may be clipped or overlap.

## Commit messages and versioning

Write commit subjects in the imperative: "Add HEIC batch limit", not "Added" or
"Adds". ConvertAll follows [Semantic Versioning](https://semver.org/); add a
line to the `Unreleased` section of [CHANGELOG.md](CHANGELOG.md) describing any
user-visible change.

## Reporting bugs

Open an issue with the template. For a conversion problem, please attach or
describe an input file that reproduces it - "HEIC from an iPhone 15, 4032x3024"
is far more useful than "HEIC doesn't work".

Security problems go through [SECURITY.md](SECURITY.md) instead, not the public
issue tracker.
