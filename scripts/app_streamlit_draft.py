from collections import defaultdict
import sqlite3
import streamlit as st
from streamlit.components.v1 import html

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

FIELD_SLOTS = {
    "GK": [(50, 88)],
    "LB": [(18, 70)],
    "CB": [(40, 70), (60, 70)],
    "RB": [(82, 70)],
    "CM": [(30, 48), (50, 42), (70, 48)],
    "LW": [(20, 22)],
    "RW": [(80, 22)],
    "ST": [(50, 12)],
}


# ==================================================
# DATABASE
# ==================================================

@st.cache_resource
def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def get_leagues(conn):

    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT
            league_id,
            league_name
        FROM player_lustrum_ratings
        ORDER BY league_name
    """)

    return [
        dict(r)
        for r in cur.fetchall()
    ]


def get_random_team(conn, league_id):

    cur = conn.cursor()

    cur.execute("""
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

    row = cur.fetchone()

    return dict(row) if row else None


def get_players(
    conn,
    lustrum_start,
    league_id,
    team_name
):

    cur = conn.cursor()

    cur.execute("""
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
        ORDER BY avg_overall DESC
    """, (
        lustrum_start,
        league_id,
        team_name
    ))

    return [
        dict(r)
        for r in cur.fetchall()
    ]


# ==================================================
# GAME
# ==================================================

def squad_complete(selected_positions):

    return all(
        len(selected_positions[pos]) >= required
        for pos, required
        in FORMATION.items()
    )


def build_available_players(
    players,
    selected_players,
    selected_positions
):

    available = []

    for player in players:

        if player["player_id"] in selected_players:
            continue

        pos = player["tactical_position"]

        if pos not in FORMATION:
            continue

        if (
            len(selected_positions[pos])
            >= FORMATION[pos]
        ):
            continue

        available.append(player)

    return available


def calculate_team_score(selected_positions):

    total = []

    for players in selected_positions.values():

        total.extend(
            p["avg_overall"]
            for p in players
        )

    return round(
        sum(total) / len(total),
        2
    )


