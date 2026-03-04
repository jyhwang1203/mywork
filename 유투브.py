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

        # If it's just the handle name without @, try adding @
        return self.get_channel_id_from_handle(channel_url)

    def get_channel_id_from_handle(self, handle):
        """핸들(@username) 또는 커스텀 URL에서 채널 ID 가져오기"""
        try:
            clean_handle = handle.lstrip('@')
            print(f"  '{clean_handle}' 채널 검색 중...")

            # 방법 1: Search API
            search_response = self.youtube.search().list(
                part='snippet',
                q=clean_handle,
                type='channel',
                maxResults=1
            ).execute()

            if search_response.get('items'):
                # First result
                item = search_response['items'][0]
                print(f"  ✓ '{item['snippet']['channelTitle']}' 채널 찾음!")
                return item['snippet']['channelId']

            # 방법 2: Channels list with forUsername (Deprecated but sometimes works)
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
        """채널의 동영상 ID 가져오기 (max_videos로 제한 가능)"""
        # 채널의 업로드 재생목록 ID 가져오기
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

        # If we just want shorts, fetching the last 100-200 videos is usually enough to find recent ones
        # Fetching *all* videos can be very expensive for large channels
        fetch_limit = 200

        while True:
            playlist_response = self.youtube.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            videos.extend(playlist_response['items'])

            if len(videos) >= fetch_limit:
                break

            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break

        return videos, channel_name

    def is_short(self, duration_str):
        """동영상이 쇼츠인지 확인 (60초 이하)"""
        try:
            duration = isodate.parse_duration(duration_str)
            return duration.total_seconds() <= 61  # 1 second buffer
        except:
            return False

    def get_transcript(self, video_id):
        """동영상 자막(스크립트) 가져오기"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(['ko'])
            except:
                try:
                    transcript = transcript_list.find_generated_transcript(['ko'])
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

    def collect_shorts_data(self, channel_url):
        channel_id = self.extract_channel_id(channel_url)
        print(f"채널 ID: {channel_id}")

        videos, channel_name = self.get_all_videos(channel_id)
        shorts_data = []

        video_ids = [v['contentDetails']['videoId'] for v in videos]

        # Bath process video details to save API quota
        # chunking by 50
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
                        # Simple date formatting
                        dt = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')
                        # Assuming KST for simplicity or just keep it simple
                        date_only = dt.strftime('%Y-%m-%d')

                        short_info = {
                            '동영상ID': item['id'],
                            '제목': snippet['title'],
                            '설명': snippet['description'],
                            '스크립트': "",  # Skip transcript for speed in batch or implement if critical
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

        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"Saved {filename}")


def main():
    API_KEY = "AIzaSyDS9QZILQ6wR3hpJ1hm9IWRJMPn1ebPmr4"

    CHANNELS = {
        "에픽무비": "https://www.youtube.com/@movieepic09",
        "타이거무비": "https: // www.youtube.com / @ Tigermovie213",
        "폭스토리": "https://www.youtube.com/@폭스토리",
        "레츠무빗": "https://www.youtube.com/@letsmovitt",
        "온무비": "https://www.youtube.com/@o_n_movie",
        "숏기스": "https://www.youtube.com/channel/UCXsaiFrtWiqgLaOImd-gSyA",
        "숏구미": "https://www.youtube.com/@shortsgumi",
        "영당포": "https://www.youtube.com/@영당포",
        "숏타임": "https://www.youtube.com/@쇼츠타임",
        "봉스무비": "https://www.youtube.com/@봉스무비"
    }

    base_dir = r"C:\python\데이터수집"
    collector = YouTubeShortCollector(API_KEY)

    summary_report = []

    print("Starting Batch Data Collection...")

    for name, url in CHANNELS.items():
        print(f"\nProcessing {name}...")
        try:
            data, channel_true_name = collector.collect_shorts_data(url)

            if data:
                # Overwrite file with fixed name
                filename = os.path.join(base_dir, f"{name}_shorts.csv")
                collector.save_to_csv(data, filename)

                avg_views = sum(d['조회수'] for d in data) / len(data)

                summary_report.append({
                    "Channel": name,
                    "Videos": len(data),
                    "Avg Views": int(avg_views),
                    "Best Video": max(data, key=lambda x: x['조회수'])['제목']
                })
            else:
                print(f"No shorts found for {name}")

        except Exception as e:
            print(f"Failed to process {name}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 30)
    print(" SUMMARY REPORT ")
    print("=" * 30)
    for item in sorted(summary_report, key=lambda x: x['Avg Views'], reverse=True):
        print(f"{item['Channel']}: {item['Avg Views']:,} avg views ({item['Videos']} videos)")
        print(f"  Best: {item['Best Video']}")
        print("-" * 20)


if __name__ == "__main__":
    main()