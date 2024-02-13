import base64
from dataclasses import dataclass

from selenium import webdriver
from bs4 import BeautifulSoup

from selenium.common import JavascriptException, WebDriverException

TEST_URL = "https://www.saaspegasus.com/guides/modern-javascript-for-django-developers/apis/"


@dataclass
class SinglePage:
    title: str
    url: str
    html_content: str
    screenshot: bytes

    def save_html(self, file_path: str):
        with open(file_path, "w") as file:
            file.write(self.html_content)

    def save_screenshot(self, file_path: str):
        with open(f"{file_path}.pdf", "wb") as file:
            file.write(self.screenshot)


# TODO: js escape some characters
def safely_execute_js(func):
    def wrapper_safely_execute_js(self, resource_url):
        if resource_url.startswith("data:"):
            return resource_url
        if not resource_url.startswith("http"):
            resource_url = self.driver.execute_script(
                f"return new URL('{resource_url}', window.location.href).href"
            )
        try:
            return func(self, resource_url)
        except (JavascriptException, WebDriverException) as e:
            print(f'Error downloading resource: {resource_url}', e.msg)
            return ""

    return wrapper_safely_execute_js


class SinglePageDownloader:
    def __init__(self):
        # Set up headless Chrome browser
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--user-data-dir=/home/kureta/.cache/chromium/scraper-profile")
        self.driver = webdriver.Chrome(options=options)

    def __del__(self):
        # Close the browser
        self.driver.quit()

    @safely_execute_js
    def fetch_image(self, resource_url):
        return self.driver.execute_script(
            f"return fetch('{resource_url}', {{cache: 'force-cache'}}).then(response => response.blob())"
            f".then(blob => new Promise((resolve, reject) => {{"
            f"    const reader = new FileReader();"
            f"    reader.onloadend = () => resolve(reader.result);"
            f"    reader.onerror = reject;"
            f"    reader.readAsDataURL(blob);"
            f"}}));"
        )

    @safely_execute_js
    def fetch_text(self, resource_url):
        return self.driver.execute_script(
            f"return fetch('{resource_url}', {{cache: 'force-cache'}}).then(response => response.text());"
        )

    @safely_execute_js
    def fetch_iframe(self, iframe_url):
        return self.fetch_html(iframe_url)

    def fetch_html(self, url):
        # Navigate to webpage
        self.driver.get(url)
        # Extract HTML content
        html_content = self.driver.page_source
        # Parse HTML content
        soup = BeautifulSoup(html_content, "html.parser")

        # Get base64 encoded data for all resources (CSS, JS, images)
        for tag in soup.find_all(["link", "script", "img", "audio", "video", "iframe"]):
            if tag.name in ["img", "audio", "video"] and tag.get("src"):
                img_url = tag["src"]
                tag["src"] = self.fetch_image(img_url)
            elif tag.name == "script" and tag.get("src"):
                js_url = tag["src"]
                tag.string = self.fetch_text(js_url)
                del tag["src"]
            # TODO: link/font
            elif tag.name == "link" and tag.get("rel") == ["stylesheet"] and tag.get("href"):
                css_url = tag["href"]
                style_tag = soup.new_tag("style")
                style_tag.string = self.fetch_text(css_url)
                tag.replace_with(style_tag)
            elif tag.name == "iframe" and tag.get("src"):
                # Assume absolute path because I am lazy.
                iframe_url = tag["src"]
                iframe_content = self.fetch_iframe(iframe_url)
                tag.replace_with(iframe_content)

        # Now html_content contains the HTML page with embedded resources
        return soup.prettify()

    def get_single_page(self, url):
        # Navigate to webpage
        self.driver.get(url)
        title = self.driver.title
        # screenshot = self.driver.get_screenshot_as_png()
        screenshot = self.driver.print_page()
        screenshot = base64.b64decode(screenshot)

        # This is where we process the html source to embed all resources
        html_content = self.fetch_html(url)

        result = SinglePage(
            title=title,
            url=url,
            html_content=html_content,
            screenshot=screenshot,
        )

        return result


def main():
    # Create an instance of SinglePage
    downloader = SinglePageDownloader()
    # Fetch the HTML content of the webpage
    single_page = downloader.get_single_page(TEST_URL)

    single_page.save_html("pytorch.html")
    single_page.save_screenshot("pytorch")


if __name__ == '__main__':
    main()
