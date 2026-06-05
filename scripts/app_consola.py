import sqlite3

DB_PATH = "database/futbol380.db"

FORMATION = {
    "GK": 1,
    "RB": 1,
    "CB": 2,
    "LB": 1,
    "CM": 3,
    "LW": 1,
    "RW": 1,
    "ST": 1,
}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_leagues(conn):
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT
            league_id,
            league_name
        FROM player_lustrum_ratings
        ORDER BY league_name
    """)

    return [dict(row) for row in cursor.fetchall()]


def select_league(conn):
    leagues = get_leagues(conn)

    print("\n==============================")
    print("SELECCIONA UNA LIGA")
    print("==============================")

    for idx, league in enumerate(leagues, start=1):
        print(f"{idx}. {league['league_name']}")

    while True:
        try:
            choice = int(input("\nLiga: ")) - 1

            if 0 <= choice < len(leagues):
                return leagues[choice]

        except ValueError:
            pass

        print("Opción no válida.")


def get_random_team(conn, league_id):
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT
            lustrum_start,
            league_id,
            league_name,
            team_name
        FROM player_lustrum_ratings
        WHERE league_id = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (league_id,))

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def get_players(conn, lustrum_start, league_id, team_name):
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            player_id,
            player_name,
            tactical_position,
            avg_overall,
            team_name,
            lustrum_start
        FROM player_lustrum_ratings
        WHERE lustrum_start = ?
          AND league_id = ?
          AND team_name = ?
          AND tactical_position IS NOT NULL
        ORDER BY RANDOM()
    """, (lustrum_start, league_id, team_name))

    return [dict(row) for row in cursor.fetchall()]


def squad_complete(selected_positions):
    for position, required in FORMATION.items():
        if len(selected_positions[position]) < required:
            return False
    return True


def build_available_players(players, selected_players, selected_positions):

    available = []

    for player in players:

        if player["player_id"] in selected_players:
            continue

        position = player["tactical_position"]

        if len(selected_positions[position]) >= FORMATION[position]:
            continue

        available.append(player)

    return available


def print_formation(selected_positions):

    print("\n========================================")
    print("TU EQUIPO")
    print("========================================")

    for position in FORMATION:

        players = selected_positions[position]

        if not players:
            print(f"{position:3} -> [VACÍO]")
            continue

        text = ", ".join(
            f"{p['player_name']} ({p['avg_overall']})"
            for p in players
        )

        print(f"{position:3} -> {text}")

    print()


def print_available_players(players):

    print("\nJUGADORES DISPONIBLES")
    print("------------------------------------------------")

    for idx, player in enumerate(players, start=1):

        print(
            f"{idx:2d}. "
            f"{player['player_name'][:30]:<30} "
            f"{player['tactical_position']:<3} "
            f"OVR {player['avg_overall']}"
        )

    print()


def calculate_team_score(selected_positions):

    total = 0
    count = 0

    for players in selected_positions.values():

        for player in players:
            total += player["avg_overall"]
            count += 1

    return round(total / count, 2)


def get_team_percentile(conn, league_id, strength):

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN team_strength <= ?
                    THEN 1
                    ELSE 0
                END
            ) AS below_or_equal
        FROM team_strength
        WHERE league_id = ?
    """, (strength, league_id))

    row = cursor.fetchone()

    total = row["total"] or 0
    below = row["below_or_equal"] or 0

    if total == 0:
        return 0

    return round(
        100.0 * below / total,
        2
    )


def simulate_points(percentile):

    return round(
        20 + 70 * (percentile / 100) ** 1.4
    )


def estimate_position(percentile):

    return max(
        1,
        min(
            20,
            round(
                20 - (percentile / 100) * 19
            )
        )
    )


def estimate_record(points):

    best = None

    for wins in range(39):

        for draws in range(39 - wins):

            losses = 38 - wins - draws

            if wins * 3 + draws != points:
                continue

            score = abs(
                draws - (38 - wins) * 0.25
            )

            if best is None or score < best[0]:
                best = (
                    score,
                    wins,
                    draws,
                    losses
                )

    return best[1], best[2], best[3]


def get_season_comment(position):

    if position == 1:
        return "Has ganado la liga."

    if position <= 4:
        return "Clasificación para Champions."

    if position <= 6:
        return "Clasificación europea."

    if position <= 10:
        return "Buena temporada."

    if position <= 14:
        return "Temporada tranquila."

    if position <= 17:
        return "Salvación sufrida."

    if position == 18:
        return "Has descendido."

    if position == 19:
        return "Te han destituido."

    return "Descenso catastrófico."


def get_neighbor_teams(conn, league_id, strength):

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            team_name,
            lustrum_start,
            team_strength
        FROM team_strength
        WHERE league_id = ?
          AND team_strength > ?
        ORDER BY team_strength
        LIMIT 1
    """, (league_id, strength))

    above = cursor.fetchone()

    cursor.execute("""
        SELECT
            team_name,
            lustrum_start,
            team_strength
        FROM team_strength
        WHERE league_id = ?
          AND team_strength < ?
        ORDER BY team_strength DESC
        LIMIT 1
    """, (league_id, strength))

    below = cursor.fetchone()

    return above, below


