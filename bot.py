import os
import json
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from typing import Optional, List

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

DATA_FILE = "data.json"

# ---------- Data helpers ----------
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {
            "games": [],
            "books": [],
            "config": {
                "games_channel_id": None,
                "books_channel_id": None,
                "add_games_role_id": None,
                "add_books_role_id": None,
                "games_ping_role_id": None,
                "admin_role_id": None,
                "announced_epic_ids": []
            }
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Ensure config exists
    if "config" not in data:
        data["config"] = {
            "games_channel_id": None,
            "books_channel_id": None,
            "add_games_role_id": None,
            "add_books_role_id": None,
            "games_ping_role_id": None,
            "admin_role_id": None,
            "announced_epic_ids": []
        }
    return data

def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_config() -> dict:
    return load_data().get("config", {})

# ---------- Permission helpers ----------
def is_owner_or_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_ID:
            return True
        config = get_config()
        admin_role_id = config.get("admin_role_id")
        if admin_role_id and any(r.id == admin_role_id for r in interaction.user.roles):
            return True
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

def can_add_games():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_ID:
            return True
        config = get_config()
        role_id = config.get("add_games_role_id")
        admin_role_id = config.get("admin_role_id")
        user_roles = [r.id for r in interaction.user.roles]
        if role_id and role_id in user_roles:
            return True
        if admin_role_id and admin_role_id in user_roles:
            return True
        await interaction.response.send_message("❌ You don't have permission to add games.", ephemeral=True)
        return False
    return app_commands.check(predicate)

def can_add_books():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_ID:
            return True
        config = get_config()
        role_id = config.get("add_books_role_id")
        admin_role_id = config.get("admin_role_id")
        user_roles = [r.id for r in interaction.user.roles]
        if role_id and role_id in user_roles:
            return True
        if admin_role_id and admin_role_id in user_roles:
            return True
        await interaction.response.send_message("❌ You don't have permission to add books.", ephemeral=True)
        return False
    return app_commands.check(predicate)

def check_channel(channel_type: str):
    """channel_type = 'games' or 'books'"""
    async def predicate(interaction: discord.Interaction) -> bool:
        config = get_config()
        if channel_type == "games":
            required = config.get("games_channel_id")
        else:
            required = config.get("books_channel_id")

        # If no channel is set, allow everywhere
        if not required:
            return True

        if interaction.channel_id != required:
            ch = interaction.guild.get_channel(required) if interaction.guild else None
            mention = ch.mention if ch else "the correct channel"
            await interaction.response.send_message(
                f"❌ Please use this command in {mention}.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

# ---------- Epic Free Games fetcher ----------
async def fetch_epic_free_games() -> List[dict]:
    url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
    params = {"locale": "en-US", "country": "US", "allowCountries": "US"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    free_games = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=12) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        for el in elements:
            promotions = el.get("promotions")
            if not promotions:
                continue

            is_free = False
            end_date = ""
            for offer_group in (promotions.get("promotionalOffers") or []):
                for offer in offer_group.get("promotionalOffers", []):
                    if offer.get("discountSetting", {}).get("discountPercentage") == 0:
                        is_free = True
                        end_date = (offer.get("endDate") or "")[:10]
                        break

            if is_free:
                title = el.get("title", "Unknown")
                desc = (el.get("description") or "No description")[:350]
                slug = el.get("productSlug") or el.get("urlSlug") or ""
                link = f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/en-US/free-games"

                image = ""
                for img in el.get("keyImages", []):
                    if img.get("type") in ("OfferImageWide", "Thumbnail", "DieselStoreFrontWide"):
                        image = img.get("url", "")
                        break

                free_games.append({
                    "id": el.get("id") or title,
                    "title": title,
                    "description": desc,
                    "link": link,
                    "platform": "Epic Games Store",
                    "image": image,
                    "expires": end_date,
                    "source": "epic"
                })
    except Exception as e:
        print(f"[Epic Fetch Error] {e}")
    return free_games

# ---------- Pagination View ----------
class PageView(discord.ui.View):
    def __init__(self, pages: List[str], title: str, author_id: int):
        super().__init__(timeout=300)
        self.pages = pages
        self.title = title
        self.author_id = author_id
        self.current = 0

        if len(pages) <= 1:
            self.prev_button.disabled = True
            self.next_button.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who started reading can control the pages.", ephemeral=True)
            return False
        return True

    async def update_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{self.title} — Page {self.current + 1}/{len(self.pages)}",
            color=discord.Color.blurple()
        )
        embed.set_image(url=self.pages[self.current])
        embed.set_footer(text="Use the buttons to change pages")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current - 1) % len(self.pages)
        await self.update_embed(interaction)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.pages)
        await self.update_embed(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Reading session closed.", embed=None, view=None)
        self.stop()

# ---------- Bot ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    if not check_new_free_games.is_running():
        check_new_free_games.start()

# ---------- Background task: check new Epic free games ----------
@tasks.loop(minutes=90)
async def check_new_free_games():
    await bot.wait_until_ready()
    config = get_config()
    channel_id = config.get("games_channel_id")
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    epic_games = await fetch_epic_free_games()
    if not epic_games:
        return

    data = load_data()
    announced = set(data["config"].get("announced_epic_ids", []))
    new_games = []

    for g in epic_games:
        gid = g.get("id") or g["title"]
        if gid not in announced:
            new_games.append(g)
            announced.add(gid)

    if not new_games:
        return

    # Update announced list
    data["config"]["announced_epic_ids"] = list(announced)[-50:]  # keep last 50
    save_data(data)

    ping_role_id = config.get("games_ping_role_id")
    content = ""
    if ping_role_id:
        content = f"<@&{ping_role_id}> **New free game(s) available!**"

    embeds = []
    for g in new_games:
        embed = discord.Embed(
            title=g["title"],
            description=g.get("description", "")[:400],
            url=g.get("link"),
            color=discord.Color.green()
        )
        embed.add_field(name="Platform", value=g.get("platform", "Epic"), inline=True)
        if g.get("expires"):
            embed.add_field(name="Expires", value=g["expires"], inline=True)
        if g.get("link"):
            embed.add_field(name="Claim here", value=f"[Open in Epic]({g['link']})", inline=False)
        if g.get("image"):
            embed.set_thumbnail(url=g["image"])
        embeds.append(embed)

    try:
        await channel.send(content=content, embeds=embeds[:5])
    except Exception as e:
        print(f"[Notify Error] {e}")

@check_new_free_games.before_loop
async def before_check():
    await bot.wait_until_ready()

# ---------- Public Commands ----------
@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Freebies Bot — Commands",
        color=discord.Color.green()
    )
    embed.add_field(name="/freegames", value="Show free games (Epic + custom)", inline=False)
    embed.add_field(name="/freebooks", value="Show free books & comics", inline=False)
    embed.add_field(name="/read", value="Read a book/comic page by page", inline=False)
    embed.add_field(name="Admin / Manager", value=(
        "`/addgame` `/addbook`\n"
        "`/setchannel` `/setrole` `/settings` `/testping`"
    ), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="freegames", description="Show free games (Epic + custom)")
