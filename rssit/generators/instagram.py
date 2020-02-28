# -*- coding: utf-8 -*-


import re
import rssit.util
import rssit.rest
import datetime
import sys
import pprint
import urllib.parse
from dateutil.tz import *
import collections
import traceback
import hashlib
import rssit.converters.social_to_feed


#instagram_ua = "Instagram 10.26.0 (iPhone7,2; iOS 10_1_1; en_US; en-US; scale=2.00; gamut=normal; 750x1334) AppleWebKit/420+"
instagram_ua = "Instagram 10.26.0 Android (23/6.0.1; 640dpi; 1440x2560; samsung; SM-G930F; herolte; samsungexynos8890; en_US)"

fbappid = "124024574287414"
webfbappid = "1217981644879628"
webdesktopfbappid = "936619743392459"
liteappid = "152431142231154"

endpoint_getentries = "https://www.instagram.com/graphql/query/?query_id=17888483320059182&variables="
endpoint_getstories = "https://www.instagram.com/graphql/query/?query_id=17873473675158481&variables="

# new endpoints:
# get entries
#   https://www.instagram.com/graphql/query/?query_hash=472f257a40c653c64c666ce877d59d2b&variables=%7B%22id%22%3A%222523526502%22%2C%22first%22%3A12%2C%22after%22%3A%22...%22%7D
#     query_hash:472f257a40c653c64c666ce877d59d2b
#     variables:{"id":"2523526502","first":12,"after":"..."}
#
# get all stories
#   https://www.instagram.com/graphql/query/?query_hash=b40536160b85d87aecc43106a1f35495&variables=%7B%7D
#     query_hash:b40536160b85d87aecc43106a1f35495
#     variables:{}
#
# get specific stories
#   https://www.instagram.com/graphql/query/?query_hash=15463e8449a83d3d60b06be7e90627c7&variables=%7B%22reel_ids%22%3A%5B%2212345%22%2C%2267890%22%5D%2C%22precomposed_overlay%22%3Afalse%7D
#      query_hash:15463e8449a83d3d60b06be7e90627c7
#      variables: {
#                   "reel_ids": [
#                     "12345",
#                     "67890"
#                     ...
#                   ],
#                   "precomposed_overlay": false
#                 }
#
# get comments
#   https://www.instagram.com/graphql/query/?query_hash=a3b895bdcb9606d5b1ee9926d885b924&variables=%7B%22shortcode%22%3A%22...%22%2C%22first%22%3A20%2C%22after%22%3A%22...%22%7D
#     query_hash:a3b895bdcb9606d5b1ee9926d885b924
#     variables: {"shortcode":"...","first":20,"after":"..."}



# others:
# descriptions are from personal observation only, could be wrong
#
# homepage items + stories
#   https://www.instagram.com/graphql/query/?query_id=17842794232208280&fetch_media_item_count=10&has_stories=true
#   https://www.instagram.com/graphql/query/?query_hash=253f5079497e7ef2756867645f972e4c&fetch_media_item_count=10&has_stories=true
#
# user suggestions based off another user
#   https://www.instagram.com/graphql/query/?query_id=17845312237175864&id=[uid]
#
# user suggestions
#   https://www.instagram.com/graphql/query/?query_id=17847560125201451&fetch_media_count=20
#
# stories?
#   https://www.instagram.com/graphql/query/?query_id=17890626976041463
#   https://www.instagram.com/graphql/query/?query_hash=b40536160b85d87aecc43106a1f35495
#
# likes
#   https://www.instagram.com/graphql/query/?query_id=17864450716183058&shortcode=[shortcode]&first=20
#
# user followed by
#   https://www.instagram.com/graphql/query/?query_id=17851374694183129&id=[uid]&first=20
#
# user following
#   https://www.instagram.com/graphql/query/?query_id=17874545323001329&id=[uid]&first=20
#
# comments
#   https://www.instagram.com/graphql/query/?query_id=17852405266163336&shortcode=[shortcode]&first=20&after=[commentid]
#
# edge_web_discover_media
#   https://www.instagram.com/graphql/query/?query_id=17863787143139595
#
# hashtag search
#   https://www.instagram.com/graphql/query/?query_id=17875800862117404&tag_name=[hashtag]&first=20
#
# get location info (+media & top posts)
#   https://www.instagram.com/graphql/query/?query_id=17865274345132052&id=[location id]&first=20
#
# saved media
#   https://www.instagram.com/graphql/query/?query_id=17885113105037631&id=[uid]&first=20
#
# contact_history
#   https://www.instagram.com/graphql/query/?query_id=17884116436028098

# e = {"id":"...","first":10,"after":"..."}
# e = /mizuki.sakamaki/
# e = /p/5ZYSGMCtZW/
# o()(_sharedData.rhx_gis + ":" + window._sharedData.config.csrf_token + ":" + window.navigator.userAgent + ":" + e)
# o = md5


post_cache = rssit.util.Cache("ig_post", 36*60*60, 50)
uid_to_username_cache = rssit.util.Cache("ig_uid_to_username", 48*60*60, 100)
api_userinfo_cache = rssit.util.Cache("ig_api_userinfo", 24*60*60, 100)
reelstray_cache = rssit.util.Cache("ig_reelstray_cache", 5*60, 0)
stories_cache = rssit.util.Cache("ig_stories_cache", 1*60, 0)
_sharedData = None

sharedDataregex1 = r"window._sharedData = *(?P<json>.*?);?</script>"
sharedDataregex2 = r"window._sharedData *= *(?P<json>.*?}) *;\\n *window\.__initialDataLoaded"
additionalDataregex = r'''window.__additionalDataLoaded[(]["'].*?["'] *, *(?P<json>{.*?})[)];? *</script>'''

csrftoken = None


def get_sharedData(config):
    do_website_request(config, "https://www.instagram.com")


def get_gis_generic(config, e):
    if not _sharedData:
        get_sharedData(config)

    useragent = None
    for key in config:
        if key.lower() == "httpheader_user-agent":
            useragent = config[key]
    #print(_sharedData["rhx_gis"])
    #print(_sharedData["config"]["csrf_token"])
    #print(useragent)
    #print(e)
    #print("---")
    #string = _sharedData["rhx_gis"] + ":" + _sharedData["config"]["csrf_token"] + ":" + useragent + ":" + e
    #string = _sharedData["rhx_gis"] + ":" + _sharedData["config"]["csrf_token"] + ":" + e
    rhx_gis = _sharedData.get("rhx_gis", "")
    string = rhx_gis + ":" + e
    m = hashlib.md5()
    m.update(string.encode('utf-8'))
    return m.hexdigest()


def set_gis_generic(config, e):
    config["httpheader_X-Instagram-GIS"] = get_gis_generic(config, e)

    if csrftoken is not None:
        config["httpheader_X-CSRFToken"] = csrftoken


def set_gis_a1(config, url):
    set_gis_generic(config, re.sub(r".*\.instagram\.com(/.*?/)\?__a=1.*$", "\\1", url))


def set_gis_graphql(config, url):
    set_gis_generic(config, re.sub(r".*[?&]variables=([^&]*).*", "\\1", url))


def get_url(config, url):
    match = re.match(r"^(https?://)?(?:\w+\.)?instagram\.com/(?P<user>[^/]*)", url)

    if match is None:
        return

    if config["prefer_uid"]:
        return "/uid/" + get_user_page(config, match.group("user"))["id"]

    return "/u/" + match.group("user").lower()


def normalize_image(url):
    return re.sub(r"&se=[^&]+", "", url)
    """url = url.replace(".com/l/", ".com/")
    url = re.sub(r"(cdninstagram\.com/[^/]*/)s[0-9]*x[0-9]*/", "\\1", url)
    url = re.sub(r"/sh[0-9]*\.[0-9]*/", "/", url)
    url = re.sub(r"/p[0-9]*x[0-9]*/", "/", url)
    url = re.sub(r"/e[0-9]*/", "/", url)
    url = url.replace("/fr/", "/")
    url = re.sub(r"(cdninstagram\.com/[^/]*/)s[0-9]*x[0-9]*/", "\\1", url)
    return url"""

    urlsplit = urllib.parse.urlsplit(url)
    urlstart = urlsplit.scheme + "://" + urlsplit.netloc + "/"

    pathsplit = urlsplit.path.split("/")

    have_t = False

    for i in pathsplit:
        if re.match(r"^t[0-9]+\.[0-9]+-[0-9]+$", i):
            urlstart += i + "/"
            have_t = True
        elif re.match(r"^[0-9_]*_[a-z]+\.[a-z0-9]+$", i):
            if not have_t:
                urlstart += "/"
            urlstart += i

    return urlstart


def base_image(url):
    return re.sub(r"\?[^/]*$", "", url)


def image_basename(url):
    return re.sub(r".*/([^.]*\.[^/?]*)(\?.*)?$", "\\1", base_image(url))


def parse_webpage_request(orig_config, config, data):
    sdata = data.decode('utf-8')

    jsondatare = re.search(sharedDataregex1, sdata)
    if jsondatare is None:
        jsondatare = re.search(sharedDataregex2, sdata)
        if jsondatare is None:
            sys.stderr.write("No sharedData!\n")
            return None

    #jsondata = bytes(jsondatare.group("json"), 'utf-8').decode('unicode-escape')
    jsondata = jsondatare.group("json")
    decoded = rssit.util.json_loads(jsondata)

    additionaldatare = re.search(additionalDataregex, sdata)
    if additionaldatare is not None:
        #additionaljson = bytes(additionaldatare.group("json"), 'utf-8').decode('unicode-escape')
        additionaljson = additionaldatare.group("json")
        additionaldecoded = rssit.util.json_loads(additionaljson)
        for key in decoded["entry_data"]:
            if type(decoded["entry_data"][key]) == list:
                decoded["entry_data"][key][0] = additionaldecoded
                break

    if "config" in decoded and "csrf_token" in decoded["config"]:
        global csrftoken
        csrftoken = decoded["config"]["csrf_token"]

    return decoded


