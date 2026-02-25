# ============================================
# ORG FUSION - FILAS + MATCH (UNIFICADO FINAL V3 + /setwin + /p)
# ============================================

import os
import asyncio
import sqlite3
import discord
from discord.ext import commands

import os
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)

# IMAGENS (URL)
LOGO_URL = "https://cdn.discordapp.com/attachments/1464089319387168838/1475902292988395846/IMG_1983.png?ex=699f2c9f&is=699ddb1f&hm=f9fd6252bc60b1efe0140eb02a4045163119368fae4f91a80ff011b731e65227&"

# QR NOVO
QR_CODE_URL = "https://cdn.discordapp.com/attachments/1475930796295458847/1475930821448826960/868A3B94-92F5-4060-AA85-A38F5D152B9C.jpg?ex=699f4731&is=699df5b1&hm=30438a2680d40ff0c65b18d819e3803e9a5fa7c607900d2e7657ec9d71f4b6c2&"

# PIX
PIX_EMAIL = "orgfusionapostados@gmail.com"

# Valores
VALORES = [2, 3, 5, 10, 20, 50, 100]

# Categorias / Canais
CAT_FILAS = "🎮-filas-por-jogo"
CAT_PARTIDAS = "🎯-sua-partida"
CH_RESULTADOS = "resultados"

CH_FC2425 = "1x1-ea-sports-fc-24-25"
CH_FC26   = "1x1-ea-sports-fc-26"
CH_MOBILE = "1x1-ea-sports-fc-mobile"
CH_2X2_FC26 = "2x2-ea-sports-fc-26"
CH_PROCLUBS = "pro-clubs-ea-fc-26"

# Games
GAME_2425 = "fc2425"
GAME_26   = "fc26"
GAME_MOB  = "mobile"
GAME_26_2X2 = "fc26_2x2"
GAME_PROCLUBS = "proclubs"

# Match
CONFIRM_TIMEOUT = 90        # 1:30
END_PROMPT_TIME = 600       # 10 min

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# chave: (gid, game, valor, gen)
queues = {}   # (gid, game, valor, gen) -> [uid]
locks  = {}   # uid -> (gid, game, valor, gen) OU ("match", gid)
matches = {}  # ch_id -> state

# ============================================
# STATS (SQLite)
# ============================================
DB_PATH = "fusion.sqlite"

def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_stats (
        user_id INTEGER PRIMARY KEY,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0
    )
    """)
    con.commit()
    con.close()

def db_add_win(uid: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    INSERT INTO player_stats (user_id, wins, losses)
    VALUES (?, 1, 0)
    ON CONFLICT(user_id) DO UPDATE SET wins = wins + 1
    """, (uid,))
    con.commit()
    con.close()