def get_team_percentile(
    conn,
    league_id,
    strength
):

    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) total,
            SUM(
                CASE
                    WHEN team_strength <= ?
                    THEN 1
                    ELSE 0
                END
            ) below_or_equal
        FROM team_strength
        WHERE league_id = ?
    """, (
        strength,
        league_id
    ))

    row = cur.fetchone()

    total = row["total"] or 0
    below = row["below_or_equal"] or 0

    if total == 0:
        return 0

    return round(
        100 * below / total,
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

            if (
                best is None
                or score < best[0]
            ):
                best = (
                    score,
                    wins,
                    draws,
                    losses
                )

    return (
        best[1],
        best[2],
        best[3]
    )


def get_season_comment(position):

    if position == 1:
        return "🏆 Has ganado la liga."

    if position <= 4:
        return "⭐ Clasificación para Champions."

    if position <= 6:
        return "🏅 Clasificación europea."

    if position <= 10:
        return "👍 Buena temporada."

    if position <= 14:
        return "😌 Temporada tranquila."

    if position <= 17:
        return "😰 Salvación sufrida."

    if position == 18:
        return "📉 Has descendido."

    if position == 19:
        return "🚨 Te han destituido."

    return "💀 Descenso catastrófico."


def get_neighbor_teams(
    conn,
    league_id,
    strength
):

    cur = conn.cursor()

    cur.execute("""
        SELECT
            team_name,
            lustrum_start,
            team_strength
        FROM team_strength
        WHERE league_id = ?
          AND team_strength > ?
        ORDER BY team_strength
        LIMIT 1
    """, (
        league_id,
        strength
    ))

    above = cur.fetchone()

    cur.execute("""
        SELECT
            team_name,
            lustrum_start,
            team_strength
        FROM team_strength
        WHERE league_id = ?
          AND team_strength < ?
        ORDER BY team_strength DESC
        LIMIT 1
    """, (
        league_id,
        strength
    ))

    below = cur.fetchone()

    return above, below


# ==================================================
# SESSION
# ==================================================

def initialize_game():

    st.session_state.selected_players = set()

    st.session_state.selected_positions = {
        pos: []
        for pos in FORMATION
    }

    st.session_state.round = 1
    st.session_state.current_team = None
    st.session_state.current_players = []
    st.session_state.page = "draft"


# ==================================================
# FIELD
# ==================================================

def render_pitch(selected_positions):

    pitch = """
    <div style="
        position:relative;
        width:100%;
        height:500px;
        background:#17853b;
        border:4px solid white;
        border-radius:12px;
    ">

    <div style="
        position:absolute;
        top:50%;
        width:100%;
        border-top:2px solid white;">
    </div>

    <div style="
        position:absolute;
        left:40%;
        top:40%;
        width:20%;
        height:20%;
        border:2px solid white;
        border-radius:50%;">
    </div>
    """

    for pos, players in selected_positions.items():

        slots = FIELD_SLOTS[pos]

        for idx, (x, y) in enumerate(slots):

            if idx < len(players):

                p = players[idx]

                label = (
                    f"{p['player_name']}"
                    f"<br>"
                    f"<small>"
                    f"OVR {p['avg_overall']}"
                    f"</small>"
                )

                bg = "#ffffff"

            else:

                label = pos
                bg = "#d9d9d9"

            pitch += f"""
            <div style="
                position:absolute;
                left:{x}%;
                top:{y}%;
                transform:translate(-50%,-50%);
                background:{bg};
                padding:8px;
                border-radius:8px;
                width:120px;
                text-align:center;
                font-size:12px;
                font-weight:bold;
            ">
                {label}
            </div>
            """

    pitch += "</div>"

    html(
        pitch,
        height=520
    )


# ==================================================
# APP
# ==================================================

st.set_page_config(
    page_title="Draft Histórico",
    layout="wide"
)

conn = get_connection()

if "page" not in st.session_state:
    st.session_state.page = "league"

# ==================================================
# LEAGUE SCREEN
# ==================================================

if st.session_state.page == "league":

    st.title("⚽ Draft Histórico")

    leagues = get_leagues(conn)

    league_name = st.selectbox(
        "Selecciona una liga",
        [
            l["league_name"]
            for l in leagues
        ]
    )

    if st.button(
        "Comenzar Draft",
        type="primary",
        use_container_width=True
    ):

        st.session_state.league = next(
            l
            for l in leagues
            if l["league_name"] == league_name
        )

        initialize_game()

        st.rerun()

# ==================================================
# DRAFT
# ==================================================

elif st.session_state.page == "draft":

    if st.session_state.current_team is None:

        while True:

            team = get_random_team(
                conn,
                st.session_state.league["league_id"]
            )

            players = get_players(
                conn,
                team["lustrum_start"],
                team["league_id"],
                team["team_name"]
            )

            available = build_available_players(
                players,
                st.session_state.selected_players,
                st.session_state.selected_positions
            )

            if available:

                st.session_state.current_team = team
                st.session_state.current_players = available

                break

    st.subheader(
    f"Ronda {st.session_state.round}/11"
)

render_pitch(
    st.session_state.selected_positions
)

team = st.session_state.current_team

st.markdown("---")

st.subheader(team["team_name"])

st.caption(
    f"{team['lustrum_start']}-{team['lustrum_start']+4}"
)

st.metric(
    "Jugadores disponibles",
    len(st.session_state.current_players)
)

        for pos in position_order:

    players = grouped.get(pos, [])

    if not players:
        continue

    st.markdown(f"## {pos}")

    players = sorted(
        players,
        key=lambda x: x["avg_overall"],
        reverse=True
    )

    CARDS_PER_ROW = 4

    for i in range(
        0,
        len(players),
        CARDS_PER_ROW
    ):

        row_players = players[
            i:i + CARDS_PER_ROW
        ]

        cols = st.columns(
            len(row_players)
        )

        for col, player in zip(
            cols,
            row_players
        ):

            with col:

                with st.container(
                    border=True
                ):

                    st.write(
                        f"**{player['player_name']}**"
                    )

                    st.caption(
                        f"OVR {player['avg_overall']}"
                    )

                    if st.button(
                        "Elegir",
                        key=(
                            f"pick_"
                            f"{pos}_"
                            f"{i}_"
                            f"{player['player_id']}_"
                            f"{player['player_name']}"
                        )
                    ):

                        st.session_state.selected_players.add(
                            player["player_id"]
                        )

                        st.session_state.selected_positions[
                            player["tactical_position"]
                        ].append(player)

                        st.session_state.round += 1

                        st.session_state.current_team = None
                        st.session_state.current_players = []

                        if squad_complete(
                            st.session_state.selected_positions
                        ):
                            st.session_state.page = "results"

                        st.rerun()

# ==================================================
# RESULTS
# ==================================================

elif st.session_state.page == "results":

    st.title(
        "🏆 XI COMPLETADO"
    )

    render_pitch(
        st.session_state.selected_positions
    )

    team_strength = calculate_team_score(
        st.session_state.selected_positions
    )

    percentile = get_team_percentile(
        conn,
        st.session_state.league["league_id"],
        team_strength
    )

    points = simulate_points(
        percentile
    )

    position = estimate_position(
        percentile
    )

    wins, draws, losses = estimate_record(
        points
    )

    comment = get_season_comment(
        position
    )

    above_team, below_team = (
        get_neighbor_teams(
            conn,
            st.session_state.league["league_id"],
            team_strength
        )
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Fuerza",
        team_strength
    )

    c2.metric(
        "Puntos",
        points
    )

    c3.metric(
        "Posición",
        f"{position}º"
    )

    st.success(comment)

    st.subheader("Temporada")

    st.write(
        f"**{wins}V - "
        f"{draws}E - "
        f"{losses}D**"
    )

    st.subheader(
        "Referencias históricas"
    )

    if above_team:

        st.write(
            f"⬆️ "
            f"{above_team['team_name']} "
            f"({above_team['lustrum_start']}"
            f"-"
            f"{above_team['lustrum_start']+4}) "
            f"[{above_team['team_strength']}]"
        )

    st.write(
        f"⭐ Tu equipo "
        f"[{team_strength}]"
    )

    if below_team:

        st.write(
            f"⬇️ "
            f"{below_team['team_name']} "
            f"({below_team['lustrum_start']}"
            f"-"
            f"{below_team['lustrum_start']+4}) "
            f"[{below_team['team_strength']}]"
        )

    if st.button(
        "Nuevo Draft",
        use_container_width=True
    ):

        st.session_state.page = "league"
        st.rerun()