def parse_a1_request(orig_config, config, data):
    try:
        data = rssit.util.json_loads(data)
    except Exception as e:
        if str(data).startswith("<!"):
            orig_config["http_error"] = 404
        raise e

    return data


web_api = rssit.rest.API({
    "name": "instagram_web",
    "type": "json",
    "headers": {
        "User-Agent": rssit.util.get_random_user_agent(),
        "X-Requested-With": "XMLHttpRequest"
    },
    "endpoints": {
        "webpage": {
            "url": rssit.rest.Format("http://www.instagram.com/%s/", rssit.rest.Arg("path", 0)),
            "parse": parse_webpage_request,
            "type": "raw"
        },

        "a1": {
            "url": rssit.rest.Format("http://www.instagram.com/%s/", rssit.rest.Arg("path", 0)),
            "pre": set_gis_a1,
            "parse": parse_a1_request,
            "type": "raw",
            "query": {
                "__a": 1
            }
        },

        "user": {
            "base": "webpage",
            "ratelimit": 60
        },

        "user_a1": {
            "base": "a1",
            "ratelimit": 60
        },

        "node": {
            "base": "webpage",
            "args": {
                "path": rssit.rest.Format("p/%s", rssit.rest.Arg("node", 0))
            },
            "ratelimit": 5
        },

        "node_a1": {
            "base": "a1",
            "args": {
                "path": rssit.rest.Format("p/%s", rssit.rest.Arg("node", 0))
            },
            "ratelimit": 5
        }
    }
})

graphql_id_api = rssit.rest.API({
    "name": "instagram_graphql_id",
    "type": "json",
    "url": "https://www.instagram.com/graphql/query/",
    "pre": set_gis_graphql,
    "headers": {
        "User-Agent": rssit.util.get_random_user_agent(),
        "accept": "*/*",
        # "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.8"
    },
    "endpoints": {
        "base": {
            "query": {
                "variables": rssit.rest.Arg("variables", 0, parse=lambda x: rssit.util.json_dumps(x))
            }
        },

        "entries": {
            "base": "base",
            "query": {
                "query_id": "17888483320059182"
            }
        },

        "stories": {
            "base": "base",
            "query": {
                "query_id": "17873473675158481"
            }
        },

        "comments": {
            "base": "base",
            "query": {
                "query_id": "17852405266163336"
            }
        }
    }
})

graphql_hash_api = rssit.rest.API({
    "name": "instagram_graphql_hash",
    "type": "json",
    "url": "https://www.instagram.com/graphql/query/",
    "pre": set_gis_graphql,
    "headers": {
        "User-Agent": rssit.util.get_random_user_agent(),
        "accept": "*/*",
        # "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.8",
        "referer": "https://www.instagram.com/",
        "origin": "https://www.instagram.com"
    },
    "endpoints": {
        "base": {
            "query": {
                "variables": rssit.rest.Arg("variables", 0, parse=lambda x: rssit.util.json_dumps(x))
            }
        },

        "entries": {
            "base": "base",
            "query": {
                #"query_hash": "472f257a40c653c64c666ce877d59d2b"
                #"query_hash": "42323d64886122307be10013ad2dcc44"
                #"query_hash": "bd0d6d184eefd4d0ce7036c11ae58ed9"
                #"query_hash": "e7e2f4da4b02303f74f0841279e52d76"
                #"query_hash": "a5164aed103f24b03e7b7747a2d94e3c"
                #"query_hash": "5b0222df65d7f6659c9b82246780caa7"
                #"query_hash": "f412a8bfd8332a76950fefc1da5785ef"
                #"query_hash": "50d3631032cf38ebe1a2d758524e3492"
                #"query_hash": "66eb9403e44cc12e5b5ecda48b667d41"
                "query_hash": "f2405b236d85e8296cf30347c9f08c2a"
            }
        },

        # {"id":"...","first":12,"after":"..."} -- after is optional
        "tagged": {
            "base": "base",
            "query": {
                #"query_hash": "de71ba2f35e0b59023504cfeb5b9857e"
                "query_hash": "ff260833edf142911047af6024eb634a"
            }
        },

        "stories": {
            "base": "base",
            "query": {
                "query_hash": "15463e8449a83d3d60b06be7e90627c7"
            }
        },

        "comments": {
            "base": "base",
            "query": {
                #"query_hash": "a3b895bdcb9606d5b1ee9926d885b924"
                #"query_hash": "f0986789a5c5d17c2400faebf16efd0d"
                "query_hash": "97b41c52301f77ce508f55e66d17620e"
            }
        },

        # {"fetch_media_item_count":12,"fetch_media_item_cursor":"...","fetch_comment_count":4,"fetch_like":10,"has_stories":false}
        # {"cached_feed_item_ids":[],"fetch_media_item_count":12,"fetch_media_item_cursor":"...","fetch_comment_count":4,"fetch_like":3,"has_stories":false,"has_threaded_comments":true}
        "home": {
            "base": "base",
            "query": {
                #"query_hash": "485c25657308f08317c1e4b967356828"
                #"query_hash": "0a5d11877357197dfcd94d328b392cde"
                #"query_hash": "bcbc6b4219dbbdf7af876bf561d7a283"
                #"query_hash": "6a6601e518828c14896420942c903e44"
                #"query_hash": "c409f8bda63382c86db99f2a2ea4a9b2"
                #"query_hash": "fcf12425b390947f4a9fc55c46b74dbf"
                #"query_hash": "01b3ccff4136c4adf5e67e1dd7eab68d"
                #"query_hash": "3f01472fb28fb8aca9ad9dbc9d4578ff"
                #"query_hash": "169431bf216e1c39bb58e999d5d5bfa6"
                "query_hash": "08574cc2c79c937fbb6da1c0972c7b39"
            }
        }
    }
})

app_api = rssit.rest.API({
    "name": "instagram_app",
    "type": "json",
    "headers": {
        "User-Agent": instagram_ua,
        "x-ig-capabilities": "36oD",
        "accept": "*/*",
        # "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.8"
    },
    "endpoints": {
        "stories": {
            "url": rssit.rest.Format("https://i.instagram.com/api/v1/feed/user/%s/story/",
                                     rssit.rest.Arg("uid", 0)),
            "ratelimit": 2
        },
        "reels_tray": {
            "url": "https://i.instagram.com/api/v1/feed/reels_tray/",
            "force": True
        },
        "news": {
            "url": "https://i.instagram.com/api/v1/news/"
        },
        "user_info": {
            "url": rssit.rest.Format("https://i.instagram.com/api/v1/users/%s/info/",
                                     rssit.rest.Arg("uid", 0))
        },
        "user_feed": {
            "url": rssit.rest.Format("https://i.instagram.com/api/v1/feed/user/%s/",
                                     rssit.rest.Arg("uid", 0)),
            "query": {
                "max_id": rssit.rest.Arg("max_id", 1)
            }
        },
        "inbox": {
            "url": "https://i.instagram.com/api/v1/direct_v2/inbox/",
            "query": {
                "persistentBadging": "true",
                "use_unified_inbox": "true"
            }
        }
    }
})


"""
def do_a1_request(config, endpoint, *args, **kwargs):
    url = "http://www.instagram.com/" + endpoint.strip("/") + "/?__a=1"
    if "extra" in kwargs and kwargs["extra"]:
        url += "&" + kwargs["extra"]
    newdl = rssit.util.download(url, config=config)
    return rssit.util.json_loads(newdl)


def get_node_info_a1(config, code):
    return do_a1_request(config, "/p/" + code)


def get_node_info_webpage(config, code):
    req = do_website_request(config, "http://www.instagram.com/p/" + code)
    return req["entry_data"]["PostPage"][0]
"""


def do_a1_request(config, endpoint, *args, **kwargs):
    return web_api.run(config, "a1", endpoint.strip("/"), _overlay={"query": kwargs})


def get_node_info_a1(config, code):
    return web_api.run(config, "node_a1", code)


def get_node_info_webpage(config, code):
    req = web_api.run(config, "node", code)
    try:
        return req["entry_data"]["PostPage"][0]
    except Exception:
        return req["entry_data"]["PostPage"]


def get_normalized_array(config, norm, orig):
    if config["use_normalized"]:
        return norm
        #return [norm, orig]
    else:
        return orig


def check_cache(config, usecache):
    if config["force_nocache"]:
        return False
    return usecache


def get_node_info_raw(config, code, usecache=True):
    info = post_cache.get(code)
    usecache = check_cache(config, usecache)
    if info and usecache:
        if "graphql" in info and "shortcode_media" in info["graphql"] and info["graphql"]["shortcode_media"] is not None:
            return info

    try:
        if config["use_shortcode_a1"]:
            req = get_node_info_a1(config, code)
        else:
            req = get_node_info_webpage(config, code)
        post_cache.add(code, req)
        return req
    except Exception as e:
        #print(e)
        traceback.print_exc()
        return {}


def get_node_info(config, code, usecache=True):
    req = get_node_info_raw(config, code, usecache)
    if "graphql" in req:
        req = req["graphql"]["shortcode_media"]
    return req


