"""
This module doesn't try or promise to do any real XML parsing, just make an
attempt at prettifying any text that looks like it might contain XML or
similar markup. Yes, that is definitly regex for XML-processing you're seeing.
"""

import re

re_tag = re.compile(r"(<[^<>\[\s\d-][^>]*>)")
re_opening_tag = re.compile(r"<(?:[^<>/\s]+)[^>]*(?<!/)>")
re_closing_tag = re.compile(r"<[/].*?>")
re_namespace = re.compile(r""" xmlns[^\"']+['\"][^\"']+[\"']""")
re_namespace_prefix = re.compile(r"""(<\/?)[^:<> ]{0,20}:""")


def process(rawstring, strip=True, clean=True, repair=False, output_format="pretty", indentation="    "):
    if strip:
        rawstring = re.sub(r"\s*(<[^<>]+>)\s*", r"\1", rawstring, flags=re.M)
    if clean:
        rawstring = clean_tags(rawstring)

    # keep very obvious non-xml unprocessed
    parts = re.split("""(<[^<>]+)(<)""", rawstring, maxsplit=1)
    if len(parts) == 4:
        preface = parts[0] + parts[1]
        rawstring = parts[2] + parts[3]
    else:
        preface = ""

    # prepare for processing by splitting into chunks of tags and values
    xml_parts = [part for part in re_tag.split(rawstring) if part != ""]

    if repair and output_format.lower() != "kv":
        xml_parts = repair_tags(xml_parts)

    if output_format.lower() == "pretty":
        xml_parts = prettify(xml_parts, indentation)
    elif output_format.lower() == "kv":
        xml_parts = key_value(xml_parts, indentation)

    # rebuild the processed xml
    return preface + "".join(xml_parts)


def prettify(xml_parts, indent="  "):
    indent_count = 0
    prettified = []

    for idx, part in enumerate(xml_parts):

        if re_tag.match(part):
            if part[1] == "/":  # Closing
                indent_count -= 1 if indent_count > 0 else 0
                previous_part = xml_parts[idx - 1] if idx > 0 else ""
                if previous_part[:2] == "</" or previous_part[-2:] == "/>":
                    prettified.append("\n%s%s" % (indent * indent_count, part))
                else:
                    prettified.append("%s" % (part))

            elif part[1] == "?":  # Prolog
                prettified.append("%s%s" % (indent * indent_count, part))

            elif part[-2] == "/":  # Self-containing
                prettified.append("\n%s%s" % (indent * indent_count, part))

            elif part[1] == "!":  # CDATA
                prettified.append(part)

            else:  # Opening
                prettified.append("\n%s%s" % (indent * indent_count, part))
                indent_count += 1

        else:  # Value
            previous_part = xml_parts[idx - 1] if idx > 0 else ""
            if previous_part[:2] == "</" or previous_part[-2:] == "/>":
                part = "\n" + part
            prettified.append(part)
    return prettified


def key_value(xml_parts, indent="  "):
    indent_count = 0
    kv = []

    for idx, part in enumerate(xml_parts):
        if re_tag.match(part):
            if part[1] == "/":  # Closing
                indent_count -= 1 if indent_count > 0 else 0
            elif part[1] == "?":  # Prolog - Does anyone using this format care about these?
                continue
            elif part[-2] == "/":  # Self-containing
                kv.append("\n%s%s" % (indent * indent_count, part[1:-2] + ":"))
            elif part[1] == "!":  # CDATA
                kv.append(part)
            else:  # Opening
                kv.append("\n%s%s" % (indent * indent_count, part[1:-1] + ": "))
                indent_count += 1
        else:  # Value
            previous_part = xml_parts[idx - 1] if idx > 0 else ""
            if previous_part[:2] == "</" or previous_part[-2:] == "/>":
                part = "\n" + part
            kv.append(part)
    return kv


def clean_tags(xml):
    xml = re_namespace.sub("", xml)
    xml = re_namespace_prefix.sub(r"\1", xml)
    return xml


def repair_tags(xml_parts):
    nodes = []
    repaired = []

    for _, part in enumerate(xml_parts):
        if re_opening_tag.match(part):
            nodes.append(part[1:-1].split(" ", 1)[0])
        elif re_closing_tag.match(part):
            inferred_part = "</" + nodes.pop() + ">" if nodes else part
            if part == "</>":
                part = inferred_part
        repaired.append(part)
    return repaired
