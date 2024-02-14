import base64
import time
from enum import Enum
from urllib.parse import urljoin, urlparse

import brotli
import click
import requests
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC  # noqa

BASE_HEADER = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-GPC": "1",
}


# TODO: implement other content types
class ContentType(Enum):
    HTML = 1
    CSS = 2
    JS = 3
    IMG = 4
    FONT = 5
    AUDIO = 6
    VIDEO = 7
    IFRAME = 8


accept = {
    ContentType.HTML: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    ContentType.IMG: "image/avif,image/webp,*/*",
    ContentType.JS: "*/*",
    ContentType.CSS: "text/css,*/*;q=0.1",
    ContentType.FONT: "application/font-woff2;q=1.0,application/font-woff;q=0.9,*/*;q=0.8",
    ContentType.AUDIO: "audio/*",
    ContentType.VIDEO: "video/*",
    ContentType.IFRAME: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def sanitize_inline_js(html_content):
    # TODO: Also remove events, don't know why
    # Remove event attributes such as onclick, onmouseover, etc.
    # sanitized_content = re.sub(r"\bon\w+\s*=\s*['\"].*?['\"]", "", html_content, flags=re.IGNORECASE)

    # Escape JavaScript content by replacing < and > with HTML entities
    sanitized_content = html_content.replace("<", "&lt;").replace(">", "&gt;")

    return sanitized_content


def get_header(content_type, referrer=None):
    header = BASE_HEADER.copy()
    if referrer:
        header.update({"Referrer": referrer})
    header.update({"Accept": accept[content_type]})
    return header


def get_content(response):
    if response.headers.get("Transfer-Encoding") == "chunked":
        content = b""
        for r in response.iter_content(1024):
            content += r
    else:
        content = response.content
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(content).decode("utf-8")


def is_svg(url):
    # there might be some parameters in the url
    path = urlparse(url).path
    return path.endswith(".svg")


class Scraper:
    def __init__(self):
        self.session = requests.Session()

        # Set up headless Chrome browser
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        # TODO: using tmpdir causes errors, find out why.
        options.add_argument(
            "--user-data-dir=/home/kureta/.cache/chromium/scraper-profile"
        )
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_window_size(1920, 1080)

    def __del__(self):
        # Close the browser
        self.driver.quit()

    def fetch_html(self, url):
        logger.debug(f"Fetching html content from {url}")

        self.driver.get(url)
        time.sleep(2)  # Wait for the page to load
        content = self.driver.execute_script(
            "return document.documentElement.outerHTML"
        )

        soup = BeautifulSoup(content, "lxml")

        loaded = []
        for tag in soup.find_all(["link", "script", "img"]):
            loaded.append(tag)
            if tag.name in ["img"] and tag.get("src"):
                img_url = tag["src"]
                # if it is a base64 encoded image, we can directly embed it
                if img_url.startswith("data:"):
                    logger.debug(f"Embedding base64 image {urlparse(img_url).path}")
                    tag["src"] = img_url
                    continue

                # if its is svg, we can directly embed it
                img_data = self.fetch_data(ContentType.IMG, img_url, url)
                if is_svg(img_url):
                    # parse the svg content and embed it
                    if isinstance(img_data, bytes):
                        logger.debug(
                            f"Decompressing svg image {urlparse(img_url).path}"
                        )
                        img_data = brotli.decompress(img_data).decode("utf-8")
                    logger.debug(f"Embedding svg image {urlparse(img_url).path}")
                    svg_soup = BeautifulSoup(img_data, "xml")
                    # replace with svg tag
                    tag.replace_with(svg_soup.find("svg"))
                else:
                    tag["src"] = f"data:image/jpeg;base64,{img_data}"
            elif tag.name == "script" and tag.get("src"):
                # TODO: maybe we can just remove all javascript
                # del tag
                js_url = tag["src"]
                tag.string = sanitize_inline_js(
                    self.fetch_data(ContentType.JS, js_url, url)
                )
                del tag["src"]
            elif (
                tag.name == "link"
                and tag.get("rel") == ["stylesheet"]
                and tag.get("href")
            ):
                css_url = tag["href"]
                style_tag = soup.new_tag("style")
                sheet = self.fetch_data(ContentType.CSS, css_url, url)
                style_tag.string = sheet
                tag.replace_with(style_tag)
            # elif tag.name == "iframe" and tag.get("src"):
            #     iframe_url = tag["src"]
            #     iframe_content = self.fetch_html(iframe_url)
            #     tag.replace_with(iframe_content)

        logger.debug(f"Loaded {len(loaded)} elements")
        return soup.prettify()

    def fetch_data(self, content_type, url, referrer=None):
        if not url.startswith("http"):
            url = urljoin(referrer, url)
        logger.debug(
            f"Fetching {content_type} from {urlparse(url).path.split('/')[-1]} (referrer {referrer})"
        )
        self.session.headers = get_header(content_type, referrer)
        try:
            response = self.session.get(url, stream=True)
        except Exception as e:
            logger.error(f"Failed to fetch {url} with error {e}")
            return ""

        return get_content(response)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("url")
def scrape(url: str):
    scraper = Scraper()
    html_content = scraper.fetch_html(url)

    with open("output.html", "w") as f:
        f.write(html_content)

    logger.info("HTML content saved to output.html")


if __name__ == "__main__":
    cli()
