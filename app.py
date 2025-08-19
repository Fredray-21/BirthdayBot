# app.py
from datetime import datetime
from quart import Quart, redirect, url_for, session, request, render_template, jsonify
import requests
import os
import asyncio
import database as db

app = Quart(__name__)
app.secret_key = os.urandom(24)

# Config Discord
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
REDIRECT_URI = os.getenv('REDIRECT_URI')

API_ENDPOINT = 'https://discord.com/api/v10'

# --- Fonctions utilitaires ---
async def get_bot_guilds():
    headers = {'Authorization': f'Bot {DISCORD_TOKEN}'}
    resp = requests.get(f'{API_ENDPOINT}/users/@me/guilds', headers=headers)
    if resp.status_code == 200:
        return [int(g['id']) for g in resp.json()]
    return []

# --- Routes ---
@app.route('/')
async def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return await render_template('index.html')

@app.route('/login')
async def login():
    return redirect(f'{API_ENDPOINT}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds')

@app.route('/callback')
async def callback():
    code = request.args.get('code')
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': 'identify guilds'
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(f'{API_ENDPOINT}/oauth2/token', data=data, headers=headers)
    token_data = response.json()
    session['access_token'] = token_data['access_token']

    user_headers = {'Authorization': f'Bearer {session["access_token"]}'}
    user_response = requests.get(f'{API_ENDPOINT}/users/@me', headers=user_headers)
    session['user'] = user_response.json()
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
async def logout():
    session.pop('user', None)
    session.pop('access_token', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
async def dashboard():
    if 'user' not in session or 'access_token' not in session:
        return redirect(url_for('index'))

    user_headers = {'Authorization': f'Bearer {session["access_token"]}'}
    guilds_response = requests.get(f'{API_ENDPOINT}/users/@me/guilds', headers=user_headers)
    user_guilds = guilds_response.json()

    bot_guild_ids = await get_bot_guilds()

    admin_guilds = []
    for guild in user_guilds:
        is_admin = (int(guild.get('permissions', 0)) & 8) == 8
        is_bot_in_guild = int(guild.get('id')) in bot_guild_ids
        if is_admin and is_bot_in_guild:
            admin_guilds.append(guild)

    return await render_template('dashboard.html', user=session['user'], guilds=admin_guilds)

@app.route('/server/<int:guild_id>', methods=['GET', 'POST'])
async def server_config(guild_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    
    current_settings = await db.get_guild_settings(guild_id)

    bot_headers = {'Authorization': f'Bot {DISCORD_TOKEN}'}
    
    roles_resp = requests.get(f'{API_ENDPOINT}/guilds/{guild_id}/roles', headers=bot_headers)
    roles = roles_resp.json() if roles_resp.status_code == 200 else []

    channels_resp = requests.get(f'{API_ENDPOINT}/guilds/{guild_id}/channels', headers=bot_headers)
    channels = [c for c in channels_resp.json() if c['type'] == 0] if channels_resp.status_code == 200 else []

    guild_resp = requests.get(f'{API_ENDPOINT}/guilds/{guild_id}', headers=bot_headers)
    guild_name = guild_resp.json().get('name', 'Serveur inconnu')

    members_resp = requests.get(f'{API_ENDPOINT}/guilds/{guild_id}/members?limit=1000', headers=bot_headers)
    all_members = members_resp.json() if members_resp.status_code == 200 else []
    non_bot_members = [m for m in all_members if not m.get('user', {}).get('bot', False)]

    all_birthdays = await db.get_all_guild_birthdays(guild_id)
    all_birthdays_str_keys = {str(k): v for k, v in all_birthdays.items()}

    if request.method == 'POST':
        data = await request.get_json()
        role_id = data.get('role_id')           # pas required
        channel_id = data.get('channel_id')     # required
        message = data.get('message')           # required avec "@membres" required

        # Vérifications côté serveur
        if not channel_id:
            return jsonify({"success": False, "error": "Le canal est obligatoire"}), 400
        if "@membres" not in message:
            return jsonify({"success": False, "error": 'Le message doit contenir "@membres"'}), 400

        await db.update_guild_settings(guild_id, role_id, channel_id, message)
        return jsonify({"success": True})

    return await render_template(
        "server_config.html",
        guild_id=guild_id,
        guild_name=guild_name,
        roles=roles,
        channels=channels,
        settings=current_settings,
        members=non_bot_members,
        birthdays=all_birthdays_str_keys
    )

@app.route('/api/update_birthday', methods=['POST'])
async def update_birthday():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Authentification requise"}), 401

    data = await request.get_json()
    guild_id = data.get('guild_id')
    member_id = data.get('member_id')
    birthday_date_str = data.get('birthday_date')

    if not all([guild_id, member_id, birthday_date_str]):
        return jsonify({"success": False, "error": "Données manquantes"}), 400

    try:
        birthday_date = datetime.strptime(birthday_date_str, "%Y-%m-%d").date()
        await db.add_birthday(int(guild_id), int(member_id), birthday_date)
        return jsonify({"success": True, "message": "Anniversaire mis à jour"}), 200
    except ValueError:
        return jsonify({"success": False, "error": "Format de date invalide, attendu YYYY-MM-DD"}), 400
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'anniversaire: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# --- Initialisation de la BDD ---
@app.before_serving
async def startup():
    for i in range(10):
        try:
            await db.connect()
            await db.create_tables()
            print("DB prête !")
            return
        except Exception as e:
            print(f"DB non prête, retry dans 3s... ({i+1}/10)")
            await asyncio.sleep(3)
    raise Exception("Impossible de se connecter à PostgreSQL après 10 essais")

# --- Main ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

