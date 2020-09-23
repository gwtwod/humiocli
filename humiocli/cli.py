#!/usr/bin/env python3

import json
import sys
import os
import re
import shlex
import subprocess
from pathlib import Path

import click
import colorama
import pendulum
import structlog
import logging
import tzlocal
from pygments.styles import get_all_styles
from tabulate import tabulate

import humioapi
from humiocli import prettyxml, utils

# Make environment variables available
humioapi.loadenv()

logger = structlog.getLogger(__name__)


class AliasedGroup(click.Group):
    """Helper class for expanding partial command names to matching commands"""

    def get_command(self, ctx, cmd_name):

        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv

        matches = [x for x in self.list_commands(ctx) if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail("Too many matches: %s" % ", ".join(sorted(matches)))


@click.group(cls=AliasedGroup, context_settings=dict(help_option_names=["-h", "--help"], max_content_width=120))
@click.option(
    "-v",
    "verbosity",
    envvar="HUMIO_VERBOSITY",
    count=True,
    default=0,
    help="Set logging level. Repeat to increase verbosity. [default: errors and warnings]"
)
def cli(verbosity):
    """
    Humio CLI for working with the Humio API.

    For detailed help about each command try:

        hc COMMAND --help

    All options may be provided by environment variables on the format
    `HUMIO_<OPTION>=<VALUE>`. If a .env file exists at `~/.config/humio/.env` it will be
    automatically sourced on execution without overwriting the existing environment.
    """

    level_map = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
        3: logging.NOTSET
    }
    humioapi.initialize_logging(fmt="human", level=level_map[verbosity])


