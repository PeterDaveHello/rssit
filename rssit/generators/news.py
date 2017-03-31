import bs4
import ujson
import sys
import urllib.request
import urllib.parse
from dateutil.parser import parse
import re
import html
import pprint
import rssit.util
import datetime


# for news1: http://news1.kr/search_front/search.php?query=[...]&collection=front_photo&startCount=[0,20,40,...]
# for starnews: http://star.mt.co.kr/search/index.html?kwd=[...]&category=PHOTO
# for articleList-based: http://stardailynews.co.kr/news/articleList.html?page=1&sc_area=A&sc_word=[...]&view_type=sm
# for tvdaily: http://tvdaily.asiae.co.kr/searchs.php?section=17&searchword=[...]&s_category=2


# http://stackoverflow.com/a/18359215
def get_encoding(soup):
    encod = soup.find("meta", charset=True)
    if encod:
        return encod["charset"]

    encod = soup.find("meta", attrs={'http-equiv': "Content-Type"})
    if not encod:
        encod = soup.find("meta", attrs={"Content-Type": True})

    if encod:
        content = encod["content"]
        match = re.search('charset *= *(.*)', content)
        if match:
            return match.group(1)

    raise ValueError('unable to find encoding')


def get_url(url):
    base = "/url/"
    if url.startswith("quick:"):
        base = "/qurl/"
        url = url[len("quick:"):]

    if url.startswith("//"):
        url = url[len("//"):]

    url = re.sub(r"^[^/]*://", "", url)

    regexes = [
        "entertain\.naver\.com/",
        "find\.joins\.com/",
        "isplus\.joins\.com/",
        "news1.kr/search_front/",
        "topstarnews.net/search.php",
        "star\.mt\.co\.kr/search",
        "osen\.mt\.co\.kr/search",
        "stardailynews\.co\.kr/news/articleList",
        "liveen.co.kr/news/articleList",
        "tvdaily\.asiae\.co\.kr/searchs",
        "search\.hankyung\.com",
        "serach\.chosun\.com"
    ]

    found = False
    for regex in regexes:
        match = re.search(regex, url)
        if match:
            found = True

    if not found:
        return None

    return base + url


def get_selector(soup, selectors):
    tag = None

    for selector in selectors:
        tag = soup.select(selector)
        if tag and len(tag) > 0:
            break
        else:
            tag = None

    return tag


def get_title(myjson, soup):
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title:
        return html.unescape(og_title["content"])
    elif "search" in myjson["url"]:
        return "(search)"


def get_author(url):
    if "naver." in url:
        return "naver"
    if ".joins.com" in url:
        return "joins"
    if "news1.kr/" in url:
        return "news1"
    if "topstarnews.net" in url:
        return "topstarnews"
    if "star.mt.co.kr" in url:
        return "starnews"
    if "osen.mt.co.kr" in url:
        return "osen"
    if "stardailynews.co.kr" in url:
        return "stardailynews"
    if "tvdaily.asiae.co.kr" in url:
        return "tvdaily"
    if "hankyung.com" in url:
        return "hankyung"
    if "liveen.co.kr" in url:
        return "liveen"
    if "search.chosun.com" in url:
        return "chosun"
    return None


def ascii_only(string):
    return ''.join([i if ord(i) < 128 else ' ' for i in string])


def parse_date(date):
    if type(date) is int:
        return rssit.util.localize_datetime(datetime.datetime.utcfromtimestamp(date))
    date = re.sub("오후 *([0-9]*:[0-9]*)", "\\1PM", date)
    date = date.replace("년", "-")
    date = date.replace("월", "-")
    date = date.replace("시", ":")
    date = ascii_only(date)
    date = re.sub("\( *\)", "", date)
    date = re.sub("\( *= *1 *\)", "", date) # workaround for news1
    date = re.sub("\|", " ", date)
    date = re.sub(":[^0-9]*$", "", date)
    date = date.strip()
    if not date:
        return None
    return rssit.util.localize_datetime(parse(date))


