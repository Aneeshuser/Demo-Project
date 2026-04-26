from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi
import requests
from bs4 import BeautifulSoup
import re

# the api key configuration
GOOGLE_API_KEY = "Google_api_key"
client = genai.Client(api_key=GOOGLE_API_KEY)
app = FastAPI()

class LinkRequest(BaseModel):
    url: str

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.post("/summarize")
def summarize_link(request: LinkRequest):
    url = request.url
    text_to_summarize = ""

    try:

        # Check the youtube URL
        if "youtube.com" not in url and "youtu.be" not in url:
            raise HTTPException(status_code=400, detail="Only YouTube URLs are supported.")

        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id_match:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL. Could not extract video ID.")
        video_id = video_id_match.group(1)

        try:
            # Fetch transcript with multi-language + auto-caption support
            langs = [
                'en', 'en-US', 'en-GB', 'a.en',
                'hi', 'es', 'fr', 'de', 'ja',
                'ko', 'zh-Hans', 'ru', 'pt', 'it', 'ar'
            ]
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=langs,
                cookies="cookies.txt"
            )
            text_to_summarize = " ".join([entry['text'] for entry in transcript])

        except Exception:
            # if captions are off, scrape the meta tags
            headers = {"User-Agent": "Mozilla/5.0"}
            yt_page = requests.get(url, headers=headers, timeout=10)
            yt_soup = BeautifulSoup(yt_page.text, 'html.parser')

            title_tag = yt_soup.find("meta", property="og:title")
            desc_tag = yt_soup.find("meta", property="og:description")

            title = title_tag["content"] if title_tag else "Unknown Title"
            desc = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

            if not desc:
                raise HTTPException(
                    status_code=400,
                    detail="No captions or description available for this video."
                )

            text_to_summarize = f"Title: {title}\nDescription: {desc}"

        # If not enough readable text found to generate a summary
        text_to_summarize = text_to_summarize[:30000]

        if len(text_to_summarize) < 50:
            raise HTTPException(
                status_code=400,
                detail="Not enough readable text found to generate a summary."
            )

        # the Prompt for the model
        prompt = """You are an expert YouTube video summarizer. Analyze the following transcript and respond using EXACTLY these 4 section headings, in this order:

### 1. Short Summary
Provide a 3-4 line high-level overview of what this video is about.

### 2. Detailed Summary
Provide a comprehensive breakdown of the core narrative, main arguments, and key concepts discussed. Be thorough and cover all major points.

### 3. Key Bullet Points
List the most important facts, statistics, quotes, or arguments as concise bullet points.

### 4. Actionable Insights / Key Takeaways
List specific lessons, advice, or actionable steps the viewer can apply in their own life or work.

Content to summarize:
"""

        # which model to use
        gemini_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt + "\n\n" + text_to_summarize
        )

        return {"summary": gemini_response.text}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")
