import base64
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin, urlparse

import brotli
import click
import requests
from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import Page, sync_playwright
from playwright_stealth import stealth_sync

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

# TODO: this is a mess
ub_version = "1.55.1rc2"
ub_zip_name = f"uBlock0_{ub_version}.chromium.zip"
ub_download_url = f"https://github.com/gorhill/uBlock/releases/download/{ub_version}/{ub_zip_name}"
ub_download_destination = Path.home() / ".cache" / "singlepage"
ub_zip_path = ub_download_destination / ub_zip_name
ub_path = ub_download_destination / f"uBlock0_{ub_version}.chromium" / "uBlock0.chromium" / "uBlock0.chromium"


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


# TODO: Download in a structured way, not just in the current directory
class Scraper:
    def __init__(self, page: Page):
        self.session = requests.Session()

        self.page = page
        stealth_sync(self.page)

    def save_screenshot(self, path):
        logger.debug(f"Saving screenshot to {path}")
        self.page.screenshot(path=path, full_page=True)

    def save_pdf(self, path):
        logger.debug(f"Saving pdf to {path}")
        client = self.page.context.new_cdp_session(self.page)
        data = client.send("Page.printToPDF", {"landscape": False, "displayHeaderFooter": False})
        with open(path, 'wb') as f:
            f.write(base64.b64decode(data["data"]))

    def fetch_html(self, url):
        logger.debug(f"Fetching html content from {url}")

        # load page
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        content = self.page.content()

        # get title
        title = self.page.title()
        # make filename
        path = title[:128] if title else urlparse(url).path[:128]

        # save screenshot
        self.save_screenshot(f"{path}.png")
        # save pdf
        self.save_pdf(f'{path}.pdf')

        # parse html content
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
            elif tag.name == "link" and tag.get("rel") == ["stylesheet"] and tag.get("href"):
                css_url = tag["href"]
                style_tag = soup.new_tag("style")
                sheet = self.fetch_data(ContentType.CSS, css_url, url)
                style_tag.string = sheet
                tag.replace_with(style_tag)
            elif tag.name == "iframe" and tag.get("src"):
                logger.warning(f"NOT IMPLEMENTED: Embedding iframe {urlparse(tag['src']).path}")
                # iframe_url = tag["src"]
                # iframe_content = self.fetch_html(iframe_url)
                # tag.replace_with(iframe_content)

        logger.debug(f"Loaded {len(loaded)} elements")

        with open(f'{path}.html', "w") as f:
            f.write(soup.prettify())

        logger.info("HTML content saved to output.html")

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


def prepare_extension():
    # check if extension is already downloaded
    if ub_path.exists():
        logger.debug(f"uBlock extension already downloaded at {ub_path}")
        return
    # download uBlock extension
    logger.debug(f"Downloading uBlock extension from {ub_download_url}")
    response = requests.get(ub_download_url)
    response.raise_for_status()
    ub_download_destination.mkdir(parents=True, exist_ok=True)
    with open(ub_zip_path, "wb") as f:
        f.write(response.content)
    # unzip the extension
    import zipfile
    with zipfile.ZipFile(ub_zip_path, 'r') as zip_ref:
        zip_ref.extractall(ub_path)
    # remove the zip file
    ub_zip_path.unlink()


@cli.command()
@click.argument("url")
def scrape(url: str):
    prepare_extension()
    # Set up headless Chrome browser
    args = [
        '--no-sandbox',
        '--disable-infobars',
        '--lang=en-US',
        '--start-maximized',
        '--window-position=-10,0',
        f"--disable-extensions-except={ub_path}",
        f"--load-extension={ub_path}",
        "--headless=new",
    ]
    ignoreDefaultArgs = ['--enable-automation']

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir='/home/kureta/.cache/chromium/scraper-profile',
            args=args, ignore_default_args=ignoreDefaultArgs,
            headless=False,
            viewport={'width': 1920, 'height': 1080},
        )

        page = browser.new_page()
        scraper = Scraper(page)
        scraper.fetch_html(url)
        browser.close()


if __name__ == "__main__":
    cli()
