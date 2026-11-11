"""Turn a Fishin Magician backup (deercast-data/backups/fishin-magician/*.json, made by that repo's backup workflow)
into SQL that REPLACES the fm_* tables' contents. Output contains private data — send it to John as a file, never commit.

    python3 tools/make_restore.py <deercast-data>/backups/fishin-magician > fishin_magician_restore.sql
Run web/supabase/schema.sql first if the tables don't exist (fresh project), then paste this into the SQL Editor.
Lure photos: the backup's lure_photos/ folder holds every file from Storage bucket fm-lures/lures/ — upload them
back there (same names) only if the bucket itself was lost.
"""
import json
import secrets
import sys
from pathlib import Path

ORDER = ["fm_users", "fm_trips", "fm_water_quality", "fm_score_freeze", "fm_lures", "fm_spots", "fm_saved", "fm_punch", "fm_punch_counter"]
COLS = {"fm_users": ["email", "name", "role"], "fm_trips": ["id", "owner", "trip_date", "session_id", "data"],
        "fm_water_quality": ["observed_at", "data"], "fm_score_freeze": ["the_date", "segment_name", "data"],
        "fm_lures": ["id", "data"], "fm_spots": ["id", "data"], "fm_saved": ["id", "owner", "kind", "data", "created_at"],
        "fm_punch": ["task_no", "owner", "data"], "fm_punch_counter": ["id", "next_no"]}
TAG = "r" + secrets.token_hex(4)


def lit(v, col):
    if v is None:
        return "null"
    if col == "data":
        s = json.dumps(v, ensure_ascii=False)
        assert f"${TAG}$" not in s
        return f"${TAG}${s}${TAG}$::jsonb"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main(folder):
    d = Path(folder)
    out = ["-- Fishin Magician restore (generated from a backup). Contains private data - do not commit.", "begin;"]
    out += [f"delete from public.{t};" for t in reversed(ORDER)]
    counts = {}
    for t in ORDER:
        p = d / f"{t}.json"
        rows = json.loads(p.read_text()) if p.exists() else []
        counts[t] = len(rows)
        cols = COLS[t]
        for i in range(0, len(rows), 200):
            chunk = rows[i:i + 200]
            out.append(f"insert into public.{t} ({', '.join(cols)}) values\n" +
                       ",\n".join("(" + ", ".join(lit(r.get(c), c) for c in cols) + ")" for r in chunk) + ";")
    if not counts["fm_users"]:
        sys.exit("That backup has no fm_users — refusing to make a restore that would lock everyone out.")
    out.append("commit;")
    out.append("-- check: " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    out.append("select " + ", ".join(f"(select count(*) from public.{t}) as {t}" for t in ORDER) + ";")
    print("\n".join(out))
    print(f"restore SQL for: {counts}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
