"""Render a day's Reels, prune old videos, update queue.json, commit and push.

Usage (from the repo root):
    python3 engine/make_day.py 2026-11-06            # renders specs/2026-11-06/*.json
    python3 engine/make_day.py 2026-11-06 --no-push  # render + commit locally only

Each spec gets a slot in order: 08:00, 12:30, 18:00 (Montréal time).
"""
import datetime as dt, glob, json, os, subprocess, sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import reel  # noqa: E402

REPO = "imanehar/caltech-reels"
SLOTS = ["08:00", "12:30", "18:00"]
KEEP_DAYS = 14
TZ = ZoneInfo("America/Toronto")
GIT_ID = ["-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com"]
TRAILER = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

def git(*args, check=True):
    return subprocess.run(["git", "-C", ROOT, *args], check=check, capture_output=True, text=True).stdout.strip()

def main():
    date = sys.argv[1]
    push = "--no-push" not in sys.argv
    specs = sorted(glob.glob(os.path.join(ROOT, "specs", date, "*.json")))
    if not specs: sys.exit(f"no specs in specs/{date}")
    specs = specs[:3]
    os.makedirs(os.path.join(ROOT, "videos"), exist_ok=True)

    items = []
    for i, path in enumerate(specs):
        spec = json.load(open(path))
        name = f"{date}-{i + 1}.mp4"
        out = os.path.join(ROOT, "videos", name)
        dur = reel.render(spec, out)
        size = os.path.getsize(out)
        if not (8 <= dur <= 90): sys.exit(f"{name}: duration {dur:.1f}s outside 8-90s")
        if size > 20 * 1024 * 1024: sys.exit(f"{name}: {size} bytes is over 20 MB")
        h, m = map(int, SLOTS[i].split(":"))
        post_at = dt.datetime.fromisoformat(date).replace(hour=h, minute=m, tzinfo=TZ)
        meta = spec.get("meta", {})
        items.append({"id": f"{date}-{i + 1}", "file": f"videos/{name}", "post_at": post_at.isoformat(),
                      "caption": spec["caption"], "hook": meta.get("hook", ""), "format": meta.get("format", ""),
                      "industry": meta.get("industry", ""), "region": meta.get("region", ""), "duration": round(dur, 1)})
        print(f"rendered {name} ({dur:.1f}s, {size // 1024} KB)")

    # prune videos older than KEEP_DAYS
    cutoff = dt.date.fromisoformat(date) - dt.timedelta(days=KEEP_DAYS)
    for f in glob.glob(os.path.join(ROOT, "videos", "*.mp4")):
        try:
            if dt.date.fromisoformat(os.path.basename(f)[:10]) < cutoff:
                git("rm", "-q", "--cached", os.path.relpath(f, ROOT), check=False); os.remove(f)
        except ValueError:
            pass

    git("add", "videos", "specs")
    git(*GIT_ID, "commit", "-q", "-m", f"Reels for {date}{TRAILER}")
    sha = git("rev-parse", "HEAD")

    qpath = os.path.join(ROOT, "queue.json")
    queue = json.load(open(qpath)) if os.path.exists(qpath) else {"items": []}
    keep_after = dt.datetime.fromisoformat(date).replace(tzinfo=TZ) - dt.timedelta(days=3)
    old = [x for x in queue["items"] if dt.datetime.fromisoformat(x["post_at"]) >= keep_after and not x["id"].startswith(date)]
    for it in items:
        it["video_url"] = f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}/{it['file']}"
        it["raw_url"] = f"https://raw.githubusercontent.com/{REPO}/{sha}/{it['file']}"
    queue["items"] = sorted(old + items, key=lambda x: x["post_at"])
    queue["updated_at"] = dt.datetime.now(TZ).isoformat(timespec="seconds")
    json.dump(queue, open(qpath, "w"), ensure_ascii=False, indent=2)
    git("add", "queue.json")
    git(*GIT_ID, "commit", "-q", "-m", f"Queue Reels for {date}{TRAILER}")

    if push:
        print(git("push", "-q", "origin", "HEAD:main"))
        print("pushed", git("rev-parse", "--short", "HEAD"))

if __name__ == "__main__":
    main()
