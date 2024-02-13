import base64
import html
from enum import Enum
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC  # noqa

TEST_URL = "https://www.jeremyjordan.me/autoencoders/"  # noqa

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


def get_header(content_type, referrer=None):
    header = BASE_HEADER.copy()
    if referrer:
        header.update({"Referrer": referrer})
    header.update({"Accept": accept[content_type]})
    return header


def get_content(response):
    if response.headers.get('Transfer-Encoding') == 'chunked':
        content = b''
        for r in response.iter_content(1024):
            content += r
    else:
        content = response.content
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(content).decode('utf-8')


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
        options.add_argument("--user-data-dir=/home/kureta/.cache/chromium/scraper-profile")
        self.driver = webdriver.Chrome(options=options)

    def __del__(self):
        # Close the browser
        self.driver.quit()

    def fetch_html(self, url):
        logger.debug(f"Fetching html content from {url}")
        # self.session.headers = get_header(ContentType.HTML)
        # response = self.session.get(url, stream=True)
        #
        # content = get_content(response)
        self.driver.get(url)
        wait = WebDriverWait(self.driver, 10)
        wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        # Extract HTML content
        content = self.driver.page_source

        soup = BeautifulSoup(content, "lxml")

        for tag in soup.find_all(["link", "script", "img", "iframe"]):
            if tag.name in ["img"] and tag.get("src"):
                img_url = tag["src"]
                img_data = self.fetch_data(ContentType.IMG, img_url, url)
                # if it is a base64 encoded image, we can directly embed it
                if img_data.startswith("data:"):
                    logger.debug(f"Embedding base64 image {img_url}")
                    tag["src"] = img_data
                # if its is svg, we can directly embed it
                elif is_svg(img_url):
                    logger.debug(f"Embedding svg image {img_url}")
                    # parse the svg content and embed it
                    svg_soup = BeautifulSoup(img_data, "lxml")
                    # replace with svg tag
                    tag.replace_with(svg_soup.find("svg"))
                else:
                    tag["src"] = f"data:image/jpeg;base64,{img_data}"
            elif tag.name == "script" and tag.get("src"):
                js_url = tag["src"]
                tag.string = html.escape(self.fetch_data(ContentType.JS, js_url, url))
                del tag["src"]
            elif tag.name == "link" and tag.get("rel") == ["stylesheet"] and tag.get("href"):
                css_url = tag["href"]
                style_tag = soup.new_tag("style")
                sheet = self.fetch_data(ContentType.CSS, css_url, url)
                style_tag.string = sheet
                tag.replace_with(style_tag)
            # elif tag.name == "iframe" and tag.get("src"):
            #     iframe_url = tag["src"]
            #     iframe_content = self.fetch_html(iframe_url)
            #     tag.replace_with(iframe_content)

        return soup.prettify()

    def fetch_data(self, content_type, url, referrer=None):
        if not url.startswith("http"):
            url = urljoin(referrer, url)
        logger.debug(f"Fetching {content_type} from {url} (referrer {referrer})")
        self.session.headers = get_header(content_type, referrer)
        try:
            response = self.session.get(url, stream=True)
        except Exception as e:
            logger.error(f"Failed to fetch {url} with error {e}")
            return ""

        return get_content(response)


def main():
    scraper = Scraper()
    html_content = scraper.fetch_html(TEST_URL)

    with open("output.html", "w") as f:
        f.write(html_content)


if __name__ == '__main__':
    main()
