import subprocess
import json
import os
import sys
import re
import tempfile
import shutil
from datetime import datetime

# ============================================================
# 두 채널 쇼츠 대본 수집 스크립트 (yt-dlp 기반)
# ============================================================

CHANNELS = {
    "MushroomScreen": "https://www.youtube.com/@MushroomScreen-tl1rf/shorts",
    "CuriousPM90": "https://www.youtube.com/@CuriousPM90/shorts",
}

BASE_DIR = r"C:\python\데이터수집"
os.makedirs(BASE_DIR, exist_ok=True)

YTDLP = [sys.executable, "-m", "yt_dlp"]


def get_video_list(channel_url, max_count=50):
    """채널의 쇼츠 영상 목록 가져오기 (flat-playlist)"""
    print(f"\n📋 영상 목록 수집 중: {channel_url}")
    
    cmd = YTDLP + [
        "--skip-download",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", str(max_count),
        channel_url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    
    video_list = []
    for line in result.stdout.splitlines():
        if line.strip():
            try:
                info = json.loads(line)
                video_list.append(info)
            except json.JSONDecodeError as e:
                pass
    
    print(f"  ✅ {len(video_list)}개 영상 발견")
    return video_list


def get_video_detail_with_subs(video_id):
    """개별 영상의 상세 정보 + 자막 가져오기"""
    url = f"https://www.youtube.com/shorts/{video_id}"
    
    # 임시 디렉토리에서 자막 파일 다운로드
    temp_dir = tempfile.mkdtemp()
    sub_file_pattern = os.path.join(temp_dir, "%(id)s")
    
    cmd = YTDLP + [
        "--skip-download",
        "--dump-json",
        "--write-auto-sub",        # 자동 생성 자막 다운로드
        "--write-sub",             # 수동 자막도 시도
        "--sub-lang", "en,ko",     # 영어, 한국어 자막
        "--sub-format", "vtt",     # VTT 포맷
        "-o", sub_file_pattern,
        url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    
    video_info = None
    subtitle_text = ""
    
    # JSON 파싱
    for line in result.stdout.splitlines():
        if line.strip():
            try:
                video_info = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    
    # 자막 파일 읽기
    if os.path.exists(temp_dir):
        for fname in os.listdir(temp_dir):
            if fname.endswith('.vtt'):
                fpath = os.path.join(temp_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    subtitle_text = parse_vtt(raw)
                    if subtitle_text:
                        break
                except:
                    pass
        
        # 임시 디렉토리 정리
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
    
    return video_info, subtitle_text


def parse_vtt(vtt_content):
    """VTT 자막 파일을 텍스트로 변환 (중복 제거)"""
    lines = vtt_content.split('\n')
    texts = []
    seen = set()
    
    for line in lines:
        line = line.strip()
        # 타임스탬프, 헤더, 빈줄 건너뛰기
        if not line:
            continue
        if line.startswith('WEBVTT'):
            continue
        if line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if '-->' in line:
            continue
        if re.match(r'^\d+$', line):
            continue
        
        # HTML 태그 제거
        clean = re.sub(r'<[^>]+>', '', line)
        clean = clean.strip()
        
        if clean and clean not in seen:
            seen.add(clean)
            texts.append(clean)
    
    return ' '.join(texts)


def collect_channel_shorts(channel_name, channel_url, max_count=50):
    """채널의 쇼츠 영상 + 대본 수집"""
    print(f"\n{'='*60}")
    print(f"🎬 {channel_name} 채널 수집 시작")
    print(f"{'='*60}")
    
    # Step 1: 영상 목록 가져오기
    video_list = get_video_list(channel_url, max_count=max_count)
    
    if not video_list:
        print(f"  ❌ 영상을 찾을 수 없습니다.")
        return []
    
    # Step 2: 각 영상의 상세 정보 + 자막 가져오기
    shorts_data = []
    total = len(video_list)
    scripts_found = 0
    
    for i, v in enumerate(video_list, 1):
        vid = v.get('id', v.get('url', ''))
        title = v.get('title', '제목없음')
        
        print(f"\n  [{i}/{total}] {title}")
        print(f"    ID: {vid}")
        
        try:
            detail, subtitle = get_video_detail_with_subs(vid)
            
            if detail:
                views = detail.get('view_count', 0) or 0
                likes = detail.get('like_count', 0) or 0
                comments = detail.get('comment_count', 0) or 0
                duration = detail.get('duration', 0) or 0
                upload_date = detail.get('upload_date', '')
                description = detail.get('description', '')
                
                # 날짜 포맷
                if upload_date and len(upload_date) == 8:
                    date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
                else:
                    date_str = upload_date
                
                if subtitle:
                    scripts_found += 1
                    print(f"    ✅ 대본 수집 성공! ({len(subtitle)}자)")
                    print(f"    📝 미리보기: {subtitle[:80]}...")
                else:
                    print(f"    ⚠️ 대본 없음 (조회수: {views:,})")
                
                entry = {
                    "채널": channel_name,
                    "동영상ID": vid,
                    "제목": detail.get('title', title),
                    "설명": description,
                    "대본": subtitle,
                    "업로드날짜": date_str,
                    "조회수": views,
                    "좋아요": likes,
                    "댓글수": comments,
                    "영상길이(초)": duration,
                    "URL": f"https://youtube.com/shorts/{vid}"
                }
                shorts_data.append(entry)
            else:
                print(f"    ❌ 상세 정보 가져오기 실패")
                
        except Exception as e:
            print(f"    ❌ 오류: {e}")
    
    print(f"\n  📊 {channel_name} 결과: 전체 {len(shorts_data)}개 중 대본 {scripts_found}개 수집")
    return shorts_data


def main():
    print("=" * 60)
    print(f" 🎯 2채널 쇼츠 대본 수집 (yt-dlp)")
    print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    all_data = {}
    
    for name, url in CHANNELS.items():
        data = collect_channel_shorts(name, url, max_count=30)
        all_data[name] = data
        
        # 채널별 JSON 저장
        if data:
            out_path = os.path.join(BASE_DIR, f"{name}_shorts_ytdlp.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  💾 저장 완료: {out_path}")
    
    # 대본이 있는 것만 모아서 저장
    scripts_only = []
    for channel, entries in all_data.items():
        for e in entries:
            if e.get("대본"):
                scripts_only.append({
                    "채널": e["채널"],
                    "제목": e["제목"],
                    "조회수": e["조회수"],
                    "대본": e["대본"],
                    "URL": e["URL"],
                    "업로드날짜": e["업로드날짜"]
                })
    
    if scripts_only:
        scripts_path = os.path.join(BASE_DIR, "2채널_대본모음_ytdlp.json")
        with open(scripts_path, 'w', encoding='utf-8') as f:
            json.dump(scripts_only, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 대본 모음 저장: {scripts_path} ({len(scripts_only)}개)")
    
    # 최종 요약
    print("\n" + "=" * 60)
    print(" 📊 최종 요약")
    print("=" * 60)
    for channel, entries in all_data.items():
        total = len(entries)
        with_script = sum(1 for e in entries if e.get("대본"))
        if total > 0:
            top = max(entries, key=lambda x: x["조회수"])
            print(f"\n🎬 {channel}")
            print(f"   전체 쇼츠: {total}개")
            print(f"   대본 수집: {with_script}개")
            print(f"   최고 영상: {top['제목']} ({top['조회수']:,}뷰)")
            
            # 대본이 있는 상위 3개 표시
            scripted = [e for e in entries if e.get("대본")]
            scripted.sort(key=lambda x: x["조회수"], reverse=True)
            if scripted:
                print(f"\n   📝 대본 샘플 (상위 3개):")
                for s in scripted[:3]:
                    print(f"   ▸ [{s['조회수']:,}뷰] {s['제목']}")
                    print(f"     {s['대본'][:120]}...")
    
    print(f"\n✅ 완료! 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
