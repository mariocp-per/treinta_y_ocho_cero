
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

import sqlite3
import re
import time
import random
from pathlib import Path

# =====================================================
# CONFIG
# =====================================================

DB_FILE = "database/futbol380.db"

LEAGUES = [
    (53, "Spain Primera Division", "spain-primera-division-1"),
    (54, "Spain Segunda Division", "spain-segunda-division-2"),
]

VERSIONS = (
    [f"fifa{i:02d}" for i in range(5, 24)]
    + ["fc24", "fc25", "fc26"]
)

BASE_URL = "https://fifaindex.com"

# =====================================================
# DB
# =====================================================

def init_db():

    Path("database").mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS fifa_player_ratings (

        fifa_version TEXT NOT NULL,
        fifa_year INTEGER NOT NULL,

        league_id INTEGER NOT NULL,
        league_name TEXT NOT NULL,

        team_name TEXT NOT NULL,

        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,

        nationality TEXT,
        position TEXT,

        age INTEGER,
        overall INTEGER,
        potential INTEGER,

        PRIMARY KEY (
            fifa_version,
            player_id
        )
    )
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_player_name
    ON fifa_player_ratings(player_name)
    """)

    conn.commit()

    return conn


# =====================================================
# HELPERS
# =====================================================

def version_to_year(version):

    if version.startswith("fifa"):
        return 2000 + int(version[-2:])

    if version.startswith("fc"):
        return 2000 + int(version[-2:])

    return None


def safe_int(value):

    try:
        return int(str(value).strip())
    except:
        return None


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

    page.wait_for_timeout(2000)

    tables = page.locator("table")

    if tables.count() == 0:
        return []

    teams_table = tables.nth(0)

    rows = teams_table.locator(
        "tbody tr"
    )

    teams = []

    for i in range(rows.count()):

        row = rows.nth(i)

        links = row.locator(
            "a[href^='/teams/']"
        )

        if links.count() == 0:
            continue

        link = links.first

        href = link.get_attribute("href")

        if not href:
            continue

        name = (
            link.inner_text()
            .strip()
        )

        teams.append(
            {
                "name": name,
                "href": href
            }
        )

    return teams


# =====================================================
# PLAYERS
# =====================================================

def get_players(
    page,
    team_url
):

    url = BASE_URL + team_url

    print("\n========================")
    print("TEAM URL:", url)

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=120000
    )

    page.wait_for_timeout(4000)

    title = page.title()

    print("TITLE:", title)

    if (
        "un momento" in title.lower()
        or "just a moment" in title.lower()
    ):
        print("CLOUDFLARE DETECTADO")
        return []

    tables = page.locator("table")

    print("TABLES:", tables.count())

    if tables.count() == 0:
        return []

    rows = tables.nth(0).locator(
        "tbody tr"
    )

    print("ROWS:", rows.count())

    players = []

    for i in range(rows.count()):

        try:

            row = rows.nth(i)

            cols = row.locator("td")

            if cols.count() < 7:
                continue

            player_link = cols.nth(1).locator("a")

            href = player_link.get_attribute(
                "href"
            )

            if not href:
                continue

            player_name = (
                player_link
                .inner_text()
                .strip()
            )

            match = re.search(
                r"/players/(\d+)",
                href
            )

            if not match:
                continue

            player_id = int(
                match.group(1)
            )

            nationality = (
                cols.nth(2)
                .inner_text()
                .strip()
            )

            position = (
                cols.nth(3)
                .inner_text()
                .strip()
            )

            age = safe_int(
                cols.nth(4).inner_text()
            )

            overall = safe_int(
                cols.nth(5).inner_text()
            )

            potential = safe_int(
                cols.nth(6).inner_text()
            )

            players.append(
                (
                    player_id,
                    player_name,
                    nationality,
                    position,
                    age,
                    overall,
                    potential
                )
            )

        except Exception as e:

            print(
                "ERROR PLAYER:",
                str(e)
            )

    return players


# =====================================================
# SAVE
# =====================================================

def save_players(
    conn,
    fifa_version,
    fifa_year,
    league_id,
    league_name,
    team_name,
    players
):

    rows = []

    for p in players:

        rows.append(
            (
                fifa_version,
                fifa_year,
                league_id,
                league_name,
                team_name,
                *p
            )
        )

    conn.executemany(
        """
        INSERT OR REPLACE
        INTO fifa_player_ratings
        VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        rows
    )

    conn.commit()


# =====================================================
# MAIN
# =====================================================

def run():

    stealth = Stealth()

    conn = init_db()

    total_players = 0

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

            print("Sesión cargada")

        except:

            context = browser.new_context(
                viewport={
                    "width": 1366,
                    "height": 768
                },
                locale="es-ES"
            )

            print("Nueva sesión")

        page = context.new_page()

        try:
            stealth.apply_stealth_sync(page)
        except:
            pass

        page.goto(
            "https://fifaindex.com",
            wait_until="domcontentloaded",
            timeout=120000
        )

        print(
            "\nSi aparece Cloudflare, resuélvelo manualmente."
        )

        input(
            "\nCuando FIFA Index esté visible correctamente pulsa ENTER..."
        )

        context.storage_state(
            path="fifaindex_state.json"
        )

        for version in VERSIONS:

            year = version_to_year(
                version
            )

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
                        f"\nTEAM: {team['name']}"
                    )

                    print(
                        f"HREF: {team['href']}"
                    )

                    players = get_players(
                        page,
                        team["href"]
                    )

                    total_players += len(players)

                    print(
                        f"{len(players)} jugadores"
                    )

                    save_players(
                        conn,
                        version,
                        year,
                        league_id,
                        league_name,
                        team["name"],
                        players
                    )

                    page.mouse.move(
                        random.randint(100, 1200),
                        random.randint(100, 700)
                    )

                    page.wait_for_timeout(
                        random.randint(500, 1500)
                    )

                    sleep_time = random.uniform(
                        3,
                        7
                    )

                    print(
                        f"Esperando {sleep_time:.1f}s..."
                    )

                    time.sleep(
                        sleep_time
                    )

        print()
        print("=" * 60)
        print(
            f"TOTAL JUGADORES: {total_players}"
        )
        print("=" * 60)

        browser.close()

    conn.close()

    print("\nFIN")


if __name__ == "__main__":
    run()
