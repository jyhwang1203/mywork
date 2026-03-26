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

# 기본 제공 보이스 ID (이름 검색 없이 바로 사용)
# 아래에서 원하는 보이스의 주석을 해제하세요
VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"   # Josh — 따뜻한 남성 (추천, 진지한 나레이션에 적합)
# VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — 깊고 안정적 남성
# VOICE_ID = "ErXwobaYiN019PkySvjV"  # Antoni — 젊고 에너지 남성
# VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — 차분한 여성
# VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Bella — 부드러운 여성
# VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel — 영국식 남성

MODEL_ID = "eleven_multilingual_v2"

VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.75,
    "style": 0.35,
    "use_speaker_boost": True
}

OUTPUT_DIR = Path(r"C:\안티그래비티\파이썬\mywork\tts_output\hacksaw_ridge")

# ============================================================
# 📜 컷별 분할 대본 (타임코드 매칭)
# ============================================================

CUTS = [
    {
        "filename": "CUT01_hook_A",
        "timecode": "01:00:00 ~ 01:01:00",
        "description": "오프닝 훅 - 폭발음, 총성 빗발",
        "text": "Every soldier carried a rifle."
    },
    {
        "filename": "CUT02_hook_B",
        "timecode": "01:01:00 ~ 01:02:00",
        "description": "반전 훅 - 성경책 넘기는 소리",
        "text": "This man carried nothing but a Bible."
    },
    {
        "filename": "CUT03_cut1_A",
        "timecode": "00:02:30 ~ 00:03:15",
        "description": "소년 시절 - 형을 거의 죽일 뻔함",
        "text": "It started when he was just a kid. He nearly killed his own brother with a brick."
    },
    {
        "filename": "CUT04_cut1_B",
        "timecode": "00:03:15 ~ 00:04:00",
        "description": "맹세 - 다시는 사람을 해치지 않겠다",
        "text": "That moment changed him forever. He swore he would never hurt another person again."
    },
    {
        "filename": "CUT05_cut2_A",
        "timecode": "00:20:12 ~ 00:21:00",
        "description": "참전 결심",
        "text": "Then the war came. He volunteered to serve — but not as a fighter."
    },
    {
        "filename": "CUT06_cut2_B",
        "timecode": "00:21:00 ~ 00:22:00",
        "description": "의무병 지원",
        "text": "He wanted to be a medic."
    },
    {
        "filename": "CUT07_cut2_C",
        "timecode": "00:22:00 ~ 00:23:00",
        "description": "소총 거부",
        "text": "The Army gave him a rifle. He refused to touch it."
    },
    {
        "filename": "CUT08_cut3_A",
        "timecode": "00:33:00 ~ 00:34:30",
        "description": "구타",
        "text": "His squadmates called him a coward. They beat him every night."
    },
    {
        "filename": "CUT09_cut3_B",
        "timecode": "00:34:30 ~ 00:36:00",
        "description": "강제 퇴출 시도",
        "text": "They shoved his face into the pillow. They wanted him gone."
    },
    {
        "filename": "CUT10_cut4_A",
        "timecode": "00:45:00 ~ 00:48:00",
        "description": "군법회의",
        "text": "The Army dragged him to court. They charged him with disobedience..."
    },
    {
        "filename": "CUT11_cut4_B",
        "timecode": "00:48:00 ~ 00:52:00",
        "description": "아버지 등장",
        "text": "But then his father appeared. A broken war veteran..."
    },
    {
        "filename": "CUT12_cut4_C",
        "timecode": "00:52:00 ~ 00:55:00",
        "description": "법적 권리",
        "text": "He carried a single letter... It proved his son had every legal right to refuse."
    },
    {
        "filename": "CUT13_cut5_A",
        "timecode": "00:58:26 ~ 01:01:00",
        "description": "오키나와 도착",
        "text": "They sent him to Okinawa. The bloodiest battle in the Pacific."
    },
    {
        "filename": "CUT14_cut5_B",
        "timecode": "01:01:00 ~ 01:05:00",
        "description": "절벽 등반",
        "text": "Soldiers climbed a 400-foot cliff straight into enemy fire. Bullets ripped through everything. Bodies dropped everywhere."
    },
    {
        "filename": "CUT15_cut6_A",
        "timecode": "01:15:29 ~ 01:16:45",
        "description": "퇴각 명령",
        "text": "Then the retreat was called. Every soldier ran for cover."
    },
    {
        "filename": "CUT16_cut6_B",
        "timecode": "01:16:45 ~ 01:18:08",
        "description": "반대로 달리다",
        "text": "But this medic ran the other way — straight into the fire."
    },
    {
        "filename": "CUT17_cut7_A",
        "timecode": "01:24:25 ~ 01:28:00",
        "description": "부상병 끌기",
        "text": "He grabbed the wounded one by one."
    },
    {
        "filename": "CUT18_cut7_B",
        "timecode": "01:28:00 ~ 01:33:00",
        "description": "밧줄 하강",
        "text": "He dragged them through mud and blood. He tied a rope around each body and lowered them off the cliff..."
    },
    {
        "filename": "CUT19_cut7_C",
        "timecode": "01:33:00 ~ 01:36:00",
        "description": "기도 - 핵심 장면",
        "text": "But he kept whispering the same prayer. Please Lord... let me get one more. Just one more."
    },
    {
        "filename": "CUT20_cut8_A",
        "timecode": "01:40:00 ~ 01:42:30",
        "description": "12시간",
        "text": "He did this for twelve straight hours. No sleep. No weapon. No help."
    },
    {
        "filename": "CUT21_cut8_B",
        "timecode": "01:42:30 ~ 01:45:00",
        "description": "75명",
        "text": "Seventy-five men. All saved by one person who refused to kill."
    },
    {
        "filename": "CUT22_cta_A",
        "timecode": "02:10:00 ~ 02:12:30",
        "description": "훈장 수여",
        "text": "The Army gave him the Medal of Honor..."
    },
    {
        "filename": "CUT23_cta_B",
        "timecode": "02:12:30 ~ 02:15:00",
        "description": "마지막 질문",
        "text": "So, here's the question. Would you trust a man who refuses to carry a gun to save your life on the battlefield?"
    }
]

