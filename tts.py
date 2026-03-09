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
#VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"   # Josh — 따뜻한 남성 (추천)
# VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — 깊고 안정적 남성
# VOICE_ID = "ErXwobaYiN019PkySvjV"  # Antoni — 젊고 에너지 남성
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — 차분한 여성
# VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Bella — 부드러운 여성
# VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel — 영국식 남성

MODEL_ID = "eleven_multilingual_v2"

VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.75,
    "style": 0.35,
    "use_speaker_boost": True
}

OUTPUT_DIR = Path("./tts_output")

# ============================================================
# 📜 컷별 분할 대본 (타임코드 매칭)
# ============================================================

CUTS = [
    {
        "filename": "CUT01_hook_00m13s",
        "timecode": "00:13:39 ~ 00:13:45",
        "description": "회사 소개 — 부엌에서 시작, 18개월 만에 220명",
        "text": "The woman started a fashion company from her kitchen. In just 18 months, it blew up to 220 employees."
    },
    {
        "filename": "CUT02_unstoppable_00m13s",
        "timecode": "00:13:16 ~ 00:13:24",
        "description": "줄스의 열정 — 자전거, 박스포장, 야근",
        "text": "She was unstoppable. She packed boxes herself. She stayed late with her team. She even rode a bike through the office to check on every department."
    },
    {
        "filename": "CUT03_investors_00m24s",
        "timecode": "00:24:52 ~ 00:25:12",
        "description": "투자자 압박 — 외부 CEO 영입 요구",
        "text": "But the investors weren't impressed. They told her she couldn't handle it alone. They wanted to bring in a new CEO. Someone above her. In her own company."
    },
    {
        "filename": "CUT04_refused_00m24s",
        "timecode": "00:24:46 ~ 00:25:19",
        "description": "줄스 거부 → 집안 문제 시작",
        "text": "At first, she refused. But then things got worse at home."
    },
    {
        "filename": "CUT05_husband_00m44s",
        "timecode": "00:44:01 ~ 00:44:18",
        "description": "남편 소개 — 커리어 포기, 전업주부",
        "text": "Her husband had quit his career to raise their daughter. And slowly, the marriage started falling apart."
    },
    {
        "filename": "CUT06_overwork_01m01s",
        "timecode": "01:01:59 ~ 01:02:05",
        "description": "줄스 과로 — 가정 소홀",
        "text": "The woman worked 18-hour days. She barely saw her kid."
    },
    {
        "filename": "CUT07_affair_seen_01m22s",
        "timecode": "01:22:35 ~ 01:25:30",
        "description": "벤이 파티에서 딸 데려다주다 외도 목격",
        "text": "Then one night, the old man, her 70-year-old intern, saw something while driving her daughter home. The husband was kissing another woman."
    },
    {
        "filename": "CUT08_silence_01m36s",
        "timecode": "01:36:39 ~ 01:37:01",
        "description": "벤의 딜레마 — 말할까 말까",
        "text": "The old man didn't know what to do. Should he tell her? He stayed quiet."
    },
    {
        "filename": "CUT09_twist_01m36s",
        "timecode": "01:36:39 ~ 01:37:22",
        "description": "반전 — 줄스는 이미 알고 있었다",
        "text": "But here's the twist. The woman already knew. She knew her husband was cheating. And that's exactly why she decided to give up her company."
    },
    {
        "filename": "CUT10_sacrifice_01m38s",
        "timecode": "01:38:48 ~ 01:39:44",
        "description": "줄스의 희생 — 결혼 구하려 CEO 자리 포기 결심",
        "text": "She thought if she stepped down, she could spend more time at home. Fix the marriage. Save the family."
    },
    {
        "filename": "CUT11_sf_trip_01m43s",
        "timecode": "01:43:26 ~ 01:44:12",
        "description": "샌프란시스코 출장 — 새 CEO 채용",
        "text": "So she flew to San Francisco and picked a new CEO to replace herself."
    },
    {
        "filename": "CUT12_husband_confess_01m52s",
        "timecode": "01:52:02 ~ 01:53:34",
        "description": "남편 사무실 방문 — 외도 고백, 꿈 포기하지 말라",
        "text": "But the husband found out. He walked into her office, confessed everything, and begged her. Don't give up your dream because of me."
    },
    {
        "filename": "CUT13_ending_01m54s",
        "timecode": "01:54:21 ~ 01:55:53",
        "description": "결말 — CEO 영입 취소, 벤을 찾아감",
        "text": "In the end, she canceled the deal. She kept her company. And the first person she wanted to tell was not her husband. It was the 70-year-old intern."
    },
    {
        "filename": "CUT14_cta",
        "timecode": "—",
        "description": "CTA — 논쟁 질문",
        "text": "So, here's the question. Would you give up your dream to save a marriage that was already broken?"
    }
]

# ============================================================
# 🔧 TTS 생성 함수
# ============================================================

def generate_tts(text, voice_id, output_path):
    """ElevenLabs TTS API 호출"""
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
    print("🎬  The Intern — 쇼츠 나레이션 TTS (컷별 분할)")
    print("=" * 65)

    # API 키 체크
    key = API_KEY.strip()
    if key == "여기에_API_키_입력" or len(key) < 10:
        print("\n❌ API 키가 설정되지 않았습니다!")
        print("   스크립트 상단 API_KEY 변수에 키를 입력하세요.")
        print("   발급: https://elevenlabs.io → Profile → API Key")
        sys.exit(1)

    print(f"\n🔑 API 키: {key[:8]}...{key[-4:]}")
    print(f"🎙️  보이스 ID: {VOICE_ID}")
    print(f"📁 출력 폴더: {OUTPUT_DIR.resolve()}\n")

    # API 키 유효성 테스트
    print("🔍 API 키 확인 중...")
    test_resp = requests.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": key}
    )
    if test_resp.status_code != 200:
        print(f"❌ API 키 인증 실패 (상태: {test_resp.status_code})")
        print(f"   응답: {test_resp.text[:300]}")
        print("\n확인사항:")
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
        cont = input("   계속하시겠습니까? (y/n): ").strip().lower()
        if cont != "y":
            sys.exit(0)

    # 컷별 생성
    print("\n" + "-" * 65)
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
    print(f"\n✅ 완료: {success}/{len(CUTS)}개 생성 | 총 {total_size:.1f}KB")
    print(f"📂 위치: {OUTPUT_DIR.resolve()}")

    # 편집 가이드
    print("\n" + "=" * 65)
    print("📋 편집 가이드 (타임코드 → 컷 매칭)")
    print("=" * 65)
    for i, cut in enumerate(CUTS, 1):
        print(f"  CUT {i:>2} | {cut['timecode']:<25} | {cut['description']}")

    print("""
💡 편집 팁:
  1. 프리미어/캡컷에서 영화 영상을 타임코드 순서대로 컷
  2. 각 CUT 음성 파일을 해당 영상 클립 위에 배치
  3. 음성 길이에 맞춰 영상 속도 조절 (1.0x ~ 1.3x)
  4. CUT14 (CTA)는 마지막에 자막 + 음성 오버레이
  5. BGM은 -15dB ~ -20dB로 깔아주기
""")

if __name__ == "__main__":
    main()