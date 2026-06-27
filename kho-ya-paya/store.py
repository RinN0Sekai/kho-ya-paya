"""
Kho-Ya-Paya — per-node SQLite store (pure stdlib).

Each Kho-Ya-Paya center is one node with its own SQLite replica. Records are append-only
(never deleted), carry an origin_node for provenance, and sync by copying any case_id the
peer doesn't have yet — the "USB courier" model. Seeds from the 2,500-row synthetic CSV,
split across nodes by reporting_center so the cross-center gap is real from the first second.
"""
import sqlite3, os, csv, time, threading

DATA_CSV = os.path.join(os.path.dirname(__file__), "..", "setu", "..",
                        "claude-impact-labs-data", "claude-impact-lab-mumbai-2026",
                        "data", "Synthetic_Missing_Persons_2500.csv")

FIELDS = ["case_id", "kind", "name", "gender", "age_band", "state", "district",
          "language", "last_seen", "center", "mobile", "description", "status",
          "reported_at", "photo", "match_group", "origin_node", "created_at"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  case_id TEXT PRIMARY KEY, kind TEXT, name TEXT, gender TEXT, age_band TEXT,
  state TEXT, district TEXT, language TEXT, last_seen TEXT, center TEXT, mobile TEXT,
  description TEXT, status TEXT, reported_at TEXT, photo TEXT, match_group TEXT,
  origin_node TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, role TEXT,
  case_id TEXT, action TEXT, reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_kind ON records(kind);
CREATE INDEX IF NOT EXISTS idx_origin ON records(origin_node);
"""


class Store:
    def __init__(self, node, db_path, centers):
        self.node = node
        self.centers = set(centers)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()
        self._seq = 0

    # ---- seeding ---------------------------------------------------------- #
    def seed_if_empty(self):
        if self.count() > 0:
            return
        with self._lock, open(DATA_CSV, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["reporting_center"].strip() not in self.centers:
                    continue
                self._insert({
                    "case_id": r["case_id"], "kind": "missing",
                    "name": r.get("missing_person_name", ""), "gender": r.get("gender", ""),
                    "age_band": r.get("age_band", ""), "state": r.get("state", ""),
                    "district": r.get("district", ""), "language": r.get("language", ""),
                    "last_seen": r.get("last_seen_location", ""),
                    "center": r.get("reporting_center", ""), "mobile": r.get("reporter_mobile", ""),
                    "description": r.get("physical_description", ""),
                    "status": r.get("status", "Pending"), "reported_at": r.get("reported_at", ""),
                    "photo": "", "match_group": "", "origin_node": self.node,
                    "created_at": r.get("reported_at", ""),
                })
            self._db.commit()

    # ---- writes ----------------------------------------------------------- #
    def _insert(self, rec):
        rec = {k: rec.get(k, "") for k in FIELDS}
        self._db.execute(
            f"INSERT OR IGNORE INTO records ({','.join(FIELDS)}) "
            f"VALUES ({','.join('?' for _ in FIELDS)})",
            [rec[k] for k in FIELDS])

    def new_case_id(self):
        self._seq += 1
        return f"KYP-{self.node}-{int(time.time())%100000}-{self._seq:03d}"

    def add(self, rec):
        with self._lock:
            if not rec.get("case_id"):
                rec["case_id"] = self.new_case_id()
            rec.setdefault("origin_node", self.node)
            rec.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M"))
            rec.setdefault("status", "Pending")
            self._insert(rec)
            self._db.commit()
        return rec["case_id"]

    def import_record(self, rec):
        """Bring in a peer's record verbatim (sync). Returns True if new."""
        with self._lock:
            if self.get(rec["case_id"]):
                return False
            self._insert(rec)
            self._db.commit()
            return True

    def set_status(self, case_id, status, match_group=None):
        with self._lock:
            if match_group is not None:
                self._db.execute("UPDATE records SET status=?, match_group=? WHERE case_id=?",
                                 (status, match_group, case_id))
            else:
                self._db.execute("UPDATE records SET status=? WHERE case_id=?", (status, case_id))
            self._db.commit()

    def audit(self, actor, role, case_id, action, reason=""):
        with self._lock:
            self._db.execute(
                "INSERT INTO audit (ts,actor,role,case_id,action,reason) VALUES (?,?,?,?,?,?)",
                (time.strftime("%Y-%m-%d %H:%M:%S"), actor, role, case_id, action, reason))
            self._db.commit()

    # ---- reads ------------------------------------------------------------ #
    def get(self, case_id):
        row = self._db.execute("SELECT * FROM records WHERE case_id=?", (case_id,)).fetchone()
        return dict(row) if row else None

    def all_records(self):
        return [dict(r) for r in self._db.execute("SELECT * FROM records").fetchall()]

    def count(self):
        return self._db.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]

    def stats(self):
        q = lambda w: self._db.execute(f"SELECT COUNT(*) c FROM records WHERE {w}").fetchone()["c"]
        return {
            "total": self.count(),
            "missing": q("kind='missing'"),
            "found": q("kind='found'"),
            "reunited": q("status='Reunited'"),
            "pending": q("status='Pending'"),
            "from_peer": q(f"origin_node!='{self.node}'"),
            "audit_events": self._db.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"],
        }

    def recent_audit(self, n=8):
        return [dict(r) for r in self._db.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (n,)).fetchall()]
