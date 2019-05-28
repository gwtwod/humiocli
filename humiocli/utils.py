"""
Collection of misc utility functions
"""

import sys
import re
import snaptime
import tzlocal
import pandas as pd
import colorama
from pygments import highlight as hl
from pygments.lexers import XmlLexer  # pylint: disable=no-name-in-module
from pygments.lexers.data import JsonLexer
from pygments.formatters import Terminal256Formatter  # pylint: disable=no-name-in-module

import structlog

logger = structlog.getLogger(__name__)


def color_init(color):
    """Enable/Disable wrapping of sys.stdout with Colorama logic"""

    if color == "auto":
        colorama.init()
    elif color == "always":
        sys.stdout = sys.__stdout__
    else:
        colorama.init(strip=True)


def parse_ts(timestring):
    """
    Parses a snapstring or common timestamp (ISO8859 and similar) and
    returns a timezone-aware pandas timestamp using the local timezone.
    """
    if timestring.lower().startswith("now"):
        timestring = ""

    try:
        return snaptime.snap(pd.Timestamp.now(tz=tzlocal.get_localzone()), timestring)
    except snaptime.main.SnapParseError:
        logger.debug(
            "Could not parse the provided timestring with snaptime", timestring=timestring
        )

    try:
        timestamp = pd.to_datetime(timestring, utc=False)
        if timestamp.tzinfo:
            return timestamp
        else:
            return timestamp.tz_localize(tz=tzlocal.get_localzone())
    except ValueError:
        logger.debug("Could not parse the provided timestring with pandas", timestring=timestring)

    raise ValueError(
        "Could understand the provided timestring ({}). Try something less ambigous?".format(
            timestring
        )
    )


def wrap_time(timestamp, offset):
    """
    Takes a datetime object and adjusts it with with the provided snaptime-offset
    """
    return snaptime.snap(timestamp, offset)


def humanized_bytes(size, precision=2):
    for unit in ["", "KB", "MB", "GB", "TB"]:
        if size < 1000.0:
            break
        size /= 1000.0
    return f"{size:.{precision}f} {unit}"


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