# ============================================================
# 🔧 TTS 생성 함수
# ============================================================

def generate_tts(text, voice_id, output_path):
    \"\"\"ElevenLabs TTS API 호출\"\"\"
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
        print(f"    ❌ API 에러 ({response.status_code}): {response.text[:200]}")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)

    size_kb = output_path.stat().st_size / 1024
    return size_kb

# ============================================================
# 🚀 메인
# ============================================================

def main():
    print("=" * 65)
    print("🎬  Hacksaw Ridge — 쇼츠 나레이션 TTS (컷별 분할)")
    print("=" * 65)

    # API 키 체크
    key = API_KEY.strip()
    if key == "여기에_API_키_입력" or len(key) < 10:
        print("\\n❌ API 키가 설정되지 않았습니다!")
        print("   스크립트 상단 API_KEY 변수에 키를 입력하세요.")
        print("   발급: https://elevenlabs.io → Profile → API Key")
        sys.exit(1)

    print(f"\\n🔑 API 키: {key[:8]}...{key[-4:]}")
    print(f"🎙️  보이스 ID: {VOICE_ID}")
    print(f"📁 출력 폴더: {OUTPUT_DIR.resolve()}\\n")

    # API 키 유효성 테스트
    print("🔍 API 키 확인 중...")
    test_resp = requests.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": key}
    )
    if test_resp.status_code != 200:
        print(f"❌ API 키 인증 실패 (상태: {test_resp.status_code})")
        print(f"   응답: {test_resp.text[:300]}")
        print("\\n확인사항:")
        print("  1. https://elevenlabs.io → Profile → API Key에서 키 재확인")
        print("  2. 키 앞뒤 공백이나 따옴표가 없는지 확인")
        print("  3. 무료 플랜이라도 키는 정상 작동해야 합니다")
        sys.exit(1)

    user_info = test_resp.json()
    tier = user_info.get("subscription", {}).get("tier", "unknown")
    char_limit = user_info.get("subscription", {}).get("character_limit", 0)
    char_used = user_info.get("subscription", {}).get("character_count", 0)
    char_remain = char_limit - char_used
    print(f"   ✅ 인증 성공! 플랜: {tier} | 남은 글자수: {char_remain:,}")

    # 전체 대본 글자수 계산
    total_chars = sum(len(c["text"]) for c in CUTS)
    print(f"   📝 대본 총 글자수: {total_chars:,}")
    if total_chars > char_remain:
        print(f"   ⚠️  글자수 부족! 필요: {total_chars:,} > 남은: {char_remain:,}")
        sys.exit(0)

    # 컷별 생성
    print("\\n" + "-" * 65)
    print(f"{'#':<4} {'파일명':<38} {'크기':>8}  타임코드")
    print("-" * 65)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_size = 0
    success = 0

    for i, cut in enumerate(CUTS, 1):
        filename = f"{cut['filename']}.mp3"
        output_path = OUTPUT_DIR / filename

        size_kb = generate_tts(cut["text"], VOICE_ID, output_path)

        if size_kb > 0:
            total_size += size_kb
            success += 1
            print(f"{i:>2}.  {filename:<38} {size_kb:>6.1f}KB  {cut['timecode']}")
        else:
            print(f"{i:>2}.  {filename:<38}    실패    {cut['timecode']}")

    # 결과 요약
    print("-" * 65)
    print(f"\\n✅ 완료: {success}/{len(CUTS)}개 생성 | 총 {total_size:.1f}KB")
    print(f"📂 위치: {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
