import sqlite3
import random
from collections import defaultdict
import streamlit as st
from streamlit.components.v1 import html
from streamlit_javascript import st_javascript

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
    "LB": [(25, 72)],
    "CB": [(42, 76), (58, 76)],
    "RB": [(75, 72)],
    "CM": [(30, 52), (50, 46), (70, 52)],
    "LW": [(25, 25)],
    "RW": [(75, 25)],
    "ST": [(50, 12)],
}

POSITION_ORDER = ["GK", "LB", "CB", "RB", "CM", "LW", "RW", "ST"]


@st.cache_resource
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_leagues(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT league_id, league_name
        FROM player_lustrum_ratings
        ORDER BY league_name
    """)
    return [dict(r) for r in cur.fetchall()]


def get_random_team(conn, league_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT lustrum_start, league_id, league_name, team_name
        FROM player_lustrum_ratings
        WHERE league_id = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (league_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_players(conn, lustrum_start, league_id, team_name):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT player_id, player_name, tactical_position,
               avg_overall, team_name, lustrum_start
        FROM player_lustrum_ratings
        WHERE lustrum_start = ?
          AND league_id = ?
          AND team_name = ?
          AND tactical_position IS NOT NULL
        ORDER BY avg_overall DESC
    """, (lustrum_start, league_id, team_name))
    return [dict(r) for r in cur.fetchall()]

def get_team_asset(conn, team_name, lustrum_start):

    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT logo_url, kit_url
            FROM team_assets
            WHERE team_name = ?
              AND lustrum_start = ?
            LIMIT 1
        """, (team_name, lustrum_start))

        row = cur.fetchone()

        return dict(row) if row else {
            "logo_url": None,
            "kit_url": None
        }

    except Exception as e:
        st.error(f"ERROR TEAM_ASSETS: {e}")
        raise

#def get_team_asset(conn, team_name, lustrum_start):
#      cur = conn.cursor()
#    cur.execute("""
#        SELECT logo_url, kit_url
#        FROM team_assets
#        WHERE team_name = ?
#          AND lustrum_start = ?
#        LIMIT 1
#    """, (team_name, lustrum_start))
#    row = cur.fetchone()
#    return dict(row) if row else {"logo_url": None, "kit_url": None}


def squad_complete(selected_positions):

    return all(len(selected_positions[p]) >= req for p, req in FORMATION.items())


def build_available_players(players, selected_players, selected_positions):
    available = []
    for player in players:
        if player["player_id"] in selected_players:
            continue
        pos = player["tactical_position"]
        if pos not in FORMATION:
            continue
        if len(selected_positions[pos]) >= FORMATION[pos]:
            continue
        available.append(player)
    return available


def calculate_team_score(selected_positions):
    vals = []
    for plist in selected_positions.values():
        vals.extend([p["avg_overall"] for p in plist])
    return round(sum(vals) / len(vals), 2)


