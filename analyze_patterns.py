import json
import re
import sys

# 출력을 파일로도 저장
output_file = r"C:\python\데이터수집\analysis_result.txt"

class Tee:
    def __init__(self, filepath):
        self.file = open(filepath, 'w', encoding='utf-8')
        self.stdout = sys.stdout
    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
    def flush(self):
        self.stdout.flush()
        self.file.flush()
    def close(self):
        self.file.close()

tee = Tee(output_file)
sys.stdout = tee

# 데이터 로드
with open(r'C:\python\데이터수집\MushroomScreen_shorts.json', 'r', encoding='utf-8') as f:
    mush = json.load(f)
with open(r'C:\python\데이터수집\CuriousPM90_shorts.json', 'r', encoding='utf-8') as f:
    curious = json.load(f)

print("=" * 70)
print(" 성공 영상 패턴 분석 리포트")
print("=" * 70)

# MushroomScreen 100만뷰+
mush_mega = sorted([v for v in mush if v['조회수'] >= 1000000], key=lambda x: x['조회수'], reverse=True)
print(f"\n[MushroomScreen] 전체: {len(mush)}개 / 100만뷰+: {len(mush_mega)}개")
print(f"평균 조회수: {int(sum(v['조회수'] for v in mush)/len(mush)):,}")

print(f"\nTOP 20 (100만뷰+):")
for i, v in enumerate(mush_mega[:20], 1):
    dur_match = re.search(r'PT(?:(\d+)M)?(\d+)S', v['영상길이'])
    if dur_match:
        secs = int(dur_match.group(1) or 0) * 60 + int(dur_match.group(2) or 0)
    elif v['영상길이'] == 'PT1M':
        secs = 60
    else:
        secs = 0
    print(f"  {i:2d}. [{v['조회수']:>12,}뷰] 참여:{v['참여도(%)']:>5.1f}% {secs}초 | {v['제목']}")

# CuriousPM90
curious_sorted = sorted(curious, key=lambda x: x['조회수'], reverse=True)
print(f"\n[CuriousPM90] 전체: {len(curious)}개")
print(f"평균 조회수: {int(sum(v['조회수'] for v in curious)/len(curious)):,}")
print(f"\n전체 순위:")
for i, v in enumerate(curious_sorted, 1):
    print(f"  {i:2d}. [{v['조회수']:>12,}뷰] 참여:{v['참여도(%)']:>5.1f}% | {v['제목']}")

# 통합 100만뷰+
all_mega = mush_mega + [v for v in curious if v['조회수'] >= 1000000]
all_mega.sort(key=lambda x: x['조회수'], reverse=True)
print(f"\n{'='*70}")
print(f"통합 100만뷰+ 영상: {len(all_mega)}개")
print("="*70)

# 제목 길이 분석
title_lens = [len(v['제목']) for v in all_mega]
print(f"\n[제목 길이]")
print(f"  평균: {sum(title_lens)/len(title_lens):.0f}자")
print(f"  최소: {min(title_lens)}자 / 최대: {max(title_lens)}자")
ranges = [(30,50),(50,70),(70,100)]
for lo, hi in ranges:
    cnt = sum(1 for l in title_lens if lo <= l < hi)
    print(f"  {lo}-{hi}자: {cnt}개 ({cnt/len(title_lens)*100:.0f}%)")

# 해시태그 분석
print(f"\n[해시태그 빈도 - 100만뷰+]")
tag_count = {}
for v in all_mega:
    tags = [w for w in v['제목'].split() if w.startswith('#')]
    for t in tags:
        tag_count[t.lower()] = tag_count.get(t.lower(), 0) + 1
for tag, cnt in sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:15]:
    print(f"  {tag}: {cnt}회")

# 키워드 분석
print(f"\n[제목 키워드 빈도 - 100만뷰+]")
word_count = {}
stop_words = {'the','a','an','is','was','were','are','in','on','of','to','and','for','it','by','he','she','his','her','but','from','with','this','that','as','at'}
for v in all_mega:
    words = re.findall(r'[a-zA-Z]+', v['제목'].lower())
    for w in words:
        if w not in stop_words and len(w) > 2:
            word_count[w] = word_count.get(w, 0) + 1
