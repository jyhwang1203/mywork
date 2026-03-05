import subprocess
import json
import os
import sys
import re
import tempfile
import shutil
from datetime import datetime

# ============================================================
# 두 채널 쇼츠 대본 수집 (yt-dlp, 자동생성 자막 포함)
# ============================================================

CHANNELS = {
    "MushroomScreen": "https://www.youtube.com/@MushroomScreen-tl1rf/shorts",
    "CuriousPM90": "https://www.youtube.com/@CuriousPM90/shorts",
}

BASE_DIR = r"C:\python\데이터수집"
os.makedirs(BASE_DIR, exist_ok=True)

YTDLP = [sys.executable, "-m", "yt_dlp"]


def get_video_list(channel_url, max_count=30):
    """채널 쇼츠 영상 목록"""
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
        line = line.strip()
        if line:
            try:
                info = json.loads(line)
                video_list.append(info)
            except json.JSONDecodeError:
                pass
    
    print(f"  ✅ {len(video_list)}개 영상 발견")
    return video_list


def parse_vtt(vtt_content):
    """VTT 자막을 깨끗한 텍스트로 변환"""
    lines = vtt_content.split('\n')
    texts = []
    seen = set()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('WEBVTT'):
            continue
        if line.startswith('Kind:') or line.startswith('Language:') or line.startswith('NOTE'):
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


def get_subtitle_for_video(video_id):
    """개별 영상의 자동생성 자막 다운로드"""
    url = f"https://www.youtube.com/shorts/{video_id}"
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 자막만 다운로드 (영상 X)
        cmd = YTDLP + [
            "--skip-download",
            "--write-auto-sub",
            "--sub-lang", "en-orig,en,ko",
            "--sub-format", "vtt",
            "--no-warnings",
            "-o", os.path.join(temp_dir, "sub"),
            url
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
        
        # 다운로드된 VTT 파일 찾기
        subtitle_text = ""
        if os.path.exists(temp_dir):
            for fname in os.listdir(temp_dir):
                if fname.endswith('.vtt'):
                    fpath = os.path.join(temp_dir, fname)
                    with open(fpath, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    parsed = parse_vtt(raw)
                    if parsed and len(parsed) > len(subtitle_text):
                        subtitle_text = parsed
        
        return subtitle_text
        
    except Exception as e:
        return ""
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def get_video_detail(video_id):
    """영상 상세 정보 (JSON)"""
    url = f"https://www.youtube.com/shorts/{video_id}"
    cmd = YTDLP + [
        "--skip-download",
        "--dump-json",
        "--no-warnings",
        url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
        for line in result.stdout.splitlines():
            if line.strip():
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
    except:
        pass
    return None


def collect_channel(channel_name, channel_url, max_count=30):
    """채널 수집 메인"""
    print(f"\n{'='*60}")
    print(f"🎬 {channel_name} 채널 수집 시작")
    print(f"{'='*60}")
    
    video_list = get_video_list(channel_url, max_count)
    if not video_list:
        print("  ❌ 영상 없음")
        return []
    
    results = []
    scripts_found = 0
    total = len(video_list)
    
    for i, v in enumerate(video_list, 1):
        vid = v.get('id', v.get('url', ''))
        title = v.get('title', '제목없음')
        print(f"\n  [{i}/{total}] {title} (ID: {vid})")
        
        # 1) 상세 정보 가져오기
        detail = get_video_detail(vid)
        
        # 2) 자막 가져오기
        subtitle = get_subtitle_for_video(vid)
        
        if detail:
            views = detail.get('view_count', 0) or 0
            likes = detail.get('like_count', 0) or 0
            comments = detail.get('comment_count', 0) or 0
            duration = detail.get('duration', 0) or 0
            upload_date = detail.get('upload_date', '')
            description = detail.get('description', '')
            
            if upload_date and len(upload_date) == 8:
                date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            else:
                date_str = upload_date
        else:
            views = v.get('view_count', 0) or 0
            likes = 0
            comments = 0
            duration = v.get('duration', 0) or 0
            date_str = ''
            description = ''
        
        if subtitle:
            scripts_found += 1
            print(f"    ✅ 대본 O ({len(subtitle)}자) | 조회수: {views:,}")
            print(f"    📝 {subtitle[:100]}...")
        else:
            print(f"    ⚠️ 대본 X | 조회수: {views:,}")
        
        results.append({
            "채널": channel_name,
            "동영상ID": vid,
            "제목": detail.get('title', title) if detail else title,
            "설명": description,
            "대본": subtitle,
            "업로드날짜": date_str,
            "조회수": views,
            "좋아요": likes,
            "댓글수": comments,
            "영상길이(초)": duration,
            "URL": f"https://youtube.com/shorts/{vid}"
        })
    
    print(f"\n  📊 {channel_name}: 전체 {len(results)}개 중 대본 {scripts_found}개 성공")
    return results


def main():
    print("=" * 60)
    print(f" 🎯 2채널 쇼츠 대본 수집 (yt-dlp auto-sub)")
    print(f" 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    all_data = {}
    
    for name, url in CHANNELS.items():
        data = collect_channel(name, url, max_count=30)
        all_data[name] = data
        
        if data:
            out_path = os.path.join(BASE_DIR, f"{name}_shorts_v2.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  💾 저장: {out_path}")
    
    # 대본 있는 것만 모음
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
        scripts_path = os.path.join(BASE_DIR, "2채널_대본모음.json")
        with open(scripts_path, 'w', encoding='utf-8') as f:
            json.dump(scripts_only, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 대본 모음: {scripts_path} ({len(scripts_only)}개)")
    
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
            print(f"   대본 수집: {with_script}개 ({with_script/total*100:.0f}%)")
            if total > 0:
                avg_views = sum(e["조회수"] for e in entries) / total
                print(f"   평균 조회수: {int(avg_views):,}")
            print(f"   최고 영상: {top['제목']} ({top['조회수']:,}뷰)")
            
            scripted = sorted([e for e in entries if e.get("대본")], key=lambda x: x["조회수"], reverse=True)
            if scripted:
                print(f"\n   📝 대본 수집 TOP 3:")
                for j, s in enumerate(scripted[:3], 1):
                    print(f"   {j}. [{s['조회수']:,}뷰] {s['제목']}")
                    print(f"      {s['대본'][:150]}...")
    
    print(f"\n✅ 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
