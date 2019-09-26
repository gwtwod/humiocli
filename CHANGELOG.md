# Changelog

## [Unreleased]

### Added

- A Changelog! :)
- The `search` subcommand has a new outformat `table`. Filter out fields beforehand with the `select()` function in Humio and pipe to `less -S` for readability if output is wide.
- The `repo` subcommand now has an outformat option.

### Changed

- The `repo` subcommand now lists views as well. The filter option now provides a regex pattern to filter out matching names. By default this option removes -qa and -test suffixes.
- The `repo` subcommand's filter option has changed to `ignore`. Takes a regex-pattern matching repo names to ignore. By default all names ending with -test or -qa are ignored. Disabled if empty.
- Turned sorting off by default to take advantage of streaming searches.
- Bumped project dependencies.

### Deprecated

- The --asyncronous option to search is gone. All searches are now syncronously streaming.

### Removed

- Various noisy logging output.
