import re
import requests

# ============================================================
# VOICE DESCRIPTION
# 목소리 스타일: 남성, 30대 중반, 미국 동부 억양
# 빠르고 긴박한 다큐멘터리 나레이터 톤.
# 문장 끝을 날카롭게 끊으며, 감탄과 충격을 짧게 강조.
# "70. You?" 같은 짧은 대사는 극도로 빠르고 건조하게.
# ============================================================

ELEVEN_LABS_API_KEY = "YOUR_API_KEY_HERE"
VOICE_ID = "YOUR_VOICE_ID_HERE"  # 예: Adam, Josh 등

# ── 원본 대본 ──────────────────────────────────────────────
RAW_SCRIPT = """
The Man walked into a startup at age 70, wearing a three-piece suit.
Ben Whittaker was retired. He'd traveled. He'd done yoga. But he felt a hole in his life.
Then he spotted a flyer: Seniors be an intern. He called his 9-year-old grandson just to figure out what a USB connector was.
Then applied anyway. He nailed the interview. You're an intern Ben. Congrats.
Day one, he showed up early. Full suit. Pocket square. Everyone stared.
Young interns checked their emails. Ben opened his: Your internship will be directly with Jules Ostin our founder.
The other intern looked over. Unfortunate. Hang in there.
Ben walked up to Jules' assistant. I'm Ben Whittaker. I have a 3:55 appointment.
She looked him up and down. I thought she was meeting her new intern. That's me.
Jules froze. Then laughed. How old are you? 70. You? I'm 24.
I know I look older. It's the job, ages you. Which won't be great in your case.
Jules was blunt: I'm not gonna have a lot for you to do. That's the truth.
Ben just smiled. He was already the best one there.
"""

# ── Speed Hack: 쉼표, 말줄임표 제거 ─────────────────────────
def preprocess_script(text: str) -> str:
    text = re.sub(r'\.{2,}', ' ', text)   # 말줄임표 제거
    text = re.sub(r',', '', text)           # 쉼표 제거
    text = re.sub(r'\s+', ' ', text)        # 다중 공백 정리
    return text.strip()

FINAL_SCRIPT = preprocess_script(RAW_SCRIPT)

print(f"[INFO] 전처리 완료 — 총 단어 수: {len(FINAL_SCRIPT.split())}개")
print(f"[SCRIPT PREVIEW]\n{FINAL_SCRIPT[:200]}...\n")

# ── ElevenLabs API 호출 ──────────────────────────────────────
def generate_tts(script: str, output_path: str = "intern_shorts_audio.mp3"):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

    headers = {
        "xi-api-key": ELEVEN_LABS_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2_5",   # ← 고속 모델 강제 적용
        "voice_settings": {
            "stability": 0.30,              # ← 낮을수록 더 다이나믹한 억양
            "similarity_boost": 0.75,
            "style": 0.0,                   # ← 스타일 오버라이드 최소화
            "use_speaker_boost": True
        }
    }

    print("[INFO] ElevenLabs API 요청 중...")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"[SUCCESS] 음성 저장 완료 → {output_path}")
    else:
        print(f"[ERROR] 상태 코드: {response.status_code}")
        print(response.text)

# ── 실행 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    generate_tts(FINAL_SCRIPT)