def get_node_media(config, node, images, videos):
    if node is None or len(node) == 0:
        return node

    node = normalize_node(node)

    image_src = None
    if "display_src" in node:
        image_src = node["display_src"]
    elif "display_url" in node:
        image_src = node["display_url"]
    else:
        sys.stderr.write("No image!!\n")
    normalized = normalize_image(image_src)

    if "caption" not in node:
        if "title" in node:
            node["caption"] = node["title"]

    if node["type"] == "carousel":
        def carousel_has_nonimage_member(carousel):
            for i in carousel:
                if "display_url" not in normalize_node(i):
                    return True
            return False

        if "carousel_media" in node and not carousel_has_nonimage_member(node["carousel_media"]):
            for i in node["carousel_media"]:
                get_node_media(config, i, images, videos)
        else:
            newnodes = get_node_info(config, node["code"])
            if newnodes is not None and len(newnodes) > 0:
                get_node_media(config, newnodes, images, videos)


    if "is_video" in node and (node["is_video"] == "true" or node["is_video"] == True):
        if "video_url" in node:
            videourl = node["video_url"]
        else:
            #videourl = rssit.util.get_local_url("/f/instagram/v/" + node["code"])
            return get_node_media(config, get_node_info(config, node["code"]), images, videos)

        found = False
        for video in videos:
            if video["video"] == videourl:
                found = True
                break

        if not found:
            videos.append({
                "image": get_normalized_array(config, normalized, image_src),
                "video": get_normalized_array(config, normalize_image(videourl), videourl)
            })
    else:
        ok = True
        for image in images:
            #if base_image(image) == base_image(normalized):
            if type(image) == list:
                image = image[0]
            if image_basename(image) == image_basename(normalized):
                ok = False
                break
        if ok:
            for video in videos:
                if "image" not in video:
                    # shouldn't happen?
                    continue
                video_image = video["image"]
                if type(video_image) == list:
                    video_image = video_image[0]
                if image_basename(video_image) == image_basename(normalized):
                    ok = False
                    break

        if ok:
            images.append(get_normalized_array(config, normalized, image_src))


def get_app_headers(config):
    config = rssit.util.simple_copy(config)
    config["httpheader_User-Agent"] = instagram_ua
    config["httpheader_x-ig-capabilities"] = "36oD"
    config["httpheader_accept"] = "*/*"
    #config["httpheader_accept-encoding"] = "gzip, deflate, br"
    config["httpheader_accept-language"] = "en-US,en;q=0.8"
    return config


def has_cookie(config):
    for key in config:
        if key.lower() == "httpheader_cookie" and config[key]:
            return True
    return False


def do_app_request(config, endpoint, **kwargs):
    if not has_cookie(config):
        return None

    return app_api.run(config, endpoint, **kwargs)
    #config = get_app_headers(config)
    #data = rssit.util.download(endpoint, config=config, http_noextra=True)
    #return rssit.util.json_loads(data)


def do_graphql_request(config, endpoint, variables):
    if config["use_hash_graphql"]:
        retval = graphql_hash_api.run(config, endpoint, variables)
    else:
        retval = graphql_id_api.run(config, endpoint, variables)
    #pprint.pprint(retval)
    return retval
    #data = rssit.util.download(endpoint, config=config)
    #return rssit.util.json_loads(data)


def get_stories_app(config, userid):
    return do_app_request(config, "stories", uid=userid)
    #storiesurl = "https://i.instagram.com/api/v1/feed/user/" + userid + "/story/"
    #return do_app_request(config, storiesurl)


def get_stories_graphql(config, userid):
    variables = {
        "reel_ids": [userid],
        "precomposed_overlay": False
    }
    return do_graphql_request(config, "stories", variables)
    #storiesurl = endpoint_getstories + urllib.parse.quote(rssit.util.json_dumps(variables))
    #return do_graphql_request(config, storiesurl)


def get_reelstray_app(config):
    if config["use_reelstray_cache"]:
        result = reelstray_cache.get("reels_tray")
        if result:
            return result

    result = do_app_request(config, "reels_tray")
    reelstray_cache.add("reels_tray", result)
    return result
    #storiesurl = "https://i.instagram.com/api/v1/feed/reels_tray/"
    #return do_app_request(config, storiesurl)


def get_user_info(config, userid, force=False):
    userinfo = None
    cached = True
    if not force:
        userinfo = api_userinfo_cache.get(userid)
        if userinfo and "user" in userinfo and "pk" not in userinfo:
            userinfo = userinfo["user"]
    if not userinfo:
        cached = False
        userinfo_app = do_app_request(config, "user_info", uid=userid)
        if not userinfo_app:
            sys.stderr.write("Unable to get app request!\n")
            return (None, False)
        userinfo = userinfo_app["user"]
        api_userinfo_cache.add(userid, userinfo)
    return (userinfo, cached)
    #return do_app_request(config, "https://i.instagram.com/api/v1/users/" + userid + "/info/")


def get_user_info_by_username_a1(config, username, *args, **kwargs):
    extra = {}
    if "max_id" in kwargs and kwargs["max_id"]:
        #extra = "max_id=" + str(kwargs["max_id"])
        extra = {
            "max_id": str(kwargs["max_id"])
        }
    return web_api.run(config, "user_a1", username.strip("/"), _overlay={"query": extra})["graphql"]["user"]
    #return do_a1_request(config, username, **extra)["graphql"]["user"]


def get_user_info_by_username_website(config, username):
    return get_user_page(config, username)


def get_user_info_by_username(config, username, *args, **kwargs):
    if "use_profile_a1" in config and config["use_profile_a1"]:
        return get_user_info_by_username_a1(config, username, *args, **kwargs)
    else:
        return get_user_info_by_username_website(config, username)


def get_user_media_by_username(config, username):
    return do_a1_request(config, username + "/media")["items"]


def do_website_request(config, url):
    data = rssit.util.download(url, config=config)

    decoded = parse_webpage_request(config, config, data)

    global _sharedData
    _sharedData = decoded

    return decoded

    #jsondatare = re.search(r"window._sharedData *= *(?P<json>.*?);</script>", str(data))
    jsondatare = re.search(r"window._sharedData *= *(?P<json>.*?}) *;\\n *window\.__initialDataLoaded", str(data))
    if jsondatare is None:
        sys.stderr.write("No sharedData!\n")
        return None

    jsondata = bytes(jsondatare.group("json"), 'utf-8').decode('unicode-escape')
    decoded = rssit.util.json_loads(jsondata)
    #print(jsondata)

    #global _sharedData
    #_sharedData = decoded
    #
    #return decoded


def get_user_page(config, username):
    url = "https://www.instagram.com/" + username + "/"  # / to avoid redirect

    """data = rssit.util.download(url, config=config)

    jsondatare = re.search(r"window._sharedData = *(?P<json>.*?);?</script>", str(data))
    if jsondatare is None:
        sys.stderr.write("No sharedData!\n")
        return None

    jsondata = bytes(jsondatare.group("json"), 'utf-8').decode('unicode-escape')
    decoded = rssit.util.json_loads(jsondata)"""

    decoded = do_website_request(config, url)

    try:
        return decoded["entry_data"]["ProfilePage"][0]["graphql"]["user"]
    except Exception:
        return decoded["entry_data"]["ProfilePage"]["graphql"]["user"]


def get_nodes_from_uid_graphql(config, uid, *args, **kwargs):
    variables = {
        "id": uid,
        "first": 12
    }

    for arg in kwargs:
        if kwargs[arg] is not None:
            variables[arg] = kwargs[arg]

    jsondumped = rssit.util.json_dumps(variables)
    url = endpoint_getentries + urllib.parse.quote(jsondumped)
    #return do_graphql_request(config, url)
    return do_graphql_request(config, "entries", variables)
    #config = get_app_headers(config)
    #data = rssit.util.download(url, config=config, http_noextra=True)
    #decoded = rssit.util.json_loads(data)
    #return decoded


def get_nodes_from_uid_app(config, uid, *args, **kwargs):
    newargs = {
        "uid": uid
    }

    if "max_id" in kwargs and kwargs["max_id"]:
        newargs["max_id"] = kwargs["max_id"]

    try:
        value = do_app_request(config, "user_feed", **newargs)
        return value
    except Exception as e:
        sys.stderr.write("Unable to fetch " + uid + "'s feed via app request, are you following them?\n")
        return None
    #url = "https://i.instagram.com/api/v1/feed/user/" + uid + "/"
    #if "max_id" in kwargs and kwargs["max_id"]:
    #    url += "?max_id=" + kwargs["max_id"]
    #return do_app_request(config, url)


def force_array(obj):
    if type(obj) == dict:
        a = []
        for i in obj:
            a.append(obj[i])
        return a
    return obj


def get_largest_url(items):
    if type(items) == str:
        return items

    max_ = 0
    url = None
    for item in force_array(items):
        if "height" in item:
            total = item["height"] + item["width"]
        elif "config_height" in item:
            total = item["config_height"] + item["config_width"]
        if total > max_:
            max_ = total

            if "url" in item:
                url = item["url"]
            else:
                url = item["src"]
    return url


def get_stories(config, userid):
    if not config["use_graphql_stories"]:
        stories = get_stories_app(config, userid)
    else:
        oldstories = get_stories_graphql(config, userid)
        reels_media = oldstories["data"]["reels_media"]

        if len(reels_media) > 0:
            stories = {
                "reel": oldstories["data"]["reels_media"][0]
            }
        else:
            stories = {"reel": None}
    #pprint.pprint(stories)
    return stories