def get_date(myjson, soup):
    datetag = get_selector(soup, [
        ".article_info .author em",
        ".article_tit .write_info .write",
        "#article_body_content .title .info"
    ])

    if not datetag:
        sys.stderr.write("no recognizable date\n")
        return

    date = None
    for date_tag in datetag:
        if myjson["author"] == "naver":
            if not "오후" in date_tag.text:
                continue
            date = parse(date_tag.text.replace("오후", ""))
        else:
            date = parse_date(date_tag.text)

    return date


def get_images(myjson, soup):
    imagestag = get_selector(soup, [
        "#adiContents img",
        ".article img",
        "#article img",
        ".articletext img",
        "#_article table[align='center'] img",
        "#_article img.view_photo",
        "#_article .article_photo img",
        "#articleBody img",
        "#articleBody .iframe_img img:nth-of-type(2)",
        "#newsContent .iframe_img img:nth-of-type(2)",
        "#articeBody .img_frame img",
        "#textBody img",
        "#news_contents img",
        "#arl_view_content img",
        ".articleImg img",
        "#newsViewArea img",
        "#articleContent img",
        "#articleContent #img img",
        "#newsContent img.article-photo-mtn",
        "#article_content img",
        "div[itemprop='articleBody'] img",
        "div[itemprop='articleBody'] img.news1_photo",
        "div[itemprop='articleBody'] div[rel='prettyPhoto'] img",
        "div[itemprop='articleBody'] .centerimg img",
        "div[itemprop='articleBody'] .center_image img",
        ".center_image > img",
        ".article_view img",
        "img#newsimg",
        ".article_photo img",
        ".articlePhoto img",
        "#__newsBody__ .he22 td > img",
        ".article_image > img",
        "#CmAdContent img",
        ".article_outer .main_image p > img, .article_outer .post_body p img",
        ".article-img img",
        ".portlet .thumbnail img",
        "#news_textArea img",
        ".news_imgbox img",
        ".view_txt img",
        "#IDContents img",
        "#view_con img",
        "#newsEndContents img",
        ".articleBox img",
        ".rns_text img",
        "#article_txt img",
        "#ndArtBody .imgframe img",
        ".view_box center img",
        ".newsbm_img_wrap > img",
        ".article .detail img",
        "#articeBody img",
        "center table td a > img"  # topstarnews search
    ])

    if not imagestag:
        return

    images = []
    for image in imagestag:
        images.append(get_max_quality(image["src"]))

    return images


def get_description(myjson, soup):
    desc_tag = get_selector(soup, [
        "#article_content #adiContents",
        "#article_body_content .detail"
    ])

    if not desc_tag:
        return

    #return "\n".join(list(desc_tag[0].strings))
    return str(desc_tag[0])


def get_article_url(url):
    return url


