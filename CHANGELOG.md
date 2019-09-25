# Changelog

## [Unreleased]

### Added

- A Changelog! :)
- Table outputformat, filter out fields beforehand with the `select()` function in Humio and pipe to `less -S` for readability if output is wide

### Changed

- Turned sorting off by default to take advantage of streaming searches
- Bumped project dependencies

### Deprecated

- The --asyncronous option to search is gone. All searches are now syncronously streaming.

### Removed

- Various noisy logging output