def main():

    conn = get_connection()

    league = select_league(conn)

    selected_players = set()

    selected_positions = {
        position: []
        for position in FORMATION
    }

    round_number = 1

    while not squad_complete(selected_positions):

        available_players = []

        while not available_players:

            team = get_random_team(
                conn,
                league["league_id"]
            )

            players = get_players(
                conn,
                team["lustrum_start"],
                team["league_id"],
                team["team_name"]
            )

            available_players = build_available_players(
                players,
                selected_players,
                selected_positions
            )

        print("\n" + "=" * 50)
        print(f"RONDA {round_number}/11")
        print("=" * 50)

        print(f"Liga   : {team['league_name']}")
        print(
            f"Lustro : "
            f"{team['lustrum_start']}-"
            f"{team['lustrum_start'] + 4}"
        )
        print(f"Equipo : {team['team_name']}")

        print_formation(selected_positions)

        print_available_players(
            available_players
        )

        while True:

            try:
                choice = int(
                    input(
                        "Selecciona jugador: "
                    )
                ) - 1

                if 0 <= choice < len(available_players):
                    break

            except ValueError:
                pass

            print("Opción no válida.")

        player = available_players[choice]

        selected_players.add(
            player["player_id"]
        )

        selected_positions[
            player["tactical_position"]
        ].append(player)

        round_number += 1

    print("\n" + "=" * 70)
    print("XI COMPLETADO")
    print("=" * 70)

    for position in FORMATION:

        for player in selected_positions[position]:

            print(
                f"{position:3} "
                f"{player['player_name'][:25]:<25} "
                f"{player['team_name'][:18]:<18} "
                f"{player['lustrum_start']}-{player['lustrum_start'] + 4} "
                f"OVR {player['avg_overall']}"
            )

    team_strength = calculate_team_score(
        selected_positions
    )

    percentile = get_team_percentile(
        conn,
        league["league_id"],
        team_strength
    )

    points = simulate_points(percentile)

    position = estimate_position(
        percentile
    )

    wins, draws, losses = estimate_record(
        points
    )

    comment = get_season_comment(
        position
    )

    above_team, below_team = get_neighbor_teams(
        conn,
        league["league_id"],
        team_strength
    )

    print("-" * 70)
    print(f"FUERZA DEL EQUIPO : {team_strength}")

    print("\nTEMPORADA SIMULADA")
    print("-" * 70)

    print(
        f"{wins}V "
        f"{draws}E "
        f"{losses}D"
    )

    print(f"\n{points} puntos")

    print(
        f"Posición final: "
        f"{position}º"
    )

    print(comment)

    print("\nREFERENCIAS HISTÓRICAS")
    print("-" * 70)

    if above_team:

        print(
            f"Por encima : "
            f"{above_team['team_name']} "
            f"({above_team['lustrum_start']}-{above_team['lustrum_start'] + 4}) "
            f"[{above_team['team_strength']}]"
        )

    print(
        f"Tu equipo  : "
        f"[{team_strength}]"
    )

    if below_team:

        print(
            f"Por debajo : "
            f"{below_team['team_name']} "
            f"({below_team['lustrum_start']}-{below_team['lustrum_start'] + 4}) "
            f"[{below_team['team_strength']}]"
        )

    conn.close()


if __name__ == "__main__":
    main()