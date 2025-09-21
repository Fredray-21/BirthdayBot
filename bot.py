import os
import discord
from discord.ext import commands, tasks
import asyncio
import database as db
from datetime import date, timedelta, datetime, time
from zoneinfo import ZoneInfo

# Créez une instance de l'intention (Intents) pour le bot
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# La fonction `on_ready` est appelée lorsque le bot est connecté à Discord
@bot.event
async def on_ready():
    print(f'Bot connecté en tant que {bot.user}!', flush=True)

    # Boucle d'attente de la DB
    for i in range(10):
        try:
            await db.connect()
            await db.create_tables()
            print("Connecté à PostgreSQL.", flush=True)
            break
        except Exception as e:
            print(f"DB non prête, retry dans 3s... ({i+1}/10) Erreur: {e}", flush=True)
            await asyncio.sleep(3)
    else:
        print("Impossible de se connecter à PostgreSQL après 10 essais.", flush=True)
        return

    print(f"daily_birthday_check.is_running() = {daily_birthday_check.is_running()}", flush=True)

    if not daily_birthday_check.is_running():
        print("Démarrage de la boucle daily_birthday_check...", flush=True)
        daily_birthday_check.start()
    else:
        print("La boucle est déjà running", flush=True)

    print("La vérification quotidienne des anniversaires est démarrée.", flush=True)

# --- Tâches Périodiques du Bot ---
# Exécution tous les jours à 00:00 heure de Paris
@tasks.loop(time=time(hour=0, minute=0, tzinfo=ZoneInfo("Europe/Paris")))
async def daily_birthday_check():
    paris_time = datetime.now(ZoneInfo("Europe/Paris"))
    today = paris_time.date()
    print(f"[{paris_time}] Vérification des anniversaires pour la date : {today}", flush=True)

    # Section 1: Célébration des anniversaires d'aujourd'hui
    birthdays_to_celebrate = await db.get_birthdays_on_date(today)
    print(f"Anniversaires trouvés aujourd'hui: {birthdays_to_celebrate}", flush=True)

    if not birthdays_to_celebrate:
        print("Aucun anniversaire à célébrer aujourd'hui.", flush=True)
    else:
        guild_birthdays = {}
        for birthday_info in birthdays_to_celebrate:
            guild_id = birthday_info['guild_id']
            member_id = birthday_info['member_id']

            if guild_id not in guild_birthdays:
                guild_birthdays[guild_id] = []
            guild_birthdays[guild_id].append(member_id)

        # Envoi d'un message pour chaque serveur
        for guild_id, member_ids in guild_birthdays.items():
            settings = await db.get_guild_settings(guild_id)

            if not settings or 'channel_id' not in settings or not settings['channel_id']:
                print(f"Les paramètres pour le serveur {guild_id} sont incomplets. Impossible de célébrer.", flush=True)
                continue

            try:
                guild = bot.get_guild(guild_id)
                if not guild:
                    continue

                channel = guild.get_channel(settings['channel_id'])
                if not channel:
                    continue

                # Création de la liste de mentions
                mentions = []
                for member_id in member_ids:
                    member = guild.get_member(member_id)
                    if member:
                        mentions.append(member.mention)

                if not mentions:
                    continue

                message = settings.get('birthday_message', "Joyeux anniversaire @membres !")
                message = message.replace('@membres', ', '.join(mentions))

                await channel.send(message)
                print(f"Message d'anniversaire envoyé sur le serveur {guild.name} pour les membres: {', '.join(mentions)}.", flush=True)

                # Ajoutez le rôle d'anniversaire si configuré
                role_id = settings.get('role_id')
                if role_id:
                    role = guild.get_role(int(role_id))
                    if role:
                        for member_id in member_ids:
                            member = guild.get_member(member_id)
                            if member and role not in member.roles:
                                await member.add_roles(role)
                                print(f"Rôle '{role.name}' ajouté à {member.display_name}.", flush=True)
                    else:
                        print(f"Rôle avec l'ID {role_id} introuvable sur le serveur {guild.name}.")
            except discord.errors.Forbidden:
                print(f"Erreur de permission sur le serveur {guild.name}. Vérifiez les permissions du bot.", flush=True)
            except Exception as e:
                print(f"Une erreur s'est produite lors du traitement des anniversaires sur le serveur {guild_id}: {e}", flush=True)

    # Section 2: Retrait des rôles d'anniversaire
    yesterday = today - timedelta(days=1)
    print(f"Vérification des anniversaires pour la date d'hier : {yesterday}", flush=True)

    birthdays_yesterday = await db.get_birthdays_on_date(yesterday)

    if not birthdays_yesterday:
        print("Aucun rôle à retirer aujourd'hui.", flush=True)
    else:
        for birthday_info in birthdays_yesterday:
            guild_id = birthday_info['guild_id']
            member_id = birthday_info['member_id']

            settings = await db.get_guild_settings(guild_id)

            if not settings or 'role_id' not in settings or not settings['role_id']:
                print(f"Pas de rôle d'anniversaire configuré pour le serveur {guild_id}.", flush=True)
                continue

            try:
                guild = bot.get_guild(guild_id)
                if not guild:
                    continue

                member = guild.get_member(member_id)
                if not member:
                    continue

                role_id = settings['role_id']
                role = guild.get_role(int(role_id))

                if role and role in member.roles:
                    await member.remove_roles(role)
                    print(f"Rôle '{role.name}' retiré de {member.display_name} sur le serveur {guild.name}.", flush=True)

            except discord.errors.Forbidden:
                print(f"Erreur de permission. Le bot ne peut pas retirer le rôle sur le serveur {guild.name}.", flush=True)
            except Exception as e:
                print(f"Une erreur s'est produite lors du retrait du rôle de {member_id}: {e}", flush=True)
    
    # --- Log de la prochaine exécution ---
    now = datetime.now(ZoneInfo("Europe/Paris"))
    tomorrow = now.date() + timedelta(days=1)
    next_run = datetime.combine(tomorrow, time(0,0, tzinfo=ZoneInfo("Europe/Paris")))
    print(f"[{now}] Task terminée → prochaine exécution prévue à {next_run}", flush=True)

# --- Log de planification ---
@daily_birthday_check.before_loop
async def before_daily_birthday_check():
    await bot.wait_until_ready()  # ✅ attendre que le bot soit prêt
    now = datetime.now(ZoneInfo("Europe/Paris"))
    tomorrow = now.date() + timedelta(days=1)
    next_run = datetime.combine(tomorrow, time(0,0, tzinfo=ZoneInfo("Europe/Paris")))
    print(f"[{now}] Task prête → prochaine exécution prévue à {next_run}", flush=True)

# Commande pour qu'un utilisateur puisse enregistrer son anniversaire
@bot.command(name='set-anniv')
async def set_anniv(ctx, date_anniv: str):
    try:
        birthday_date = date.fromisoformat(date_anniv)
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        await db.add_birthday(guild_id, user_id, birthday_date)
        await ctx.send(f"Ton anniversaire a été enregistré pour le {birthday_date} !")
    except ValueError:
        await ctx.send("Le format de la date est incorrect. Utilise le format AAAA-MM-JJ.")

discord_token = os.getenv('DISCORD_TOKEN')

if discord_token:
    bot.run(discord_token)
else:
    print("Erreur : Le token du bot n'a pas été trouvé. Assurez-vous que la variable d'environnement 'DISCORD_TOKEN' est bien définie.", flush=True)