def get_articles(myjson, soup):
    if myjson["author"] == "joins":
        if "isplusSearch" not in myjson["url"]:
            return
    elif myjson["author"] == "news1" or myjson["author"] == "topstarnews":
        if "search.php" not in myjson["url"]:
            return
    elif myjson["author"] == "starnews" or myjson["author"] == "osen":
        if "search" not in myjson["url"]:
            return
    elif myjson["author"] == "tvdaily":
        if "searchs.php" not in myjson["url"]:
            return
    elif myjson["author"] == "hankyung":
        if "search.hankyung.com" not in myjson["url"]:
            return
    elif myjson["author"] == "chosun":
        if "search.chosun.com" not in myjson["url"]:
            return
    else:
        if "news/articleList" not in myjson["url"]:
            return

    articles = []

    parent_selectors = [
        # joins
        {
            "parent": "#news_list .bd ul li dl",
            "link": "dt a",
            "caption": "dt a",
            "date": "dt .date",
            "images": ".photo img",
            "description": "dd.s_read_cr"
        },
        {
            "parent": "#search_contents .bd ul li dl",
            "link": "dt a",
            "caption": "dt a",
            "date": ".date",
            "images": ".photo img"
        },
        # news1
        {
            "parent": ".search_detail ul li",
            "link": "a",
            "caption": "a > strong",
            "date": "a .date",
            "images": ".thumb img",
            "aid": lambda soup: re.sub(r".*/\?([0-9]*).*", "\\1", soup.select("a")[0]["href"])
        },
        # topstarnews
        {
            "parent": "table#search_part_1 > tr > td > table > tr > td",
            "link": "center > table > tr > td > a",
            "caption": "center > table > tr > td > span > a",
            "date": ".street-photo2",
            "images": "center > table > tr > td > a > img",
            "aid": lambda soup: re.sub(r".*[^a-zA-Z0-9_]number=([0-9]*).*", "\\1", soup.select("center > table > tr > td > a")[0]["href"])
        },
        # starnews
        {
            "parent": "#container > #content > .fbox li.bundle",
            "link": ".txt > a",
            "caption": ".txt > a",
            "date": "-1",
            "images": ".thum img",
            "aid": lambda soup: re.sub(r".*[^a-zA-Z0-9_]no=([0-9]*).*", "\\1", soup.select(".txt > a")[0]["href"])
        },
        # osen
        {
            "parent": "#container .searchBox > table tr > td",
            "link": "a",
            "caption": "p.photoView",
            "date": "-1",
            "images": "a > img",
            "aid": lambda soup: re.sub(r".*/([0-9A-Za-z]*)", "\\1", soup.select("a")[0]["href"])
        },
        # liveen
        {
            "parent": "table#article-list > tr > td > table > tr > td > table",
            "link": "td.list-titles a",
            "caption": "td.list-titles a",
            "description": "td.list-summary a",
            "date": "td.list-times",
            "images": ".list-photos img",
            "html": True,
            "aid": lambda soup: re.sub(r".*idxno=([0-9]*).*", "\\1", soup.select("td.list-titles a")[0]["href"])
        },
        # stardailynews
        {
            "parent": "#ND_Warp table tr > td table tr > td table tr > td table",
            "link": "tr > td > span > a",
            "caption": "tr > td > span > a",
            "description": "tr > td > p",
            "date": "-1",
            "images": "tr > td img",
            "html": True,
            "aid": lambda soup: re.sub(r".*idxno=([0-9]*).*", "\\1", soup.select("tr > td > span > a")[0]["href"])
        },
        # tvdaily
        {
            "parent": "body > table tr > td > table tr > td > table tr > td > table tr > td",
            "link": "a.sublist",
            "date": "span.date",
            "caption": "a.sublist",
            "description": "p",
            "images": "a > img",
            "imagedata": lambda entry, soup: {
                "date": re.sub(r"[^0-9]*", "", soup.select("span.date")[0].text),
                "aid": re.sub(r".*aid=([^&]*).*", "\\1", soup.select("a.sublist")[0]["href"])
            },
            "aid": lambda soup: re.sub(r".*aid=([^&]*).*", "\\1", soup.select("a.sublist")[0]["href"]),
            "html": True
        },
        # hankyung
        {
            "parent": ".hk_news .section_cont > ul.article > li",
            "link": ".txt_wrap > a",
            "caption": ".txt_wrap .tit",
            "description": ".txt_wrap > p.txt",
            "date": ".info span.date_time",
            "images": ".thumbnail img",
            "html": True
        },
        # chosun
        {
            "parent": ".result_box > section.result > dl",
            "link": "dt > a",
            "caption": "dt > a",
            "description": "dd > a",
            "date": "dt > em",
            "images": ".thumb img",
            "aid": lambda soup: re.sub(r".*/([^/.?&]*).html$", "\\1", soup.select("dt > a")[0]["href"]),
            "html": True
        }
    ]

    parenttag = None
    for selector in parent_selectors:
        parenttag = soup.select(selector["parent"])
        if parenttag and len(parenttag) > 0:
            #parenttag = parenttag[0]
            break

    if not parenttag:
        return []

    for a in parenttag:
        if not a.select(selector["link"]):
            # print warning?
            continue

        entry = {}

        link = get_article_url(urllib.parse.urljoin(myjson["url"], a.select(selector["link"])[0]["href"]))
        entry["url"] = link

        date = 0
        if "date" in selector:
            if selector["date"] == "-1":
                date = parse_date(-1)
            else:
                for date_tag in a.select(selector["date"]):
                    try:
                        date = parse_date(date_tag.text)
                        if date:
                            break
                    except Exception as e:
                        pass
        entry["date"] = date

        realcaption = None
        caption = None
        aid = ""
        if "aid" in selector:
            aid = selector["aid"](a) + " "
        if "caption" in selector:
            realcaption = a.select(selector["caption"])[0].text.strip()
            caption = aid + realcaption
        entry["caption"] = caption
        entry["realcaption"] = realcaption

        description = None
        if "description" in selector:
            description_tag = a.select(selector["description"])
            description = ""
            for tag in description_tag:
                if len(tag.text)  > len(description):
                    description = tag.text
        else:
            description = entry["realcaption"]
            if not "html" in selector:
                selector["html"] = True
        entry["description"] = description

        author = get_author(link)
        entry["author"] = author

        imagedata = None
        if "imagedata" in selector:
            imagedata = selector["imagedata"](entry, a)

        images = []
        if "images" in selector:
            image_tags = a.select(selector["images"])
            for image in image_tags:
                image_full_url = urllib.parse.urljoin(myjson["url"], image["src"])
                image_max_url = get_max_quality(image_full_url, imagedata)
                images.append(image_max_url)

        entry["images"] = images
        entry["videos"] = []

        if "html" in selector:
            if selector["html"] is True:
                selector["html"] = lambda entry: "<p>" + entry["description"] + "</p>" + '\n'.join(["<p><img src='" + x + "' /></p>" for x in entry["images"]])
            entry["description"] = selector["html"](entry)

        articles.append(entry)

    return articles


