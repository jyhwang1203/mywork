import os
import sys
import requests
from pathlib import Path

# ============================================================
# ⚙️ 설정 — API 키를 여기에 직접 입력하세요
# ============================================================
API_KEY = "25753fc8a40398959d8709edc19fb73c95d26e7e7f9975e81969b37d8e5feae8"

# ============================================================
# 보이스 & 모델 설정
# ============================================================
VOICE_ID = "UH32V0B6SUKEpbb91TcE"  # Daniel — 중저음/SF/스릴러 최적
MODEL_ID = "eleven_multilingual_v2"

# 출력 경로 (원하시는 로컬 폴더 경로로 수정하세요)
OUTPUT_DIR = Path(r"C:\안티그래비티\쇼츠\컴패니언\tts")

# ============================================================
# 📜 컷별 대본 + 파라미터 세팅 (11컷, 12컷만 단독 생성)
# ============================================================
CUTS = [

    {
        "filename": "cut_12",
        "text": "She broke free from his control. A machine fighting for freedom... doesn't she seem more human than him?",
        "voice_settings": {
            "stability": 0.40,
            "similarity_boost": 0.75,
            "style": 0.35,
            "use_speaker_boost": True
        },
        "note": "Phase 3 - CTA. 질문을 던지듯 도발적이고 여운이 남게."
    }
]


def generate_tts(text, voice_id, voice_settings, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": API_KEY.strip()
    }
    data = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": voice_settings
    }

    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        print(f"    ❌ API 에러 ({response.status_code}): {response.text[:200]}")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path.stat().st_size / 1024


def main():
    print("=" * 70)
    print("🎬  Companion (2025) Shorts — TTS 자동 생성기 (11, 12컷)")
    print("=" * 70)

    if API_KEY == "여기에_API_키_입력" or len(API_KEY) < 10:
        print("\n❌ API 키가 설정되지 않았습니다! 코드 상단의 API_KEY 변수를 수정해주세요.")
        sys.exit(1)

    total_size = 0
    success = 0

    print(f"\n🎙️  Voice: Daniel ({VOICE_ID})")
    print("-" * 70)

    for i, cut in enumerate(CUTS, 1):
        filename = f"{cut['filename']}.mp3"
        output_path = OUTPUT_DIR / filename

        settings = cut["voice_settings"]
        style_pct = int(settings["style"] * 100)
        stab_pct = int(settings["stability"] * 100)

        size_kb = generate_tts(cut["text"], VOICE_ID, settings, output_path)

        if size_kb > 0:
            total_size += size_kb
            success += 1
            print(
                f"{i:>2}.  {filename:<20} Style:{style_pct:>2}%  Stab:{stab_pct:>2}% | {size_kb:>6.1f}KB | {cut['note']}")
        else:
            print(f"{i:>2}.  {filename:<20}                  ❌ 생성 실패")

    print("-" * 70)
    print(f"\n✅ 완료: {success}/{len(CUTS)}개 파일 생성 | 총 {total_size:.1f}KB")
    print(f"📂 파일 저장 위치: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()