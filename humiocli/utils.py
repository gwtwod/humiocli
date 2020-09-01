"""
Collection of misc utility functions
"""

import re
import sys
import json
from fnmatch import fnmatch
from collections import defaultdict

from tabulate import tabulate
import colorama
import pandas as pd
import snaptime
import structlog
from pygments import highlight as hl
from pygments.formatters import Terminal256Formatter  # pylint: disable=no-name-in-module
from pygments.lexers import XmlLexer  # pylint: disable=no-name-in-module
from pygments.lexers.data import JsonLexer

logger = structlog.getLogger(__name__)


def color_init(color):
    """Enable/Disable wrapping of sys.stdout with Colorama logic"""

    if color == "auto":
        colorama.init()
    elif color == "always":
        sys.stdout = sys.__stdout__
    else:
        colorama.init(strip=True)


def wrap_time(timestamp, offset):
    """
    Takes a datetime object and adjusts it with with the provided snaptime-offset
    """
    return snaptime.snap(timestamp, offset)


def humanized_bytes(size, precision=2):
    """
    Returns a humanized storage size string from bytes
    """
    unit = ""
    for x in ["", "KB", "MB", "GB", "TB"]:
        if size < 1000.0:
            unit = x
            break
        size /= 1000.0
    return f"{size:.{precision}f} {unit}"


def run_ipython(ns):
    """
    Drop into an ipython shell with the provided variables
    """

    try:
        from IPython import start_ipython
        from traitlets.config import Config
    except ImportError as e:
        raise ImportError(f"This feature requires the optional extra `ipykernel` package to be installed: {str(e)}")

    msg = f"{colorama.Fore.LIGHTBLUE_EX}The following variables have been preloaded:{colorama.Fore.RESET}\n\n"
    msg += "\n".join([f"  - {colorama.Fore.LIGHTBLUE_EX}{n} ({type(ns[n])}){colorama.Fore.RESET}" for n in ns.keys()])
    msg += "\n"
    config = Config()
    config.TerminalInteractiveShell.banner1 = msg
    start_ipython(argv=[], config=config, user_ns=ns)


def detect_encoding(unknown_file):
    """Sniff a file's contents and try to detect the encoding used with chardet"""

    import chardet

    detector = chardet.UniversalDetector()

    with open(unknown_file, "rb") as unknown_io:
        for line in unknown_io:
            detector.feed(line)
            if detector.done:
                break
    detector.close()
    return detector.result


def readevents_split(io, sep="^."):
    """
    Yields complete events as defined by the provided start of record separator `sep`
    after reading the file object line by line. Do not use trailing/end-of-record
    patterns (for example `\n` ) or results will probably not be as expected.

    A final trailing newline is stripped from each event if any. All other whitespaces
    are left intact.
    """

    def chomp(x):
        """Perl-like chomp, strip final newlines but keep whitespaces unlike rstrip"""
        if x.endswith("\r\n"):
            return x[:-2]
        if x.endswith("\n") or x.endswith("\r"):
            return x[:-1]
        return x

    sep = re.compile("(" + sep + ")", flags=re.MULTILINE | re.DOTALL)
    buffer = ""

    while True:
        line = io.readline()
        if not line:
            break  # EOF

        # `pending_events` will hold possibly partial events whenever a match of `sep`
        # occurs. We won't know if there are additional lines belonging to the last
        # event until we either see a new separator or the whole file has been processed
        # `continuation` holds non-matches, which belong to the previous event
        continuation, *parts = sep.split(line)
        pending_events = [a + b for a, b in zip(parts[::2], parts[1::2])]
        # print('continuation:', repr(continuation), 'pending_events:', repr(pending_events))

        if continuation:
            buffer += continuation

        if pending_events:
            *complete, incomplete = pending_events

            if buffer:
                yield chomp(buffer)

            buffer = incomplete
            for event in complete:
                yield chomp(event)
    yield chomp(buffer)


def highlight(rawstring, style):
    """
    Returns a syntax highlighted version of the input string using the provided
    highlighting style
    """

    xmllexer = XmlLexer()
    jsonlexer = JsonLexer()
    termformatter = Terminal256Formatter(style=style)

    # TODO: Consider finding xml/json substrings and highlighting with re.sub(,,repl())
    #       Chaining overlapping strings with pygments lexers seems unstable

    try:
        if rawstring.lstrip().startswith("{") and rawstring.rstrip().endswith("}"):
            rawstring = hl(rawstring, jsonlexer, termformatter)
        rawstring = hl(rawstring, xmllexer, termformatter)
        return rawstring.strip()
    except Exception as err:
        logger.exception("An unexptected error occured during highlighting", error=err)
        return rawstring