def db_add_loss(uid: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    INSERT INTO player_stats (user_id, wins, losses)
    VALUES (?, 0, 1)
    ON CONFLICT(user_id) DO UPDATE SET losses = losses + 1
    """, (uid,))
    con.commit()
    con.close()

def db_get_stats(uid: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT wins, losses FROM player_stats WHERE user_id = ?", (uid,))
    row = cur.fetchone()
    con.close()
    if not row:
        return (0, 0)
    return (int(row[0]), int(row[1]))


# ============================================
# HELPERS
# ============================================
def is_admin(m: discord.Member) -> bool:
    return m.guild_permissions.administrator or m.guild.owner_id == m.id

def qkey(gid: int, game: str, valor: int, gen=None):
    return (gid, game, valor, gen)

def mode_label(game: str) -> str:
    if game == GAME_MOB:
        return "1v1 Mobile"
    if game == GAME_26_2X2:
        return "2x2 EA SPORTS FC 26"
    if game == GAME_PROCLUBS:
        return "ProClubs EA SPORTS FC 26"
    return "1x1 Console"

def title_game(game: str) -> str:
    return {
        GAME_2425: "EA SPORTS FC 24/25",
        GAME_26: "EA SPORTS FC 26",
        GAME_MOB: "EA FC MOBILE",
        GAME_26_2X2: "EA SPORTS FC 26 (2x2)",
        GAME_PROCLUBS: "PRO CLUBS EA SPORTS FC 26",
    }.get(game, game)

def format_brl(v: int) -> str:
    return f"R$ {v}"

def make_bar(wins: int, losses: int, size: int = 10) -> str:
    total = wins + losses
    if total <= 0:
        return "⬛" * size
    win_blocks = round((wins / total) * size)
    win_blocks = max(0, min(size, win_blocks))
    loss_blocks = size - win_blocks
    return ("🟩" * win_blocks) + ("🟥" * loss_blocks)

async def fetch_member(guild: discord.Guild, uid: int):
    m = guild.get_member(uid)
    if m:
        return m
    try:
        return await guild.fetch_member(uid)
    except:
        return None

async def get_or_create_category(guild: discord.Guild, name: str):
    cat = discord.utils.get(guild.categories, name=name)
    if cat:
        return cat
    return await guild.create_category(name=name)

async def get_or_create_channel(guild: discord.Guild, name: str, category: discord.CategoryChannel):
    ch = discord.utils.get(guild.text_channels, name=name)
    if ch:
        return ch
    return await guild.create_text_channel(name=name, category=category)

async def ensure_result_channel(guild: discord.Guild):
    cat = await get_or_create_category(guild, CAT_PARTIDAS)
    ch = discord.utils.get(guild.text_channels, name=CH_RESULTADOS)
    if not ch:
        await guild.create_text_channel(CH_RESULTADOS, category=cat)

async def log_result(guild: discord.Guild, text: str):
    ch = discord.utils.get(guild.text_channels, name=CH_RESULTADOS)
    if ch:
        await ch.send(text)

async def delete_all_messages(channel: discord.TextChannel):
    while True:
        msgs = [m async for m in channel.history(limit=100)]
        if not msgs:
            break
        for m in msgs:
            try:
                await m.delete()
            except:
                pass
        await asyncio.sleep(0.2)

async def close_match_channel(guild: discord.Guild, ch: discord.TextChannel):
    """Fecha a match do canal atual, destrava players e apaga o canal."""
    st = matches.get(ch.id)
    if not st:
        return False

    for uid in st["players"]:
        locks.pop(uid, None)

    matches.pop(ch.id, None)

    try:
        await log_result(guild, f"🔒 MATCH FECHADA #{ch.name}")
    except:
        pass

    try:
        await ch.delete()
    except:
        pass

    return True


# ============================================
# FILAS — EMBED + VIEW
# ============================================
async def make_card_embed(guild: discord.Guild, game: str, valor: int):
    e = discord.Embed(
        title=f"{mode_label(game)} | ORG FUSION",
        color=0x00FF44
    )
    e.set_thumbnail(url=LOGO_URL)
    e.add_field(name="Valor", value=format_brl(valor), inline=False)

    if game in (GAME_2425, GAME_26):
        q_old = queues.get(qkey(guild.id, game, valor, "old"), [])
        q_new = queues.get(qkey(guild.id, game, valor, "new"), [])

        def fmt(q):
            if not q:
                return "Nenhum jogador na fila."
            return "\n".join([f"<@{uid}>" for uid in q])

        e.add_field(name="Antiga Geração", value=fmt(q_old), inline=True)
        e.add_field(name="Nova Geração", value=fmt(q_new), inline=True)
        return e

    q = queues.get(qkey(guild.id, game, valor, None), [])
    players = "Nenhum jogador na fila." if not q else "\n".join([f"<@{uid}>" for uid in q])
    e.add_field(name="Jogadores", value=players, inline=False)
    return e

def make_card_view(game: str, valor: int):
    v = discord.ui.View(timeout=None)

    if game in (GAME_2425, GAME_26):
        v.add_item(discord.ui.Button(
            label="Antiga Geração",
            style=discord.ButtonStyle.primary,
            custom_id=f"join:{game}:{valor}:old"
        ))
        v.add_item(discord.ui.Button(
            label="Nova Geração",
            style=discord.ButtonStyle.success,
            custom_id=f"join:{game}:{valor}:new"
        ))
        v.add_item(discord.ui.Button(
            label="Sair da fila",
            style=discord.ButtonStyle.danger,
            custom_id=f"leave:{game}:{valor}"
        ))
        return v

    v.add_item(discord.ui.Button(
        label="Entrar na fila",
        style=discord.ButtonStyle.success,
        custom_id=f"join:{game}:{valor}"
    ))
    v.add_item(discord.ui.Button(
        label="Sair da fila",
        style=discord.ButtonStyle.danger,
        custom_id=f"leave:{game}:{valor}"
    ))
    return v

async def update_card_message(interaction: discord.Interaction, game: str, valor: int):
    try:
        emb = await make_card_embed(interaction.guild, game, valor)
        await interaction.message.edit(embed=emb, view=make_card_view(game, valor))
    except:
        pass


# ============================================
# MATCH — VIEWS
# ============================================
def match_confirm_view(ch_id: int):
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="✅ Confirmar", style=discord.ButtonStyle.success,
                                 custom_id=f"m:confirm:{ch_id}"))
    v.add_item(discord.ui.Button(label="❌ Cancelar", style=discord.ButtonStyle.danger,
                                 custom_id=f"m:cancel:{ch_id}"))
    return v

def match_finish_view(ch_id: int):
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="✅ Encerrar partida", style=discord.ButtonStyle.success,
                                 custom_id=f"m:finish:{ch_id}"))
    return v


# ============================================
# MATCH — TIMEOUT
# ============================================
async def match_timeout_watch(gid: int, ch_id: int):
    await asyncio.sleep(CONFIRM_TIMEOUT)

    st = matches.get(ch_id)
    if not st:
        return

    if len(st["confirmed"]) == 2:
        return

    guild = bot.get_guild(gid)
    if not guild:
        return

    ch = guild.get_channel(ch_id)
    if not ch:
        return

    for uid in st["players"]:
        locks.pop(uid, None)

    matches.pop(ch_id, None)

    try:
        await log_result(guild, f"⏳ TIMEOUT #{ch.name}")
        await ch.delete()
    except:
        pass


# ============================================
# MATCH — AFTER 10 MIN PROMPT (ADM)
# ============================================
async def match_end_prompt_watch(gid: int, ch_id: int):
    await asyncio.sleep(END_PROMPT_TIME)

    st = matches.get(ch_id)
    if not st:
        return

    guild = bot.get_guild(gid)
    if not guild:
        return

    ch = guild.get_channel(ch_id)
    if not ch:
        return

    msg = await ch.send("Partida já acabou? Defina o vencedor.", view=match_finish_view(ch_id))
    st["end_prompt_msg_id"] = msg.id


# ============================================
# MATCH — CREATE CHANNEL
# ============================================
async def create_match_channel(guild: discord.Guild, game: str, valor: int, p1: int, p2: int, gen=None):
    cat = await get_or_create_category(guild, CAT_PARTIDAS)
    await ensure_result_channel(guild)

    m1 = await fetch_member(guild, p1)
    m2 = await fetch_member(guild, p2)
    if not m1 or not m2:
        locks.pop(p1, None)
        locks.pop(p2, None)
        return

    bot._match_seq = getattr(bot, "_match_seq", 0) + 1
    seq = bot._match_seq

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
        m1: discord.PermissionOverwrite(view_channel=True),
        m2: discord.PermissionOverwrite(view_channel=True),
    }
    for r in guild.roles:
        if r.permissions.administrator:
            overwrites[r] = discord.PermissionOverwrite(view_channel=True)

    gen_tag = ""
    gen_line = ""
    if gen == "old":
        gen_tag = "-old"
        gen_line = "\nGeração: **Antiga**"
    elif gen == "new":
        gen_tag = "-new"
        gen_line = "\nGeração: **Nova**"

    ch_name = f"partida-{seq:03d}-{game}{gen_tag}-r{valor}".lower()
    ch = await guild.create_text_channel(ch_name, category=cat, overwrites=overwrites)

    matches[ch.id] = {
        "guild_id": guild.id,
        "game": game,
        "valor": valor,
        "gen": gen,
        "players": [p1, p2],
        "confirmed": set(),
        "status": "aguardando",
        "control_msg_id": None,
        "pix_sent": False,
        "end_prompt_msg_id": None,
    }

    emb = discord.Embed(
        title="🎯 Partida criada",
        description=(
            f"Jogo: **{title_game(game)}**{gen_line}\n"
            f"Valor: **{format_brl(valor)}**\n"
            f"{m1.mention} vs {m2.mention}\n\n"
            f"⏳ Confirmação obrigatória dos 2.\n"
            f"⏳ Tempo: 1min30."
        ),
        color=0x00FF44
    )
    emb.set_thumbnail(url=LOGO_URL)

    msg = await ch.send(embed=emb, view=match_confirm_view(ch.id))
    matches[ch.id]["control_msg_id"] = msg.id

    asyncio.create_task(match_timeout_watch(guild.id, ch.id))
    asyncio.create_task(match_end_prompt_watch(guild.id, ch.id))


# ============================================
# INTERACTIONS (BUTTONS)
# ============================================
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data or "custom_id" not in interaction.data:
        return

    cid = interaction.data["custom_id"]
    guild = interaction.guild
    if not guild:
        return

    uid = interaction.user.id
    await interaction.response.defer()

    # FILA: SAIR
    if cid.startswith("leave:"):
        _, game, valor_s = cid.split(":")
        valor = int(valor_s)

        lk = locks.get(uid)
        if not lk or lk[0] == "match":
            return

        gid, g2, v2, gen = lk
        if gid != guild.id or g2 != game or v2 != valor:
            return

        q = queues.get(qkey(guild.id, game, valor, gen), [])
        if uid in q:
            q.remove(uid)

        locks.pop(uid, None)
        await update_card_message(interaction, game, valor)
        return

    # FILA: ENTRAR
    if cid.startswith("join:"):
        parts = cid.split(":")
        game = parts[1]
        valor = int(parts[2])
        gen = parts[3] if len(parts) == 4 else None

        if uid in locks:
            return

        effective_gen = gen if game in (GAME_2425, GAME_26) else None
        q = queues.setdefault(qkey(guild.id, game, valor, effective_gen), [])

        if len(q) == 1:
            other = q[0]
            q.clear()

            locks[uid] = ("match", guild.id)
            locks[other] = ("match", guild.id)

            await update_card_message(interaction, game, valor)
            await create_match_channel(guild, game, valor, other, uid, effective_gen)
            return

        q.append(uid)
        locks[uid] = (guild.id, game, valor, effective_gen)
        await update_card_message(interaction, game, valor)
        return

    # MATCH BUTTONS
    if not cid.startswith("m:"):
        return

    _, action, ch_id_s = cid.split(":")
    ch_id = int(ch_id_s)

    st = matches.get(ch_id)
    if not st:
        return

    ch = guild.get_channel(ch_id)
    players = st["players"]

    # cancelar
    if action == "cancel":
        if uid not in players:
            return

        for p in players:
            locks.pop(p, None)

        matches.pop(ch_id, None)
        try:
            if ch:
                await ch.delete()
        except:
            pass
        return

    # confirmar
    if action == "confirm":
        if uid not in players:
            return
        if uid in st["confirmed"]:
            return

        st["confirmed"].add(uid)

        if ch:
            temp_msg = await ch.send(f"✅ <@{uid}> confirmou a aposta.")
            await asyncio.sleep(5)
            try:
                await temp_msg.delete()
            except:
                pass

        if len(st["confirmed"]) == 2 and not st["pix_sent"]:
            st["pix_sent"] = True
            st["status"] = "confirmada"

            control = st.get("control_msg_id")
            if control and ch:
                try:
                    m = await ch.fetch_message(control)
                    await m.edit(view=None)
                except:
                    pass

            if ch:
                pix_embed = discord.Embed(
                    title="💸 PAGAMENTO VIA PIX",
                    description=f"**Chave:**\n`{PIX_EMAIL}`",
                    color=0x00FF44
                )
                pix_embed.set_thumbnail(url=LOGO_URL)
                pix_embed.set_image(url=QR_CODE_URL)
                pix_embed.set_footer(text="ORG FUSION • Pagamento Oficial")
                await ch.send(embed=pix_embed)

        return

    # encerrar partida (ADM)
    if action == "finish":
        if not is_admin(interaction.user):
            return

        if ch:
            await close_match_channel(guild, ch)
        return


# ============================================
# SLASH COMMANDS
# ============================================
async def post_cards(channel: discord.TextChannel, guild: discord.Guild, game: str):
    for v in VALORES:
        emb = await make_card_embed(guild, game, v)
        await channel.send(embed=emb, view=make_card_view(game, v))
        await asyncio.sleep(0.05)


@bot.tree.command(name="inicio", description="Posta os cards novos das filas.")
async def inicio(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Sem permissão.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    cat = await get_or_create_category(guild, CAT_FILAS)
    await get_or_create_category(guild, CAT_PARTIDAS)
    await ensure_result_channel(guild)

    ch2425 = await get_or_create_channel(guild, CH_FC2425, cat)
    ch26   = await get_or_create_channel(guild, CH_FC26, cat)
    chmob  = await get_or_create_channel(guild, CH_MOBILE, cat)
    ch2x2  = await get_or_create_channel(guild, CH_2X2_FC26, cat)
    chpro  = await get_or_create_channel(guild, CH_PROCLUBS, cat)

    await post_cards(ch2425, guild, GAME_2425)
    await post_cards(ch26, guild, GAME_26)
    await post_cards(chmob, guild, GAME_MOB)
    await post_cards(ch2x2, guild, GAME_26_2X2)
    await post_cards(chpro, guild, GAME_PROCLUBS)

    await interaction.followup.send("✅ Cards postados.", ephemeral=True)


@bot.tree.command(name="limparchat", description="Apaga todas as mensagens dos canais de fila.")
async def limparchat(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Sem permissão.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    targets = [CH_FC2425, CH_FC26, CH_MOBILE, CH_2X2_FC26, CH_PROCLUBS]
    for name in targets:
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch:
            await delete_all_messages(ch)

    await interaction.followup.send("🧹 Chats limpos.", ephemeral=True)


@bot.tree.command(name="limparfilas", description="Limpa filas e destrava jogadores.")
async def limparfilas(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Sem permissão.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    for k in list(queues.keys()):
        if k[0] == guild.id:
            queues.pop(k, None)

    for u, lk in list(locks.items()):
        if isinstance(lk, tuple) and len(lk) == 2 and lk[0] == "match" and lk[1] == guild.id:
            locks.pop(u, None)
        elif isinstance(lk, tuple) and len(lk) == 4 and lk[0] == guild.id:
            locks.pop(u, None)

    for ch_id, st in list(matches.items()):
        if st.get("guild_id") == guild.id:
            matches.pop(ch_id, None)

    await interaction.followup.send("♻️ Filas resetadas.", ephemeral=True)


@bot.tree.command(name="fecharmatch", description="Fecha a match deste canal.")
async def fecharmatch(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Sem permissão.", ephemeral=True)
        return

    ch = interaction.channel
    await interaction.response.defer(ephemeral=True)

    ok = await close_match_channel(guild, ch)
    if ok:
        try:
            await interaction.followup.send("✅ Match fechada.", ephemeral=True)
        except:
            pass
    else:
        await interaction.followup.send("Esse canal não é uma match.", ephemeral=True)


# =========================
# NOVO: /setwin
# =========================
@bot.tree.command(name="setwin", description="Define o vencedor desta match (o outro vira perdedor e a match fecha).")
async def setwin(interaction: discord.Interaction, winner: discord.Member):
    guild = interaction.guild
    if not guild:
        return

    if not is_admin(interaction.user):
        await interaction.response.send_message("Sem permissão.", ephemeral=True)
        return

    ch = interaction.channel
    st = matches.get(ch.id)
    if not st:
        await interaction.response.send_message("Esse canal não é uma match.", ephemeral=True)
        return

    players = st["players"]
    if winner.id not in players:
        await interaction.response.send_message("Esse jogador não faz parte dessa match.", ephemeral=True)
        return

    loser_id = players[0] if winner.id == players[1] else players[1]

    db_add_win(winner.id)
    db_add_loss(loser_id)

    # log em #resultados
    try:
        await log_result(guild,
            f"🏆 **RESULTADO**\n"
            f"Canal: #{ch.name}\n"
            f"Vencedor: <@{winner.id}>\n"
            f"Perdedor: <@{loser_id}>\n"
            f"Setado por: <@{interaction.user.id}>"
        )
    except:
        pass

    await interaction.response.send_message(
        f"✅ Vitória setada: {winner.mention} | ❌ Derrota: <@{loser_id}>.\n🔒 Fechando match...",
        ephemeral=True
    )

    await close_match_channel(guild, ch)


# =========================
# NOVO: /p
# =========================
@bot.tree.command(name="p", description="Mostra vitórias/derrotas e taxa de vitória de um jogador.")
async def p(interaction: discord.Interaction, player: discord.Member):
    guild = interaction.guild
    if not guild:
        return

    # Se quiser liberar em qualquer lugar, apaga esse IF:
    if not interaction.channel.name.startswith("partida-"):
        await interaction.response.send_message("Use isso no canal da partida.", ephemeral=True)
        return

    wins, losses = db_get_stats(player.id)
    total = wins + losses
    win_rate = (wins / total) * 100 if total else 0.0
    loss_rate = 100.0 - win_rate
    bar = make_bar(wins, losses, 10)

    embed = discord.Embed(
        title=f"📊 Stats: {player.display_name}",
        color=0x00FF44 if win_rate >= 50 else 0xFF3333
    )
    embed.set_thumbnail(url=player.display_avatar.url)
    embed.add_field(name="V / D", value=f"**V:** {wins}\n**D:** {losses}", inline=True)
    embed.add_field(name="Taxa de vitória", value=f"🟢 {win_rate:.0f}%\n🔴 {loss_rate:.0f}%", inline=True)
    embed.add_field(name="Barra", value=f"{bar}\n——— {win_rate:.0f} / {loss_rate:.0f} ———", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================
# READY
# ============================================
@bot.event
async def on_ready():
    db_init()
    await bot.tree.sync()
    print(f"BOT ONLINE: {bot.user}")



bot.run(TOKEN)