def get_team_percentile(conn, league_id, strength):
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) total,
               SUM(CASE WHEN team_strength <= ? THEN 1 ELSE 0 END) below_or_equal
        FROM team_strength
        WHERE league_id = ?
    """, (strength, league_id))
    row = cur.fetchone()
    total = row["total"] or 0
    below = row["below_or_equal"] or 0
    return 0 if total == 0 else round(100 * below / total, 2)


def simulate_points(percentile):
    return round(20 + 70 * (percentile / 100) ** 1.4)


def estimate_position(percentile):
    return max(1, min(20, round(20 - (percentile / 100) * 19)))


def estimate_record(points):
    best = None
    for wins in range(39):
        for draws in range(39 - wins):
            losses = 38 - wins - draws
            if wins * 3 + draws != points:
                continue
            score = abs(draws - (38 - wins) * 0.25)
            if best is None or score < best[0]:
                best = (score, wins, draws, losses)
    return best[1], best[2], best[3]


def get_season_comment(position):
    if position == 1: return "🏆 Has ganado la liga."
    if position <= 4: return "⭐ Clasificación para Champions."
    if position <= 6: return "🏅 Clasificación europea."
    if position <= 10: return "👍 Buena temporada."
    if position <= 14: return "😌 Temporada tranquila."
    if position <= 17: return "😰 Salvación sufrida."
    if position == 18: return "📉 Has descendido."
    if position == 19: return "🚨 Te han destituido."
    return "💀 Descenso catastrófico."


def get_neighbor_teams(conn, league_id, strength):
    cur = conn.cursor()

    cur.execute("""
        SELECT team_name,lustrum_start,team_strength
        FROM team_strength
        WHERE league_id=? AND team_strength > ?
        ORDER BY team_strength
        LIMIT 1
    """, (league_id, strength))
    above = cur.fetchone()

    cur.execute("""
        SELECT team_name,lustrum_start,team_strength
        FROM team_strength
        WHERE league_id=? AND team_strength < ?
        ORDER BY team_strength DESC
        LIMIT 1
    """, (league_id, strength))
    below = cur.fetchone()

    return above, below


def initialize_game():
    st.session_state.selected_players = set()
    st.session_state.selected_positions = {p: [] for p in FORMATION}
    st.session_state.round = 1
    st.session_state.current_team = None
    st.session_state.current_players = []
    st.session_state.spinning = False
    st.session_state.page = "draft"



def load_random_team(conn):

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
            team_asset = get_team_asset(
                conn,
                team["team_name"],
                team["lustrum_start"]
            )
            team["logo_url"] = team_asset.get("logo_url")
            team["kit_url"] = team_asset.get("kit_url")
            st.session_state.current_team = team
            st.session_state.current_players = available
            return


def render_pitch(selected_positions):

    def ovr_color(ovr):
        if ovr >= 90:
            return "#2e7d32"   # verde
        elif ovr >= 80:
            return "#f57c00"   # naranja
        elif ovr >= 70:
            return "#fbc02d"   # amarillo
        else:
            return "#d32f2f"   # rojo

    pitch = """
    <div style="
        position:relative;
        width:100%;
        height:700px;
        background:
            repeating-linear-gradient(
                0deg,
                #1d8f3e 0px,
                #1d8f3e 80px,
                #239b45 80px,
                #239b45 160px
            );
        border:4px solid white;
        border-radius:12px;
        overflow:hidden;
    ">

        <div style="
            position:absolute;
            bottom:0;
            left:20%;
            width:60%;
            height:22%;
            border:3px solid white;
            box-sizing:border-box;
        "></div>

        <div style="
            position:absolute;
            bottom:0;
            left:35%;
            width:30%;
            height:10%;
            border:3px solid white;
            box-sizing:border-box;
        "></div>

        <div style="
            position:absolute;
            bottom:16%;
            left:50%;
            width:8px;
            height:8px;
            background:white;
            border-radius:50%;
            transform:translate(-50%,50%);
        "></div>

        <div style="
            position:absolute;
            bottom:13%;
            left:50%;
            width:88px;
            height:60px;
            border:3px solid white;
            border-bottom:none;
            border-radius:120px 120px 0 0;
            transform:translateX(-50%);
        "></div>

        <div style="
            position:absolute;
            top:0;
            left:0;
            width:100%;
            height:3px;
            background:white;
        "></div>

        <div style="
            position:absolute;
            top:-70px;
            left:50%;
            width:140px;
            height:140px;
            border:3px solid white;
            border-radius:50%;
            transform:translateX(-50%);
        "></div>
    """

    for pos, players in selected_positions.items():

        for idx, (x, y) in enumerate(FIELD_SLOTS[pos]):

            if idx < len(players):

                p = players[idx]
                color = ovr_color(float(p["avg_overall"]))

                kit_html = ""
                if p.get("kit_url"):
                    kit_html = f'<img src="{p["kit_url"]}" style="height:70px;margin-bottom:4px;">'

                label = f"""
                {kit_html}
                <div style="
                    font-weight:700;
                    font-size:7px;
                    color:#111;
                    margin-bottom:2px;
                ">
                    {p['player_name']}
                </div>

                <div style="
                    font-size:8px;
                    color:#666;
                    margin-bottom:1px;
                ">
                    {p['team_name']}
                </div>

                <div style="
                    font-size:7px;
                    color:#777;
                    margin-bottom:4px;
                ">
                    {p['lustrum_start']}-{p['lustrum_start'] + 4}
                </div>

                <span style="
                    background:{color};
                    color:white;
                    padding:3px 8px;
                    border-radius:6px;
                    font-weight:700;
                    font-size:11px;
                ">
                    OVR {round(p['avg_overall'])}
                </span>
                """

                pitch += f"""
                <div style="
                    position:absolute;
                    left:{x}%;
                    top:{y}%;
                    transform:translate(-50%,-50%);
                    background:white;
                    border-radius:12px;
                    width:88px;
                    padding:4px;
                    text-align:center;
                    box-shadow:0 3px 8px rgba(0,0,0,.25);
                ">
                    {label}
                </div>
                """

            else:

                pitch += f"""
                <div style="
                    position:absolute;
                    left:{x}%;
                    top:{y}%;
                    transform:translate(-50%,-50%);
                    background:rgba(255,255,255,.75);
                    border-radius:8px;
                    width:60px;
                    padding:4px;
                    text-align:center;
                    font-size:8px;
                    font-weight:700;
                ">
                    {pos}
                </div>
                """

    pitch += "</div>"

    html(pitch, height=730)


st.set_page_config(page_title="Draft Histórico", layout="wide")

conn = get_connection()

if "page" not in st.session_state:
    st.session_state.page = "league"

if st.session_state.page == "league":

    st.title("⚽ Draft Histórico")

    leagues = get_leagues(conn)

    league_name = st.selectbox(
        "Selecciona una liga",
        [l["league_name"] for l in leagues]
    )

    if st.button("Comenzar Draft", type="primary", use_container_width=True):
        st.session_state.league = next(
            l for l in leagues if l["league_name"] == league_name
        )
        initialize_game()
        st.rerun()

elif st.session_state.page == "draft":

    if st.session_state.get("scroll_top", False):
        st_javascript("""
            window.scrollTo({
            top: 0,
            behavior: 'instant'});
            """)

        st.session_state.scroll_top = False


    if st.session_state.current_team is None:

        st.markdown("## 🎰 Sorteo de equipo")

        slot = st.empty()

        if st.button(
            "Girar ruleta",
            type="primary",
            use_container_width=True
        ):

            import time

            for _ in range(25):

                fake_team = get_random_team(
                    conn,
                    st.session_state.league["league_id"]
                )

                fake_asset = get_team_asset(conn,fake_team['team_name'],fake_team['lustrum_start'])
                logo = fake_asset.get('logo_url') or ''
                slot.markdown(
                    f"""
                    <div style="
                        background:#111;
                        color:white;
                        text-align:center;
                        padding:20px;
                        border-radius:12px;
                        font-size:32px;
                        font-weight:700;
                    ">
                        <div style="display:flex;gap:20px;justify-content:center;align-items:center;">
                          <div style="background:#222;padding:15px;border-radius:10px;min-width:140px;">
                            <img src="{logo}" style="height:80px;">
                          </div>
                          <div style="background:#222;padding:15px;border-radius:10px;min-width:140px;">
                            {fake_team['lustrum_start']}-{fake_team['lustrum_start']+4}
                          </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                time.sleep(0.08)

            load_random_team(conn)

            st.rerun()

        st.stop()

    team = st.session_state.current_team

    st.subheader(f"Ronda {st.session_state.round}/11")

    c_logo, c_title = st.columns([1,5])
    with c_logo:
        if team.get("logo_url"):
            st.image(team["logo_url"], width=80)
    with c_title:
        st.markdown(f"# {team['team_name']}")
        st.caption(f"{team['lustrum_start']}-{team['lustrum_start'] + 4}")

    render_pitch(st.session_state.selected_positions)

    st.metric(
        "Jugadores disponibles",
        len(st.session_state.current_players)
    )

    st.markdown("---")

    grouped = defaultdict(list)
    for player in st.session_state.current_players:
        grouped[player["tactical_position"]].append(player)

    for pos in POSITION_ORDER:

        players = grouped.get(pos, [])

        if not players:
            continue

        st.markdown(f"## {pos}")

        for i in range(0, len(players), 6):

            row_players = players[i:i + 6]
            cols = st.columns(6)

            for col, player in zip(cols, row_players):

                with col:

                    with st.container(border=True):

                        st.markdown(
                            f"**{player['player_name']}**  \n"
                            f"OVR {player['avg_overall']:.1f}"
                        )

                        if st.button(
                            "Elegir",
                            key=(
                                f"pick_"
                                f"{player['lustrum_start']}_"
                                f"{team['league_id']}_"
                                f"{player['team_name']}_"
                                f"{player['player_name']}_"
                                f"{player['tactical_position']}_"
                                f"{player['player_id']}"
                                )
                            ):

                                st.session_state.selected_players.add(player["player_id"])
                                
                                asset = get_team_asset(
                                    conn,
                                    player["team_name"],
                                    player["lustrum_start"]
                                )
                                player["logo_url"] = asset.get("logo_url")
                                player["kit_url"] = asset.get("kit_url")

                                st.session_state.selected_positions[player["tactical_position"]].append(player)


                                st.session_state.round += 1
                                st.session_state.current_team = None
                                st.session_state.current_players = []

                                if squad_complete(st.session_state.selected_positions):
                                    st.session_state.page = "results"

                                st.components.v1.html(
                                    """
                                        <script>
                                          window.parent.scrollTo(0, 0);
                                        </script>
                                    """,
                                    height=0,
                                )       

                                st.session_state.scroll_top = True
                                
                                st.rerun()

