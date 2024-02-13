from selenium import webdriver
from bs4 import BeautifulSoup
import base64

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

# Get base64 encoded data for all resources (CSS, JS, images)
for tag in soup.find_all(["link", "script", "img"]):
    if tag.name == "img" and tag.get("src"):
        img_url = tag["src"]
        if not img_url.startswith("http"):
            img_url = driver.execute_script(
                f"return new URL('{img_url}', window.location.href).href"
            )
        print(img_url)
        print("============")
        try:
            img_data = driver.execute_script(
                f"return fetch('{img_url}').then(response => response.blob()).then(blob => new Promise((resolve, reject) => {{"
                f"    const reader = new FileReader();"
                f"    reader.onloadend = () => resolve(reader.result);"
                f"    reader.onerror = reject;"
                f"    reader.readAsDataURL(blob);"
                f"}}));"
            )
        except:
            img_data = ""

        tag["src"] = img_data
    elif tag.name == "script" and tag.get("src"):
        js_url = tag["src"]
        if not js_url.startswith("http"):
            js_url = driver.execute_script(
                f"return new URL('{js_url}', window.location.href).href"
            )
        try:
            js_content = driver.execute_script(
                f"return fetch('{js_url}').then(response => response.text());"
            )
        except:
            js_content = ""
        tag.string = js_content
    elif tag.name == "link" and tag.get("rel") == ["stylesheet"] and tag.get("href"):
        css_url = tag["href"]
        if css_url.startswith("http"):
            css_content = driver.execute_script(
                f"return fetch('{css_url}').then(response => response.text());"
            )
        else:
            absolute_css_url = driver.execute_script(
                f"return new URL('{css_url}', window.location.href).href"
            )
            css_content = driver.execute_script(
                f"return fetch('{absolute_css_url}').then(response => response.text());"
            )
        style_tag = soup.new_tag("style")
        style_tag.string = css_content
        tag.replace_with(style_tag)

# Close the browser
driver.quit()

# Now html_content contains the HTML page with embedded resources
# print(soup.prettify())

# save the soup into index,html
with open("index.html", "w") as file:
    file.write(soup.prettify())