@check_channel("games")
async def freegames(interaction: discord.Interaction):
    await interaction.response.defer()

    data = load_data()
    custom = data.get("games", [])
    epic = await fetch_epic_free_games()
    all_games = epic + custom

    if not all_games:
        await interaction.followup.send("No free games found right now.")
        return

    embeds = []
    for g in all_games[:8]:
        embed = discord.Embed(
            title=g.get("title", "Unknown"),
            description=g.get("description", "")[:350],
            url=g.get("link"),
            color=discord.Color.blue()
        )
        embed.add_field(name="Platform", value=g.get("platform", "Unknown"), inline=True)
        if g.get("expires"):
            embed.add_field(name="Expires", value=g["expires"], inline=True)
        if g.get("link"):
            embed.add_field(name="Link", value=f"[Click here]({g['link']})", inline=False)
        if g.get("image"):
            embed.set_thumbnail(url=g["image"])
        embeds.append(embed)

    await interaction.followup.send(content=f"**{len(all_games)} free game(s)**", embeds=embeds[:5])
    if len(embeds) > 5:
        await interaction.followup.send(embeds=embeds[5:])

@bot.tree.command(name="freebooks", description="Show free books / comics")
@check_channel("books")
async def freebooks(interaction: discord.Interaction):
    data = load_data()
    books = data.get("books", [])

    if not books:
        await interaction.response.send_message("No free books/comics added yet.")
        return

    embeds = []
    for b in books[:8]:
        embed = discord.Embed(
            title=b.get("title", "Unknown"),
            description=b.get("description", "")[:350],
            color=discord.Color.purple()
        )
        embed.add_field(name="Type", value=b.get("type", "Book"), inline=True)
        pages = len(b.get("pages", []))
        embed.add_field(name="Pages", value=str(pages) if pages else "Link only", inline=True)
        if b.get("link"):
            embed.add_field(name="Link", value=f"[Open]({b['link']})", inline=False)
        embeds.append(embed)

    await interaction.response.send_message(content=f"**{len(books)} item(s)**", embeds=embeds[:5])

