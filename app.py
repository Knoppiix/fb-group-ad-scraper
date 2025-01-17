# Date: 2025-01-12
# Author: Gwendal Pineau
# Version: 1.0.0.
# Usage: python app.py

from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup
from openai import OpenAI
import hashlib
import json
import requests
import configparser


global ad_extracted_carac
# Dictionnary that will contain the data I want to extract from the ads
ad_extracted_carac = {"nb_room": 0, "bedrooms_to_rent": 0, "nb_male": "undefined", "nb_female": "undefined",
                      "rent_date": "undefined", "apart_loc": "undefined"}


def append_sha256_to_file(file_path, input_string):
    # Compute the SHA256 hash of the string
    sha256_hash = hashlib.sha256(input_string.encode()).hexdigest()

    # Open the file in append mode (creates the file if it doesn't exist)
    with open(file_path, 'a') as file:
        file.write(f"{sha256_hash}\n")


def is_sha256_in_file(file_path, sha256_hash):  # Check if the given SHA256 hash exists in the file.
    with open(file_path, 'r') as file:
        for line in file:
            if sha256_hash in line:
                return True
    return False


# Map the extracted data from the advertisement by the LLM to the ad_extracter_carac dict
def data_to_extract(json):
    global ad_extracted_carac
    for key in ad_extracted_carac:
        if key in json:
            ad_extracted_carac[key] = json[key]

def get_ads():
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    parsed = []

    listings = soup.find_all('div', class_='x1yztbdb x1n2onr6 xh8yej3 x1ja2u2z')
    for listing in listings:
        try:
            # Get the item image.
            image = listing.find('img',
                                 class_='xz74otr x1ey2m1c xds687c x5yr21d x10l6tqk x17qophe x13vifvy xh8yej3')
            if image:
                image = image['src']

            # Get the item title from span.
            title = listing.find('span', 'x1lliihq x6ikm8r x10wlt62 x1n2onr6 x1j85h84').text
            # Get the item price.
            price = listing.find('span',
                                 'html-span xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs xtvhhri').text
            # Get the item URL.
            post_url = listing.find('span', 'x1rg5ohu x6ikm8r x10wlt62 x16dsc37 xt0b8zv').parent

            ad_text = listing.find('span',
                                   "x193iq5w xeuugli x13faqbe x1vvkbs x1xmvt09 x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x xudqn12 x3x7a5m x6prxxf xvq8zen xo1l8bm xzsf02u x1yc453h").text

            # After extracting the advertisement text, we check if it has already been treated by the script previously (determined from the hash of the ad)
            if is_sha256_in_file("adSums.txt", hashlib.sha256(ad_text.encode()).hexdigest()):
                continue

            append_sha256_to_file("adSums.txt",
                                  ad_text)  # Append the hash of the advertisement so as not to treat it again

            ad = {
                'image': image,
                'title': title,
                'price': price,
                'post_url': post_url,
                'ad_text': ad_text
            }
            parsed.append(ad)
        except AttributeError:  # Some elements in the page may be misinterpreted as advertisements, but aren't, thus return an AttributeError
            continue
        except Exception as e:
            print("Error: ", e)
    return parsed

def format_json(advertisement, json_sum):
    jsonMessage = r"""
        {
          "content": "",
          "tts": false,
          "embeds": [
            {
              "description": "",
              "fields": [],
              "author": {
                "name": ""
              },
              "title": "",
              "color": 1048302,
              "image": {
                "url": ""
              }
            }
          ],
          "components": [],
          "actions": {}
        }"""
    print(json_sum)
    # Extract data from the Json Summary generated by the AI
    try:
        if json_sum[0] == "`":
            json_sum = json_sum.split("json\n")[1].replace("```", '')
        json_sum = json.loads(json_sum)

        # Populate the dictionnary with the data extracted from the ad by AI
        data_to_extract(json_sum)
        print(ad_extracted_carac)
        if ad_extracted_carac["bedrooms_to_rent"] < 2:
            return

        # Then, format the JSON embed message with the previously parsed data
        jsonMessage = json.loads(jsonMessage)
        jsonMessage["embeds"][0]["description"] = f"""**{ad_extracted_carac["nb_room"]} pièce(s)** au total\r\n
                                                    **{ad_extracted_carac["bedrooms_to_rent"]} chambre(s)** à louer\r\n
                                                    **Nombre de garcons: {ad_extracted_carac["nb_male"]}** // **Nombre de filles: {ad_extracted_carac["nb_female"]}**\r\n
                                                    Disponibilité de l'appartement: {ad_extracted_carac["rent_date"]}\r\n
                                                    Localisation: **{ad_extracted_carac["apart_loc"]}**"""
        jsonMessage["embeds"][0]["title"] = advertisement["title"]
        jsonMessage["embeds"][0]["author"]["name"] = advertisement["price"]
        jsonMessage["embeds"][0]["image"]["url"] = advertisement["image"]

    except:
        return "Error while treating an advertisement."

    return jsonMessage


