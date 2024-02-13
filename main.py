from selenium import webdriver
from bs4 import BeautifulSoup

from selenium.common import JavascriptException


class SinglePage:
    def __init__(self):
        # Set up headless Chrome browser
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        self.driver = webdriver.Chrome(options=options)

    def __del__(self):
        # Close the browser
        self.driver.quit()

    def fetch_image(self, resource_url):
        if not resource_url.startswith("http"):
            resource_url = self.driver.execute_script(
                f"return new URL('{resource_url}', window.location.href).href"
            )
        try:
            img_data = self.driver.execute_script(
                f"return fetch('{resource_url}', {{cache: 'force-cache'}}).then(response => response.blob()).then(blob => new Promise((resolve, reject) => {{"
                f"    const reader = new FileReader();"
                f"    reader.onloadend = () => resolve(reader.result);"
                f"    reader.onerror = reject;"
                f"    reader.readAsDataURL(blob);"
                f"}}));"
            )
        except JavascriptException:
            print(f"Failed to fetch image {resource_url}")
            img_data = ""
        return img_data

    def fetch_text(self, resource_url):
        if not resource_url.startswith("http"):
            resource_url = self.driver.execute_script(
                f"return new URL('{resource_url}', window.location.href).href"
            )
        try:
            content = self.driver.execute_script(
                f"return fetch('{resource_url}', {{cache: 'force-cache'}}).then(response => response.text());"
            )
        except JavascriptException:
            print(f"Failed to fetch text {resource_url}")
            content = ""
        return content

    def fetch_html(self, url):
        # Navigate to webpage
        self.driver.get(url)
        # Extract HTML content
        html_content = self.driver.page_source
        # Parse HTML content
        soup = BeautifulSoup(html_content, "html.parser")

        # Get base64 encoded data for all resources (CSS, JS, images)
        for tag in soup.find_all(["link", "script", "img", "iframe"]):
            if tag.name == "img" and tag.get("src"):
                img_url = tag["src"]
                tag["src"] = self.fetch_image(img_url)
            elif tag.name == "script" and tag.get("src"):
                js_url = tag["src"]
                tag.string = self.fetch_text(js_url)
                del tag["src"]
            elif tag.name == "link" and tag.get("rel") == ["stylesheet"] and tag.get("href"):
                css_url = tag["href"]
                style_tag = soup.new_tag("style")
                style_tag.string = self.fetch_text(css_url)
                tag.replace_with(style_tag)
            elif tag.name == "iframe" and tag.get("src"):
                # Assume absolute path because I am lazy.
                iframe_url = tag["src"]
                iframe_content = self.fetch_html(iframe_url)
                tag.replace_with(iframe_content)

        # Now html_content contains the HTML page with embedded resources
        return soup.prettify()


def main():
    # Create an instance of SinglePage
    single_page = SinglePage()
    # Fetch the HTML content of the webpage
    html_content = single_page.fetch_html(
        "https://www.saaspegasus.com/guides/modern-javascript-for-django-developers/apis/")
    # Save the HTML content
    with open("index.html", "w") as file:
        file.write(html_content)


if __name__ == '__main__':
    main()
