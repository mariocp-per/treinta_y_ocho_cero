from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

import sqlite3
import re
import time
import random
from urllib.parse import urljoin

# =====================================================
# CONFIG
# =====================================================

DB_FILE = "database/futbol380.db"

LEAGUES = [
    (53, "Spain Primera Division", "spain-primera-division-1"),
    (54, "Spain Segunda Division", "spain-segunda-division-2"),
]

LUSTRUMS = [
    ("fifa05", 2005),
    ("fifa10", 2010),
    ("fifa15", 2015),
    ("fifa20", 2020),
    ("fc25", 2025),
]

BASE_URL = "https://fifaindex.com"

# =====================================================
# DB
# =====================================================

def init_db():

    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS team_assets (

        team_id INTEGER NOT NULL,
        lustrum_start INTEGER NOT NULL,

        team_name TEXT NOT NULL,

        logo_url TEXT,
        kit_url TEXT,

        PRIMARY KEY (
            team_id,
            lustrum_start
        )
    )
    """)

    conn.commit()

    return conn


# =====================================================
# URLS
# =====================================================

def build_league_url(
    league_id,
    league_slug,
    version
):

    return (
        f"{BASE_URL}/leagues/"
        f"{league_id}-{league_slug}/"
        f"{version}"
    )


# =====================================================
# TEAMS
# =====================================================

def get_teams(
    page,
    league_id,
    league_slug,
    version
):

    url = build_league_url(
        league_id,
        league_slug,
        version
    )

    print(f"\nLiga: {url}")

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=120000
    )

    page.wait_for_timeout(2500)

    tables = page.locator("table")

    if tables.count() == 0:
        return []

    rows = tables.nth(0).locator(
        "tbody tr"
    )

    teams = []

    for i in range(rows.count()):

        try:

            row = rows.nth(i)

            links = row.locator(
                "a[href*='/equipos/'], a[href*='/teams/']"
            )

            if links.count() == 0:
                continue

            link = links.first

            href = link.get_attribute(
                "href"
            )

            if not href:
                continue

            name = (
                link.inner_text()
                .strip()
            )

            match = re.search(
                r"/(?:equipos|teams)/(\d+)",
                href
            )

            if not match:
                continue

            team_id = int(
                match.group(1)
            )

            teams.append(
                {
                    "team_id": team_id,
                    "team_name": name,
                    "href": href
                }
            )

        except Exception:
            pass

    return teams


# =====================================================
# TEAM ASSETS
# =====================================================

def extract_team_assets(
    page,
    team_href
):

    url = urljoin(
        BASE_URL,
        team_href
    )

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=120000
    )

    page.wait_for_timeout(3000)

    images = page.locator("img")

    logo_url = None
    kit_url = None

    urls = []

    for i in range(images.count()):

        try:

            src = images.nth(i).get_attribute(
                "src"
            )

            if not src:
                continue

            full_url = urljoin(
                BASE_URL,
                src
            )

            urls.append(
                full_url
            )

        except:
            pass

    # ==========================================
    # LOGO
    # ==========================================

    for img in urls:

        low = img.lower()

        if (
            "team" in low
            or "teams" in low
            or "badge" in low
            or "crest" in low
        ):

            logo_url = img
            break

    # ==========================================
    # HOME KIT
    # ==========================================

    for img in urls:

        low = img.lower()

        if (
            "kit" in low
            or "kits" in low
            or "jersey" in low
            or "uniform" in low
        ):

            kit_url = img
            break

    # ==========================================
    # DEBUG
    # ==========================================

    print("\nLOGO:", logo_url)
    print("KIT :", kit_url)

    return (
        logo_url,
        kit_url
    )


# =====================================================
# SAVE
# =====================================================

def save_team_assets(
    conn,
    team_id,
    lustrum_start,
    team_name,
    logo_url,
    kit_url
):

    conn.execute(
        """
        INSERT OR REPLACE
        INTO team_assets (

            team_id,
            lustrum_start,
            team_name,

            logo_url,
            kit_url

        )
        VALUES (
            ?,?,?,?,?
        )
        """,
        (
            team_id,
            lustrum_start,
            team_name,
            logo_url,
            kit_url
        )
    )

    conn.commit()


# =====================================================
# MAIN
# =====================================================

def run():

    conn = init_db()

    stealth = Stealth()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled"
            ]
        )

        try:

            context = browser.new_context(
                storage_state="fifaindex_state.json",
                viewport={
                    "width": 1366,
                    "height": 768
                },
                locale="es-ES"
            )

            print(
                "Sesión cargada"
            )

        except:

            context = browser.new_context(
                viewport={
                    "width": 1366,
                    "height": 768
                },
                locale="es-ES"
            )

            print(
                "Nueva sesión"
            )

        page = context.new_page()

        try:
            stealth.apply_stealth_sync(page)
        except:
            pass

        page.goto(
            BASE_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        for version, lustrum_start in LUSTRUMS:

            print()
            print("=" * 60)
            print(version.upper())
            print("=" * 60)

            for (
                league_id,
                league_name,
                league_slug
            ) in LEAGUES:

                teams = get_teams(
                    page,
                    league_id,
                    league_slug,
                    version
                )

                print(
                    f"{league_name}: "
                    f"{len(teams)} equipos"
                )

                for team in teams:

                    print(
                        f"\n{team['team_name']} "
                        f"({lustrum_start})"
                    )

                    try:

                        logo_url, kit_url = (
                            extract_team_assets(
                                page,
                                team["href"]
                            )
                        )

                        save_team_assets(
                            conn,
                            team["team_id"],
                            lustrum_start,
                            team["team_name"],
                            logo_url,
                            kit_url
                        )

                        print(
                            "OK"
                        )

                    except Exception as e:

                        print(
                            "ERROR:",
                            str(e)
                        )

                    page.mouse.move(
                        random.randint(
                            100,
                            1200
                        ),
                        random.randint(
                            100,
                            700
                        )
                    )

                    page.wait_for_timeout(
                        random.randint(
                            500,
                            1500
                        )
                    )

                    time.sleep(
                        random.uniform(
                            2,
                            5
                        )
                    )

        browser.close()

    conn.close()

    print("\nFIN")


if __name__ == "__main__":
    run()