#!/usr/bin/env python3

import json
import sys
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path

import click
import colorama
import humiocore
import pendulum
import structlog
import tzlocal
from click_default_group import DefaultGroup
from pygments.styles import get_all_styles
from tabulate import tabulate

from . import prettyxml, utils

# Make environment variables available
humiocore.loadenv()

logger = structlog.getLogger(__name__)
# Restore original stdout after Colorama rudely overwrites it through Structlog
sys.stdout = sys.__stdout__
humiocore.setup_excellent_logging("INFO")


@click.group(cls=DefaultGroup, default="search", default_if_no_args=True)
def cli():
    """
    Humio CLI for working with the humio API. Defaults to the search command.

    For detailed help about each command try:

        hc <command> --help

    All options may be provided by environment variables on the format
    `HUMIO_<OPTION>=<VALUE>`. If a .env file exists at `~/.config/humio/.env` it will be
    automatically sourced on execution without overwriting the existing environment.
    """


@cli.command()
@click.option(
    "--base-url",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--token",
    envvar="HUMIO_TOKEN",
    required=True,
    help="Your *secret* API token found in your account settings",
)
@click.option(
    "--repo",
    "repo_",
    envvar="HUMIO_REPO",
    multiple=True,
    default=["sandbox"],
    help="Name of repository or view, supports wildcards and multiple options",
    show_default=True,
)
@click.option(
    "--start",
    envvar="HUMIO_START",
    default="@d",
    metavar="SNAPTIME/TIMESTRING",
    help="Begin search at this snaptime or common timestring",
    show_default=True,
)
@click.option(
    "--end",
    envvar="HUMIO_END",
    default="now",
    metavar="SNAPTIME/TIMESTRING",
    help="End search at this snaptime or common timestring",
    show_default=True,
)
@click.option(
    "--color",
    envvar="HUMIO_COLOR",
    default="auto",
    type=click.Choice(["auto", "always", "never"]),
    help="Colorize logging and known @rawstring formats",
    show_default=True,
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
    help="Pygments style to use when syntax-highlighting",
    show_default=True,
)
@click.option(
    "--outformat",
    envvar="HUMIO_OUTFORMAT",
    type=click.Choice(["pretty", "raw", "ndjson", "or-values", "or-fields"]),
    default="pretty",
    show_default=True,
    help="Output format when emitting events. Pretty and raw outputs @rawstrings with "
    "fallback to ND-JSON. or-values and or-fields will output search filter strings for use "
    "in new searches, for example by piping to a new search with --fields read from stdin",
)
@click.option(
    "--sort",
    envvar="HUMIO_SORT",
    default="@timestamp",
    metavar="FIELDNAME/<EMPTY>",
    help="Field to sort results by, pass the empty string to disable",
    show_default=True,
)
@click.option(
    "--asyncronous/--syncronous",
    envvar="HUMIO_ASYNCRONOUS",
    default=True,
    help="Run searches asyncronously or syncronously. Syncronous searches are streaming and will "
    "allow results that do not fit in memory if sorting is disabled (--sort='')",
    show_default=True,
)
@click.option(
    "--fields",
    envvar="HUMIO_FIELDS",
    required=False,
    default="{}",
    metavar="JSON",
    help="Optional fields to inject into the query using the Python formatting mini-language "
    "wherever a formatting token {field} occurs. Input must be provided as JSON document. "
    "If a `-` (dash) is given, wait for and parse a single line from STDIN as JSON.",
)
@click.argument("query", envvar="HUMIO_QUERY")
def search(
    base_url, token, repo_, start, end, color, style, outformat, sort, asyncronous, fields, query
):
    """
    Execute a Humio-search in the provided time range.

    Time may be a valid snaptime-identifier (-60m@m) or a common timestamp
    such as ISO8859. Timestamps may be partial. 10:00 means today at 10:00.

    Rawstrings are prettified and syntax-highlighted by default while aggregated
    searches provide ND-JSON results
    """

    utils.color_init(color)

    start = utils.parse_ts(start)
    end = utils.parse_ts(end)

    # Load and interpolate any passed fields into the query string
    if fields == "-":
        fields = json.loads(click.get_text_stream("stdin").readline())
    else:
        fields = json.loads(fields)
    query = query.format(**fields)

    client = humiocore.HumioAPI(base_url=base_url, token=token)

    matches = lambda x: any(
        [fnmatch(x, pattern) for pattern in repo_]  # pylint: disable=not-an-iterable
    )
    target_repos = set(
        [
            reponame
            for reponame, meta in client.repositories().items()
            if meta.get("read_permission") and matches(reponame)
        ]
    )

    if asyncronous:
        events = client.async_search(query, target_repos, start, end)
    else:
        events = client.streaming_search(query, target_repos, start, end)

    if outformat == "or-values" or outformat == "or-fields":
        if outformat == "or-values":
            template = "{value}"
        else:
            template = "{field}={value}"

        data = defaultdict(set)
        for event in events:
            for field, value in event.items():
                if field in ["@timestamp", "@rawstring"]:
                    continue
                data[field].add(template.format(field=json.dumps(field), value=json.dumps(value)))
        if len(data.keys()) > 5:
            logger.warning(
                "The emitted searching includes more than 5 fields, did you forget select relevant fields?",
                fields=sorted(data.keys()),
            )
        data = {key: " or ".join(values) for key, values in data.items()}
        data["SUBSEARCH"] = "(" + ") and (".join([value for key, value in data.items()]) + ")"
        print(json.dumps(data))

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


