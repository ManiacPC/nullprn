# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-11-18

### Changed
- The tray icon no longer toggles the redirection on left-click. Enabling or
  disabling capture is now done only from the right-click context menu
  ("Active" item), to avoid accidental toggles.

## [1.0.2] - 2026-11-18

### Changed
- Auto-start ("Start with Windows") now creates a shortcut in the user's
  Startup folder (`shell:startup\NullPrn.lnk`) instead of writing the HKCU
  `Run` registry key. Writing the Run key triggered antivirus behavioural
  heuristics (e.g. Kaspersky `PDM:Trojan.Win32.Generic`) and could cause the
  process to be terminated; the shortcut approach is user-visible and avoids
  that false positive. The shortcut is not recreated if it already exists.

### Docs
- Added an "Antivirus note" to the README and a real tray-menu screenshot.

## [1.0.1] - 2026-11-18

### Fixed
- Enforce a single running instance via an OS-level file lock
  (`%TEMP%\nullprn.lock`). Launching NullPrn twice previously started
  multiple tray instances; a second launch now shows an "already running"
  message and exits. The lock is released automatically on exit or crash.

## [1.0.0] - 2026-11-18

### Added
- Initial release.
- Redirect a legacy/parallel port (LPT1 by default) to the Windows null
  device via `DefineDosDevice`, so legacy software printing to LPT1/USB001
  no longer fails on Windows 10/11.
- `--port` option (repeatable) to redirect multiple ports at once.
- `--target` option to discard output (`nul`) or capture printed data to a file.
- "Start with Windows" auto-start toggle (HKCU Run key).
- System tray app with on/off toggle and embedded icon.
- `test_lpt1.py` helper to verify redirection.
- README, MIT license, `requirements.txt`, and `build.bat`.

[1.0.3]: https://github.com/ManiacPC/nullprn/releases/tag/v1.0.3
[1.0.2]: https://github.com/ManiacPC/nullprn/releases/tag/v1.0.2
[1.0.1]: https://github.com/ManiacPC/nullprn/releases/tag/v1.0.1
[1.0.0]: https://github.com/ManiacPC/nullprn/releases/tag/v1.0.0
