import json

# MushroomScreen 확인
with open(r'C:\python\데이터수집\MushroomScreen_shorts_ytdlp.json', 'r', encoding='utf-8') as f:
    data1 = json.load(f)

scripts1 = [d for d in data1 if d.get('대본')]
print(f"=== MushroomScreen ===")
print(f"총: {len(data1)}개, 대본있음: {len(scripts1)}개")
for s in scripts1[:5]:
    print(f"  [{s['조회수']:,}뷰] {s['제목'][:60]}")
    print(f"    대본: {s['대본'][:120]}...")
    print()

# CuriousPM90 확인
with open(r'C:\python\데이터수집\CuriousPM90_shorts_ytdlp.json', 'r', encoding='utf-8') as f:
    data2 = json.load(f)

scripts2 = [d for d in data2 if d.get('대본')]
print(f"\n=== CuriousPM90 ===")
print(f"총: {len(data2)}개, 대본있음: {len(scripts2)}개")
for s in scripts2[:5]:
    print(f"  [{s['조회수']:,}뷰] {s['제목'][:60]}")
    print(f"    대본: {s['대본'][:120]}...")
    print()
