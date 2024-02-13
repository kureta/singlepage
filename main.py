from selenium import webdriver
from bs4 import BeautifulSoup
import base64

from selenium.common import JavascriptException

# Set up headless Chrome browser
options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=options)

# Navigate to webpage
url = "https://www.saaspegasus.com/guides/modern-javascript-for-django-developers/apis/"
driver.get(url)

# Extract HTML content
html_content = driver.page_source

# Parse HTML content
soup = BeautifulSoup(html_content, "html.parser")

# Base URL of the webpage
base_url = driver.current_url


def fetch_image(resource_url):
    if not resource_url.startswith("http"):
        resource_url = driver.execute_script(
            f"return new URL('{resource_url}', window.location.href).href"
        )
    try:
        img_data = driver.execute_script(
            f"return fetch('{resource_url}').then(response => response.blob()).then(blob => new Promise((resolve, reject) => {{"
            f"    const reader = new FileReader();"
            f"    reader.onloadend = () => resolve(reader.result);"
            f"    reader.onerror = reject;"
            f"    reader.readAsDataURL(blob);"
            f"}}));"
        )
    except JavascriptException:
        img_data = ""
    return img_data


def fetch_text(resource_url):
    if not resource_url.startswith("http"):
        resource_url = driver.execute_script(
            f"return new URL('{resource_url}', window.location.href).href"
        )
    try:
        content = driver.execute_script(
            f"return fetch('{resource_url}').then(response => response.text());"
        )
    except JavascriptException:
        content = ""
    return content


# Get base64 encoded data for all resources (CSS, JS, images)
for tag in soup.find_all(["link", "script", "img"]):
    if tag.name == "img" and tag.get("src"):
        img_url = tag["src"]
        tag["src"] = fetch_image(img_url)
    elif tag.name == "script" and tag.get("src"):
        js_url = tag["src"]
        tag.string = fetch_text(js_url)
        del tag["src"]
    elif tag.name == "link" and tag.get("rel") == ["stylesheet"] and tag.get("href"):
        css_url = tag["href"]
        style_tag = soup.new_tag("style")
        style_tag.string = fetch_text(css_url)
        tag.replace_with(style_tag)

# Close the browser
driver.quit()

# Now html_content contains the HTML page with embedded resources
# print(soup.prettify())

# save the soup into index,html
with open("index.html", "w") as file:
    file.write(soup.prettify())