def normalize_node(node):
    if "node" in node:
        node = node["node"]
    node = rssit.util.simple_copy(node)

    if "caption" in node and node["caption"] is None:
        node["caption"] = ""

    if "caption" not in node:
        if (("edge_media_to_caption" in node) and
            ("edges" in node["edge_media_to_caption"]) and
            (len(node["edge_media_to_caption"]["edges"]) > 0)):
            firstedge = node["edge_media_to_caption"]["edges"][0]
            node["caption"] = firstedge["node"]["text"]

    if "caption" in node and type(node["caption"]) == dict:
        node["caption"] = node["caption"]["text"]

    if "date" not in node:
        if "taken_at_timestamp" in node:
            node["date"] = node["taken_at_timestamp"]
        elif "created_time" in node:
            node["date"] = int(node["created_time"])
        elif "taken_at" in node:
            node["date"] = node["taken_at"]

    if "shortcode" not in node:
        if "pk" in node:
            node["shortcode"] = to_shortcode(node["pk"])

    if "code" not in node:
        if "shortcode" in node:
            node["code"] = node["shortcode"]

    if "type" not in node:
        if "__typename" in node:
            if node["__typename"] in ["GraphImage", "GraphStoryImage"]:
                node["type"] = "image"
            elif node["__typename"] in ["GraphVideo", "GraphStoryVideo"]:
                node["type"] = "video"
            elif node["__typename"] == "GraphSidecar":
                node["type"] = "carousel"

    if (("carousel_media" in node and type(node["carousel_media"]) == list and len(node["carousel_media"]) > 0)
        and ("type" in node and node["type"] != "carousel")):
        node["type"] = "carousel"

    if "video_url" not in node:
        base = None

        if "videos" in node:
            base = node["videos"]
        elif "video_resources" in node:
            base = node["video_resources"]
        elif "video_versions" in node:
            base = node["video_versions"]

        if base:
            new_url = get_largest_url(base)
            if new_url:
                node["video_url"] = new_url

            """max_ = 0
            for video in node["videos"]:
                total = video["height"] + video["width"]
                if total > max_:
                    max_ = total
                    node["video_url"] = video["url"]"""

    #if "video_url" in node:
    #    node["video_url"] = normalize_image(node["video_url"])

    if "type" not in node:
        if "video_url" not in node:
            node["type"] = "image"
        else:
            node["type"] = "video"

    if "display_url" not in node:
        base = None

        if "images" in node:
            base = node["images"]
        elif "image_versions2" in node:
            base = node["image_versions2"]["candidates"]

        if base:
            new_url = get_largest_url(base)
            if new_url:
                node["display_url"] = new_url

            """new_url = get_largest_url(node["images"])
            if new_url:
                node["display_url"] = new_url"""

    if ("display_url" not in node) and ("carousel_media" in node):
        node["display_url"] = normalize_node(node["carousel_media"][0])["display_url"]

    #if "display_url" in node:
    #    node["display_url"] = normalize_image(node["display_url"])

    if "is_video" not in node:
        node["is_video"] = node["type"] == "video"

    if node["type"] == "carousel" and "carousel_media" not in node:
        if "edge_sidecar_to_children" in node:
            node["carousel_media"] = []
            for newnode in node["edge_sidecar_to_children"]["edges"]:
                node["carousel_media"].append(newnode["node"])

    if "user" not in node:
        if "owner" in node:
            node["user"] = node["owner"]

    return node


def get_entry_from_node(config, node, user):
    node = normalize_node(node)

    caption = ""
    if "product_type" in node and node["product_type"] == "igtv":
        caption = "[IGTV] "

    if "caption" in node:
        caption = caption + str(node["caption"])
    elif caption == "":
        caption = None

    date = datetime.datetime.fromtimestamp(int(node["date"]), None).replace(tzinfo=tzlocal())

    images = []
    videos = []

    get_node_media(config, node, images, videos)

    if False and "__typename" in node and node["__typename"] == "GraphSidecar":
        newnodes = get_node_info(config, node["code"])

        if len(newnodes) > 0:
            if "edge_sidecar_to_children" not in newnodes:
                sys.stderr.write("No 'edge_sidecar_to_children' property in " + sidecar_url + "\n")
            else:
                for newnode in newnodes["edge_sidecar_to_children"]["edges"]:
                    get_node_media(config, newnode["node"], images, videos)

    return {
        "url": "https://www.instagram.com/p/%s/" % node["code"],
        "caption": caption,
        "author": user,
        "date": date,
        "images": images,
        "videos": videos
    }


def normalize_story_entries(config, storiesjson):
    if "reel" not in storiesjson or not storiesjson["reel"]:
        storiesjson["reel"] = {"items": []}

        if "tray" in storiesjson and type(storiesjson["tray"]) == list:
            for tray in storiesjson["tray"]:
                if "items" not in tray:
                    continue
                for item in tray["items"]:
                    storiesjson["reel"]["items"].append(item)

    if "post_live_item" not in storiesjson or not storiesjson["post_live_item"]:
        storiesjson["post_live_item"] = {"broadcasts": []}

        if (("post_live" in storiesjson and storiesjson["post_live"])
            and ("post_live_items" in storiesjson["post_live"]
                 and storiesjson["post_live"]["post_live_items"])):
            for item in storiesjson["post_live"]["post_live_items"]:
                if "broadcasts" in item and item["broadcasts"]:
                    for broadcast in item["broadcasts"]:
                        storiesjson["post_live_item"]["broadcasts"].append(broadcast)

    if "broadcasts" not in storiesjson or not storiesjson["broadcasts"]:
        storiesjson["broadcasts"] = []

        if "broadcast" in storiesjson and storiesjson["broadcast"]:
            storiesjson["broadcasts"].append(storiesjson["broadcast"])

    return storiesjson


def parse_story_entries(config, storiesjson, do_stories=True):
    """if "reel" not in storiesjson or not storiesjson["reel"]:
        storiesjson["reel"] = {"items": []}

        if "tray" in storiesjson and type(storiesjson["tray"]) == list:
            for tray in storiesjson["tray"]:
                if "items" not in tray:
                    continue
                for item in tray["items"]:
                    storiesjson["reel"]["items"].append(item)

    if "post_live_item" not in storiesjson or not storiesjson["post_live_item"]:
        storiesjson["post_live_item"] = {"broadcasts": []}

        if (("post_live" in storiesjson and storiesjson["post_live"])
            and ("post_live_items" in storiesjson["post_live"]
                 and storiesjson["post_live"]["post_live_items"])):
            for item in storiesjson["post_live"]["post_live_items"]:
                if "broadcasts" in item and item["broadcasts"]:
                    for broadcast in item["broadcasts"]:
                        storiesjson["post_live_item"]["broadcasts"].append(broadcast)

    if "broadcasts" not in storiesjson or not storiesjson["broadcasts"]:
        storiesjson["broadcasts"] = []

        if "broadcast" in storiesjson and storiesjson["broadcast"]:
            storiesjson["broadcasts"].append(storiesjson["broadcast"])"""
    #pprint.pprint(storiesjson)
    if "raw" in config and config["raw"]:
        pprint.pprint(storiesjson)

    storiesjson = normalize_story_entries(config, storiesjson)

    entries = []

    story_items = []

    if config["stories"]:
        if "tray" in storiesjson:
            max_reelitems = config["max_extra_stories"]
            max_requests = config["max_extra_story_requests"]
            current_reelitem = 0
            current_request = 0
            storiesjson["tray"].sort(key=lambda x: int(x["latest_reel_media"]) if "latest_reel_media" in x else 0)
            newtray = reversed(storiesjson["tray"])
            for tray_user in newtray:
                # most users don't have items
                # via the "latest_reel_media" property, it would be possible to check for, and query stories
                if "items" in tray_user:
                    for item in tray_user["items"]:
                        story_items.append(item)
                else:
                    if "latest_reel_media" in tray_user:
                        if current_reelitem >= max_reelitems:
                            continue
                        current_reelitem += 1
                        basepattern = "*_" + str(tray_user["id"])
                        pattern = str(tray_user["latest_reel_media"]) + "_" + basepattern
                        found = False
                        if True:
                            for skey in stories_cache.scan(pattern):
                                found = True
                                break
                        if found:
                            for key in stories_cache.scan(basepattern):
                                story_items.append(stories_cache.get(key))
                        else:
                            if current_request >= max_requests:
                                continue
                            current_request += 1

                            try:
                                user_stories = get_stories(config, tray_user["id"])
                                user_stories = normalize_story_entries(config, user_stories)
                                if "reel" in user_stories:
                                    for item in user_stories["reel"]["items"]:
                                        found = False
                                        for sitem in storiesjson["reel"]["items"]:
                                            if sitem["id"] == item["id"]:
                                                found = True
                                                break
                                        if not found:
                                            storiesjson["reel"]["items"].append(item)
                                #if "post_live_item" in user_stories:
                                #    storiesjson["post_live_item"]["broadcasts"].extend(user_stories["post_live_item"]["broadcasts"])
                                #if "broadcasts" in user_stories:
                                #    storiesjson["broadcasts"].extend(user_stories["broadcasts"])
                            except Exception as e:
                                sys.stderr.write(str(e) + " (HTTP: " + str(config["http_error"]) + ")\n")
                                pass
        if "reel" in storiesjson and "items" in storiesjson["reel"]:
            for item in storiesjson["reel"]["items"]:
                story_items.append(item)

    for item in story_items:#storiesjson["reel"]["items"]:
        if not config["stories"]:
            #if not do_stories:
            break

        if "taken_at" in item and "id" in item:
            scacheid = str(item["taken_at"]) + "_" + str(item["id"])
            stories_cache.add(scacheid, item)

        item = normalize_node(item)

        image_src = item["display_url"]
        image = normalize_image(image_src)

        url = image
        images = [get_normalized_array(config, image, image_src)]
        videos = []

        if "video_url" in item and item["video_url"]:
            videos = [{
                "image": get_normalized_array(config, image, image_src),
                "video": get_normalized_array(config, normalize_image(item["video_url"]), item["video_url"])
            }]
            url = videos[0]["video"]
            images = []

        caption = "[STORY]"

        if "caption" in item and item["caption"]:
            caption = "[STORY] " + item["caption"]

        date = datetime.datetime.fromtimestamp(int(item["date"]), None).replace(tzinfo=tzlocal())

        extra = ""
        if "story_cta" in item and item["story_cta"]:
            links = []
            for cta in item["story_cta"]:
                for thing in cta:
                    if thing == "links":
                        for link in cta["links"]:
                            links.append(link["webUri"])
                    else:
                        sys.stderr.write("Unhandled story_cta: " + str(thing) + "!\n")

            if len(links) > 0:
                extra += "Links:\n"
                for link in links:
                    extra += str(link) + "\n"

        guid_url = "http://guid.instagram.com/" + item["id"]
        story_url = guid_url
        if "story_post_url" in config and config["story_post_url"] is True:
            story_url = id_to_url(item["id"])

        entries.append({
            "url": story_url,
            "guid": guid_url,
            "caption": caption,
            "extratext": extra,
            "author": uid_to_username(config, item["user"]),  #["username"],
            "date": date,
            "images": images,
            "videos": videos
        })

    for item in storiesjson["post_live_item"]["broadcasts"]:
        if not config["lives"]:
            break

        date = datetime.datetime.fromtimestamp(int(item["published_time"]), None).replace(tzinfo=tzlocal())

        post_video = {
            "video": rssit.util.get_local_url("/f/instagram/livereplay/" + item["media_id"])
        }

        if "cover_frame_url" in item:
            post_video["image"] = item["cover_frame_url"]

        entries.append({
            "url": "http://guid.instagram.com/" + item["media_id"],
            "caption": "[LIVE REPLAY]",
            "author": uid_to_username(config, item["broadcast_owner"]),  #["username"],
            "date": date,
            "images": [],
            "videos": [post_video]
        })

    for item in storiesjson["broadcasts"]:
        if not config["lives"]:
            break

        date = datetime.datetime.fromtimestamp(int(item["published_time"]), None).replace(tzinfo=tzlocal())

        video_item = {
            "video": item.get("dash_abr_playback_url") or item["dash_playback_url"],
            "live": True,
            "type": "instagram_live"
        }

        if "cover_frame_url" in item:
            video_item["image"] = item["cover_frame_url"]

        guests = []
        try:
            if "cobroadcasters" in item and type(item["cobroadcasters"]) == list:
                for cobroadcaster in item["cobroadcasters"]:
                    guests.append(uid_to_username(config, cobroadcaster))
        except Exception:
            pass

        entries.append({
            "url": "http://guid.instagram.com/" + item["media_id"],
            "caption": "[LIVE]",
            "author": uid_to_username(config, item["broadcast_owner"]),  #["username"],
            "coauthors": guests,
            "date": date,
            "images": [],
            "videos": [video_item]
        })

    return entries


