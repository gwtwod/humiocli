# Changelog

## [Unreleased]

### Added

### Changed

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
