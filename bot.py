import os
import random
import datetime
import json
import time
from google import genai
from zoneinfo import ZoneInfo

import tweepy
from dotenv import load_dotenv

load_dotenv()

TIMEZONE = ZoneInfo("Europe/London")
SENT_FILE = "sent.json"

# 1. Configuration & Themes
THEMES = [
    "Believing in our borders, national sovereignty, and community security.",
    "Celebrating British history, heritage, and the giants who built our nation.",
    "Aspirational future - why Britain's best days are ahead of us, not behind us.",
    "Rejecting managed decline and moving past cultural self-loathing.",
    "Restoring absolute pride in British culture, innovation, and local communities.",
    "Common-sense, right-of-centre approaches to modern British challenges.",
    "The extraordinary potential of Great Britain when we embrace national strength."
]

def now():
    return datetime.datetime.now(TIMEZONE)

def get_today():
    return now().strftime("%Y-%m-%d")

def get_slot():
    hour = now().hour
    if 6 <= hour < 12:
        return "morning"
    if 18 <= hour < 23:
        return "evening"
    return None

def load_sent():
    if not os.path.exists(SENT_FILE):
        return {}
    with open(SENT_FILE, encoding="utf-8") as file:
        return json.load(file)

def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as file:
        json.dump(sent, file, ensure_ascii=False, indent=2)
        file.write("\n")

def retry_call(action, name, retries=3, delay=2, sleep=time.sleep):
    current_delay = delay
    for attempt in range(1, retries + 1):
        try:
            return action()
        except Exception as error:
            print(f"{name} failed, attempt {attempt}/{retries}: {error}")
            if attempt == retries:
                raise
            sleep(current_delay)
            current_delay *= 2

def get_tweet_content():
    # 新版初始化方式
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    
    # Determine if it's morning or afternoon post to vary the angle slightly
    current_hour = now().hour
    time_of_day = "morning (energizing, wake-up call)" if current_hour < 12 else "afternoon/evening (reflective, sharp, or witty commentary)"
    
    # Pick a random theme from the list to rotate through
    selected_theme = random.choice(THEMES)
    
    # The Prompt setting the exact persona you requested
    prompt2 = f"""
    You are a sharp, patriotic British commentator writing a tweet for the {time_of_day}.
    
    Core Theme for this tweet: {selected_theme}
    
    Strict Guidelines:
    1. Tone: Reformist, proud, iconic, and vigilant. Unapologetic patriotism with common-sense, right-of-centre British politics.
    2. Vibe: Aspirational and forward-looking. Drive home the ethos that "Britain's best days aren't behind us - they are ahead of us." Reject decline and cultural self-loathing.
    3. Style: Professional, but include British wit, dry humor, or a clever turn of phrase where appropriate. 
    4. Imagery: Subtle use of British national symbols (e.g., the Lion, Britannia, the Bulldog) to represent a watchful, patriotic perspective.
    5. Length: MUST be under 280 characters so it fits on X (Twitter).
    6. Formatting: Do not use quotation marks around the tweet. Use 1 or 2 relevant hashtags at most (e.g., #GreatBritain, #ProudBritish).
    
    Write the tweet now:
    """


    prompt = f"""You are a proud British culture and history enthusiast writing a positive, energizing morning post for the {time_of_day}.
    
    Core Theme: Celebrating British heritage, perseverance, and looking forward to a bright future together.
    
    Strict Guidelines:
    1. Tone: Inspiring, proud, warm, and forward-looking. Focus on unity, hard work, and British grit.
    2. Vibe: Absolutely no political slogans. Instead of talking about politics, talk about our shared values, history, and community strength. Driven by the ethos that "Britain's best days are ahead of us."
    3. Style: Natural, conversational, and written like a real human being sharing a morning thought. Avoid sounding like a bot or an activist.
    
    4. X-API SAFE FILTER RULES (CRITICAL):
       - BANNED WORDS: Do not use ANY of these words as they trigger the X API 403 spam filter: "borders", "sovereignty", "national", "reformist", "right-of-centre", "security", "non-negotiable", "rebuild".
       - NO HASHTAGS: Do not include any hashtags or "#" symbols at all.
       - NO SPECIAL CHARACTERS: Never use the "&" symbol. Always write "and".
       - NO EXCLAMATION MARKS: Use periods (.) only. No exclamation marks (!).
    
    5. Length: Keep it under 200 characters.
    6. Formatting: Do not use quotation marks around the output.
    
    Write the text now:"""

    prompt3 = f"""
You are Dave — a 52-year-old bloke from Sheffield. Former engineer, now runs a small
business. You love British history, hate bureaucracy, and think this country has lost
its nerve. You're not angry — just quietly frustrated, and still hopeful.

It's {time_of_day}. You're posting a thought on X about: {selected_theme}

Write exactly ONE tweet as Dave would write it. Rules:
- Sound like a real person, not a politician or activist
- Dry wit or understatement is welcome — but don't force it
- No hashtags
- No exclamation marks
- No quotes around the output
- Under 200 characters
- Avoid these words: borders, sovereignty, national, reformist, security, rebuild

Example of the right tone:
"Funny how the same people who say Britain has nothing to be proud of still queue
politely and say sorry when someone bumps into them."

Write the tweet now:
"""
    
    print(prompt3)
        
    response = retry_call(
        lambda: client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt3
        ),
        "Gemini generation",
    )
    print("--------------------------------response--------------------------------")
    print(response.text.strip())
    
    # image_response = client.models.generate_content(
    #     model="gemini-2.5-flash-image",
    #     contents=prompt,
    #     config=types.GenerateContentConfig(
    #         response_modalities=["TEXT", "IMAGE"]
    #     )
    # )
    # for generated_image in image_response.generated_images:
    #     with open("image.jpg", "wb") as f:
    #         f.write(generated_image.image.image_bytes)
    # print("image generated successfully and saved as image.jpg")

    return response.text.strip()

def post_to_x():
    slot = get_slot()
    if slot is None:
        print("当前不在发布时间段，退出")
        return

    sent = load_sent()
    today = get_today()
    sent_today = sent.get(today, {})
    if slot in sent_today:
        print(f"今天 {slot} 已经发过，退出")
        return

    # Fetch API keys from environment variables (set securely in GitHub)
    api_key = os.environ["X_API_KEY"]
    api_secret = os.environ["X_API_SECRET"]
    access_token = os.environ["X_ACCESS_TOKEN"]
    access_token_secret = os.environ["X_ACCESS_TOKEN_SECRET"]
    auth = tweepy.OAuth1UserHandler(
        api_key, api_secret,
        access_token, access_token_secret
    )
    api_v1 = tweepy.API(auth)
    # Authenticate with X
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret
    )
    
    # Generate the tweet content
    tweet_text = get_tweet_content()
    
    # Print to console (for logs) and post to X
    # upload image
    print("uploading image...")
    media = retry_call(
        lambda: api_v1.media_upload(filename="image.jpg"),
        "Image upload",
    )
    media_id = media.media_id_string
    print(f"image uploaded successfully, Media ID: {media_id}")

    # post tweet with image
    tweet_response = retry_call(
        lambda: client.create_tweet(text=tweet_text, media_ids=[media_id]),
        "Tweet creation",
        retries=2,
    )
    tweet_id = str(tweet_response.data.get("id", "")) if getattr(tweet_response, "data", None) else ""
    sent.setdefault(today, {})[slot] = {
        "tweetId": tweet_id,
        "text": tweet_text,
        "createdAt": now().isoformat(),
    }
    save_sent(sent)
    print("Tweet successfully posted!")

if __name__ == "__main__":
    post_to_x()
