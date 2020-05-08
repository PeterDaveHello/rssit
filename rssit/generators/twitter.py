# -*- coding: utf-8 -*-


import datetime
import re
import rssit.util
import bs4
import sys
try:
    import tweepy
except ImportError:
    tweepy = None
    sys.stderr.write("Warning: no twitter API support (install tweepy to fix)\n")
import pprint
from calendar import timegm
import xml.sax.saxutils
import urllib.parse


from email.utils import parsedate_tz, mktime_tz
#try:
#    from rfc822 import parsedate
#except ImportError:
#    from email.utils import parsedate


auths = {}
#user_infos = {}


def get_string(element):
    if type(element) is bs4.element.NavigableString:
        return str(element.string)
    else:
        string = ""

        for i in element.children:
            string += get_string(i)

        return string


def get_url(config, url):
    match = re.match(r"^(https?://)?(?:\w+\.)?twitter.com/(?P<user>[^?&/]*)", url)

    if match is None:
        return

    return "/u/" + match.group("user").lower()


def get_orig_image(image_url):
    if image_url.endswith(":large"):
        image_url = image_url.replace(":large", ":orig")
    elif not image_url.endswith(":orig"):
        image_url += ":orig"

    return image_url


def generate_html(user, config):
    url = "https://twitter.com/" + user
    user = user.lower()

    if config["with_replies"]:
        url += "/with_replies"

    data = rssit.util.download(url)

    soup = bs4.BeautifulSoup(data, 'lxml')

    author = "@" + user
    description = "%s's twitter" % author

    init_data = soup.select("#init-data")

    if len(init_data) > 0:
        init_data = init_data[0]

        if "value" in init_data.attrs:
            init_json = rssit.util.json_loads(init_data.attrs["value"])

            if not config["author_username"]:
                if len(init_json["profile_user"]["name"]) > 0:
                    author = init_json["profile_user"]["name"]

            if len(init_json["profile_user"]["description"]) > 0:
                description = init_json["profile_user"]["description"]

            if len(init_json["profile_user"]["screen_name"]) > 0:
                user = init_json["profile_user"]["screen_name"]

    feed = {
        "title": author,
        "description": description,
        "url": "https://twitter.com/" + user,
        "author": user,
        "entries": []
    }

    for tweet in soup.find_all(attrs={"data-tweet-id": True}):
        timestamp = int(tweet.find_all(attrs={"data-time": True})[0]["data-time"])
        date = rssit.util.localize_datetime(datetime.datetime.fromtimestamp(timestamp, None))

        username = tweet["data-screen-name"].lower()

        link = urllib.parse.urljoin(url, tweet["data-permalink-path"])

        caption = ""
        urls = []

        for text in tweet.select("p.tweet-text"):
            for i in text.children:
                if type(i) is bs4.element.NavigableString:
                    caption += str(i.string)
                else:
                    if i.name == "img":
                        caption += i["alt"]
                    elif i.name == "a":
                        if "data-expanded-url" in i.attrs:
                            a_url = i["data-expanded-url"]
                            caption += a_url
                            urls.append(a_url)
                        elif not "u-hidden" in i["class"]:
                            caption += get_string(i)

        image_holder = tweet.find_all(attrs={"data-image-url": True})

        if len(image_holder) > 0:
            images = []

            for image in image_holder:
                image_url = image["data-image-url"]
                image_url = get_orig_image(image_url)
                images.append(image_url)
        else:
            images = None

        is_video_el = tweet.select(".AdaptiveMedia-video")
        if len(is_video_el) > 0:
            tweet_id = tweet["data-tweet-id"]
            video_url = "https://twitter.com/i/videos/%s" % tweet_id
            pmp = tweet.select(".PlayableMedia-player")[0]
            preview_url = re.search(r"background-image: *url.'(?P<url>.*?)'",
                                   pmp["style"]).group("url")

            videos = [{
                "image": preview_url,
                "video": video_url
            }]
        else:
            videos = None

        feed["entries"].append({
            "url": link,
            "caption": caption,
            "author": username,
            "date": date,
            "updated_date": date,
            "images": images,
            "videos": videos
        })

    return feed


