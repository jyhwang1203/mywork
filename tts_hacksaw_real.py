import os
import sys
import requests
from pathlib import Path

# Fix terminal encoding
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = "25753fc8a40398959d8709edc19fb73c95d26e7e7f9975e81969b37d8e5feae8"
VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"   # Josh
MODEL_ID = "eleven_multilingual_v2"

VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.75,
    "style": 0.35,
    "use_speaker_boost": True
}

OUTPUT_DIR = Path(r"C:\안티그래비티\파이썬\mywork\tts_output\hacksaw_ridge")

CUTS = [
    {"filename": "CUT01_hook_A", "timecode": "01:32:00 ~ 01:32:10", "text": "Every soldier carried a rifle."},
    {"filename": "CUT02_hook_B", "timecode": "01:33:00 ~ 01:33:10", "text": "This man carried nothing but a Bible."},
    {"filename": "CUT03_cut1_A", "timecode": "00:03:00 ~ 00:03:45", "text": "It started when he was just a kid. He nearly killed his own brother with a brick."},
    {"filename": "CUT04_cut1_B", "timecode": "00:03:45 ~ 00:04:30", "text": "That moment changed him forever. He swore he would never hurt another person again."},
    {"filename": "CUT05_cut2_A", "timecode": "00:36:30 ~ 00:37:30", "text": "Then the war came. He volunteered to serve — but not as a fighter."},
    {"filename": "CUT06_cut2_B", "timecode": "00:37:30 ~ 00:38:30", "text": "He wanted to be a medic."},
    {"filename": "CUT07_cut2_C", "timecode": "00:38:30 ~ 00:39:30", "text": "The Army gave him a rifle. He refused to touch it."},
    {"filename": "CUT08_cut3_A", "timecode": "00:40:30 ~ 00:41:30", "text": "His squadmates called him a coward. They beat him every night."},
    {"filename": "CUT09_cut3_B", "timecode": "00:42:00 ~ 00:43:00", "text": "They shoved his face into the pillow. They wanted him gone."},
    {"filename": "CUT10_cut4_A", "timecode": "00:58:00 ~ 01:00:00", "text": "The Army dragged him to court. They charged him with disobedience..."},
    {"filename": "CUT11_cut4_B", "timecode": "01:01:00 ~ 01:02:00", "text": "But then his father appeared. A broken war veteran..."},
    {"filename": "CUT12_cut4_C", "timecode": "01:02:30 ~ 01:03:30", "text": "He carried a single letter... It proved his son had every legal right to refuse."},
    {"filename": "CUT13_cut5_A", "timecode": "01:07:00 ~ 01:08:00", "text": "They sent him to Okinawa. The bloodiest battle in the Pacific."},
    {"filename": "CUT14_cut5_B", "timecode": "01:08:00 ~ 01:09:00", "text": "Soldiers climbed a 400-foot cliff straight into enemy fire. Bullets ripped through everything. Bodies dropped everywhere."},
    {"filename": "CUT15_cut6_A", "timecode": "01:32:30 ~ 01:33:30", "text": "Then the retreat was called. Every soldier ran for cover."},
    {"filename": "CUT16_cut6_B", "timecode": "01:33:30 ~ 01:34:30", "text": "But this medic ran the other way — straight into the fire."},
    {"filename": "CUT17_cut7_A", "timecode": "01:45:00 ~ 01:46:00", "text": "He grabbed the wounded one by one."},
    {"filename": "CUT18_cut7_B", "timecode": "01:46:00 ~ 01:48:00", "text": "He dragged them through mud and blood. He tied a rope around each body and lowered them off the cliff..."},
    {"filename": "CUT19_cut7_C", "timecode": "01:50:00 ~ 01:51:50", "text": "But he kept whispering the same prayer. Please Lord... let me get one more. Just one more."},
    {"filename": "CUT20_cut8_A", "timecode": "01:54:00 ~ 01:55:00", "text": "He did this for twelve straight hours. No sleep. No weapon. No help."},
    {"filename": "CUT21_cut8_B", "timecode": "02:01:00 ~ 02:02:00", "text": "Seventy-five men. All saved by one person who refused to kill."},
    {"filename": "CUT22_cta_A", "timecode": "02:09:00 ~ 02:10:00", "text": "The Army gave him the Medal of Honor..."},
    {"filename": "CUT23_cta_B", "timecode": "02:10:00 ~ 02:11:00", "text": "So, here's the question. Would you trust a man who refuses to carry a gun to save your life on the battlefield?"}
]

def generate_tts(text, voice_id, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": API_KEY.strip()
    }
    data = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        print(f"    FAIL ({response.status_code}): {response.text[:200]}")
        return 0
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path.stat().st_size / 1024

def main():
    print("=" * 65)
    print("TTS Generation (Hacksaw Ridge)")
    print("=" * 65)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_size = 0
    success = 0

    print(f"{'#':<4} {'Filename':<38} {'Size':>8}  Timecode")
    print("-" * 65)

    for i, cut in enumerate(CUTS, 1):
        filename = f"{cut['filename']}.mp3"
        output_path = OUTPUT_DIR / filename
        
        # Skip if already generated properly
        if output_path.exists() and output_path.stat().st_size > 0:
            size_kb = output_path.stat().st_size / 1024
            print(f"{i:>2}.  {filename:<38} {size_kb:>6.1f}KB  {cut['timecode']} (Cached)")
            total_size += size_kb
            success += 1
            continue

        size_kb = generate_tts(cut["text"], VOICE_ID, output_path)
        if size_kb > 0:
            total_size += size_kb
            success += 1
            print(f"{i:>2}.  {filename:<38} {size_kb:>6.1f}KB  {cut['timecode']}")
        else:
            print(f"{i:>2}.  {filename:<38}    FAIL    {cut['timecode']}")

    print("-" * 65)
    print(f"DONE: {success}/{len(CUTS)} files | Total {total_size:.1f}KB")
    print(f"Path: {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