elif st.session_state.page == "results":

    st.title("🏆 XI COMPLETADO")

    render_pitch(st.session_state.selected_positions)

    strength = calculate_team_score(st.session_state.selected_positions)

    percentile = get_team_percentile(
        conn,
        st.session_state.league["league_id"],
        strength
    )

    points = simulate_points(percentile)
    position = estimate_position(percentile)
    wins, draws, losses = estimate_record(points)

    st.success(get_season_comment(position))

    st.subheader("Temporada")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Ovrall", strength)
    c2.metric("Puntos", points)
    c3.metric("Posición", f"{position}º")
    c4.metric("Balance", f"{wins}-{draws}-{losses}")


    above_team, below_team = get_neighbor_teams(
        conn,
        st.session_state.league["league_id"],
        strength
    )

    if above_team:
        st.write(f"⬆️ {above_team['team_name']} ({above_team['lustrum_start']}-{above_team['lustrum_start']+4}) [{above_team['team_strength']}]")

    st.write(f"⭐ Tu equipo [{strength}]")

    if below_team:
        st.write(f"⬇️ {below_team['team_name']} ({below_team['lustrum_start']}-{below_team['lustrum_start']+4}) [{below_team['team_strength']}]")

    if st.button("Nuevo Draft", use_container_width=True):
        st.session_state.page = "league"
        st.rerun()