def searchstring_from_fields(events, outformat, ignored=None):
    """
    Generate Humio search strings from all available fields in all events by OR-ing all
    values (if outformat is or-values), or fields and values (if outformat is or-fields).

    A special searchstring SUBSEARCH is also provided by AND-ing all the individual searchstrings

    Parameters
    ----------
    events : iterable
        An iterable of dictionaries
    outformat : string
        The template name to use, either `or-fields` or `or-values`
    ignored : list, optional
        A list of fields that should be ignored. By default ["@timestamp", "@rawstring"]

    Returns
    -------
    dict
        A dictionary with field-names and searchstrings
    """

    if ignored is None:
        ignored = ["@timestamp", "@rawstring"]

    if outformat == "or-values":
        template = "{value}"
    else:
        template = "{field}={value}"

    data = defaultdict(set)

    for event in events:
        for field, value in event.items():
            if field in ignored:
                continue
            data[field].add(template.format(field=json.dumps(field), value=json.dumps(value)))
    if len(data.keys()) > 5:
        logger.warning(
            "The emitted searching includes more than 5 fields, did you forget select relevant fields?",
            fields=sorted(data.keys()),
        )
    data = {key: " or ".join(values) for key, values in data.items()}
    data["SUBSEARCH"] = "(" + ") and (".join([value for key, value in data.items()]) + ")"
    return data


def table_from_events(events, leading=None, trailing=None, drop=None):
    df = pd.DataFrame.from_dict(events)
    if leading is None:
        leading = ["timestamp", "@timestamp"]
    if trailing is None:
        trailing = ["#repo", "#type", "@host", "@source", "@timezone", "@id", "@rawstring"]
    if drop is None:
        if "timestamp" in df.columns:
            drop = ["@timestamp", "@timezone"]
        else:
            drop = []

    df = df.drop(columns=drop, errors="ignore")
    if "@timestamp" in df.columns:
        df["@timestamp"] = pd.to_datetime(df["@timestamp"], unit="ms", utc=True)

    leading = [x for x in leading if x in df.columns]
    trailing = [x for x in trailing if x in df.columns and x not in leading]
    middle = [x for x in df.columns if x not in leading and x not in trailing]
    df = df[leading + middle + trailing]

    df = df.fillna("")
    return tabulate(df, headers=df.columns, showindex=False)


def filter_repositories(repositories, patterns=None, ignore=None, strict_views=True, **kwargs):
    """
    Takes a dict of repositories (`humioapi.HumioAPI.repositories()`) and
    returns a reduced version according to the supplied filters.

    Parameters
    ----------
    repositories : dict
        A dictionary of repo names and their properties, see `humioapi.HumioAPI.repositories()`
    patterns : list, optional
        A list of simple `fnmatch` strings, allowing wildcards, by default ["*"]
    ignore : regex string, optional
        A regex string matching repo names to ignore, by default None
    strict_views : bool, optional
        Require view names to be matched exactly, by default True
    **kwargs: optional
        Repository must have a key==value for the provided key-value argument

    Returns
    -------
    dict
        A dictionary of repo names and their properties
    """

    if not patterns:
        patterns = ["*"]
    matching_repositories = {}

    def _check_attributes(repository, attributes):
        for attr, value in attributes.items():
            if attr not in repository:
                return False
            if repository[attr] != value:
                return False
        return True

    for name, repository in repositories.items():
        for pattern in patterns:
            if strict_views and repository.get("type") == "view" and name != pattern:
                # Views must match exactly in strict mode, try next pattern
                continue

            if not fnmatch(name, pattern):
                # No fnmatch, try next pattern
                continue

            if ignore and re.search(ignore, name):
                # Repo should be ignored
                continue

            if not _check_attributes(repository, kwargs):
                # At least one attribute requirement does not match
                continue

            matching_repositories[name] = repository

    return matching_repositories


def is_tty():
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    if not is_a_tty:
        return False
    return True
