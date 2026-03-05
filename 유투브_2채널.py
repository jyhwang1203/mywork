import re
import csv
import json
import os
import time
from datetime import datetime
import pytz
from urllib.parse import unquote
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)


class YouTubeShortCollector:
    def __init__(self, api_key):
        """YouTube Data API 클라이언트 초기화"""
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def extract_channel_id(self, channel_url):
        """채널 URL에서 채널 ID 추출"""
        channel_url = unquote(channel_url)
        patterns = [
            r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
            r'youtube\.com/@([^/?&\s]+)',
            r'youtube\.com/c/([^/?&\s]+)',
            r'youtube\.com/user/([^/?&\s]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, channel_url)
            if match:
                identifier = match.group(1)
                if '@' in channel_url or '/c/' in channel_url or '/user/' in channel_url:
                    return self.get_channel_id_from_handle(identifier)
                return identifier

        if channel_url.startswith('UC') and len(channel_url) == 24:
            return channel_url

        if channel_url.startswith('@'):
            return self.get_channel_id_from_handle(channel_url[1:])

        return self.get_channel_id_from_handle(channel_url)

    def get_channel_id_from_handle(self, handle):
        """핸들(@username) 또는 커스텀 URL에서 채널 ID 가져오기"""
        try:
            clean_handle = handle.lstrip('@')
            print(f"  '{clean_handle}' 채널 검색 중...")

            search_response = self.youtube.search().list(
                part='snippet',
                q=clean_handle,
                type='channel',
                maxResults=1
            ).execute()

            if search_response.get('items'):
                item = search_response['items'][0]
                print(f"  ✓ '{item['snippet']['channelTitle']}' 채널 찾음!")
                return item['snippet']['channelId']

            try:
                response = self.youtube.channels().list(
                    part='id',
                    forUsername=clean_handle
                ).execute()
                if response.get('items'):
                    return response['items'][0]['id']
            except:
                pass

        except HttpError as e:
            print(f"  API 오류: {e}")

        raise ValueError(f"채널을 찾을 수 없습니다: {handle}")

    def get_all_videos(self, channel_id, max_videos=None):
        """채널의 동영상 ID 가져오기"""
        channel_response = self.youtube.channels().list(
            part='contentDetails,snippet',
            id=channel_id
        ).execute()

        if not channel_response['items']:
            raise ValueError("채널을 찾을 수 없습니다.")

        channel_name = channel_response['items'][0]['snippet']['title']
        playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        videos = []
        next_page_token = None

        while True:
            playlist_response = self.youtube.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            videos.extend(playlist_response['items'])

            if max_videos and len(videos) >= max_videos:
                videos = videos[:max_videos]
                break

            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break

        return videos, channel_name

    def is_short(self, duration_str):
        """동영상이 쇼츠인지 확인 (60초 이하)"""
        try:
            duration = isodate.parse_duration(duration_str)
            return duration.total_seconds() <= 61
        except:
            return False

    def get_transcript(self, video_id):
        """동영상 자막(스크립트) 가져오기"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(['en', 'ko'])
            except:
                try:
                    transcript = transcript_list.find_generated_transcript(['en', 'ko'])
                except:
                    return ""

            transcript_text = ' '.join([entry['text'] for entry in transcript.fetch()])
            return transcript_text.strip()
        except:
            return ""

    def calculate_engagement_metrics(self, views, likes, comments):
        if views == 0:
            return {'좋아요율': 0.0, '댓글율': 0.0, '참여도': 0.0}

        like_rate = (likes / views) * 100
        comment_rate = (comments / views) * 100
        engagement_rate = ((likes + comments) / views) * 100

        return {
            '좋아요율': round(like_rate, 2),
            '댓글율': round(comment_rate, 2),
            '참여도': round(engagement_rate, 2)
        }

    def collect_shorts_data(self, channel_url, get_all_transcripts=False):
        channel_id = self.extract_channel_id(channel_url)
        print(f"채널 ID: {channel_id}")

        videos, channel_name = self.get_all_videos(channel_id)
        shorts_data = []

        video_ids = [v['contentDetails']['videoId'] for v in videos]
        chunks = [video_ids[i:i + 50] for i in range(0, len(video_ids), 50)]

        print(f"동영상 {len(video_ids)}개 확인 중...")

        for chunk in chunks:
            try:
                video_response = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(chunk)
                ).execute()

                for item in video_response['items']:
                    duration = item['contentDetails']['duration']
                    if self.is_short(duration):
                        stats = item['statistics']
                        snippet = item['snippet']

                        views = int(stats.get('viewCount', 0))
                        likes = int(stats.get('likeCount', 0))
                        comments = int(stats.get('commentCount', 0))
                        engagement = self.calculate_engagement_metrics(views, likes, comments)

                        published_at = snippet['publishedAt']
                        dt = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')
                        date_only = dt.strftime('%Y-%m-%d')

                        # 대본 수집: get_all_transcripts=True이면 모든 영상, 아니면 100만뷰 이상만
                        if get_all_transcripts:
                            transcript = self.get_transcript(item['id'])
                        else:
                            transcript = self.get_transcript(item['id']) if views >= 1000000 else ""

                        short_info = {
                            '동영상ID': item['id'],
                            '제목': snippet['title'],
                            '설명': snippet['description'],
                            '스크립트': transcript,
                            '업로드날짜': date_only,
                            '조회수': views,
                            '좋아요': likes,
                            '댓글수': comments,
                            '참여도(%)': engagement['참여도'],
                            '영상길이': duration,
                            'URL': f"https://youtube.com/shorts/{item['id']}"
                        }
                        shorts_data.append(short_info)
            except Exception as e:
                print(f"Error fetching video details: {e}")

        return shorts_data, channel_name

    def save_to_csv(self, data, filename):
        if not data: return

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"Saved {filename}")

    def save_to_json(self, data, filename):
        if not data: return

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved {filename}")


def main():
    API_KEY = "AIzaSyDS9QZILQ6wR3hpJ1hm9IWRJMPn1ebPmr4"

    # 요청된 두 채널만
    CHANNELS = {
        "MushroomScreen": "https://www.youtube.com/@MushroomScreen-tl1rf",
        "CuriousPM90": "https://www.youtube.com/@CuriousPM90",
    }

    base_dir = r"C:\python\데이터수집"
    collector = YouTubeShortCollector(API_KEY)

    summary_report = []
    all_scripts = {}

    print("=" * 50)
    print(" 2채널 쇼츠 대본 수집 시작")
    print("=" * 50)

    for name, url in CHANNELS.items():
        print(f"\n{'='*40}")
        print(f"Processing {name}...")
        print(f"{'='*40}")
        try:
            # get_all_transcripts=True로 모든 쇼츠 대본 수집
            data, channel_true_name = collector.collect_shorts_data(url, get_all_transcripts=True)

            if data:
                # CSV 저장
                csv_filename = os.path.join(base_dir, f"{name}_shorts.csv")
                collector.save_to_csv(data, csv_filename)

                # JSON 저장
                json_filename = os.path.join(base_dir, f"{name}_shorts.json")
                collector.save_to_json(data, json_filename)

                avg_views = sum(d['조회수'] for d in data) / len(data)

                # 대본이 있는 영상만 모음
                scripts_found = [d for d in data if d['스크립트']]

                summary_report.append({
                    "Channel": name,
                    "ChannelName": channel_true_name,
                    "TotalShorts": len(data),
                    "ScriptsFound": len(scripts_found),
                    "AvgViews": int(avg_views),
                    "BestVideo": max(data, key=lambda x: x['조회수'])['제목'],
                    "BestViews": max(data, key=lambda x: x['조회수'])['조회수']
                })

                all_scripts[name] = scripts_found

                # 대본 있는 영상 출력
                print(f"\n📝 {name} - 대본이 있는 영상: {len(scripts_found)}개 / 전체 쇼츠: {len(data)}개")
                for i, s in enumerate(scripts_found[:5], 1):  # 상위 5개만 미리보기
                    print(f"\n  [{i}] {s['제목']}")
                    print(f"      조회수: {s['조회수']:,} | 좋아요: {s['좋아요']:,}")
                    print(f"      대본: {s['스크립트'][:100]}...")

            else:
                print(f"No shorts found for {name}")

        except Exception as e:
            print(f"Failed to process {name}: {e}")
            import traceback
            traceback.print_exc()

    # 최종 요약
    print("\n" + "=" * 60)
    print(" 📊 최종 요약 리포트")
    print("=" * 60)
    for item in summary_report:
        print(f"\n🎬 {item['Channel']} ({item['ChannelName']})")
        print(f"   전체 쇼츠: {item['TotalShorts']}개")
        print(f"   대본 수집: {item['ScriptsFound']}개")
        print(f"   평균 조회수: {item['AvgViews']:,}")
        print(f"   최고 영상: {item['BestVideo']} ({item['BestViews']:,}뷰)")
        print("-" * 40)

    # 전체 대본 JSON으로도 저장
    scripts_output = os.path.join(base_dir, "2채널_대본모음.json")
    all_script_data = []
    for channel, scripts in all_scripts.items():
        for s in scripts:
            all_script_data.append({
                "채널": channel,
                "제목": s['제목'],
                "조회수": s['조회수'],
                "대본": s['스크립트'],
                "URL": s['URL']
            })

    if all_script_data:
        with open(scripts_output, 'w', encoding='utf-8') as f:
            json.dump(all_script_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 전체 대본 파일 저장: {scripts_output}")


if __name__ == "__main__":
    main()
