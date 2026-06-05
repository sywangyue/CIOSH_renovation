#!/usr/bin/env python3
"""Download all CIOSH exhibition data from LiXiaoYun CRM and save to SQLite."""

import json
import sqlite3
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────
EXH_ID = "afb2cba1172d580696cefd9ecbc3db36"
EXH_NAME = "中国劳动保护用品交易会"
DB_PATH = "ciosh_data.db"
PAGE_SIZE = 200  # Max tested page size

HEADERS = {
    "authorization": "Token token=ikcrm01a7af2ed5ea4fee2c91a4052d33790d",
    "app_token": "a14cc8b00f84e64b438af540390531e4",
    "crm_platform_type": "lixiaoyun",
    "distinct_id": "24778024",
    "brand": "%E5%8A%B1%E9%94%80",
    "project_name": "%E7%8B%AC%E7%AB%8B",
    "platform_type": "PC",
    "accept": "application/json, text/plain, */*",
    "referer": "https://lxcrm.weiwenjia.com/",
}


# ── API Helpers ─────────────────────────────────────────────────
def api_fetch(url):
    """Fetch JSON from API with retries."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2)


def fetch_paginated(section, extra_params=None, label=None):
    """Fetch all pages for a given section. Returns list of items."""
    params = {
        "section": section,
        "exhName": EXH_NAME,
        "id": EXH_ID,
        "pageSize": str(PAGE_SIZE),
        "hasSyncClue": "0",
        "hasSyncRobot": "0",
        "hasUnfolded": "0",
        "hasSyncDx": "0",
    }
    if label:
        params["label"] = label
        # label queries don't use exhName
        del params["exhName"]
    if extra_params:
        params.update(extra_params)

    all_items = []
    page = 1
    total = None

    while True:
        params["page"] = str(page)
        qs = urllib.parse.urlencode(params)
        url = f"https://enterprise.weiwenjia.com/api_skb/v2/exhibition/exhibitionSectionInfo?{qs}"

        data = api_fetch(url)
        if not data.get("success"):
            print(f"  [ERROR] section={section} page={page}: {data.get('message', 'unknown')}")
            break

        # Find the data key (varies by section)
        container = None
        for key, val in (data.get("data") or {}).items():
            if isinstance(val, dict) and "items" in val:
                container = val
                break

        if container is None:
            print(f"  [WARN] No container found in response keys={list((data.get('data') or {}).keys())}")
            break

        if total is None:
            total = container.get("total", 0)
            print(f"  Total: {total}, pageSize={PAGE_SIZE}, pages={-(-total // PAGE_SIZE)}")

        items = container.get("items") or []
        all_items.extend(items)
        print(f"  Page {page}: fetched {len(items)}, cumulative: {len(all_items)}/{total}")

        if len(all_items) >= total or len(items) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.3)  # Rate limit

    return all_items


def fetch_all_journals():
    """Fetch all 27 journal records from AllPreviousJournal label=AllJournalInfo."""
    params = {
        "section": "AllPreviousJournal",
        "label": "AllJournalInfo",
        "id": EXH_ID,
        "page": "1",
        "pageSize": "50",
    }
    qs = urllib.parse.urlencode(params)
    url = f"https://enterprise.weiwenjia.com/api_skb/v2/exhibition/exhibitionSectionInfo?{qs}"
    data = api_fetch(url)
    if data.get("success"):
        items = data["data"]["AllJournalInfo"]["items"]
        print(f"  Journals: {len(items)} records")
        return items
    return []


def fetch_org_stats():
    """Fetch organizer statistics."""
    params = {
        "section": "AllPreviousJournal",
        "label": "OrgUnitStatistics",
        "id": EXH_ID,
        "page": "1",
        "pageSize": "50",
    }
    qs = urllib.parse.urlencode(params)
    url = f"https://enterprise.weiwenjia.com/api_skb/v2/exhibition/exhibitionSectionInfo?{qs}"
    data = api_fetch(url)
    if data.get("success"):
        items = data["data"]["OrgUnitStatistics"]["items"]
        print(f"  OrgUnitStatistics: {len(items)} records")
        return items
    return []


def fetch_exhibition_info():
    """Fetch base exhibition info."""
    url = f"https://enterprise.weiwenjia.com/api_skb/v2/exhibition/exhibitionBaseInfo?exhId={EXH_ID}"
    data = api_fetch(url)
    if data.get("success"):
        info = data["data"]
        print(f"  Exhibition: {info.get('exhName', 'N/A')}")
        return info
    return {}


# ── Database Setup ──────────────────────────────────────────────
def setup_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Exhibition base info
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exhibition_base (
            exh_id TEXT PRIMARY KEY,
            exh_name TEXT,
            exh_class TEXT,
            exh_desc TEXT,
            journals_count INTEGER,
            exhibitor_count INTEGER,
            raw_json TEXT
        )
    """)

    # Journals (sessions/届次)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS journals (
            journal_id TEXT PRIMARY KEY,
            exh_id TEXT,
            journal_name TEXT,
            journal_start_date TEXT,
            journal_end_date TEXT,
            exhibitor_count INTEGER,
            hold_address TEXT,
            organizer_json TEXT,
            sponsor_json TEXT,
            FOREIGN KEY (exh_id) REFERENCES exhibition_base(exh_id)
        )
    """)

    # Exhibitors (参展商信息)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exhibitors (
            pid TEXT NOT NULL,
            exh_id TEXT NOT NULL,
            ent_name TEXT,
            par_count INTEGER,
            has_synced INTEGER DEFAULT 0,
            has_unfold INTEGER DEFAULT 0,
            par_region_json TEXT,
            par_time_json TEXT,
            journals_json TEXT,
            company_tags_json TEXT,
            PRIMARY KEY (pid, exh_id),
            FOREIGN KEY (exh_id) REFERENCES exhibition_base(exh_id)
        )
    """)

    # Forecast exhibitors (预测参展商)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forecast_exhibitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exh_id TEXT NOT NULL,
            ent_name TEXT,
            high_light_ent_name TEXT,
            b2b_product TEXT,
            high_light_b2b_product TEXT,
            es_date TEXT,
            ent_address TEXT,
            FOREIGN KEY (exh_id) REFERENCES exhibition_base(exh_id)
        )
    """)

    # Org unit statistics (主办方/承办方统计)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS org_unit_stats (
            pid TEXT NOT NULL,
            exh_id TEXT NOT NULL,
            ent_name TEXT,
            par_type_json TEXT,
            hold_count INTEGER,
            hold_region_json TEXT,
            hold_time_json TEXT,
            PRIMARY KEY (pid, exh_id),
            FOREIGN KEY (exh_id) REFERENCES exhibition_base(exh_id)
        )
    """)

    conn.commit()
    return conn, cur


