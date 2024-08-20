# Change Log

## 0.0.18 - 2024-08-20

### Added
- The `--debug` option.

### Changed
- `dacreate` now creates a standard `.gitignore` file.
- `dawatchinstall` replaced with `dainstall --watch`.
- When uploading to the Playground, `dainstall --watch` uploads only
  the file or files that changed, instead of uploading the whole
  package. It also uses checksums to verify that the content of the
  file actually changed.

## 0.0.17 - 2023-12-20

### Fixed
- Added `packaging` as a dependency.

## 0.0.16 - 2023-12-20

### Changed
- When deciding whether to restart, look at dependencies.

## 0.0.15 - 2023-12-03

### Fixed
- Bug in a line that raised an exception.

## 0.0.14 - 2023-12-03

### Added
- Additional documentation.

## 0.0.13 - 2023-11-05

### Added
- `dacreate` command.

### Fixed
- The ZIP files were not using compression.
- Bug in a line that raised an exception.

## 0.0.12 - 2023-01-30

### Changed
- Avoid additional types of temporary files.

## 0.0.11 - 2022-12-01

### Changed
- If the `project` does not exist, create it.
- Avoid additional types of temporary files.

## 0.0.10 - 2022-06-24

### Changed
- Avoid additional types of temporary files.

### Fixed
- Fixed issue with waiting for server when Playground is used.

## 0.0.9 - 2022-05-14

### Changed
- Switched `dawatchinstall` from `inotifywait` to `fswatch` for MacOS
  compatibility.
- If a restart is triggered, script will wait for the server to restart.

## 0.0.8 - 2022-03-01

### Changed
- Added instructions for running on Windows Subsystem for Linux.

## 0.0.7 - 2021-03-23

### Added
- Automatic installation of the `dawatchinstall` script.

## 0.0.6 - 2021-03-23

### Added
- The `dawatchinstall` script.

## 0.0.5 - 2021-03-15

### Added
- The `--playground` option.

## 0.0.4 - 2021-02-27

Initial version
