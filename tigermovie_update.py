import subprocess
import json
import os
import sys
import re
import tempfile
import shutil
from datetime import datetime

# ============================================================
# Tigermovie213 채널 쇼츠 정보 수집 (yt-dlp)
# ============================================================

CHANNELS = {
    "Tigermovie213": "https://www.youtube.com/@Tigermovie213/shorts",
}

BASE_DIR = r"g:\내 드라이브\antigravity\ㅁㄳㅊ"
os.makedirs(BASE_DIR, exist_ok=True)

YTDLP = [sys.executable, "-m", "yt_dlp"]

def get_video_list(channel_url, max_count=100):
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

def collect_channel(channel_name, channel_url, max_count=100):
    """채널 수집 메인"""
    print(f"\n{'='*60}")
    print(f"🎬 {channel_name} 채널 수집 시작 (최대 {max_count}개)")
    print(f"{'='*60}")
    
    video_list = get_video_list(channel_url, max_count)
    if not video_list:
        print("  ❌ 영상 없음")
        return []
    
    results = []
    total = len(video_list)
    
    for i, v in enumerate(video_list, 1):
        vid = v.get('id', v.get('url', ''))
        title = v.get('title', '제목없음')
        print(f"\n  [{i}/{total}] {title} (ID: {vid})")
        
        detail = get_video_detail(vid)
        
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
        
        print(f"    ✅ 조회수: {views:,}")
        
        results.append({
            "채널": channel_name,
            "동영상ID": vid,
            "제목": title,
            "설명": description,
            "업로드날짜": date_str,
            "조회수": views,
            "좋아요": likes,
            "댓글수": comments,
            "영상길이(초)": duration,
            "URL": f"https://youtube.com/shorts/{vid}"
        })
    
    return results

def main():
    all_data = {}
    for name, url in CHANNELS.items():
        data = collect_channel(name, url, max_count=100) # 최근 100개 정보 가져오기
        all_data[name] = data
        
        if data:
            out_path = os.path.join(BASE_DIR, f"{name}_latest_shorts.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  💾 저장: {out_path}")
            
            # Markdown 파일 생성
            md_path = os.path.join(BASE_DIR, "agent", "성과분석.md")
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(f"# 🐯 {name} 채널 최신 성과 분석\n")
                f.write(f"**업데이트 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # 정렬 (조회수 기준)
                sorted_by_views = sorted(data, key=lambda x: x['조회수'], reverse=True)
                
                f.write("## 🏆 Top 10 쇼츠 (조회수 순)\n")
                f.write("| 순위 | 제목 | 업로드날짜 | 조회수 | 좋아요 | URL |\n")
                f.write("|:-:|---|:-:|---:|---:|---|\n")
                for i, v in enumerate(sorted_by_views[:10], 1):
                    f.write(f"| {i} | {v['제목']} | {v['업로드날짜']} | {v['조회수']:,} | {v['좋아요']:,} | [링크]({v['URL']}) |\n")
                
                f.write("\n## 🆕 최근 업로드 10개 성과\n")
                sorted_by_date = sorted(filter(lambda x: x['업로드날짜'], data), key=lambda x: x['업로드날짜'], reverse=True)
                f.write("| 최근순 | 제목 | 업로드날짜 | 조회수 | URL |\n")
                f.write("|:-:|---|:-:|---:|---|\n")
                for i, v in enumerate(sorted_by_date[:10], 1):
                    f.write(f"| {i} | {v['제목']} | {v['업로드날짜']} | {v['조회수']:,} | [링크]({v['URL']}) |\n")
                
            print(f"  💾 저장: {md_path}")
            
if __name__ == "__main__":
    main()
