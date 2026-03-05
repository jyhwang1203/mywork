import subprocess, sys, os

# 1. 자막 목록 확인
url = "https://youtube.com/shorts/ef1f4Bg8fJ8"
cmd = [sys.executable, "-m", "yt_dlp", "--list-subs", "--skip-download", url]
result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

out_path = r"C:\python\데이터수집\sub_test.txt"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write("=== STDOUT ===\n")
    f.write(result.stdout)
    f.write("\n=== STDERR ===\n")
    f.write(result.stderr)

print("저장 완료:", out_path)

# 2. 자동 자막 다운로드 테스트
import tempfile, shutil
temp_dir = tempfile.mkdtemp()
cmd2 = [sys.executable, "-m", "yt_dlp",
    "--skip-download",
    "--write-auto-sub",
    "--sub-lang", "en",
    "--sub-format", "vtt",
    "-o", os.path.join(temp_dir, "%(id)s.%(ext)s"),
    url
]
result2 = subprocess.run(cmd2, capture_output=True, text=True, encoding='utf-8')

print("\n=== 자막 다운로드 결과 ===")
print("STDOUT:", result2.stdout[-500:] if result2.stdout else "(empty)")
print("STDERR:", result2.stderr[-500:] if result2.stderr else "(empty)")

# 다운받은 파일 확인
if os.path.exists(temp_dir):
    files = os.listdir(temp_dir)
    print(f"\n다운로드된 파일들: {files}")
    for fname in files:
        fpath = os.path.join(temp_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"\n--- {fname} ({len(content)}자) ---")
        print(content[:500])
    shutil.rmtree(temp_dir)
else:
    print("임시 폴더 없음")