@cli.command(short_help="Search for data in Humio")
@click.option(
    "--base-url",
    "-b",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--token",
    "-t",
    envvar="HUMIO_TOKEN",
    required=True,
    help="Your *secret* API token found in your account settings",
)
@click.option(
    "--repo",
    "-r",
    "repo_",
    envvar="HUMIO_REPO",
    multiple=True,
    default=["sandbox_*"],
    show_default=True,
    help="Name of repository or view, supports wildcards and multiple options. View names must "
    "match the pattern exactly unless --no-strict-views is set.",
)
@click.option(
    "--ignore-repo",
    "-i",
    "ignore_repo",
    envvar="HUMIO_IGNORE_REPO",
    default="(-qa|-test)$",
    show_default=True,
    required=False,
    type=str,
    help="Ignore repositories and views with names matching the provided pattern. Pass the empty "
    "string to disable this option.",
)
@click.option(
    "--strict-views/--no-strict-views",
    envvar="HUMIO_STRICT_VIEWS",
    required=False,
    default=True,
    show_default=True,
    help="Require view names (special repos that include one or more repos) to match exactly",
)
@click.option(
    "--start",
    "-s",
    envvar="HUMIO_START",
    default="@d",
    show_default=True,
    metavar="SNAPTIME/TIMESTRING",
    help="Begin search at this snaptime or common timestring",
)
@click.option(
    "--stop",
    "-e",
    envvar="HUMIO_STOP",
    default="now",
    show_default=True,
    metavar="SNAPTIME/TIMESTRING",
    help="Stop search at this snaptime or common timestring",
)
@click.option(
    "--color",
    "-c",
    envvar="HUMIO_COLOR",
    default="auto",
    type=click.Choice(["auto", "always", "never"]),
    show_default=True,
    help="Colorize logging and known @rawstring formats",
)
@click.option(
    "--outformat",
    "-o",
    envvar="HUMIO_OUTFORMAT",
    type=click.Choice(["pretty", "raw", "ndjson", "table", "or-values", "or-fields", "ipython"]),
    default="pretty",
    show_default=True,
    help="Output format when emitting events. Pretty and raw outputs @rawstrings with "
    "fallback to ND-JSON. Table will output an aligned table. The or-values and or-fields "
    "choices will produce search filter strings for use in new searches, for example by "
    "piping to a new search with --fields read from stdin",
)
@click.option(
    "--sort",
    "-S",
    envvar="HUMIO_SORT",
    default="",
    show_default=True,
    metavar="FIELDNAME/<EMPTY>",
    help="Field to sort results by. Pass the empty string to disable. Sorting requires holding "
    "all results in memory, so consider sorting large datasets in Humio instead",
)
@click.option(
    "--fields",
    "-f",
    envvar="HUMIO_FIELDS",
    required=False,
    metavar="JSON",
    help="Optional fields to inject into the QUERY where wherever a token {{field}} occurs. "
    "Input must be provided as JSON document. Using this option will disable waiting for fields "
    "from STDIN when the QUERY contains tokens",
)
@click.option(
    "--style",
    envvar="HUMIO_STYLE",
    default="paraiso-dark",
    type=click.Choice(
        sorted(
            set(get_all_styles()).intersection(
                {
                    "paraiso-dark",
                    "paraiso-light",
                    "solarized-dark",
                    "solarized-light",
                    "tango",
                    "bw",
                    "monokai",
                }
            )
        )
    ),
    show_default=True,
    help="Pygments style to use when syntax-highlighting",
)
@click.argument("query", envvar="HUMIO_QUERY")
def search(
    base_url,
    token,
    repo_,
    ignore_repo,
    strict_views,
    start,
    stop,
    color,
    outformat,
    sort,
    fields,
    style,
    query,
):
    """
    Execute a QUERY against the Humio API in the provided time range. QUERY may contain optional
    tokens to inject provided fields into the query wherever `{{field}}` occurs. These fields must
    be provided as one line of JSON data to STDIN or through the --fields option.

    Time may be a valid snaptime-identifier (-60m@m) or a common timestamp
    such as ISO8859. Timestamps may be partial. 10:00 means today at 10:00.

    Rawstrings are prettified and syntax-highlighted by default while aggregated
    searches provide ND-JSON results
    """

    utils.color_init(color)

    # Check for tokens in the query string and load fields if necessary
    token_pattern = re.compile(r"\{\{ *(?P<token>[@#._]?[\w.-]+) *\}\}")
    tokens = token_pattern.findall(query)
    if tokens:
        logger.debug("Query contains valid tokens, loading provided JSON fields", tokens=tokens)
        if fields:
            logger.debug("JSON-data read from --fields", json=fields)
            fields = json.loads(fields)
        else:
            logger.debug("Expecting one line of JSON-data from STDIN before proceeding")
            in_stream = click.get_text_stream("stdin").readline()
            logger.debug("JSON-data read from STDIN", json=in_stream)
            fields = json.loads(in_stream)
    else:
        fields = {}

    def token_sub(matchobj):
        if matchobj.group(1) in fields:
            return fields.get(matchobj.group(1))
        return matchobj.group(0)

    query = token_pattern.sub(token_sub, query)
    logger.info("Prepared query", query=query, repo=repo_, fields=json.dumps(fields))

    client = humioapi.HumioAPI(base_url=base_url, token=token)

    target_repos = [
        name
        for name in utils.filter_repositories(
            client.repositories(),
            repo_,
            ignore=ignore_repo,
            strict_views=strict_views,
            read_permission=True,
        )
    ]
    if "sandbox" in repo_:
        # Humio maps sandbox to the current user's sandbox so we shouldn't
        # have to require the full name (sandbox-<some-long-id-here>)
        target_repos.append("sandbox")

    events = client.streaming_search(query, target_repos, start, stop)

    if outformat == "ipython":
        utils.run_ipython({"repositories": target_repos, "client": client, "humioapi": humioapi, "events": events})
        sys.exit(0)

    if outformat == "or-values" or outformat == "or-fields":
        searchstrings = utils.searchstring_from_fields(events, outformat=outformat)
        if searchstrings.get("SUBSEARCH") == "()":
            logger.error("Search did not produce any results, unable to generate search strings")
        else:
            print(json.dumps(searchstrings, ensure_ascii=False))
        sys.exit(0)

    elif outformat == "table":
        print(utils.table_from_events(events))

    else:
        order = lambda x: sorted(events, key=lambda e: e.get(sort, 0)) if sort else x
        for event in order(events):
            if outformat == "ndjson" or "@rawstring" not in event:
                output = json.dumps(event, ensure_ascii=False, sort_keys=True)
            elif outformat == "pretty":
                output = prettyxml.process(event.get("@rawstring"))
            else:
                output = event.get("@rawstring")

            if color == "always" or color == "auto" and sys.stdout.isatty():
                print(utils.highlight(output, style=style))
            else:
                print(output)

    if utils.is_tty():
        for repository in sorted(target_repos):
            url = humioapi.utils.create_humio_url(base_url, repository, query, start, stop, scheme="https")
            click.echo(" > Humio URL: " + click.style(url, fg="green"), err=True)


