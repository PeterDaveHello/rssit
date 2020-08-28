import rssit.util
import rssit.status
import urllib.parse
import collections
import threading
import time
import sys
import pprint
import re


class Arg(object):
    def __init__(self, varname, argnum=None, parse=None):
        self.varname = varname
        self.argnum = argnum
        self.parse = parse

    def get(self, val):
        if self.parse:
            return self.parse(val)
        else:
            return val


class Format(object):
    def __init__(self, format_, *args):
        self.format_ = format_
        self.args = args


class API(object):
    def __init__(self, apidef):
        self.apidef = apidef
        self.lock = threading.Lock()
        self.lastran = 0

    def get_endpoint(self, endpoint_name):
        if endpoint_name not in self.apidef["endpoints"]:
            raise Exception("Endpoint " + str(endpoint_name) + " doesn't exist")

        return self.apidef["endpoints"][endpoint_name]

    def get_setting(self, endpoint_name, setting, args):
        val = None

        if setting in self.apidef:
            val = rssit.util.simple_copy(self.apidef[setting])

        endpoint = self.get_endpoint(endpoint_name)

        if setting in endpoint:
            newval = rssit.util.simple_copy(endpoint[setting])

            if not val:
                val = newval
            elif type(newval) in [dict, collections.OrderedDict]:
                val.update(newval)
            else:
                val = newval

        curargs = args
        while curargs and "_overlay" in curargs and setting in curargs["_overlay"]:
            newval = rssit.util.simple_copy(curargs["_overlay"][setting])

            if not val:
                val = newval
            elif type(newval) in [dict, collections.OrderedDict]:
                val.update(newval)
            else:
                val = newval

            curargs = curargs.get("_overlay")

        return val

    def get_value(self, value, args, kwargs):
        newvalue = value

        if type(value) in [dict, collections.OrderedDict]:
            if type(value) == collections.OrderedDict:
                newvalue = collections.OrderedDict()
            else:
                newvalue = {}
            for x in value:
                newvalue[self.get_value(x, args, kwargs)] = self.get_value(value[x], args, kwargs)
        elif type(value) in [list, tuple]:
            newvalue = []
            for x in value:
                newvalue.append(self.get_value(x, args, kwargs))

            if type(value) == tuple:
                newvalue = tuple(newvalue)
        elif str(type(value)) == str(Format):  # needed for updates
            newargs = []
            for x in value.args:
                newargs.append(self.get_value(x, args, kwargs))
            newvalue = value.format_ % tuple(newargs)
        elif str(type(value)) == str(Arg):  # needed for updates
            if value.varname and value.varname in kwargs:
                newvalue = value.get(kwargs[value.varname])
            elif value.argnum is not None and value.argnum < len(args):
                newvalue = value.get(args[value.argnum])
            else:
                newvalue = None

        return newvalue

    def run(self, config, endpoint_name, *args, **kwargs):
        kwargs = rssit.util.simple_copy(kwargs)
        endpoint = self.get_endpoint(endpoint_name)

        if "base" in endpoint:
            newendpoint = rssit.util.simple_copy(endpoint)
            if "_overlay" in kwargs:
                newendpoint["_overlay"] = kwargs["_overlay"]
            kwargs["_overlay"] = newendpoint
            return self.run(config, endpoint["base"], *args, **kwargs)

        newargs = self.get_setting(endpoint_name, "args", kwargs)
        if newargs:
            for arg in newargs:
                if arg not in kwargs:
                    argval = self.get_value(arg, args, kwargs)
                    val = self.get_value(newargs[arg], args, kwargs)
                    kwargs[argval] = val

        baseurl = self.get_value(self.get_setting(endpoint_name, "url", kwargs), args, kwargs)

        queryargs = {}
        query = self.get_setting(endpoint_name, "query", kwargs)
        if query:
            for arg in query:
                argval = self.get_value(arg, args, kwargs)
                val = self.get_value(query[arg], args, kwargs)
                if val is not None:
                    queryargs[argval] = val

        querystr = urllib.parse.urlencode(queryargs, quote_via=urllib.parse.quote)

        if querystr:
            baseurl = baseurl + "?" + querystr

        orig_config = config
        config = rssit.util.simple_copy(config)

        method = self.get_value(self.get_setting(endpoint_name, "method", kwargs), args, kwargs)
        if method is None:
            method = "GET"
        config["http_method"] = method

        form = self.get_value(self.get_setting(endpoint_name, "form", kwargs), args, kwargs)
        if form is not None:
            form_encoding = self.get_value(self.get_setting(endpoint_name, "form_encoding", kwargs), args, kwargs)
            if form_encoding == "json":
                form = rssit.util.json_dumps(form).encode("utf-8")
                config["httpheader_Content-Type"] = "application/json"
            else:
                form = urllib.parse.urlencode(form).encode("utf-8")

        headers = self.get_setting(endpoint_name, "headers", kwargs)
        if headers:
            for header in headers:
                value = self.get_value(headers[header], args, kwargs)
                config["httpheader_" + self.get_value(header, args, kwargs)] = value

        cookiejar = self.get_setting(endpoint_name, "cookiejar", kwargs)
        noextra = self.get_setting(endpoint_name, "http_noextra", kwargs)

        do_ratelimit = False
        if self.get_value(self.get_setting(endpoint_name, "force", kwargs), args, kwargs) is not True:
            do_ratelimit = True

        limit = self.get_value(self.get_setting(endpoint_name, "ratelimit", kwargs), args, kwargs)
        if not limit:
            limit = 1

        status_obj = rssit.status.add_api({
            "endpoint": endpoint_name,
            "apidef": self.apidef
        })

        if do_ratelimit:
            self.lock.acquire()
            now = time.monotonic()
            diff = now - self.lastran
            if diff < limit:
                time.sleep(limit - diff)

        prefunc = self.get_setting(endpoint_name, "pre", kwargs)
        if prefunc:
            prefunc(config, baseurl)

        if "http_debug" in config and config["http_debug"]:
            sys.stderr.write(str(method) + " " + str(baseurl) + "\n")

        data = None

        config["out_headers"] = {}
        header_out = config["out_headers"]
        try:
            download_kw = {
                "config": config,
                "http_noextra": noextra,
                "http_cookiejar": cookiejar,
                "header_out": header_out
            }
            if form is not None:
                download_kw["post"] = form
            if method is not None:
                download_kw["method"] = method

            #if "http_debug" in config and config["http_debug"]:
            #    sys.stderr.write(pprint.pformat(download_kw) + "\n")
            data = rssit.util.download(baseurl, **download_kw)
        except Exception as e:
            if do_ratelimit:
                self.lock.release()

            rssit.status.remove_api(status_obj)
            if "http_error" in config:
                orig_config["http_error"] = config["http_error"]
            if "http_resp" in config:
                orig_config["http_resp"] = config["http_resp"]
            raise e

        rssit.status.remove_api(status_obj)

        if do_ratelimit:
            self.lastran = time.monotonic()
            self.lock.release()

        if "http_error" in config:
            orig_config["http_error"] = config["http_error"]

        if "http_debug_printout" in config and config["http_debug_printout"]:
            print(data.decode("utf-8"))

        encoding_type = self.get_setting(endpoint_name, "type", kwargs)
        if encoding_type == "json":
            data = rssit.util.json_loads(data)
        elif encoding_type == "json_callback":
            data = data.decode("utf-8")
            data = re.sub(r"[^(]*[(]({.*})[)];?$", "\\1", data)
            data = data.replace("\&quot;", "&quot;")
            data = rssit.util.json_loads(data)

        parser = self.get_setting(endpoint_name, "parse", kwargs)
        if parser:
            return parser(orig_config, config, data)
        else:
            return data
