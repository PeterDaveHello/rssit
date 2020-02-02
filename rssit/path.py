# -*- coding: utf-8 -*-


import os.path
import re
import rssit.paths.all
import rssit.config
import rssit.status
import traceback
import urllib.parse


def questionmark(path):
    if "?" not in path:
        return (path, {})

    firstidx = path.index("?")
    kvs = path[firstidx:]
    idx = 0

    options = {}

    while idx < len(kvs):
        kvs = kvs[idx + 1:]

        if "?" in kvs:
            idx = len(kvs)
        if "&" in kvs:
            idx = kvs.index("&")
        else:
            idx = len(kvs)

        kv = kvs[:idx]

        if "=" not in kv:
            continue

        eq = kv.index("=")

        key = kv[:eq]
        value = rssit.config.parse_value_simple(urllib.parse.unquote(kv[eq + 1:]))

        options[key] = value

    return (path[:firstidx], options)


def do_normpath(path):
    return re.sub("/+", "/", path)


def process(server, path):
    normpath = re.sub("^/*", "", do_normpath(path))
    newpath, options = questionmark(normpath)
    path_name = re.sub("@.*", "", newpath.split("/")[0].lower())

    path_list = rssit.paths.all.paths_dict

    if path_name not in path_list:
        path_name = "404"

    format_exc = None

    status_obj = rssit.status.add_path(path)

    try:
        path_list[path_name]["process"](server, path, newpath, options)
    except rssit.util.HTTPErrorException as err:
        if int(err.code/100) == 2:
            err.code = 500
        server.send_response(err.code, "Internal Server Error")
        format_exc = err.traceback
    except Exception as err:
        server.send_response(500, "Internal Server Error")
        format_exc = traceback.format_exc()

    rssit.status.remove_path(status_obj)

    if format_exc:
        server.end_headers()

        server.wfile.write(bytes(format_exc, "UTF-8"))
        print(format_exc)