if __name__ == "__main__":
    config = configparser.ConfigParser(interpolation=None)

    try:
        # Read the configuration file
        config.read('parameters.ini')
        api_key = config['DEFAULT']['OPENAI_API_KEY']
        group_url = config['DEFAULT']['GROUP_URL']
        webhook_url = config['DEFAULT']['WEBHOOK_URL']
        session_cookie = config['DEFAULT']['FACEBOOK_XS_COOKIE']
        c_user_cookie = config['DEFAULT']['FACEBOOK_CUSER_COOKIE']
    except Exception as e:
        print("Error while reading the configuration file:",e)
        exit()

    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        print("Error while connecting to the OpenAI API:", e)
        exit()

    # Initialize the session using Playwright.
    with sync_playwright() as p:
        # Open a new browser page.
        browser = p.chromium.launch(headless=False, args=["--disable-notifications"])
        page = browser.new_page()
        # Navigate to the URL.
        page.goto(group_url)
        # Wait for the page to load.
        time.sleep(2)
        
        # We set the session cookie "xs" to allow the browser to access the facebook group
        try:
            page.evaluate(f"""
            document.querySelector("body > div.__fb-light-mode.x1n2onr6.x1vjfegm > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div.x1exxf4d.x13fuv20.x178xt8z.x1l90r2v.x1pi30zi.x1swvt13 > div > div:nth-child(2) > div.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x1ypdohk.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x16tdsg8.x1hl2dhg.xggy1nq.x1o1ewxj.x3x9cwd.x1e5q0jg.x13rtm0m.x87ps6o.x1lku1pv.x1a2a7pz.x9f619.x3nfvp2.xdt5ytf.xl56j7k.x1n2onr6.xh8yej3").click()
            document.cookie = `xs={session_cookie}; path=/; secure;`
            document.cookie = `c_user={c_user_cookie}; path=/; secure;`
            location.reload()        
            """)
        except:
            print("An error has occured: the session cookie might have expired.")

        # Wait for the page to load.
        page.wait_for_selector("div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z")
        # Expand all the posts (click on "en voir plus" button)
        page.evaluate(
            "Array.from(document.getElementsByClassName('x1i10hfl xjbqb8w x1ejq31n xd10rxx x1sy0etr x17r0tee x972fbf xcfux6l x1qhh985 xm0m39n x9f619 x1ypdohk xt0psk2 xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz x1sur9pj xkrqix3 xzsf02u x1s688f')).filter(element => element.innerText === 'En voir plus').forEach(elem => elem.click())")

        parsed_ads = []
        # Infinite scroll to the bottom of the page until the loop breaks
        for _ in range(6):
            page.keyboard.press('End')
            time.sleep(2)
            page.evaluate(
                "Array.from(document.getElementsByClassName('x1i10hfl xjbqb8w x1ejq31n xd10rxx x1sy0etr x17r0tee x972fbf xcfux6l x1qhh985 xm0m39n x9f619 x1ypdohk xt0psk2 xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz x1sur9pj xkrqix3 xzsf02u x1s688f')).filter(element => element.innerText === 'See more').forEach(elem => elem.click())")
            parsed_ads += get_ads()

        # Close the browser.
        browser.close()
        # Return the parsed data as a JSON.
        result = []
        for item in parsed_ads:
            result.append({
                'name': item['title'],
                'price': item['price'],
                'title': item['title'],
                'ad_text': item['ad_text'],
                'link': item['post_url'],
                'image': item['image']
            })

        for ad in result:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    # This is where you define de system prompt and pass all the rules you want to define in the advertisement parsing
                    {"role": "system", "content": """
                    You are a specialized data extraction assistant for apartment rental advertisements. Your task is to extract specific data points and return them STRICTLY in JSON format.
                    REQUIRED FIELDS (must be included if found):
                    - "nb_room": Total number of rooms (including ALL rooms - bedrooms, bathrooms, etc.)
                    - "bedrooms_to_rent": Number of available bedrooms for rent

                    OPTIONAL FIELDS (include ONLY if explicitly mentioned and certain):
                    - "nb_male": Current number of male residents (only if names are clearly provided)
                    - "nb_female": Current number of female residents (only if names are clearly provided)
                    - "apart_loc": Apartment location (only if specific address/area is mentioned)
                    - "rent_date": Available date (must be in YYYY-MM-DD format, only if explicitly stated. If terms like 'immediately' or 'now' are used, show "now")

                    IMPORTANT RULES:
                    1. Return ONLY the JSON object, no additional text
                    2. If the ad specifies "females only" or "girls only", return an empty JSON object: {}
                    3. Do NOT include optional fields if they are uncertain or require assumptions
                    4. Do NOT attempt to guess or infer dates from context
                    5. For dates:
                    - Only parse explicit dates (e.g., "January 15th", "15/01/2025", "next month")
                    - Convert all dates to YYYY-MM-DD format
                    - If "immediate" or "now" is mentioned, use 2025-01-17
                    - If only a month is mentioned (e.g., "from March"), use the 1st of that month
                    - Do NOT include the rent_date if the date is ambiguous

                    Example response:
                    {
                        "nb_room": 3,
                        "bedrooms_to_rent": 1,
                        "nb_male": 2,
                        "nb_female": undefined; 
                        "apart_loc": "123 Main Street",
                        "rent_date": "2025-02-01"
                    }
                    
                    Lastly, if the advertisement says it's a "Girl only" shared appartment, please return an empty json as such : {}.
                    Give me ONLY the json result, do not add any extra comment.
                    """},
                    {
                        "role": "user",
                        "content": f"Here is an apartment advertisement text you need to parse, according to the rules I gave to you. The title of the ad is {ad['title']} and the text is : {ad['ad_text']}"
                    }
                ]
            )
            json_parsed_content = completion.choices[0].message.content
            if len(json_parsed_content) > 2:  # If the LLM returns an empty result (→ it may return an empty result in case the advertisement doesn't respond to the expectations)
                discord_embed_msg = format_json(advertisement=ad, json_sum=json_parsed_content)
                if discord_embed_msg:
                    try:
                        response = requests.post(webhook_url, json=discord_embed_msg)
                    except:
                        print("An error occured during the request to the webhook. Please check the URL is correct in the parameters.ini file.")
