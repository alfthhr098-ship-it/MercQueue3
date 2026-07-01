"""
MercAdmin Queue Bot
--------------------
Fitur:
- Auto-create role "MercAdmin" di setiap server saat bot join / start.
- /start           -> mulai queue (khusus MercAdmin)
- /join            -> masuk ke queue (semua orang) [tambahan, karena tidak ada di spek asli /leave butuh pasangan]
- /leave           -> keluar dari queue (semua orang)
- /queue list      -> lihat list queue (khusus MercAdmin)
- /pull            -> keluarkan orang nomor 1 dari queue + auto buat ticket channel (khusus MercAdmin)
- /queue stop      -> stop queue (khusus MercAdmin)
"""

import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # optional, untuk instant sync saat testing
TICKET_CATEGORY_NAME = os.getenv("TICKET_CATEGORY_NAME", "Tickets")

ROLE_NAME = "MercAdmin"

intents = discord.Intents.default()
intents.members = True  # perlu diaktifkan juga di Developer Portal > Bot > Privileged Gateway Intents

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------------------------------------------------
# In-memory storage per guild:
# queues[guild_id] = {"active": bool, "list": [user_id, user_id, ...]}
# ------------------------------------------------------------------
queues: dict[int, dict] = {}


def get_queue(guild_id: int) -> dict:
    if guild_id not in queues:
        queues[guild_id] = {"active": False, "list": []}
    return queues[guild_id]


async def ensure_mercadmin_role(guild: discord.Guild) -> discord.Role:
    """Pastikan role MercAdmin ada di guild, buat kalau belum ada."""
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        try:
            role = await guild.create_role(
                name=ROLE_NAME,
                reason="Auto-create role MercAdmin untuk sistem queue bot",
                color=discord.Color.blurple(),
            )
            print(f"[INFO] Role '{ROLE_NAME}' dibuat di guild: {guild.name}")
        except discord.Forbidden:
            print(f"[WARN] Bot tidak punya izin membuat role di guild: {guild.name}")
    return role


def is_mercadmin():
    """Decorator check: user harus punya role MercAdmin."""

    async def predicate(interaction: discord.Interaction) -> bool:
        role = discord.utils.get(interaction.guild.roles, name=ROLE_NAME)
        if role is None:
            await interaction.response.send_message(
                f"❌ Role `{ROLE_NAME}` belum ada di server ini.", ephemeral=True
            )
            return False
        if role not in interaction.user.roles:
            await interaction.response.send_message(
                f"❌ Command ini khusus untuk role `{ROLE_NAME}`.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)


# ------------------------------------------------------------------
# Events
# ------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"[INFO] Login sebagai {bot.user} (ID: {bot.user.id})")

    for guild in bot.guilds:
        await ensure_mercadmin_role(guild)

    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
            print(f"[INFO] Synced {len(synced)} command ke guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"[INFO] Synced {len(synced)} command secara global")
    except Exception as e:
        print(f"[ERROR] Gagal sync command: {e}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    await ensure_mercadmin_role(guild)


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------
@bot.tree.command(name="start", description="Mulai queue untuk role MercAdmin")
@is_mercadmin()
async def start_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)
    if q["active"]:
        await interaction.response.send_message("⚠️ Queue sudah aktif.", ephemeral=True)
        return

    q["active"] = True
    q["list"] = []
    await interaction.response.send_message(
        "✅ Queue telah **dimulai**! Gunakan `/join` untuk masuk ke antrian."
    )


# ------------------------------------------------------------------
# /join  (tambahan, agar orang bisa masuk queue)
# ------------------------------------------------------------------
@bot.tree.command(name="join", description="Masuk ke dalam queue")
async def join_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)

    if not q["active"]:
        await interaction.response.send_message("❌ Queue belum dimulai.", ephemeral=True)
        return

    if interaction.user.id in q["list"]:
        pos = q["list"].index(interaction.user.id) + 1
        await interaction.response.send_message(
            f"ℹ️ Kamu sudah ada di queue, posisi #{pos}.", ephemeral=True
        )
        return

    q["list"].append(interaction.user.id)
    pos = len(q["list"])
    await interaction.response.send_message(
        f"✅ {interaction.user.mention} masuk queue di posisi **#{pos}**."
    )


# ------------------------------------------------------------------
# /leave
# ------------------------------------------------------------------
@bot.tree.command(name="leave", description="Keluar dari queue")
async def leave_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)

    if interaction.user.id not in q["list"]:
        await interaction.response.send_message(
            "❌ Kamu tidak ada di dalam queue.", ephemeral=True
        )
        return

    q["list"].remove(interaction.user.id)
    await interaction.response.send_message(
        f"👋 {interaction.user.mention} keluar dari queue."
    )


