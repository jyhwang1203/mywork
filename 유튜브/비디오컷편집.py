"""
AIR (2023) 쇼츠 v2 대본 — 원본 영상 컷 추출 스크립트 (MoviePy)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
프레임 단위 정밀 컷 — 재인코딩 포함

설치: pip install moviepy
사용법: python air_cuts_moviepy.py
"""

from moviepy.editor import VideoFileClip
import os
import sys
import time

# ═══════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════
SOURCE = r"C:\안티그래비티\쇼츠\AIR\Air.2023.mp4"
OUTPUT_DIR = r"C:\안티그래비티\쇼츠\AIR\cuts"
BUFFER = 1.0  # 컷당 앞뒤 여유 (초)

# ═══════════════════════════════════════════════════
# 컷 리스트 (v2 대본 기준)
# ═══════════════════════════════════════════════════
# 형식: (파일명, 시작, 종료, 타입, 설명)
# 타입: D=실제대사(오디오 포함), N=나레이션용 영상(TTS 덮어씌울 장면)

CUTS = [
    # ── CUT 01 (00:00~00:03) Phase 1 HOOK ──
    # N: "This man bet his entire career on one rookie..."
    ("cut_01_N_hook",
     "00:30:42", "00:30:50", "N",
     "소니 열변 — 테이블 치며 주장하는 장면"),

    # ── CUT 02 (00:03~00:08) ──
    # D: "Our basketball division is fucking terrible."
    ("cut_02a_D_terrible",
     "00:26:17", "00:26:26", "D",
     "소니 '우리 농구 부서는 개판' 대사"),
    # N: 나이키 본사 + 예산 논의 장면
    ("cut_02b_N_budget",
     "00:14:47", "00:15:00", "N",
     "본사 건물 외관 + 전략회의 '예산 25만' 장면"),
    # N: 추가 — "9억 벌면서 농구에 25만" 대비 장면
    ("cut_02c_N_900m",
     "00:15:31", "00:15:40", "N",
     "'9억 벌었는데 농구에 25만' 소니 항의"),

    # ── CUT 03 (00:08~00:13) ──
    # D: "You ask me what I do here — this is what I do..."
    ("cut_03_D_bet_career",
     "00:30:47", "00:31:04", "D",
     "소니 '경력을 걸겠습니다 + 느낌이 와요' 열변"),

    # ── CUT 04 (00:13~00:19) ──
    # N: 소니-롭 회의, 반대하는 동료들
    ("cut_04a_N_opposition",
     "00:25:41", "00:25:56", "N",
     "소니 제안에 반대하는 동료들 반응"),
    # N: 추가 — "한 명에게 전체 예산?" "매직 존슨도 자기 신발 없어"
    ("cut_04b_N_magic",
     "00:29:55", "00:30:05", "N",
     "'죽어도 안 돼' + '매직 존슨도 자기 신발 없어'"),

    # ── CUT 05 (00:19~00:23) ──
    # D: "He doesn't wear the shoe. He IS the shoe."
    ("cut_05_D_is_the_shoe",
     "00:25:21", "00:25:30", "D",
     "'그가 곧 신발이다' 핵심 컨셉 선언"),

    # ── CUT 06 (00:23~00:29) ──
    # N: 소니 차 운전 — 노스캐롤라이나 이동
    ("cut_06a_N_drive",
     "00:39:53", "00:40:02", "N",
     "소니 무단 출장 — 노스캐롤라이나 이동"),
    # D: 롭 전화 "대체 어디야?" "노스캐롤라이나"
    ("cut_06b_D_where",
     "00:39:54", "00:40:12", "D",
     "'어디야?' '노스캐롤라이나' — 무단 방문 발각"),
    # D: "I believe in your son. I believe he's different..."
    ("cut_06c_D_believe",
     "00:46:18", "00:46:37", "D",
     "델로리스에게 '아드님을 믿습니다' 고백"),

    # ── CUT 07 (00:29~00:34) ──
    # N: 에이전트 전화 발견
    ("cut_07a_N_agent_intro",
     "00:46:51", "00:46:57", "N",
     "포크 전화 시작 — 뻔뻔하기도 하지"),
    # D: "I will bury you alive, and light you on fire..."
    ("cut_07b_D_bury_alive",
     "00:47:44", "00:47:57", "D",
     "포크 폭주 — '산 채로 묻고 불태울 거야'"),
    # D: "herpes simplex 2 motherfucker!"
    ("cut_07c_D_herpes",
     "00:47:58", "00:48:10", "D",
     "포크 폭주 연장 — 헤르페스 욕설 장면"),
    # D: "Monday. Michael's coming to Nike."
    ("cut_07d_D_monday",
     "00:49:10", "00:49:36", "D",
     "'월요일이야. 마이클이 나이키에 간다' 반전"),

    # ── CUT 08 (00:34~00:40) ──
    # N: 조던 가족 나이키 본사 도착
    ("cut_08a_N_arrival",
     "01:11:21", "01:11:32", "N",
     "조던 가족 본사 도착 장면"),
    # D: "마이클은 싫어해. 엄마 때문이야"
    ("cut_08b_D_forced",
     "00:49:24", "00:49:30", "D",
     "'흥분하지 마. 마이클은 싫어해. 엄마 때문이야'"),
    # N: 프레젠테이션 도입
    ("cut_08c_N_presentation",
     "01:15:50", "01:16:07", "N",
     "소니 프레젠테이션 시작 — 신발 공개"),

    # ── CUT 09 (00:40~00:46) ──
    # D: "Money can buy you almost anything. It can't buy you immortality."
    ("cut_09a_D_immortality",
     "01:19:15", "01:19:34", "D",
     "소니 연설 클라이맥스 — '불멸은 못 사요'"),
    # D: "You're going to change the fucking world."
    ("cut_09b_D_change_world",
     "01:19:00", "01:19:15", "D",
     "'세상을 바꿀 거예요' — 미래 예언 연설"),

    # ── CUT 10 (00:46~00:50) ──
    # D: "A shoe is just a shoe until somebody steps into it."
    ("cut_10a_D_shoe",
     "01:19:33", "01:19:44", "D",
     "'신발은 그냥 신발' 명대사"),
    # D: "Everyone at this table will be forgotten... except for you."
    ("cut_10b_D_forgotten",
     "01:19:52", "01:20:05", "D",
     "'여기 있는 사람들은 잊힐 거예요. 당신만 빼고.'"),

    # ── CUT 11 (00:50~00:54) ──
    # N: 델로리스 수익배분 요구
    ("cut_11a_N_revenue_demand",
     "01:27:17", "01:27:34", "N",
     "델로리스 '수익 일정 비율' 요구 장면"),
    # D: 소니 "업계가 그렇지 않아요" 당황
    ("cut_11b_D_shocked",
     "01:27:37", "01:27:59", "D",
     "소니+롭 당황 — '업계에서 난리가 날 거예요'"),
    # D: CEO "You are remembered for the rules you break."
    ("cut_11c_D_rules_break",
     "01:33:09", "01:33:46", "D",
     "필 나이트 '제길 그렇게 해' + '규칙을 깬 사람만 기억된다'"),

    # ── CUT 12 (00:54~01:00) Phase 3 CTA ──
    # D: "We just signed Michael Jordan!"
    ("cut_12a_D_signed",
     "01:36:05", "01:36:20", "D",
     "'마이클 조던과 계약했어요!' 환호 장면"),
    # N: 에어 조던 첫해 매출 자막
    ("cut_12b_N_162m",
     "01:41:19", "01:41:28", "N",
     "'첫해 1억6200만 달러' 자막 장면"),
    # N: 연 매출 40억 자막
    ("cut_12c_N_4billion",
     "01:43:08", "01:43:14", "N",
     "'에어 조던 연 매출 40억 달러' 자막"),
    # N: 조던 연 수입 4억 자막
    ("cut_12d_N_400m_royalty",
     "01:43:48", "01:43:59", "N",
     "'매년 4억 달러 로열티' 자막 + CTA용 마무리"),
]