def get_story_entries(config, uid, username):
    if not config["stories"] and not config["lives"]:
        return []

    try:
        storiesjson = get_stories(config, uid)

        if not storiesjson:
            sys.stderr.write("Warning: not logged in, so no stories\n")
            return []

        if "raw" in config and config["raw"]:
            pprint.pprint(storiesjson)
    except Exception as e:  # soft error
        sys.stderr.write(str(e) + " (HTTP: " + str(config["http_error"]) + ")\n")
        return []

    return parse_story_entries(config, storiesjson)


def get_reels_entries(config):
    storiesjson = get_reelstray_app(config)

    if not storiesjson:
        sys.stderr.write("Warning: not logged in, so no stories\n")
        return []

    return parse_story_entries(config, storiesjson, do_stories=False)


def get_author(config, userinfo):
    author = "@" + userinfo["username"]

    if not config["author_username"]:
        if "full_name" in userinfo and type(userinfo["full_name"]) == str and len(userinfo["full_name"]) > 0:
            author = userinfo["full_name"]

    return author


def cut_to_nearest(num, nearest):
    return int(num / nearest) * nearest


def get_feed(config, userinfo):
    username = userinfo["username"].lower()

    outobj = {
        "title": get_author(config, userinfo),
        "description": "%s's instagram" % username,
        "url": "https://www.instagram.com/" + username + "/",
        "author": username,
        "entries": []
    }

    if "description_uid" in config and config["description_uid"]:
        followers = 0
        if "edge_followed_by" in userinfo:
            followers = int(userinfo["edge_followed_by"]["count"])
        elif "follower_count" in userinfo:
            followers = int(userinfo["follower_count"])

        uid = 0
        if "id" in userinfo:
            uid = userinfo["id"]
        elif "pk" in userinfo:
            uid = userinfo["pk"]

        # To reduce the amount of changed entries in webrssview
        if config["round_followers"]:
            followers = cut_to_nearest(followers, 1000)

            if followers > 100*1000:
                followers = cut_to_nearest(followers, 10*1000)
            if followers > 1000*1000:
                followers = cut_to_nearest(followers, 100*1000)
        outobj["description"] = "%s\n---\nUID: %s\nFollowers: %s" % (
            outobj["description"],
            str(uid),
            str(followers)
        )
        if "external_url" in userinfo:
            outobj["description"] += "\nLink: %s" % userinfo["external_url"]

    return outobj


def get_home_entries(config):
    origcount = config["count"]
    count = config["count"]
    if count < 0 or count > config["max_graphql_count"]:
        count = config["max_graphql_count"]
        if count < 0:
            origcount = count

    variables = {
        "fetch_media_item_count": count,
        "cached_feed_item_ids": [],
        "has_stories": False,
        "fetch_like": 3,
        "fetch_comment_count": 4,
        "has_threaded_comments": True
    }

    if count <= 12 and False:
        variables = {}

    def get_nodes(cursor):
        if cursor:
            variables["fetch_media_item_cursor"] = cursor
        home_api = do_graphql_request(config, "home", variables)["data"]["user"]["edge_web_feed_timeline"]

        nodes = []

        for edge in home_api["edges"]:
            if "node" in edge:
                edge = edge["node"]
            post_cache.add(edge["shortcode"], edge)
            #nodes.append(get_entry_from_node(config, edge, edge["owner"]["username"]))
            nodes.append(edge)

        return (nodes, home_api["page_info"]["end_cursor"], home_api["page_info"]["has_next_page"])

    nodes = instagram_paginate(config, origcount, get_nodes)
    entries = []
    for node in nodes:
        entries.append(get_entry_from_node(config, node, node["owner"]["username"]))

    return entries


def get_profilepic_entry_raw(config, userinfo):
    if not userinfo:
        return

    url = None
    # api
    if "hd_profile_pic_url_info" in userinfo:
        url = userinfo["hd_profile_pic_url_info"]["url"]
    # graphql
    elif "profile_pic_url_hd" in userinfo:
        url = userinfo["profile_pic_url_hd"]
    elif "profile_pic_url" in userinfo:
        url = userinfo["profile_pic_url"]
    else:
        sys.stderr.write("No profile pic!\n")
        return

    newurl = normalize_image(url)
    id_ = re.sub(r".*/([^.]*)\.[^/]*$", "\\1", newurl)
    id_withext = image_basename(newurl) # re.sub(r".*/([^.]*\.[^/]*)$", "\\1", newurl)

    date = rssit.util.parse_date(-1)
    if "profile_pic_id" in userinfo:
        date = get_datetime_from_id(userinfo["profile_pic_id"])

    return {
        "url": newurl,
        "caption": "[DP] " + str(id_),
        "author": userinfo["username"],
        "date": date,
        "guid": "https://scontent-sea1-1.cdninstagram.com//" + id_withext,
        "images": [get_normalized_array(config, newurl, url)],
        "videos": []
    }


def get_profilepic_entry(config, userinfo):
    if not config["use_profilepic_api"]:
        return get_profilepic_entry_raw(config, userinfo)

    if "hd_profile_pic_url_info" not in userinfo:
        new_userinfo, cached = get_user_info(config, userinfo["id"])
        if cached:
            api_basename = image_basename(new_userinfo["hd_profile_pic_url_info"]["url"])
            orig_basename = image_basename(userinfo["profile_pic_url"])
            if api_basename != orig_basename:
                new_userinfo, cached = get_user_info(config, userinfo["id"], True)
        return get_profilepic_entry_raw(config, new_userinfo)


def get_igtv(config, userinfo):
    if "edge_felix_video_timeline" not in userinfo:
        return None

    videos = userinfo["edge_felix_video_timeline"]
    if "edges" not in videos and type(videos["edges"]) is not list:
        return None

    edges = videos["edges"]

    entries = []
    for edge in edges:
        entries.append(get_entry_from_node(config, edge, userinfo["username"]))

    return entries


def instagram_paginate(config, mediacount, f):
    total = config["count"]
    if config["count"] == -1:
        total = mediacount

    maxid = None
    nodes = []
    nodecount = 0
    console = False
    has_next_page = True

    while has_next_page:
        if total >= 0 and nodecount >= total:
            break

        output = f(maxid)
        if len(output[0]) == 0:
            sys.stderr.write("\rLoading media (%i/%i, skipping)... " % (len(nodes), total))
            sys.stderr.flush()
            console = True
            break

        nodecount += len(output[0])

        for item in output[0]:
            duplicate = False
            newitem = normalize_node(item)
            for oitem in nodes:
                if newitem["shortcode"] == normalize_node(oitem)["shortcode"]:
                    duplicate = True
                    break
            if duplicate:
                continue
            nodes.append(item)

        if total < 0 or nodecount < total:
            sys.stderr.write("\rLoading media (%i/%s)... " % (nodecount, str(total) if total >= 0 else "??"))
            sys.stderr.flush()
            console = True
        maxid = output[1]
        has_next_page = output[2]

    if console:
        sys.stderr.write("\n")
        sys.stderr.flush()

    return nodes