@cli.command(short_help="List available repositories and views")
@click.option(
    "--base-url",
    "-b",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--token",
    "-t",
    envvar="HUMIO_TOKEN",
    required=True,
    help="Your *secret* API token found in your account settings",
)
@click.option(
    "--color",
    "-c",
    envvar="HUMIO_COLOR",
    default="auto",
    type=click.Choice(["auto", "always", "never"]),
    help="Colorize output",
    show_default=True,
)
@click.option(
    "--ignore-repo",
    "-i",
    "ignore_repo",
    envvar="HUMIO_IGNORE_REPO",
    default="(-qa|-test)$",
    show_default=True,
    required=False,
    type=str,
    help="Ignore repositories and views with names matching the provided pattern. Pass the empty "
    "string to disable this option.",
)
@click.option(
    "--outformat",
    "-o",
    envvar="HUMIO_OUTFORMAT",
    type=click.Choice(["raw", "table", "ipython"]),
    default="table",
    show_default=True,
    help="Output format when emitting repositories and views.",
)
@click.argument("PATTERNS", nargs=-1)
def repo(base_url, token, color, ignore_repo, outformat, patterns):
    """List available repositories and views matching an optional filter."""
    utils.color_init(color)

    client = humioapi.HumioAPI(base_url=base_url, token=token)

    repositories = utils.filter_repositories(client.repositories(), patterns, ignore=ignore_repo, strict_views=False)

    if outformat == "ipython":
        utils.run_ipython({"repositories": repositories, "client": client, "humioapi": humioapi})
        sys.exit(0)

    def _emojify(authorized):
        if authorized:
            return f"{colorama.Fore.GREEN}✓{colorama.Style.RESET_ALL}"
        return f"{colorama.Fore.RED}✗{colorama.Style.RESET_ALL}"

    if outformat == "raw":
        for reponame, meta in sorted(repositories.items()):
            last_ingest = meta.get("last_ingest")
            if last_ingest:
                meta["last_ingest"] = str(last_ingest)
            meta["name"] = reponame
            print(json.dumps(meta))
        sys.exit(0)

    output = []
    for reponame, meta in sorted(repositories.items()):
        readable = meta.get("read_permission", False)
        colorprefix = colorama.Fore.GREEN if readable else colorama.Fore.RED

        try:
            last_ingest = meta.get("last_ingest").in_timezone(tzlocal.get_localzone())
            last_ingest = pendulum.now().diff_for_humans(last_ingest, True) + " ago"
        except (TypeError, AttributeError):
            last_ingest = colorama.Fore.RED + "no events" + colorama.Style.RESET_ALL

        data = {
            "Repository name": colorprefix + reponame + colorama.Style.RESET_ALL,
            "Last ingest": last_ingest,
            "Real size": utils.humanized_bytes(meta.get("uncompressed_bytes")),
            "Read": _emojify(meta.get("read_permission")),
            "Write": _emojify(meta.get("write_permission")),
            "Parsers": _emojify(meta.get("parseradmin_permission")),
            "Alerts": _emojify(meta.get("alertadmin_permission")),
            "Dashboards": _emojify(meta.get("parseradmin_permission")),
            "Queries": _emojify(meta.get("parseradmin_permission")),
            "Files": _emojify(meta.get("parseradmin_permission")),
            "Type": meta.get("type"),
        }
        output.append(data)
    print(tabulate(output, headers="keys"))