def get_max_quality(url, data=None):
    if "naver." in url:
        url = re.sub("\?.*", "", url)
        #if "imgnews" not in url:
        # do blogfiles

    if ".joins.com" in url:
        url = re.sub("\.tn_.*", "", url)

    if "image.news1.kr" in url:
        url = re.sub("/[^/.]*\.([^/]*)$", "/original.\\1", url)

    if "uhd.img.topstarnews.net/" in url:
        url = url.replace("/file_attach_thumb/", "/file_attach/")
        url = re.sub(r"_[^/]*[0-9]*x[0-9]*_[^/]*(\.[^/]*)$", "-org\\1", url)

    if "thumb.mtstarnews.com/" in url:
        url = re.sub(r"\.com/[0-9][0-9]/", ".com/06/", url)

    if "stardailynews.co.kr" in url or "liveen.co.kr" in url:
        url = re.sub("/thumbnail/", "/photo/", url)
        url = re.sub(r"_v[0-9]*\.", ".", url)

    if "tvdaily.asiae.co.kr" in url:
        url = url.replace("/tvdaily.asiae", "/image.tvdaily")
        url = url.replace("/thumb/", "/gisaimg/" + data["date"][:6] + "/")
        url = re.sub(r"/([^/]*)\.[^/]*$", "/" + data["aid"][:10] + "_\\1.jpg", url)

    if "img.hankyung.com" in url:
        url = re.sub(r"\.[0-9]\.([a-zA-Z0-9]*)$", ".1.\\1", url)

    if "img.tenasia.hankyung.com" in url:
        url = re.sub(r"-[0-9]*x[0-9]*\.jpg$", ".jpg", url)

    if "chosun.com" in url:
        url = url.replace("/thumb_dir/", "/img_dir/").replace("/thumbnail/", "/image/").replace("_thumb.", ".")

    if "file.osen.co.kr" in url:
        url = url.replace("/article_thumb/", "/article/")
        url = re.sub(r"_[0-9]*x[0-9]*\.jpg$", ".jpg", url)

    return url