# ── Data Insertion ──────────────────────────────────────────────
def insert_exhibition(cur, info):
    cur.execute(
        """INSERT OR REPLACE INTO exhibition_base
           (exh_id, exh_name, exh_class, exh_desc, journals_count, exhibitor_count, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            info.get("exhId", EXH_ID),
            info.get("exhName", ""),
            info.get("exhClass", ""),
            info.get("exhDesc", ""),
            info.get("journalsCount", 0),
            info.get("exhibitorCount", 0),
            json.dumps(info, ensure_ascii=False),
        ),
    )
    print(f"  Inserted exhibition base info")


def insert_journals(cur, journals):
    for j in journals:
        cur.execute(
            """INSERT OR REPLACE INTO journals
               (journal_id, exh_id, journal_name, journal_start_date, journal_end_date,
                exhibitor_count, hold_address, organizer_json, sponsor_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                j.get("journalId", ""),
                j.get("exhId", EXH_ID),
                j.get("journalName", ""),
                j.get("journalSd", ""),
                j.get("journalEd", ""),
                j.get("exhibitorCount", 0),
                j.get("holdAddress", ""),
                json.dumps(j.get("organizer", []), ensure_ascii=False),
                json.dumps(j.get("sponsor", []), ensure_ascii=False),
            ),
        )
    print(f"  Inserted {len(journals)} journals")