@cli.command(short_help="Ingests events from files or STDIN into Humio")
@click.option(
    "--base-url",
    "-b",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--ingest-token",
    "-t",
    envvar="HUMIO_INGEST_TOKEN",
    required=True,
    help="Your *secret* ingest token found in your repository settings",
)
@click.option(
    "--separator",
    "-s",
    envvar="HUMIO_SEPARATOR",
    default="^.",
    help="PATTERN indicating the start of a new event. Assumes single-line if not provided. "
    "For example `^\\d{4}-\\d{2}-\\d{2}[T\\s]\\d{2}:\\d{2}:\\d{2}`",
)
@click.option(
    "--fields",
    "-f",
    envvar="HUMIO_FIELDS",
    required=False,
    default="{}",
    help="Optional fields to send with all events. Must be provided as a parseable JSON object",
)
@click.option(
    "--encoding",
    "-e",
    envvar="HUMIO_ENCODING",
    required=False,
    help="Encoding to use when reading the provided files. Autodetected if not provided",
)
@click.option(
    "--soft-limit",
    "-l",
    envvar="HUMIO_SOFT_LIMIT",
    default=2 ** 20,
    help="Soft limit for messages sent with each POST requests. Messages will throw a warning "
    "and be sent by themselves if they exceed the limit",
)
@click.option(
    "--dry/--no-dry",
    envvar="HUMIO_DRY_RUN",
    required=False,
    default=False,
    help="Prepare ingestion without commiting any changes",
)
@click.argument("ingestfiles", nargs=-1, type=click.Path(exists=True))
def ingest(base_url, ingest_token, separator, fields, encoding, soft_limit, dry, ingestfiles):
    """
    Ingests events from files or STDIN with the provided event separator and ingest token. If no
    ingestfiles are provided events are expected from STDIN.

    If the ingest token is not associated with a parser, a JSON object with the type
    field must minimally be included, for example: {"#type":"parsername", "@host":"server01"}.

    If no encoding is provided chardet will be used to find an appropriate encoding.
    """

    client = humioapi.HumioAPI(base_url=base_url, ingest_token=ingest_token)
    fields = json.loads(fields)

    for ingestfile in ingestfiles:

        if not encoding:
            detected = utils.detect_encoding(ingestfile)
            if detected["confidence"] < 0.9:
                logger.warning(
                    "Detected encoding has low confidence",
                    filedetection=detected,
                    ingestfile=ingestfile,
                )
            if not detected["encoding"]:
                logger.error(
                    "Skipping file with unknown encoding",
                    filedetection=detected,
                    ingestfile=ingestfile,
                )
                continue
            encoding = detected["encoding"]

        with open(ingestfile, "r", encoding=encoding) as ingest_io:
            client.ingest_unstructured(
                utils.readevents_split(ingest_io, sep=separator),
                fields=fields,
                soft_limit=soft_limit,
                dry=dry,
            )

    if not ingestfiles:
        with click.open_file("-", "r") as ingest_stdin:
            client.ingest_unstructured(
                utils.readevents_split(ingest_stdin, sep=separator),
                fields=fields,
                soft_limit=soft_limit,
                dry=dry,
            )


@cli.command(short_help="Upload a parser file to a repo")
@click.option(
    "--base-url",
    "-b",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--token",
    "-t",
    envvar="HUMIO_TOKEN",
    required=True,
    help="Your *secret* API token found in your account settings",
)
@click.option(
    "--repo",
    "-r",
    "repo_",
    envvar="HUMIO_REPO",
    multiple=True,
    default=["sandbox_*"],
    show_default=True,
    help="Name of repository or view, supports wildcards and multiple options. View names must "
    "match the pattern exactly unless --no-strict-views is set.",
)
@click.option(
    "--ignore-repo",
    "-i",
    "ignore_repo",
    envvar="HUMIO_IGNORE_REPO",
    default="(-qa|-test)$",
    show_default=True,
    required=False,
    type=str,
    help="Ignore repositories and views with names matching the provided pattern. Pass the empty "
    "string to disable this option.",
)
@click.option(
    "--strict-views/--no-strict-views",
    envvar="HUMIO_STRICT_VIEWS",
    required=False,
    default=True,
    show_default=True,
    help="Require view names (special repos that include one or more repos) to match exactly",
)
@click.option(
    "--encoding",
    "-e",
    envvar="HUMIO_ENCODING",
    required=False,
    help="Encoding to use when reading the provided files. Autodetected if not provided",
)
@click.argument("parser", nargs=1, type=click.Path(exists=True))
def makeparser(base_url, token, repo_, ignore_repo, strict_views, encoding, parser):
    """
    Takes a parser file and creates or updates a parser with the same name as the file
    in the requested repository (or repositories).

    If no encoding is provided chardet will be used to find an appropriate encoding.
    """

    client = humioapi.HumioAPI(base_url=base_url, token=token)

    target_repos = [
        name
        for name in utils.filter_repositories(
            client.repositories(),
            repo_,
            ignore=ignore_repo,
            strict_views=strict_views,
            parseradmin_permission=True,
        ).keys()
    ]
    if "sandbox" in repo_:
        # Humio maps sandbox to the current user's sandbox so we shouldn't
        # have to require the full name (sandbox-<some-long-id-here>)
        target_repos.append("sandbox")

    if not encoding:
        detected = utils.detect_encoding(parser)
        if detected["confidence"] < 0.9:
            logger.warning("Detected encoding has low confidence", filedetection=detected, parser=parser)
        if not detected["encoding"]:
            logger.error("Skipping file with unknown encoding", filedetection=detected, parser=parser)
            return
        encoding = detected["encoding"]

    with open(parser, "r", encoding=encoding) as parser_io:
        source = parser_io.read()
        client.create_update_parser(repos=target_repos, parser=Path(parser).stem, source=source)