def generate_api(user, config):
    #global user_infos
    global auths
    user_infos = {}

    auth_key = config["consumer_key"] + config["consumer_secret"] +\
               config["access_token"] + config["access_secret"]

    if auth_key in auths:
        api = auths[auth_key]["api"]
    else:
        auth = tweepy.OAuthHandler(config["consumer_key"], config["consumer_secret"])
        auth.set_access_token(config["access_token"], config["access_secret"])

        api = tweepy.API(auth)

        auths[auth_key] = {
            "auth": auth,
            "api": api
        }

    if user not in user_infos:
        user_infos[user] = api.get_user(id=user)

    user_info = user_infos[user]

    username = user_info.screen_name.lower()

    title = "@" + user_info.screen_name

    if not config["author_username"] and "name" in user_info.__dict__ and len(user_info.name) > 0:
        title = user_info.name

    if "description" in user_info.__dict__ and len(user_info.description) > 0:
        description = user_info.description
    else:
        description = "%s's twitter" % title

    feed = {
        "title": title,
        "description": description,
        "author": username,
        "url": "https://twitter.com/" + username,
        "social": True,
        "entries": []
    }


    tl = []
    if config["count"] == -1:
        maxid = None

        while True:
            temp_tl = api.user_timeline(id=user, max_id=maxid, count=200, tweet_mode="extended")
            if not temp_tl:
                break

            tl = tl + temp_tl
            maxid = tl[-1].id - 1

            sys.stderr.write("\r" + str(len(tl)) + " / " + str(user_info.statuses_count))
    else:
        tl = api.user_timeline(id=user, count=config["count"], tweet_mode="extended")

    if not tl:
        return None

    for obj in tl:
        #caption = xml.sax.saxutils.unescape(re.sub(" *http[^ ]*t\.co/[^ ]*", "", obj.text))
        #caption = xml.sax.saxutils.unescape(obj.text)
        #pprint.pprint(obj.__dict__)

        is_retweeted = False
        if "retweeted_status" in obj.__dict__ and obj.retweeted_status:
            is_retweeted = True

        if is_retweeted and not config["with_retweets"]:
            continue

        origcaption = obj.full_text.replace("\r", "\n")
        newcaption = origcaption

        if "entities" in obj.__dict__:
            if "urls" in obj.entities:
                for url in obj.entities["urls"]:
                    newcaption = newcaption.replace(url["url"], url["expanded_url"])

        caption = xml.sax.saxutils.unescape(re.sub(" *https?://t\.co/[^ ]*", "", newcaption))
        #caption = xml.sax.saxutils.unescape(newcaption)

        date = rssit.util.localize_datetime(datetime.datetime.fromtimestamp(mktime_tz(parsedate_tz(obj._json["created_at"]))))

        entrydict = {
            "url": "https://twitter.com/" + obj.author.screen_name + "/status/" + obj.id_str,
            "caption": caption,
            "date": date,
            "updated_date": date,
            "author": obj.author.screen_name.lower(),
            "images": [],
            "videos": []
        }

        #pprint.pprint(obj.__dict__)

        if "extended_entities" in obj.__dict__:
            for media in obj.__dict__["extended_entities"]["media"]:
                if media["type"] == "photo":
                    url = media["media_url"]
                    url = get_orig_image(url)
                    entrydict["images"].append(url)
                    #entrydict["images"].append(media["media_url"])
                elif media["type"] == "video" or media["type"] == "animated_gif":
                    videodict = {
                        "image": media["media_url"]
                    }

                    variants = media["video_info"]["variants"]

                    max_bitrate = -1
                    curr = None
                    for variant in variants:
                        if "bitrate" in variant and variant["bitrate"] > max_bitrate:
                            curr = variant

                    if not curr:
                        curr = variants[0]

                    videodict["video"] = curr["url"]
                    entrydict["videos"].append(videodict)

        feed["entries"].append(entrydict)

    return feed


def generate_user(server, config, user):
    if len(config["consumer_key"]) > 0 and tweepy:
        return ("social", generate_api(user, config))
    else:
        return ("social", generate_html(user, config))


def generate(server, config, path):
    if path.startswith("/u/"):
        user = path[len("/u/"):]

        return generate_user(server, config, user)
        """if len(config["consumer_key"]) > 0 and tweepy:
            return ("social", generate_api(user, config))
        else:
            return ("social", generate_html(user, config))"""


infos = [{
    "name": "twitter",
    "display_name": "Twitter",

    "endpoints": {
        "u": {
            "name": "User's feed",
            "process": generate_user
        }
    },

    "config": {
        "author_username": {
            "name": "Author = Username",
            "description": "Set the author's name to be their username",
            "value": False
        },

        "with_replies": {
            "name": "Include replies (requires login)",
            "value": True
        },

        "with_retweets": {
            "name": "Include retweets",
            "value": True
        },

        "consumer_key": {
            "name": "Consumer Key (API Key)",
            "value": ""
        },

        "consumer_secret": {
            "name": "Consumer Secret (API Secret)",
            "value": ""
        },

        "access_token": {
            "name": "Access Token",
            "value": ""
        },

        "access_secret": {
            "name": "Access Token Secret",
            "value": ""
        }
    },

    "get_url": get_url,
    "process": generate
}]