def generate_user(config, *args, **kwargs):
    config["is_index"] = True  # for livestreams they are part of

    if "username" in kwargs:
        username = kwargs["username"].lower()

        if not config["use_profile_a1"]:
            decoded_user = get_user_page(config, username)
        else:
            decoded_user = get_user_info_by_username(config, username)

        uid = decoded_user["id"]

        # cache
        uid_to_username(config, {
            "uid": uid,
            "username": username
        })

        mediacount = decoded_user["edge_owner_to_timeline_media"]["count"]
        medianodes = decoded_user["edge_owner_to_timeline_media"]["edges"]
    elif "uid" in kwargs:
        uid = kwargs["uid"]
        decoded_user, decoded_user_cached = get_user_info(config, uid, True)
        username = decoded_user["username"]

        mediacount = decoded_user["media_count"]
        medianodes = []

    user_isnt_following = "followed_by_viewer" not in decoded_user or not decoded_user["followed_by_viewer"]

    if config["fail_if_not_following"]:
        if user_isnt_following:
            if "requested_by_viewer" not in decoded_user or not decoded_user["requested_by_viewer"]:
                config["http_error"] = 490
                return None

    feed = get_feed(config, decoded_user)

    ppentry = get_profilepic_entry(config, decoded_user)
    if ppentry:
        feed["entries"].append(ppentry)

    igtv = get_igtv(config, decoded_user)
    if igtv and config["igtv"]:
        feed["entries"].extend(igtv)

    def paginate(f, maxid=None):
        total = config["count"]
        if config["count"] == -1:
            total = mediacount

        nodes = []
        nodecount = 0
        console = False
        has_next_page = True

        while (nodecount < total) and has_next_page:
            output = f(maxid)
            if len(output[0]) == 0:
                sys.stderr.write("\rLoading media (%i/%i, skipping)... " % (len(nodes), total))
                sys.stderr.flush()
                console = True
                break

            nodecount += len(output[0])

            for item in output[0]:
                duplicate = False
                newitem = normalize_node(item)
                for oitem in nodes:
                    if newitem["shortcode"] == normalize_node(oitem)["shortcode"]:
                        duplicate = True
                        break
                if duplicate:
                    continue
                nodes.append(item)

            if nodecount < total:
                sys.stderr.write("\rLoading media (%i/%i)... " % (nodecount, total))
                sys.stderr.flush()
                console = True
            maxid = output[1]
            has_next_page = output[2]

        if console:
            sys.stderr.write("\n")
            sys.stderr.flush()

        return nodes

    count = config["count"]

    if count < 0:
        count = mediacount

    if config["use_media"]:
        nodes = get_user_media_by_username(config, username)
    elif config["use_graphql_entries"] and count > len(medianodes):
        # there doesn't seem to be a limit, but let's impose one just in case
        if count > config["max_graphql_count"]:
            count = config["max_graphql_count"]
        elif count == 1:
            count = 20

        cursor = None

        try:
            timeline_media = decoded_user["edge_owner_to_timeline_media"]
            #cursor = timeline_media["page_info"]["end_cursor"]
        except Exception as e:
            pass

        def get_nodes(cursor):
            media = get_nodes_from_uid_graphql(config, uid, first=count, after=cursor)
            edges = media["data"]["user"]["edge_owner_to_timeline_media"]["edges"]
            pageinfo = media["data"]["user"]["edge_owner_to_timeline_media"]["page_info"]

            end_cursor = pageinfo["end_cursor"]
            has_next_page = pageinfo["has_next_page"]

            # workaround for private accounts
            if len(edges) == 0:
                end_cursor = None
                has_next_page = None

            nodes = []
            for node in edges:
                nodes.append(node["node"])

            return (nodes, end_cursor, has_next_page)

        nodes = paginate(get_nodes, cursor)
    elif config["use_api_entries"] and not user_isnt_following:
        def get_nodes(cursor):
            media = get_nodes_from_uid_app(config, uid, max_id=cursor)

            return (media["items"], media["next_max_id"], media["more_available"])
        nodes = paginate(get_nodes)
    else:
        def get_nodes(max_id):
            if max_id or "edge_owner_to_timeline_media" not in decoded_user:
                media = get_user_info_by_username(config, username, max_id=max_id)["edge_owner_to_timeline_media"]
            else:
                media = decoded_user["edge_owner_to_timeline_media"]
            nodes = media["edges"]
            page_info = media["page_info"]

            end_cursor = page_info["end_cursor"]
            has_next_page = page_info["has_next_page"]

            # workaround for private accounts
            if len(nodes) == 0:
                end_cursor = None
                has_next_page = None

            if not config["use_profile_a1"]:
                end_cursor = None
                has_next_page = None

            return (nodes, end_cursor, has_next_page)
        nodes = paginate(get_nodes)

    for node in nodes:
        feed["entries"].append(get_entry_from_node(config, node, username))

    story_entries = get_story_entries(config, uid, username)
    for entry in story_entries:
        feed["entries"].append(entry)

    return ("social", feed)


def generate_tagged(config, username):
    config["is_index"] = True

    feed = {
        "title": "@%s's tagged photos" % username,
        "description": "Photos that tag %s" % username,
        "url": "https://www.instagram.com/%s/tagged/" % username,
        "author": "instagram",
        "entries": []
    }

    origcount = config["count"]
    count = config["count"]
    if count == 1:
        count = config["max_graphql_count"]

    if count < 0 or count > config["max_graphql_count"]:
        count = config["max_graphql_count"]
        if count < 0:
            origcount = count

    userinfo = get_user_info_by_username(config, username)

    variables = {
        "id": str(userinfo["id"]),
        "first": count
    }

    def get_nodes(cursor):
        if cursor:
            variables["after"] = cursor
        tagged_api = do_graphql_request(config, "tagged", variables)["data"]["user"]["edge_user_to_photos_of_you"]

        nodes = []

        for edge in tagged_api["edges"]:
            if "node" in edge:
                edge = edge["node"]
            #post_cache.add(edge["shortcode"], edge)
            nodes.append(edge)

        return (nodes, tagged_api["page_info"]["end_cursor"], tagged_api["page_info"]["has_next_page"])

    nodes = instagram_paginate(config, origcount, get_nodes)
    entries = []
    for node in nodes:
        node_username = node["owner"].get("username", None)
        if not node_username:
            node_username = uid_to_username(config, node["owner"]["id"])
        entries.append(get_entry_from_node(config, node, node_username))

    feed["entries"] = entries
    return ("social", feed)


def generate_home(config):
    config["is_index"] = True

    feed = {
        "title": "Home",
        "description": "Instagram homepage (current feeds)",
        "url": "https://www.instagram.com/",
        "author": "instagram",
        "entries": []
    }

    feed["entries"] = get_home_entries(config)

    return ("social", feed)


def generate_reelstray(config):
    config["is_index"] = True

    feed = {
        "title": "Live streams",
        "description": "Live streams/replays (reels tray)",
        "url": "https://reelstray.instagram.com/",  # fake url for now
        "author": "instagram",
        "entries": []
    }

    feed["entries"] = get_reels_entries(config)

    return ("social", feed)


def generate_video(config, server, id):
    url = "https://www.instagram.com/p/%s/" % id

    data = rssit.util.download(url, config=config)

    match = re.search(r"\"og:video\".*?content=\"(?P<video>.*?)\"", str(data))

    server.send_response(301, "Moved")
    server.send_header("Location", match.group("video"))
    server.end_headers()

    return True


def generate_livereplay_reelstray(config, server, id):
    reelsurl = "https://i.instagram.com/api/v1/feed/reels_tray/"
    config = get_app_headers(config)
    reels_data = rssit.util.download(reelsurl, config=config, http_noextra=True)

    reelsjson = rssit.util.json_loads(reels_data)

    for live in reelsjson["post_live"]["post_live_items"]:
        for broadcast in live["broadcasts"]:
            if id == broadcast["media_id"]:
                server.send_response(200, "OK")
                server.send_header("Content-type", "application/xml")
                server.end_headers()
                server.wfile.write(broadcast["dash_manifest"].encode('utf-8'))
                return True

    sys.stderr.write("Unable to find media id %s\n" % id)
    return None


def generate_livereplay(config, server, id):
    uid = re.sub(r".*_([0-9]+)$", "\\1", id)
    reelsurl = "https://i.instagram.com/api/v1/feed/user/" + uid + "/story/"

    config = get_app_headers(config)
    reels_data = rssit.util.download(reelsurl, config=config, http_noextra=True)

    reelsjson = rssit.util.json_loads(reels_data)

    for broadcast in reelsjson["post_live_item"]["broadcasts"]:
        if id == broadcast["media_id"]:
            server.send_response(200, "OK")
            server.send_header("Content-type", "application/xml")
            server.end_headers()
            server.wfile.write(broadcast["dash_manifest"].encode('utf-8'))
            return True

    sys.stderr.write("Unable to find media id %s\n" % id)
    return None


shortcode_arr = [chr(x) for x in range(ord('A'), ord('Z') + 1)]
shortcode_arr.extend([chr(x) for x in range(ord('a'), ord('z') + 1)])
shortcode_arr.extend([chr(x) for x in range(ord('0'), ord('9') + 1)])
shortcode_arr.extend(['-', '_'])