# ------------------------------------------------------------------
# /queue group -> list & stop
# ------------------------------------------------------------------
queue_group = app_commands.Group(name="queue", description="Kelola queue MercAdmin")


@queue_group.command(name="list", description="Lihat list queue (khusus MercAdmin)")
@is_mercadmin()
async def queue_list_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)

    if not q["list"]:
        await interaction.response.send_message("📋 Queue kosong.", ephemeral=True)
        return

    lines = []
    for i, user_id in enumerate(q["list"], start=1):
        member = interaction.guild.get_member(user_id)
        name = member.mention if member else f"<@{user_id}>"
        lines.append(f"**#{i}** - {name}")

    status = "🟢 Aktif" if q["active"] else "🔴 Tidak aktif"
    embed = discord.Embed(
        title="📋 Queue List",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Status queue: {status}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@queue_group.command(name="stop", description="Stop queue (khusus MercAdmin)")
@is_mercadmin()
async def queue_stop_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)

    if not q["active"]:
        await interaction.response.send_message("⚠️ Queue memang belum aktif.", ephemeral=True)
        return

    q["active"] = False
    q["list"] = []
    await interaction.response.send_message("🛑 Queue telah **dihentikan** dan list dikosongkan.")


bot.tree.add_command(queue_group)


# ------------------------------------------------------------------
# /pull
# ------------------------------------------------------------------
async def create_ticket_channel(guild: discord.Guild, member: discord.Member) -> discord.TextChannel:
    """Buat ticket channel privat untuk member yang di-pull."""
    mercadmin_role = discord.utils.get(guild.roles, name=ROLE_NAME)

    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if category is None:
        category = await guild.create_category(TICKET_CATEGORY_NAME)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if mercadmin_role:
        overwrites[mercadmin_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )

    safe_name = "".join(c for c in member.name.lower() if c.isalnum() or c in "-_") or "user"
    channel_name = f"ticket-{safe_name}"

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        reason=f"Ticket otomatis dari /pull untuk {member}",
    )
    return channel


@bot.tree.command(name="pull", description="Keluarkan orang teratas dari queue & buat ticket (khusus MercAdmin)")
@is_mercadmin()
async def pull_cmd(interaction: discord.Interaction):
    q = get_queue(interaction.guild_id)

    if not q["list"]:
        await interaction.response.send_message("❌ Queue kosong, tidak ada yang bisa di-pull.", ephemeral=True)
        return

    await interaction.response.defer()

    user_id = q["list"].pop(0)  # orang #1 keluar, sisanya otomatis naik (list shift)
    member = interaction.guild.get_member(user_id)

    if member is None:
        await interaction.followup.send(
            f"⚠️ User dengan ID `{user_id}` sudah tidak ada di server, dilewati (skip)."
        )
        return

    try:
        channel = await create_ticket_channel(interaction.guild, member)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Bot tidak punya izin (Manage Channels) untuk membuat ticket. "
            f"{member.mention} sudah dikeluarkan dari queue, tapi ticket gagal dibuat."
        )
        return

    await channel.send(
        f"🎫 Halo {member.mention}, kamu telah dipanggil dari queue oleh {interaction.user.mention}.\n"
        f"Silakan tunggu di sini."
    )

    await interaction.followup.send(
        f"✅ {member.mention} dikeluarkan dari queue. Ticket dibuat: {channel.mention}"
    )


# ------------------------------------------------------------------
# Error handler umum untuk app commands
# ------------------------------------------------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        return  # sudah dihandle di predicate
    print(f"[ERROR] {error}")
    if interaction.response.is_done():
        await interaction.followup.send("⚠️ Terjadi error saat menjalankan command.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Terjadi error saat menjalankan command.", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN belum diset di file .env")
    bot.run(TOKEN)
