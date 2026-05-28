Python
import os
import random
import datetime
import google.generativeai as genai
import tweepy

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

def get_tweet_content():
    # Configure Gemini
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-pro')
    
    # Determine if it's morning or afternoon post to vary the angle slightly
    current_hour = datetime.datetime.now().hour
    time_of_day = "morning (energizing, wake-up call)" if current_hour < 12 else "afternoon/evening (reflective, sharp, or witty commentary)"
    
    # Pick a random theme from the list to rotate through
    selected_theme = random.choice(THEMES)
    
    # The Prompt setting the exact persona you requested
    prompt = f"""
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
    
    response = model.generate_content(prompt)
    return response.text.strip()

def post_to_x():
    # Fetch API keys from environment variables (set securely in GitHub)
    api_key = os.environ["X_API_KEY"]
    api_secret = os.environ["X_API_SECRET"]
    access_token = os.environ["X_ACCESS_TOKEN"]
    access_token_secret = os.environ["X_ACCESS_TOKEN_SECRET"]
    
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
    print(f"Generated Tweet:\n{tweet_text}")
    client.create_tweet(text=tweet_text)
    print("Tweet successfully posted!")

if __name__ == "__main__":
    post_to_x()