def to_shortcode(n):
    if n < 64:
        return shortcode_arr[n]
    else:
        return to_shortcode(n // 64) + shortcode_arr[n % 64]


def id_to_url(id):
    if "_" in id:
        id = id.split("_")[0]

    shortcode = to_shortcode(int(id))
    return "https://www.instagram.com/p/" + shortcode + "/"


def get_uid_from_id(id):
    return id.split("_")[1]


# https://carrot.is/coding/instagram-ids
def get_timestamp_from_id(id):
    return (int(id.split("_")[0]) >> (64-41)) + (1314220021*1000)


def get_datetime_from_id(id):
    return datetime.datetime.fromtimestamp(int(get_timestamp_from_id(id) / 1000), None).replace(tzinfo=tzlocal())


def normalize_user(user):
    if "uid" not in user:
        if "pk" in user:
            user["uid"] = user["pk"]
        elif "id" in user:
            user["uid"] = user["id"]

    return user


def uid_to_username(config, uid):
    real_uid = uid
    do_cache = False

    if type(uid) == dict:
        uid = normalize_user(rssit.util.simple_copy(uid))

        if "uid" in uid:
            real_uid = uid["uid"]
            do_cache = True
        elif "username" in uid:
            return uid["username"]
        else:
            return None

    if "debug" in config and config["debug"]:
        return real_uid

    username = uid_to_username_cache.get(real_uid)
    if not username or do_cache:
        if type(uid) == dict and "username" in uid:
            username = uid["username"]
        else:
            userinfo, cached = get_user_info(config, real_uid)
            username = userinfo["username"]
        uid_to_username_cache.add(real_uid, username)
    return username


def username_to_url(username):
    return "https://www.instagram.com/" + username + "/"


def uid_to_url(config, uid):
    return username_to_url(uid_to_username(config, uid))


def generate_convert(config, server, url):
    if url.startswith("uid/"):
        username = uid_to_username(config, url[len("uid/"):])

        server.send_response(301, "Moved")
        server.send_header("Location", "https://www.instagram.com/" + username)
        server.end_headers()

    return True


def generate_news_media(config, medias):
    content = ""
    for media in medias:
        #content += "<p><a href='%s'><img src='%s' alt='(image)' /></a></p>" % (
        #    id_to_url(media["id"]),
        #    normalize_image(media["image"]),
        #)
        content += rssit.converters.social_to_feed.do_image(config, get_normalized_array(config, normalize_image(media["image"]), media["image"]), id_to_url(media["id"]))

    return content


def generate_simple_news(config, story):
    args = story["args"]
    caption = args["text"]

    if "links" not in args:
        content = "<p>" + caption + "</p>"
    else:
        caption_parts = []
        last_end = 0

        for link in args["links"]:
            caption_parts.append(caption[last_end:link["start"]])

            if link["type"] == "user":
                caption_parts.append("<a href='%s'>%s</a>" % (
                    uid_to_url(config, link["id"]),
                    #rssit.util.get_local_url("/f/instagram/convert/uid/" + link["id"]),
                    caption[link["start"]:link["end"]]
                ))
            else:
                sys.stderr.write("Unhandled news type: " + link["type"] + "\n")
                caption_parts.append(caption[link["start"]:link["end"]])

            last_end = link["end"]

        caption_parts.append(caption[last_end:])

        content = "".join(caption_parts)
        content = "<p>" + content + "</p>"

    if "media" not in args:
        args["media"] = []

    content += generate_news_media(config, args["media"])

    return (caption, content)


def generate_news(config):
    #newsreq = do_app_request(config, "https://i.instagram.com/api/v1/news")
    newsreq = do_app_request(config, "news")

    if "raw" in config and config["raw"]:
        return ("feed", newsreq)

    config["no_dl"] = True

    feed = {
        "title": "News",
        "description": "Events happening in your Instagram feed",
        "url": "https://news.instagram.com/",  # fake url for now
        "author": "instagram",
        "entries": []
    }

    author = "instagram"

    for story in newsreq["stories"]:
        args = story["args"]

        story_type = story["story_type"]
        caption = args["text"]
        date = datetime.datetime.fromtimestamp(int(args["timestamp"]), None).replace(tzinfo=tzlocal())

        # story_type:
        # 12 = leave a comment
        # 13 = like comment
        # 60 = like post
        # 101 = started following
        # 128 = taking a video at n

        # type:
        # 1 = 1 person likes 1 post, or leave a comment on 1 post, or n people like/leave a comment on 1 post
        # 2 = 1 person likes n posts, or 'took n videos at n'
        # 4 = 1 person starts following 1-n other people
        # 14 = 1 person likes 1 comment

        subjs = []
        objs = []
        comments = {}

        link_users = []
        for link in args["links"]:
            if link["type"] == "user":
                link_users.append({
                    "uid": link["id"],
                    "username": caption[link["start"]:link["end"]]
                })

        if "media" in args and len(args["media"]) > 0:
            if len(args["media"]) > 1:
                # for "1 liked n of 2's posts."
                different_uids = False
                last_uid = None

                for media in args["media"]:
                    v = {
                        "media": media,
                        "uid": get_uid_from_id(media["id"])
                    }

                    if not last_uid:
                        last_uid = v["uid"]
                    elif v["uid"] != last_uid:
                        different_uids = True

                    objs.append(v)

                users = link_users
                if (len(args["media"]) > 1 and
                    len(link_users) > 1 and
                    not different_uids and
                    last_uid == link_users[-1]["uid"]):
                    users = link_users[:-1]

                for user in users:
                    subjs.append(user)
            elif "comment_ids" in args and len(args["comment_ids"]) > 1:
                # There are n comments on 1's post: @2: ...\n@3: ...
                # problem: only one user link (1, not 2 and 3)
                for user_i in range(len(link_users[1:])):
                    v = {
                        "comment": args["comment_ids"][user_i]
                    }
                    v.update(link_users[user_i])
                    subjs.append(v)

                v = {
                    "media": media,
                }
                v.update(link_users[0])
                objs.append(v)
            else:
                for user in link_users[:-1]:
                    subjs.append(user)
                v = {
                    "media": args["media"][0]
                }
                if "comment_id" in args:
                    v["comment"] = args["comment_id"]
                v.update(link_users[-1])
                objs.append(v)
        elif story_type == 101:
            subjs.append(link_users[0])
            objs.extend(link_users[1:])

        def add_simple():
            caption, content = generate_simple_news(config, story)
            feed["entries"].append({
                "url": "http://tuuid.instagram.com/tuuid:" + args["tuuid"],
                "title": caption,
                "author": author,
                "date": date,
                "content": content
            })

        if ((story_type != 12 and story_type != 13 and story_type != 60 and story_type != 101) or
            len(subjs) == 0 or
            len(objs) == 0 or
            ((story_type == 12 or story_type == 13) and len(args["media"]) > 1)):
            if story_type != 101 or True:
                sys.stderr.write("Possibly unhandled story_type: " + str(story_type) + "\n")
                if len(subjs) == 0 or len(objs) == 0:
                    sys.stderr.write("Unable to find subject(s) or object(s): " + pprint.pformat(story) + "\n")
            add_simple()
            continue

        if story_type == 12 or story_type == 13:
            lastpos = args["links"][-1]["end"]
            newcaption = caption[lastpos:]
            newcaption = newcaption[newcaption.index(":") + 1:]

            # There are n comments on 1's post: @2: ...\n@3: ...
            multi = len(args["comment_ids"]) > 1
            for comment_id_i in range(len(args["comment_ids"])):
                if multi:
                    newcaption = newcaption[newcaption.index(":") + 1:]

                if "\n" in newcaption:
                    curr = newcaption[:newcaption.index("\n")]
                else:
                    curr = newcaption

                #comments.push((comment_id, curr.strip()))
                comments[args["comment_ids"][comment_id_i]] = curr.strip()

                if len(newcaption) > (len(curr) + 1):
                    newcaption = newcaption[len(curr) + 1:]

        formatted = {
            12: "##1## left a comment on ##2##'s post: ",
            13: "##1## liked ##2##'s comment: ",
            60: "##1## liked ##2##'s post.",
            101: "##1## started following ##2##."
        }

        def uids_to_names(uids):
            if type(uids) != list:
                uids = [uids]

            links = []
            for uid in uids:
                username = uid_to_username(config, uid)
                links.append(username)

            return links

        def uids_to_links(uids):
            if type(uids) != list:
                uids = [uids]

            links = []
            for uid in uids:
                username = uid_to_username(config, uid)
                links.append("<a href='%s'>%s</a>" % (username_to_url(username), username))

            return links

        def english_array(array):
            if len(array) == 0:
                return ""

            if len(array) == 1:
                return array[0]

            text = ""
            for i in range(len(array)):
                if i == 0:
                    text += array[i]
                elif i + 1 == len(array):
                    text += " and " + array[i]
                else:
                    text += ", " + array[i]

            return text

        def do_format(func, subj, obj):
            text = formatted[story_type]
            text = text.replace("##1##", english_array(func(subj)))
            text = text.replace("##2##", english_array(func(obj)))

            if comment:
                text += comments[comment]

            return text

        comment = None
        media = None

        for subj in subjs:
            if "media" in subj:
                media = subj["media"]
            if "comment" in subj:
                comment = subj["comment"]

            for obj_i in range(len(objs)):
            #for media_i in range(len(args["media"])):
                obj = objs[obj_i]

                if "media" in obj:
                    media = obj["media"]
                if "comment" in obj:
                    comment = obj["comment"]

                #media = args["media"][obj_i]
                #obj = objs[obj_i]

                caption = do_format(uids_to_names, subj, obj)
                content = "<p>%s</p>" % do_format(uids_to_links, subj, obj)

                if media:
                    content += generate_news_media(config, [media])

                tuuid = "story_type:%s/subject:%s" % (
                    #args["tuuid"],
                    story_type,
                    subj["uid"]
                )

                if media:
                    tuuid += "/media:%s" % media["id"]

                    if comment:
                        tuuid += "/comment_id:%s" % str(comment) #str(args["comment_id"])
                else:
                    tuuid += "/object:%s" % obj["uid"]

                feed["entries"].append({
                    "url": "http://tuuid.instagram.com/" + tuuid,
                    "title": caption,
                    "author": author,
                    "date": date,
                    "content": content
                })

        continue

        tuuid = args["tuuid"]
        tuuid += "/" + str(story["story_type"])

        if "comment_ids" in args and len(args["comment_ids"]):
            tuuid += "/" + str(args["comment_ids"][0])

        feed["entries"].append({
            "url": "http://tuuid.instagram.com/" + tuuid,
            "title": caption,
            "author": author,
            "date": date,
            "content": content
        })

    return ("feed", feed)


def generate_inbox(config):
    inboxreq = do_app_request(config, "inbox")

    if "raw" in config and config["raw"]:
        return ("feed", inboxreq)

    config["no_dl"] = True

    feed = {
        "title": "Inbox",
        "description": "Direct messages",
        "url": "http://inbox.instagram.com/",  # fake url for now
        "author": "instagram",
        "entries": []
    }

    for thread in inboxreq["inbox"]["threads"]:
        for user in thread["users"]:
            # cache
            uid_to_username(config, {
                "uid": user["pk"],
                "username": user["username"]
            })

        for item in thread["items"]:
            guid = item["item_id"]
            title = None
            content = None
            if "text" in item:
                content = item["text"]
                title = content
            elif "link" in item:
                content = item["link"]["text"]
                title = content
            elif "action_log" in item:
                content = "<em>%s</em>" % item["action_log"]["description"]
            if not content:
                content = "(n/a)"
            if not title:
                title = ""
            caption = "[" + thread["thread_title"] + "] " + title
            if item["user_id"] == thread["viewer_id"]:
                if True:
                    continue
            author = uid_to_username(config, item["user_id"])
            date = datetime.datetime.fromtimestamp(int(item["timestamp"])/1000000, None).replace(tzinfo=tzlocal())
            feed["entries"].append({
                "url": "http://guid.instagram.com/" + guid,
                "title": caption,
                "author": author,
                "date": date,
                "content": content
            })

    return ("feed", feed)


def generate_raw(config, path):
    if path.startswith("p/"):
        post = path[len("p/"):]
        #node = get_node_info_webpage(config, post)["graphql"]["shortcode_media"]
        node_raw = get_node_info(config, post, usecache=False)
        if not node_raw:
            config["http_error"] = 404
            return None

        node = node_raw
        node = normalize_node(node)

        images = []
        videos = []
        get_node_media(config, node, images, videos)

        node["node_images"] = images
        node["node_videos"] = videos

        comments = node["edge_media_to_parent_comment"]
        after = comments["page_info"]["end_cursor"]

        def get_comments(maxid):
            if not maxid:
                maxid = after
            try:
                newcomments_api = do_graphql_request(config, "comments", {
                    "shortcode": post,
                    "first": config["max_graphql_count"],
                    "after": maxid
                })["data"]["shortcode_media"]["edge_media_to_parent_comment"]
            except Exception:
                sys.stderr.write("Unable to load comments\n")
                newcomments_api = {
                    "edges": [],
                    "page_info": {
                        "end_cursor": None,
                        "has_next_page": False
                    }
                }

            retval = (newcomments_api["edges"],
                    newcomments_api["page_info"]["end_cursor"],
                    newcomments_api["page_info"]["has_next_page"])
            return retval

        if after:
            morecomments = rssit.util.paginate(config, comments["count"], get_comments)
            comments["edges"] = comments["edges"] + morecomments
            comments["edges"].sort(key=lambda x: x["node"]["created_at"])
            #node["edge_media_to_comment"] = comments

        return ("raw", node)
    if path.startswith("uid/"):
        uid = path[len("uid/"):]
        decoded_user, decoded_user_cached = get_user_info(config, uid, True)
        return ("raw", decoded_user)
    return None


def init(config):
    useragent_header = rssit.util.get_httpheader(config, "user-agent")
    if useragent_header:
        web_api.apidef["headers"]["User-Agent"] = useragent_header
        graphql_id_api.apidef["headers"]["User-Agent"] = useragent_header
        graphql_hash_api.apidef["headers"]["User-Agent"] = useragent_header


def process(server, config, path):
    if path.startswith("/u/"):
        return generate_user(config, username=path[len("/u/"):])

    if path.startswith("/v/"):
        return generate_video(config, server, path[len("/v/"):])

    if path.startswith("/livereplay/"):
        return generate_livereplay(config, server, path[len("/livereplay/"):])

    if path.startswith("/uid/"):
        return generate_user(config, uid=path[len("/uid/"):])

    if path.startswith("/convert/"):
        return generate_convert(config, server, path[len("/convert/"):])

    if path.startswith("/news"):
        return generate_news(config)

    if path.startswith("/reels_tray"):
        return generate_reelstray(config)

    if path.startswith("/inbox"):
        return generate_inbox(config)

    return None


infos = [{
    "name": "instagram",
    "display_name": "Instagram",

    "init": init,

    "endpoints": {
        "u": {
            "name": "User's feed by username",
            "process": lambda server, config, path: generate_user(config, username=path)
        },
        "tagged": {
            "name": "User's tagged feed by username",
            "process": lambda server, config, path: generate_tagged(config, username=path)
        },
        "v": {
            "name": "Redirect to the URL of a video",
            "internal": True,
            "process": lambda server, config, path: generate_video(config, server, path)
        },
        "livereplay": {
            "name": "Serve a live replay's DASH manifest",
            "internal": True,
            "process": lambda server, config, path: generate_livereplay(config, server, path)
        },
        "uid": {
            "name": "User's feed by UID",
            "process": lambda server, config, path: generate_user(config, uid=path)
        },
        "convert": {
            "name": "Convert between formats",
            "internal": True,
            "process": lambda server, config, path: generate_convert(config, server, path)
        },
        "news": {
            "name": "Events happening in your instagram feed",
            "process": lambda server, config, path: generate_news(config)
        },
        "reels_tray": {
            "name": "Live videos/replays",
            "process": lambda server, config, path: generate_reelstray(config)
        },
        "inbox": {
            "name": "Inbox",
            "process": lambda server, config, path: generate_inbox(config)
        },
        "raw": {
            "name": "Raw API access",
            "internal": True,
            "process": lambda server, config, path: generate_raw(config, path)
        },
        "home": {
            "name": "Homepage feed",
            "process": lambda server, config, path: generate_home(config)
        }
    },

    "config": {
        "author_username": {
            "name": "Author = Username",
            "description": "Set the author's name to be their username",
            "value": False
        },

        "prefer_uid": {
            "name": "Prefer user ID",
            "description": "Prefer user IDs over usernames",
            "value": False
        },

        "use_media": {
            "name": "Use /media/ endpoint",
            "description": "Uses the now-removed /media/?__a=1, which provides 20 feeds",
            "value": False
        },

        "use_profile_a1": {
            "name": "Use [profile]/?__a=1 endpoint",
            "description": "Uses the [profile]/?__a=1 endpoint, more prone to rate-limiting",
            "value": False
        },

        "use_shortcode_a1": {
            "name": "Use /p/[shortcode]/?__a=1 endpoint",
            "description": "Uses the /p/[shortcode]/?__a=1 endpoint, faster, but possibly more prone to rate-limiting",
            "value": False
        },

        "use_graphql_stories": {
            "name": "Use graphql stories",
            "description": "Uses graphql for stories instead of the app API. Less rate-limited, but less features (no livestreams, no caption, no click-to-action).",
            "value": False
        },

        "use_graphql_entries": {
            "name": "Use graphql entries",
            "description": "Uses graphql for entries if needed, rate-limited",
            "value": True
        },

        "stories": {
            "name": "Process stories",
            "description": "Process stories, possibly requires an extra call",
            "value": True
        },

        "lives": {
            "name": "Process live videos",
            "description": "Process live videos, requires an extra call",
            "value": True
        },

        "igtv": {
            "name": "Process IGTV",
            "description": "Process IGTV, doesn't require an extra call",
            "value": True
        },

        "use_reelstray_cache": {
            "name": "Use reels_tray cache",
            "description": "Uses cached API calls for story/live calls if possible. Only use when splitting story/live feeds",
            "value": False
        },

        "use_api_entries": {
            "name": "Use API entries",
            "description": "Uses API for entries if needed, rate-limited, but very fast",
            "value": False
        },

        "use_hash_graphql": {
            "name": "Use hash graphql",
            "description": "Uses query_hash instead of query_id for graphql",
            "value": True
        },

        "use_normalized": {
            "name": "Use normalized images",
            "description": "Uses normalized images over the ones given by Instagram",
            "value": True
        },

        "use_profilepic_api": {
            "name": "Use API for DP",
            "description": "Uses the API for the profile picture (higher quality, but extra call)",
            "value": True
        },

        "max_graphql_count": {
            "name": "Largest GraphQL Query",
            "description": "Maximum number of items a single GraphQL call will return",
            "value": 12
        },

        "fail_if_not_following": {
            "name": "Fail if not following",
            "description": "Return 490 if not following the account",
            "value": False
        },

        "force_nocache": {
            "name": "Force not using cache",
            "description": "Forces redoing every request without using cache",
            "value": False
        },

        "description_uid": {
            "name": "UID in description",
            "description": "Adds the UID to the description field",
            "value": False
        },

        "story_post_url": {
            "name": "Real story URLs",
            "description": "Uses a real post URL for stories, sometimes Instagram doesn't support this",
            "value": False
        },

        "max_extra_stories": {
            "name": "Maximum extra users for stories",
            "description": "The maximum amount of extra users to check for when using stories in reels_tray",
            "value": 5
        },

        "max_extra_story_requests": {
            "name": "Maximum extra story requests",
            "description": "The maximum amount of extra story requests to run for reels_tray",
            "value": 2
        },

        "round_followers": {
            "name": "Round followers",
            "description": "Rounds the follower count, helpful for less DB updates",
            "value": True
        }
    },

    "get_url": get_url,
    "process": process
}]