@bot.tree.command(name="read", description="Read a book/comic page by page")
@app_commands.describe(title="Title of the book or comic")
@check_channel("books")
async def read_command(interaction: discord.Interaction, title: str):
    data = load_data()
    books = data.get("books", [])

    matched = None
    for b in books:
        if title.lower() in b.get("title", "").lower():
            matched = b
            break

    if not matched:
        await interaction.response.send_message(f"No book/comic found matching **{title}**.", ephemeral=True)
        return

    pages = matched.get("pages", [])
    if not pages:
        link = matched.get("link", "")
        msg = f"**{matched['title']}** has no page images.\n"
        if link:
            msg += f"Open it here: {link}"
        await interaction.response.send_message(msg)
        return

    view = PageView(pages=pages, title=matched["title"], author_id=interaction.user.id)
    embed = discord.Embed(
        title=f"{matched['title']} — Page 1/{len(pages)}",
        color=discord.Color.blurple()
    )
    embed.set_image(url=pages[0])
    embed.set_footer(text="Only you can control the buttons")
    await interaction.response.send_message(embed=embed, view=view)

# ---------- Add commands ----------
@bot.tree.command(name="addgame", description="Add a custom free game")
@app_commands.describe(
    title="Game title",
    link="Direct link",
    platform="Platform (Steam, Epic, itch.io...)",
    description="Short description",
    expires="YYYY-MM-DD (optional)",
    image="Image URL (optional)"
)
@can_add_games()
@check_channel("games")
async def addgame(
    interaction: discord.Interaction,
    title: str,
    link: str,
    platform: str,
    description: str = "No description",
    expires: str = "",
    image: str = ""
):
    data = load_data()
    data["games"].append({
        "title": title,
        "description": description,
        "link": link,
        "platform": platform,
        "image": image,
        "expires": expires,
        "source": "custom"
    })
    save_data(data)
    await interaction.response.send_message(f"✅ Added free game: **{title}**", ephemeral=True)

@bot.tree.command(name="addbook", description="Add a free book / comic / PDF")
@app_commands.describe(
    title="Title",
    link="Download or page link",
    type="Book / Comic / PDF / Other",
    description="Short description",
    pages="Comma-separated image URLs of pages (for /read)"
)
@can_add_books()
@check_channel("books")
async def addbook(
    interaction: discord.Interaction,
    title: str,
    link: str,
    type: str = "Book",
    description: str = "No description",
    pages: str = ""
):
    page_list = [p.strip() for p in pages.split(",") if p.strip()] if pages else []

    data = load_data()
    data["books"].append({
        "title": title,
        "description": description,
        "link": link,
        "type": type,
        "pages": page_list
    })
    save_data(data)

    msg = f"✅ Added **{title}** ({type})"
    if page_list:
        msg += f" with {len(page_list)} page(s)"
    await interaction.response.send_message(msg, ephemeral=True)