@cli.command(short_help="Start a guided setup process to configure this CLI")
def wizard():
    """
    Start a guided setup process to create/update the configuration file
    """

    env_file = Path.home() / ".config/humio/.env"
    env = humioapi.loadenv(env=env_file)

    message = click.style("You're about to update your configuration file at", fg="green")
    message += f" {env_file}\n"
    click.echo(message=message)

    env["base_url"] = click.prompt(
        click.style("Enter the base URL for your Humio install", fg="green"),
        default=env.get("base_url"),
        type=str,
    )
    env["token"] = click.prompt(
        click.style("Enter your personal Humio token", fg="green"),
        default=env.get("token"),
        type=str,
    )
    env["start"] = click.prompt(
        click.style("Enter your preferred default search start time", fg="green"),
        default=env.get("start", "-2d@d"),
        type=str,
    )
    env["stop"] = click.prompt(
        click.style("Enter your preferred default search stop time", fg="green"),
        default=env.get("stop", "@s"),
        type=str,
    )
    unmanaged = set(env.keys()) - set(["base_url", "token", "start", "stop"])
    if unmanaged:
        click.echo(click.style(f"\nThe following keys are left unmodified: {', '.join(unmanaged)}\n", fg="yellow"))

    os.makedirs(Path.home() / ".config/humio", exist_ok=True)
    with open(env_file, "w+") as config_io:
        for key, value in env.items():
            config_io.write(f"HUMIO_{key.upper()}={value}\n")

    click.echo(
        click.style("You're all set, try", fg="green")
        + click.style(" hc repo ", fg="yellow")
        + click.style("to see whats available 🧙 🎉 🦉", fg="green")
    )


@cli.command(
    name="urlsearch",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
    short_help="Create and execute a search from a Humio URL",
)
@click.option(
    "--dry/--no-dry",
    envvar="HUMIO_DRY_RUN",
    required=False,
    default=False,
    help="Prepare a search command without executing it",
)
@click.argument("url", nargs=1)
@click.pass_context
def urlsearch(ctx, dry, url):
    """
    Create and execute a search command from a Humio search URL. Extra options
    will be passed along to the search command. Use the --dry option to create
    the command without executing it.
    """

    query, repo_, start, stop = humioapi.utils.parse_humio_url(url)
    start = humioapi.utils.tstrip(start.isoformat())
    stop = humioapi.utils.tstrip(stop.isoformat())
    safe_query = shlex.quote(query)

    options = [option.split("=") for option in ctx.args]
    safe_options = ["=".join([opt[0], shlex.quote(opt[1])]) if len(opt) > 1 else opt[0] for opt in options]

    if safe_options:
        command = f'hc search --repo={repo_} --start="{start}" --stop="{stop}" {" ".join(safe_options)} {safe_query}'
    else:
        command = f'hc search --repo={repo_} --start="{start}" --stop="{stop}" {safe_query}'

    click.echo(" > Humio command: " + click.style(command, fg="green"), err=True)

    if not dry:
        subprocess.run(
            ["hc", "search", "--repo", repo_, "--start", str(start), "--stop", str(stop)] + options + [query]
        )


if __name__ == "__main__":
    cli()