def insert_exhibitors(cur, exhibitors):
    count = 0
    for e in exhibitors:
        pid = e.get("pid", "")
        if not pid:
            continue
        cur.execute(
            """INSERT OR REPLACE INTO exhibitors
               (pid, exh_id, ent_name, par_count, has_synced, has_unfold,
                par_region_json, par_time_json, journals_json, company_tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid,
                e.get("exhId", EXH_ID),
                e.get("entName", ""),
                e.get("parCount", 0),
                1 if e.get("hasSynced") else 0,
                1 if e.get("hasUnfold") else 0,
                json.dumps(e.get("parRegion", []), ensure_ascii=False),
                json.dumps(e.get("parTime", []), ensure_ascii=False),
                json.dumps(e.get("journals", []), ensure_ascii=False),
                json.dumps(e.get("companyTags", []), ensure_ascii=False),
            ),
        )
        count += 1
    print(f"  Inserted {count} exhibitors")


def insert_forecast(cur, forecasts):
    count = 0
    for f in forecasts:
        es_ts = f.get("esDate")
        es_date = None
        if es_ts:
            try:
                es_date = datetime.fromtimestamp(es_ts / 1000).strftime("%Y-%m-%d")
            except Exception:
                es_date = str(es_ts)

        cur.execute(
            """INSERT INTO forecast_exhibitors
               (exh_id, ent_name, high_light_ent_name, b2b_product, high_light_b2b_product, es_date, ent_address)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                EXH_ID,
                f.get("entName", ""),
                f.get("highLightEntName", ""),
                f.get("b2bProduct", ""),
                f.get("highLightB2bProduct", ""),
                es_date,
                f.get("entAddress", ""),
            ),
        )
        count += 1
    print(f"  Inserted {count} forecast exhibitors")


def insert_org_stats(cur, stats):
    count = 0
    for s in stats:
        pid = s.get("pid", "")
        if not pid:
            continue
        cur.execute(
            """INSERT OR REPLACE INTO org_unit_stats
               (pid, exh_id, ent_name, par_type_json, hold_count, hold_region_json, hold_time_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                pid,
                s.get("exhId", EXH_ID),
                s.get("entName", ""),
                json.dumps(s.get("parType", []), ensure_ascii=False),
                s.get("holdCount", 0),
                json.dumps(s.get("holdRegion", []), ensure_ascii=False),
                json.dumps(s.get("holdTime", []), ensure_ascii=False),
            ),
        )
        count += 1
    print(f"  Inserted {count} org unit stats")


# ── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("CIOSH Data Downloader - LiXiaoYun CRM")
    print("=" * 60)

    print("\n[1/5] Fetching exhibition base info...")
    exh_info = fetch_exhibition_info()

    print("\n[2/5] Fetching journals (届次/会刊)...")
    journals = fetch_all_journals()

    print("\n[3/5] Fetching org unit statistics...")
    org_stats = fetch_org_stats()

    print("\n[4/5] Fetching exhibitors (参展商信息)...")
    exhibitors = fetch_paginated("ExhibitorInfo")

    print("\n[5/5] Fetching forecast exhibitors (预测参展商)...")
    forecasts = fetch_paginated("ForecastExhibitorInfo")

    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Journals:          {len(journals)}")
    print(f"  OrgUnitStats:      {len(org_stats)}")
    print(f"  Exhibitors:        {len(exhibitors)}")
    print(f"  Forecast:          {len(forecasts)}")
    print(f"  TOTAL:             {len(exhibitors) + len(forecasts)} exhibitor records")
    print(f"{'=' * 60}")

    print(f"\nWriting to SQLite: {DB_PATH}")
    conn, cur = setup_db(DB_PATH)
    insert_exhibition(cur, exh_info)
    insert_journals(cur, journals)
    insert_org_stats(cur, org_stats)
    insert_exhibitors(cur, exhibitors)
    insert_forecast(cur, forecasts)
    conn.commit()

    # Verify
    print("\n--- Database Summary ---")
    for table in ["exhibition_base", "journals", "exhibitors", "forecast_exhibitors", "org_unit_stats"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count} rows")

    conn.close()
    print(f"\nDone! Database saved to {DB_PATH}")


if __name__ == "__main__":
    main()