@cli.command()
@click.option(
    "--base-url",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--token",
    envvar="HUMIO_TOKEN",
    required=True,
    help="Your *secret* API token found in your account settings",
)
@click.option(
    "--color",
    envvar="HUMIO_COLOR",
    default="auto",
    type=click.Choice(["auto", "always", "never"]),
    help="Colorize output",
    show_default=True,
)
@click.option(
    "--filter",
    "filter_",
    envvar="HUMIO_FILTER",
    required=False,
    type=click.Choice(["read", "noread"]),
    help="Only list repos with or without read access",
)
def repo(base_url, token, color, filter_):
    """List available repositories and views matching an optional filter."""
    utils.color_init(color)

    client = humiocore.HumioAPI(base_url=base_url, token=token)
    repositories = client.repositories()

    def _boolemoji(authorized):
        if authorized:
            return f"{colorama.Fore.GREEN}✓{colorama.Style.RESET_ALL}"
        else:
            return f"{colorama.Fore.RED}✗{colorama.Style.RESET_ALL}"

    output = []
    for reponame, meta in sorted(repositories.items()):
        readable = meta.get("read_permission", False)

        if filter_ == "read" and not readable:
            continue
        if filter_ == "noread" and readable:
            continue
        colorprefix = colorama.Fore.GREEN if readable else colorama.Fore.RED

        try:
            last_ingest = meta.get("last_ingest").tz_convert(tzlocal.get_localzone())
            last_ingest = pendulum.parse(str(last_ingest))
            last_ingest = pendulum.now().diff_for_humans(last_ingest, True) + " ago"
        except (TypeError, AttributeError):
            last_ingest = colorama.Fore.RED + "no events" + colorama.Style.RESET_ALL

        data = {
            "Repository name": colorprefix + reponame + colorama.Style.RESET_ALL,
            "Last ingest": last_ingest,
            "Real size": utils.humanized_bytes(meta.get("uncompressed_bytes")),
            "Read": _boolemoji(meta.get("read_permission")),
            "Write": _boolemoji(meta.get("write_permission")),
            "Parsers": _boolemoji(meta.get("parseradmin_permission")),
            "Alerts": _boolemoji(meta.get("alertadmin_permission")),
            "Dashboards": _boolemoji(meta.get("parseradmin_permission")),
            "Queries": _boolemoji(meta.get("parseradmin_permission")),
            "Files": _boolemoji(meta.get("parseradmin_permission")),
        }
        output.append(data)

    print(tabulate(output, headers="keys"))


@cli.command()
@click.option(
    "--base-url",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--ingest-token",
    envvar="HUMIO_INGEST_TOKEN",
    required=True,
    help="Your *secret* ingest token found in your repository settings",
)
@click.option(
    "--encoding",
    envvar="HUMIO_ENCODING",
    required=False,
    help="Encoding to use when reading the provided files. Autodetected if not provided",
)
@click.option(
    "--separator",
    envvar="HUMIO_SEPARATOR",
    default="^.",
    help="PATTERN indicating the start of a new event. Assumes single-line if not provided. "
    "For example `^\\d{4}-\\d{2}-\\d{2}[T\\s]\\d{2}:\\d{2}:\\d{2}`",
)
@click.option(
    "--soft-limit",
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
@click.option(
    "--fields",
    envvar="HUMIO_FIELDS",
    required=False,
    default="{}",
    help="Optional fields to send with all events. Must be provided as a parseable JSON object",
)
@click.argument("ingestfiles", nargs=-1, type=click.Path(exists=True))
def ingest(base_url, ingest_token, encoding, separator, soft_limit, dry, fields, ingestfiles):
    """
    Ingests events from files with the provided event separator and ingest token.

    If the ingest token is not associated with a parser, a JSON object with the type
    field must minimally be included, for example: {"type":"parsername"}

    If no encoding is provided chardet will be used to find an appropriate encoding.
    """

    client = humiocore.HumioAPI(base_url=base_url, ingest_token=ingest_token)
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


@cli.command()
@click.option(
    "--base-url",
    envvar="HUMIO_BASE_URL",
    required=True,
    help="Humio base URL to connect to, for example https://cloud.humio.com",
)
@click.option(
    "--token",
    envvar="HUMIO_TOKEN",
    required=True,
    help="Your *secret* API token found in your account settings",
)
@click.option(
    "--repo",
    "repo_",
    envvar="HUMIO_REPO",
    multiple=True,
    default=["sandbox"],
    help="Name of repository to create or update the provided parser in, supports wildcards and "
    "multiple options",
    show_default=True,
)
@click.option(
    "--encoding",
    envvar="HUMIO_ENCODING",
    required=False,
    help="Encoding to use when reading the provided files. Autodetected if not provided",
)
@click.argument("parser", nargs=1, type=click.Path(exists=True))
def makeparser(base_url, token, repo_, encoding, parser):
    """
    Takes a parser file and creates or updates a parser with the same name as the file
    in the requested repository (or repositories).

    If no encoding is provided chardet will be used to find an appropriate encoding.
    """

    client = humiocore.HumioAPI(base_url=base_url, token=token)

    matches = lambda x: any(
        [fnmatch(x, pattern) for pattern in repo_]  # pylint: disable=not-an-iterable
    )
    target_repos = set(
        [reponame for reponame, meta in client.repositories().items() if matches(reponame)]
    )

    if not encoding:
        detected = utils.detect_encoding(parser)
        if detected["confidence"] < 0.9:
            logger.warning(
                "Detected encoding has low confidence", filedetection=detected, parser=parser
            )
        if not detected["encoding"]:
            logger.error(
                "Skipping file with unknown encoding", filedetection=detected, parser=parser
            )
            return
        encoding = detected["encoding"]

    with open(parser, "r", encoding=encoding) as parser_io:
        source = parser_io.read()
        client.create_update_parser(repos=target_repos, parser=Path(parser).stem, source=source)


if __name__ == "__main__":
    cli()
