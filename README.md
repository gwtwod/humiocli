# Do things with the Humio API from the command line

> This project requires `Python>=3.6.1`

This is a companion CLI to the unofficial [humioapi](https://github.com/gwtwod/humioapi) library. It lets you use most of its features easily from the command line. If you're looking for the official CLI it can be found [here: humiolib](https://github.com/humio/python-humio).

## Installation

```bash
python3 -m pip install humiocli
# or even better
pipx install humiocli
```

## Main features

* Streaming searches with several output formats
* Subsearches (pipe output from one search into a new search)
* Defaults configured through ENV variables (precedence: `shell options` > `shell environment` > `config-file`)
* Splunk-like chainable relative time modifiers
* Switch easily from browser to CLI by passing the search URL to urlsearch
* Ingest data to Humio (but you should use Filebeat for serious things)
* List repositories

## First time setup

Start the guided setup wizard to configure your environment

```bash
hc wizard
```

This will help you create an environment file with a default Humio URL and token, so you don't have to explicitly provide them as options later.

All options may be provided by environment variables on the format
`HUMIO_<OPTION>=<VALUE>`. If a .env file exists in `~/.config/humio/.env` it
will be automatically sourced on execution without overwriting the
existing environment.

## Examples

### Execute a search in all repos starting with `reponame` and output `@rawstring`s

```bash
hc search --repo 'reponame*' '#type=accesslog statuscode>=400'
```

### Execute a search using results with fields from another search ("subsearch")

#### Step 1: Set the output format to `or-fields`

```bash
hc search --repo=auth 'username | select([session_id, app_name])' --outformat=or-fields | jq '.'
```

This gives a JSON-structure with prepared search strings from all field-value combinations. The special field `SUBSEARCH` combines all search strings for all fields.

Example output:

```json
{
  "session_id": "\"session_id\"=\"5CF4A111\" or \"session_id\"=\"14C8BCEA\"",
  "app_name": "\"app_name\"=\"frontend\"",
  "SUBSEARCH": "(\"session_id\"=\"5CF4A111\" or \"session_id\"=\"14C8BCEA\") and (\"app_name\"=\"frontend\")"
}
```

#### Step 2: Pipe this result to a new search and reference the desired fields:

```bash
hc search --repo=auth 'username | select([session_id, app_name])' --outformat=or-fields | hc --repo=frontend '#type=accesslog {{session_id}}'
```

### Output aggregated results as ND-JSON events

Simple example:

> _Humios bucketing currently creates partial buckets in both ends depending on search period. You may want to provide a rounded start and stop to ensure we only get whole buckets._

```bash
hc search --repo 'sandbox*' --start=-60m@m --stop=@m "#type=accesslog | timechart(span=1m, series=statuscode)"
```

Or with a longer multiline search

```bash
hc search --repo 'sandbox*' --start -60m@m --stop=@m  "$(cat << EOF
#type=accesslog
| case {
    statuscode<=400 | status_ok := 1 ;
    statuscode=4*  | status_client_error := "client_error" ;
    statuscode=5*  | status_server_error := "server_error" ;
    * | status_broken := 1
}
| bucket(limit=50, function=[count(as="count"), count(field=status_ok, as="ok"), count(field=status_client_error, as="client_error"), count(field=status_server_error, as="server_error")])
| error_percentage := (((client_error + server_error) / count) * 100)
EOF
)"
```

### Upload a parser file to the destination repository, overwriting any existing parser

```bash
hc makeparser --repo='sandbox*' customjson
```

### Ingest a single-line log file with an ingest-token associated with a parser

```bash
hc ingest customjson
```

### Ingest a multi-line file with a user provided record separator (markdown headers) and parser

```bash
hc ingest README.md --separator '^#' --fields '{"#repo":"sandbox", "#type":"markdown", "@host":"localhost"}'
```

## Development

To install the cli and api packages in editable mode:

```bash
git clone https://github.com/gwtwod/humiocli.git
poetry install
```

## Create self-contained executables for easy distribution

This uses [Shiv](https://github.com/linkedin/shiv) to create a `zipapp`. A single self-contained file with all python dependencies and a shebang.

On first run, this will unpack the required modues to `~/.shiv/hc/` which will cause a short delay in startup. Subsequent runs should be fast however. The location can be controlled with the env variable `SHIV_ROOT`. You should probably clean this directory once in a while, since a new one is created every time the distributable changes.

```bash
pip install shiv
shiv -c hc -o hc humiocli -p "/usr/bin/env python3"
```