for word, cnt in sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:25]:
    print(f"  '{word}': {cnt}회")

# 제목 구조 분석
print(f"\n[제목 구조 분석 - 100만뷰+]")
structure_patterns = {
    "He/She/Man/Boy/Girl 주어 시작": 0,
    "숫자 포함 ($, 달러)": 0,
    "의문형 (?)": 0,
    "감탄형 (!)": 0,
    "마침표(.) 종료": 0,
    "but/however 반전": 0,
    "never/don't 부정": 0,
}

for v in all_mega:
    t = v['제목']
    if re.match(r'^(He|She|Man|Boy|Girl|Woman|Soldier|Police|Jewish|German|Soviet|Recruit)', t):
        structure_patterns["He/She/Man/Boy/Girl 주어 시작"] += 1
    if re.search(r'[\$\d]', t):
        structure_patterns["숫자 포함 ($, 달러)"] += 1
    if '?' in t:
        structure_patterns["의문형 (?)"] += 1
    if '!' in t or '！' in t:
        structure_patterns["감탄형 (!)"] += 1
    if t.rstrip().endswith('.'):
        structure_patterns["마침표(.) 종료"] += 1
    if re.search(r'\b(but|however|yet)\b', t, re.I):
        structure_patterns["but/however 반전"] += 1
    if re.search(r"\b(never|don't|doesn't|didn't|cannot|can't|not|no)\b", t, re.I):
        structure_patterns["never/don't 부정"] += 1

for p, cnt in sorted(structure_patterns.items(), key=lambda x: x[1], reverse=True):
    print(f"  {p}: {cnt}/{len(all_mega)} ({cnt/len(all_mega)*100:.0f}%)")

# 영상 길이 분석
print(f"\n[영상 길이 - 100만뷰+]")
durations = []
for v in all_mega:
    m = re.search(r'PT(?:(\d+)M)?(\d+)S', v['영상길이'])
    if m:
        durations.append(int(m.group(1) or 0) * 60 + int(m.group(2) or 0))
    elif v['영상길이'] == 'PT1M':
        durations.append(60)

if durations:
    print(f"  평균: {sum(durations)/len(durations):.0f}초")
    print(f"  최소: {min(durations)}초 / 최대: {max(durations)}초")
    for lo, hi in [(45,50),(50,55),(55,60),(60,61)]:
        cnt = sum(1 for d in durations if lo <= d <= hi)
        print(f"  {lo}-{hi}초: {cnt}개 ({cnt/len(durations)*100:.0f}%)")

# 참여도 상위
print(f"\n[참여도 상위 TOP10 (100만뷰+)]")
all_mega_eng = sorted(all_mega, key=lambda x: x['참여도(%)'], reverse=True)
for i, v in enumerate(all_mega_eng[:10], 1):
    print(f"  {i}. 참여:{v['참여도(%)']:.1f}% | {v['조회수']:>12,}뷰 | {v['제목']}")

# 장르/주제 분류
print(f"\n[장르/주제 태그 분류 - 100만뷰+]")
genre_tags = {}
for v in all_mega:
    tags = re.findall(r'#(\w+)', v['제목'])
    for t in tags:
        t_lower = t.lower()
        genre_tags[t_lower] = genre_tags.get(t_lower, 0) + 1
for tag, cnt in sorted(genre_tags.items(), key=lambda x: x[1], reverse=True):
    print(f"  #{tag}: {cnt}회")

# 업로드 빈도
print(f"\n[업로드 빈도 - MushroomScreen]")
dates = [v['업로드날짜'] for v in mush if v['업로드날짜']]
if dates:
    print(f"  최신: {max(dates)} / 최초: {min(dates)}")
    months = {}
    for d in dates:
        m = d[:7]
        months[m] = months.get(m, 0) + 1
    for m, cnt in sorted(months.items(), reverse=True)[:6]:
        print(f"  {m}: {cnt}개")

sys.stdout = tee.stdout
tee.close()
print(f"\n분석 결과 저장: {output_file}")
