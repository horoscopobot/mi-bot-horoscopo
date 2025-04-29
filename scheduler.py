import asyncio
import database
import requests
from bs4 import BeautifulSoup

async def send_daily_horoscopes(bot):
    users = database.get_all_users()
    for user_id, signo in users:
        try:
            url = f'https://www.horoscopodehoy.net/{signo}-hoy/'
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            horoscopo_div = soup.find('div', class_='horoscope-content')
            if horoscopo_div:
                texto = horoscopo_div.get_text(strip=True)
                mensaje = f"✨ Tu horóscopo diario para {signo.capitalize()} ✨\n\n{texto}"
                await bot.send_message(chat_id=user_id, text=mensaje)
        except Exception as e:
            print(f"Error enviando horóscopo a {user_id}: {e}")

async def scheduler(bot):
    while True:
        await send_daily_horoscopes(bot)
        await asyncio.sleep(86400)  # Espera 24 horas