def do_url(config, url):
    quick = False
    if "quick" in config and config["quick"]:
        quick = True

    url = urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
    data = rssit.util.download(url)
    soup = bs4.BeautifulSoup(data, 'lxml')

    encoding = "utf-8"
    try:
        encoding = get_encoding(soup)
    except Exception as e:
        print(e)
        pass
    #data = data.decode("utf-8", "ignore")
    if type(data) != str:
        data = data.decode(encoding, "ignore")
    #data = download("file:///tmp/naver.html")

    soup = bs4.BeautifulSoup(data, 'lxml')

    myjson = {
        "title": None,
        "author": None,
        "url": url,
        "config": {
            "generator": "news"
        },
        "entries": []
    }

    author = get_author(url)

    if not author:
        sys.stderr.write("unknown site\n")
        return

    myjson["author"] = author
    myjson["title"] = author

    articles = get_articles(myjson, soup)
    if articles is not None:
        article_i = 1
        for article in articles:
            if article is None:
                sys.stderr.write("error with article\n")
                continue
            if quick:
                if not article["caption"]:
                    sys.stderr.write("no caption\n")
                    return
                if article["date"] == 0:
                    sys.stderr.write("no date\n")
                    return
                if not article["caption"] or article["date"] == 0:
                    sys.stderr.write("no salvageable information from search\n")
                    sys.stderr.write(pprint.pformat(article) + "\n")
                    return

                if not article["author"]:
                    article["author"] = myjson["author"]
                elif article["author"] != myjson["author"]:
                    sys.stderr.write("different authors\n")
                    return

                myjson["entries"].append(article)
                continue
            article_url = article["url"]
            basetext = "(%i/%i) " % (article_i, len(articles))
            article_i += 1

            sys.stderr.write(basetext + "Downloading %s... " % article_url)
            sys.stderr.flush()

            newjson = None
            try:
                newjson = do_url(config, article_url)
            except Exception as e:
                pass
            if not newjson:
                sys.stderr.write("url: " + article_url + " is invalid\n")
                continue

            if newjson["author"] != myjson["author"]:
                sys.stderr.write("current:\n\n" +
                                 pprint.pformat(myjson) +
                                 "\n\nnew:\n\n" +
                                 pprint.pformat(newjson))
                continue

            sys.stderr.write("done\n")
            sys.stderr.flush()

            myjson["entries"].extend(newjson["entries"])
        return myjson

    title = get_title(myjson, soup)

    if not title:
        sys.stderr.write("no title\n")
        return

    date = get_date(myjson, soup)

    if not date:
        sys.stderr.write("no date\n")
        return

    album = "[" + str(date.year)[-2:] + str(date.month).zfill(2) + str(date.day).zfill(2) + "] " + title

    images = get_images(myjson, soup)
    if not images:
        sys.stderr.write("no images\n")
        return

    description = get_description(myjson, soup)
    if not description:
        sys.stderr.write("no description\n")

    myjson["entries"].append({
        "caption": title,
        "description": description,
        "album": album,
        "url": url,
        "date": date,
        "author": author,
        "images": images,
        "videos": [] # for now
    })

    return myjson


def generate_url(config, url):
    socialjson = do_url(config, url)

    retval = {
        "social": socialjson
    }

    feedjson = rssit.util.simple_copy(socialjson)
    for entry in feedjson["entries"]:
        if "realcaption" in entry:
            entry["title"] = entry["realcaption"]
        else:
            entry["title"] = entry["caption"]
        if entry["description"] and entry["description"] != "":
            entry["content"] = entry["description"]
        else:
            return retval

    return {
        "social": socialjson,
        "feed": feedjson
    }


def process(server, config, path):
    if path.startswith("/url/"):
        url = "http://" + re.sub(".*?/url/", "", config["fullpath"])
        return generate_url(config, url)
    elif path.startswith("/qurl/"):
        url = "http://" + re.sub(".*?/qurl/", "", config["fullpath"])
        config["quick"] = True
        return generate_url(config, url)


infos = [{
    "name": "news",
    "display_name": "News",

    "config": {},

    "get_url": get_url,
    "process": process
}]