def time_to_seconds(t: str) -> float:
    """HH:MM:SS → 초 변환"""
    parts = t.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(t)


def main():
    # ── 사전 체크 ──
    if not os.path.isfile(SOURCE):
        print(f"[ERROR] 원본 파일을 찾을 수 없습니다:\n  {SOURCE}")
        print("  경로를 확인해 주세요.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"{'='*60}")
    print(f"  AIR (2023) 쇼츠 v2 — MoviePy 컷 추출")
    print(f"  원본: {SOURCE}")
    print(f"  출력: {OUTPUT_DIR}")
    print(f"  버퍼: ±{BUFFER}초")
    print(f"  총 클립: {len(CUTS)}개")
    print(f"{'='*60}\n")

    # ── 원본 영상 로드 (한 번만) ──
    print("  ⏳ 원본 영상 로딩 중... (최초 1회만 소요)")
    load_start = time.time()
    video = VideoFileClip(SOURCE)
    load_time = time.time() - load_start
    print(f"  ✅ 로딩 완료 ({load_time:.1f}초)")
    print(f"  📐 해상도: {video.size[0]}x{video.size[1]}")
    print(f"  ⏱️  전체 길이: {video.duration:.1f}초 ({int(video.duration//60)}분 {int(video.duration%60)}초)")
    print(f"  🎞️  FPS: {video.fps}")
    print()

    success = 0
    failed = 0
    total_start = time.time()

    for i, (name, start_str, end_str, clip_type, desc) in enumerate(CUTS, 1):
        out_path = os.path.join(OUTPUT_DIR, f"{name}.mp4")
        type_label = "🎬 D(실제대사)" if clip_type == "D" else "🖼️  N(나레이션용)"

        # 버퍼 적용
        t_start = max(0, time_to_seconds(start_str) - BUFFER)
        t_end = min(video.duration, time_to_seconds(end_str) + BUFFER)

        print(f"[{i:02d}/{len(CUTS)}] {type_label}  {name}")
        print(f"         원본: {start_str} ~ {end_str}")
        print(f"         버퍼: {t_start:.1f}s ~ {t_end:.1f}s  ({t_end - t_start:.1f}초)")
        print(f"         📝 {desc}")

        try:
            clip_start = time.time()

            # ── 프레임 정밀 서브클립 ──
            sub = video.subclip(t_start, t_end)

            # ── 내보내기 ──
            sub.write_videofile(
                out_path,
                codec="libx264",
                audio_codec="aac",
                preset="fast",         # 속도 우선 (ultrafast → fast 균형)
                threads=4,
                logger=None,           # 진행 로그 숨김
                bitrate="5000k",       # 원본에 가까운 품질
                audio_bitrate="192k",
            )
            sub.close()

            clip_time = time.time() - clip_start
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"         ✅ 완료 ({size_mb:.1f} MB, {clip_time:.1f}초)")
            success += 1

        except Exception as e:
            print(f"         ❌ 오류: {e}")
            failed += 1

        print()

    # ── 정리 ──
    video.close()
    total_time = time.time() - total_start

    # ── 결과 요약 ──
    print(f"{'='*60}")
    print(f"  추출 완료: ✅ {success}개  ❌ {failed}개")
    print(f"  총 소요 시간: {total_time:.0f}초 ({total_time/60:.1f}분)")
    print(f"{'='*60}\n")

    # ── 프리미어 배치 가이드 ──
    print("📋 프리미어 프로 배치 순서:")
    print("─" * 60)

    cut_groups = {}
    for name, start, end, clip_type, desc in CUTS:
        cut_num = name.split("_")[1]
        base_num = ''.join(filter(str.isdigit, cut_num))
        if base_num not in cut_groups:
            cut_groups[base_num] = []
        cut_groups[base_num].append((name, clip_type, desc))

    for cut_num in sorted(cut_groups.keys(), key=int):
        clips = cut_groups[cut_num]
        print(f"\n  ▶ CUT {cut_num}")
        for name, clip_type, desc in clips:
            t = "D" if clip_type == "D" else "N"
            print(f"    [{t}] {name}.mp4  — {desc}")

    print(f"\n{'='*60}")
    print("  D 클립 = 원본 오디오 사용 (V1+A1에 배치)")
    print("  N 클립 = 영상만 사용 (V1), TTS mp3는 A2에 배치")
    print(f"{'='*60}")
    print()
    print("  💡 TIP: N 클립은 프리미어에서 '링크 해제' 후")
    print("         원본 오디오(A1) 삭제 → TTS mp3를 A2에 드래그")
    print()


if __name__ == "__main__":
    main()