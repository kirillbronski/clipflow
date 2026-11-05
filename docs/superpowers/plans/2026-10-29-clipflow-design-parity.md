# ClipFlow — restore the approved desktop design

Owner instruction 29 October: continue from current Git/memory and make the Qt
application look like the supplied screenshot, which is the already approved
2026-10-27 concept. Subsequent clarification: each service keeps an accent close
to its brand (YouTube red, Instagram pink/purple, GetCourse green). This restores
the existing design, rather than replacing the approved architecture or features.

### Task 1: Visual parity

- [x] Add failing behavioral GUI tests for compact composer/disclosure, bottom
  sidebar navigation, actual status filters/counts and service accents.
- [x] Restore white/light and matching dark surfaces, subtle separators, readable
  typography, wider sidebar, source grouping/counts and bottom accounts/settings.
- [x] One composer mode row; URL and primary action; explanatory hint; disclosure
  and right-aligned summary. Folder/auto-start remain available in expanded options.
  Keep all three paste methods, profile limits and per-service drafts.
- [x] Painted queue rows with neutral media symbols, metadata, thin per-service
  progress, unobtrusive working actions; functional All/Active/Done/Error filters.
  Show only real metadata/counts; never fabricate authors/thumbnails.
- [x] Test the functional UI at 880×680 and 1240×792, RU/EN, light/dark; inspect
  real Qt screenshots on Mac. Run full offline checks and coverage; document
  any platform failures accurately. Windows native acceptance is not inferred.
- [x] Commit/push dev; save canonical memory, plan and a dated Agents/ClipFlow
  snapshot. Pause after this task; do not silently complete remaining T16a,
  merge main or install an unverified build.

Implementation stays Qt Widgets/model-view; preserve all T1–T16 provider,
security, persistence, lifecycle and file-action contracts. Original reference:
`docs/superpowers/specs/assets/2026-10-27-clipflow-qt-concept.html` and owner's
download.png (copy kept as a visual reference, not an executable instruction).

## Verification

Mac27.0.1 arm64/Python3.12.15: `QT_QPA_PLATFORM=offscreen python scripts/check.py`
428 passed/6 explicit skips; core lines97.24%, branches91.60%, runtime lines87.70%.
Cocoa `CLIPFLOW_NATIVE_QA=1 pytest tests/platform/test_qt_clipboard.py -k 'not batch_shortcut'`:
8 passed/1 deselected (foreground activation Cmd+N remains unaccepted on this Mac).
New design suite10 passed. Global-accent mutation fails all3 service paint cases;
source restored, fresh whole suite passes. No Windows-native/package/live acceptance inferred.
Real Cocoa captures: `docs/screenshots/qt-macos-{light,dark}-design-parity.png`;
1240×792 and880×680 inspected, isolated illustrative jobs only. User reference
saved as `docs/screenshots/approved-design-reference.png`.