# ---------- Settings Commands ----------
@bot.tree.command(name="setchannel", description="[Admin] Set games or books channel")
@app_commands.describe(type="games or books", channel="The channel to assign")
@app_commands.choices(type=[
    app_commands.Choice(name="games", value="games"),
    app_commands.Choice(name="books", value="books")
])
@is_owner_or_admin()
async def setchannel(interaction: discord.Interaction, type: str, channel: discord.TextChannel):
    data = load_data()
    if type == "games":
        data["config"]["games_channel_id"] = channel.id
    else:
        data["config"]["books_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ {type.capitalize()} channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="setrole", description="[Admin] Set permission or ping roles")
@app_commands.describe(
    type="Which role setting",
    role="The role to assign"
)
@app_commands.choices(type=[
    app_commands.Choice(name="Add Games Role", value="add_games"),
    app_commands.Choice(name="Add Books Role", value="add_books"),
    app_commands.Choice(name="Games Ping Role", value="games_ping"),
    app_commands.Choice(name="Admin Role", value="admin")
])
@is_owner_or_admin()
async def setrole(interaction: discord.Interaction, type: str, role: discord.Role):
    data = load_data()
    key_map = {
        "add_games": "add_games_role_id",
        "add_books": "add_books_role_id",
        "games_ping": "games_ping_role_id",
        "admin": "admin_role_id"
    }
    data["config"][key_map[type]] = role.id
    save_data(data)
    await interaction.response.send_message(f"✅ {type.replace('_', ' ').title()} set to {role.mention}", ephemeral=True)

@bot.tree.command(name="settings", description="[Admin] Show current configuration")
@is_owner_or_admin()
async def settings(interaction: discord.Interaction):
    config = get_config()
    guild = interaction.guild

    def fmt_channel(cid):
        if not cid:
            return "Not set"
        ch = guild.get_channel(cid) if guild else None
        return ch.mention if ch else f"`{cid}` (not found)"

    def fmt_role(rid):
        if not rid:
            return "Not set"
        role = guild.get_role(rid) if guild else None
        return role.mention if role else f"`{rid}` (not found)"

    embed = discord.Embed(title="Bot Settings", color=discord.Color.orange())
    embed.add_field(name="Games Channel", value=fmt_channel(config.get("games_channel_id")), inline=False)
    embed.add_field(name="Books Channel", value=fmt_channel(config.get("books_channel_id")), inline=False)
    embed.add_field(name="Add Games Role", value=fmt_role(config.get("add_games_role_id")), inline=True)
    embed.add_field(name="Add Books Role", value=fmt_role(config.get("add_books_role_id")), inline=True)
    embed.add_field(name="Games Ping Role", value=fmt_role(config.get("games_ping_role_id")), inline=True)
    embed.add_field(name="Admin Role", value=fmt_role(config.get("admin_role_id")), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="testping", description="[Admin] Test the free games notification")
@is_owner_or_admin()
async def testping(interaction: discord.Interaction):
    config = get_config()
    channel_id = config.get("games_channel_id")
    if not channel_id:
        await interaction.response.send_message("Games channel is not set. Use `/setchannel` first.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("Games channel not found.", ephemeral=True)
        return

    ping = ""
    if config.get("games_ping_role_id"):
        ping = f"<@&{config['games_ping_role_id']}> "

    embed = discord.Embed(
        title="Test Notification",
        description="This is a test of the free games ping system.",
        color=discord.Color.green()
    )
    await channel.send(content=f"{ping}**Test free game notification!**", embed=embed)
    await interaction.response.send_message("✅ Test notification sent!", ephemeral=True)

# ---------- Run ----------
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN not found in .env")
    else:
        if OWNER_ID == 0:
            print("WARNING: OWNER_ID not set.")
        bot.run(TOKEN)
