# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

### Deprecated

### Removed

## [0.8.1] - 2021-02-18

### Changed

- Bump `humioapi` to 0.8.2. APIs are now based on `humiolib` (wrapped by `humioapi`). This means several commands have changed slightly. All HTTP requests are now done through `requests` rather than `httpx`.
- The `search` command no longer allows multiple repos. Use `humio-search-all` or a view instead. Reponame pattern related options are also removed due to this.
- The `ingest` command now accept tags and parser as options.

### Removed

- Some short-option flags for little used options.

## [0.8.0] - 2021-01-31

### Changed

- Bump `humioapi` to 0.7.0. Switches networking backend from `httpcore` to `urllib3` as a temporary measure for weird HTTP 502s in Humio 1.18


## [0.7.3] - 2020-09-24

### Changed

- Bump `humioapi` to 0.6.1. Adds coloring to trace logging level (used by `httpx`) so colored console logging doesn't break with very verbose output.
- Add environment variable info to help strings


## [0.7.2] - 2020-09-23

### Changed

- More intuitive verbose flag. Unset is logging.WARN, -v is logging-INFO, -vv is logging.DEBUG, -vvv is logging.NOTSET.
- Bump humioapi to 0.6.0 Increases timeouts to 30 seconds by default in searches (httpx had 5 seconds default).
- Use wider help output (from 79 to 120 characters)


## [0.7.1] - 2020-09-01

### Added

### Changed

- Only write (to stderr) humio URLs after searches that attached to a TTY

### Deprecated

### Removed


## [0.7.0] - 2020-08-30

### Added

### Changed

- Added `ipython` output mode to `repo` and `search` commands which drops you into an ipython session where the results are made available. Furure enhancements pending. (jupyter-notebook and simple visualizations perhaps?)
- Fixed some overzealous find/replace in the readme
- Updated Shiv build instructions

### Deprecated

### Removed


## [0.6.0] - 2020-08-29

### Added

### Changed

- Renamed `end` parameters to `stop` everywhere
- Allow use of "sandbox" repo name without specifying the whole sandbox ID or wildcare-use
- Make `repo --outformat=raw` output JSON rather than just python repr()

### Deprecated

### Removed


## [0.5.0] - 2019-09-26

### Added

- A Changelog! :)
- The `search` subcommand has a new outformat `table`. Filter out fields beforehand with the `select()` function in Humio and pipe to `less -S` for readability if output is wide.
- The `repo` subcommand now has an outformat option.
- Subcommands that take a `--repo` option now accept view names.
  - View names must match exactly, unless `--no-strict-views` is set.
  - In addition these subcommands also take a `--ignore-repo` regex string with repository names to ignore. By default the suffixes `-qa` and `-test` are ignored. Pass the empty string to disable.

### Changed

- The `repo` subcommand now lists views
- Turned sorting off by default to take advantage of streaming searches.
- Bumped project dependencies.

### Deprecated

- The --asyncronous option to search is gone. All searches are now syncronously streaming.

### Removed

- Various noisy logging output.
