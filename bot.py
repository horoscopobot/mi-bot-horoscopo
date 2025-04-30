#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOT DE HORÓSCOPO - VERSIÓN COMPLETA CON BASE DE DATOS CORREGIDA
"""

import logging
import aiohttp
import sqlite3
import os
import asyncio
import re
from datetime import datetime, time, date, timedelta
from typing import Dict, List, Optional
import pytz
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Configuración avanzada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('horoscope_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8084223356:AAFQAjulnzkX_qL92xW5emWkmU5MW5-rgsI")
HORA_ENVIO = time(8, 0, 0, tzinfo=pytz.timezone('America/Mexico_City'))
BASE_URL = "https://www.horoscopodehoy.net"
CANAL_ID = "@horoscopodehoynet"  # Cambiar a "@tucanal" o "-100123456789" para habilitar envío a canales
VIP_ENABLED = True  # Habilitar zona VIP
PRECIO_VIP = 5.00  # 5€ anuales
METODOS_PAGO = {
    "paypal": "https://www.paypal.com/paypalme/tuusuario",
    "bizum": "+34600000000"  # Reemplazar con tu número Bizum
}

# Datos de signos
SIGNOS = {
    "aries": {"emoji": "♈", "nombre": "Aries", "url_suffix": "aries-hoy"},
    "tauro": {"emoji": "♉", "nombre": "Tauro", "url_suffix": "tauro-hoy"},
    "geminis": {"emoji": "♊", "nombre": "Géminis", "url_suffix": "geminis-hoy"},
    "cancer": {"emoji": "♋", "nombre": "Cáncer", "url_suffix": "cancer-hoy"},
    "leo": {"emoji": "♌", "nombre": "Leo", "url_suffix": "leo-hoy"},
    "virgo": {"emoji": "♍", "nombre": "Virgo", "url_suffix": "virgo-hoy"},
    "libra": {"emoji": "♎", "nombre": "Libra", "url_suffix": "libra-hoy"},
    "escorpio": {"emoji": "♏", "nombre": "Escorpio", "url_suffix": "escorpio-hoy"},
    "sagitario": {"emoji": "♐", "nombre": "Sagitario", "url_suffix": "sagitario-hoy"},
    "capricornio": {"emoji": "♑", "nombre": "Capricornio", "url_suffix": "capricornio-hoy"},
    "acuario": {"emoji": "♒", "nombre": "Acuario", "url_suffix": "acuario-hoy"},
    "piscis": {"emoji": "♓", "nombre": "Piscis", "url_suffix": "piscis-hoy"},
}

class DatabaseManager:
    """Gestor de base de datos con estructura corregida"""
    
    def __init__(self, db_name: str = 'horoscopo.db'):
        self.db_name = db_name
        self.conn = None
        self._initialize_db()
    
    def _initialize_db(self):
        try:
            # Eliminar la base de datos existente para recrearla
            if os.path.exists(self.db_name):
                os.remove(self.db_name)
                
            self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            with self.conn:
                # Tabla de usuarios con todas las columnas necesarias
                self.conn.execute('''
                    CREATE TABLE IF NOT EXISTS usuarios (
                        user_id INTEGER PRIMARY KEY,
                        chat_id INTEGER NOT NULL,
                        signo TEXT NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        ultima_consulta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        recibir_diario BOOLEAN DEFAULT TRUE,
                        hora_envio TEXT DEFAULT '08:00',
                        es_vip BOOLEAN DEFAULT FALSE,
                        fecha_vip DATE
                    )
                ''')
                
                # Tabla de estadísticas con estructura corregida
                self.conn.execute('''
                    CREATE TABLE IF NOT EXISTS estadisticas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fecha TEXT NOT NULL,
                        signo TEXT NOT NULL,
                        consultas INTEGER DEFAULT 0
                    )
                ''')
                
                # Tabla de pagos VIP
                self.conn.execute('''
                    CREATE TABLE IF NOT EXISTS pagos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        metodo TEXT NOT NULL,
                        cantidad REAL NOT NULL,
                        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        confirmado BOOLEAN DEFAULT FALSE,
                        FOREIGN KEY(user_id) REFERENCES usuarios(user_id)
                    )
                ''')
                
                # Crear índices para mejorar el rendimiento
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_usuarios_signo ON usuarios(signo)')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_estadisticas_fecha ON estadisticas(fecha)')
                
        except sqlite3.Error as e:
            logger.error(f"Error al inicializar DB: {e}")
            raise

    def guardar_usuario(self, user_id: int, chat_id: int, signo: str, 
                      username: str = None, first_name: str = None, 
                      last_name: str = None):
        try:
            with self.conn:
                self.conn.execute('''
                    INSERT OR REPLACE INTO usuarios 
                    (user_id, chat_id, signo, username, first_name, last_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, chat_id, signo, username, first_name, last_name))
        except sqlite3.Error as e:
            logger.error(f"Error al guardar usuario: {e}")

    def actualizar_signo(self, user_id: int, signo: str):
        try:
            with self.conn:
                self.conn.execute('''
                    UPDATE usuarios SET signo = ? WHERE user_id = ?
                ''', (signo, user_id))
                return True
        except sqlite3.Error as e:
            logger.error(f"Error al actualizar signo: {e}")
            return False

    def obtener_usuario(self, user_id: int) -> Optional[dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM usuarios WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error al obtener usuario: {e}")
            return None

    def guardar_consulta(self, user_id: int, signo: str):
        try:
            with self.conn:
                # Registrar consulta
                self.conn.execute('''
                    UPDATE usuarios 
                    SET ultima_consulta = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (user_id,))
                
                # Actualizar estadísticas
                fecha_hoy = date.today().isoformat()
                self.conn.execute('''
                    INSERT INTO estadisticas (fecha, signo, consultas)
                    VALUES (?, ?, 1)
                ''', (fecha_hoy, signo))
                
        except sqlite3.Error as e:
            logger.error(f"Error al guardar consulta: {e}")

    def obtener_usuarios_por_signo(self, signo: str) -> List[dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT user_id, chat_id FROM usuarios 
                WHERE signo = ? AND recibir_diario = TRUE
            ''', (signo,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error al obtener usuarios: {e}")
            return []

    def obtener_estadisticas_hoy(self) -> List[dict]:
        try:
            fecha_hoy = date.today().isoformat()
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT signo, SUM(consultas) as total 
                FROM estadisticas 
                WHERE fecha = ?
                GROUP BY signo 
                ORDER BY total DESC
            ''', (fecha_hoy,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error al obtener estadísticas: {e}")
            return []

    def activar_vip(self, user_id: int, metodo_pago: str, cantidad: float) -> bool:
        """Activa VIP y registra el pago"""
        try:
            with self.conn:
                # Registrar pago
                self.conn.execute('''
                    INSERT INTO pagos (user_id, metodo, cantidad)
                    VALUES (?, ?, ?)
                ''', (user_id, metodo_pago, cantidad))
                
                # Activar VIP con fecha de expiración (1 año)
                fecha_expiracion = (datetime.now() + timedelta(days=365)).date().isoformat()
                self.conn.execute('''
                    UPDATE usuarios 
                    SET es_vip = TRUE, fecha_vip = ?
                    WHERE user_id = ?
                ''', (fecha_expiracion, user_id))
                
                return True
        except sqlite3.Error as e:
            logger.error(f"Error al activar VIP: {e}")
            return False

    def verificar_vip(self, user_id: int) -> bool:
        """Verifica si el usuario tiene VIP activo"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT es_vip, fecha_vip 
                FROM usuarios 
                WHERE user_id = ? 
                AND es_vip = TRUE 
                AND (fecha_vip IS NULL OR fecha_vip >= DATE('now'))
            ''', (user_id,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error al verificar VIP: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()

# Inicializar base de datos
db = DatabaseManager()

async def obtener_prediccion(signo: str, es_vip: bool = False) -> Optional[str]:
    """Extrae la predicción con contenido VIP si corresponde"""
    if signo not in SIGNOS:
        return None
    
    url = f"{BASE_URL}/{SIGNOS[signo]['url_suffix']}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Buscar predicción base
                    prediccion = ""
                    for h2 in soup.find_all('h2'):
                        if 'Predicción del Día' in h2.text:
                            siguiente = h2.find_next_sibling('p')
                            if siguiente:
                                prediccion = ' '.join(siguiente.stripped_strings)
                                break
                    
                    if not prediccion:
                        entry_content = soup.find('div', class_='entry-content')
                        if entry_content:
                            for p in entry_content.find_all('p'):
                                text = ' '.join(p.stripped_strings)
                                if len(text.split()) > 15:
                                    prediccion = text
                                    break
                    
                    if not prediccion:
                        logger.warning(f"No se encontró predicción para {signo}")
                        return None
                    
                    # Añadir contenido VIP si corresponde
                    if es_vip:
                        contenido_vip = "\n\n🌟 *Contenido VIP Exclusivo:*\n"
                        # Buscar siguiente párrafo para contenido VIP
                        siguiente_vip = siguiente.find_next_sibling('p') if siguiente else None
                        if siguiente_vip:
                            contenido_vip += ' '.join(siguiente_vip.stripped_strings)
                        else:
                            contenido_vip += "• Predicción extendida detallada\n• Compatibilidad amorosa\n• Consejos personalizados"
                        return prediccion + contenido_vip
                    
                    return prediccion
                
                logger.error(f"Error HTTP {response.status} para {signo}")
                return None
                
    except Exception as e:
        logger.error(f"Error al obtener horóscopo: {e}")
        return None

def generar_teclado_principal() -> InlineKeyboardMarkup:
    """Genera teclado interactivo con botón VIP en columna única"""
    botones = []
    signos_ordenados = sorted(SIGNOS.items(), key=lambda x: x[1]['nombre'])
    
    # Agrupar signos en filas de 3
    for i in range(0, len(signos_ordenados), 3):
        fila = [
            InlineKeyboardButton(
                f"{data['emoji']} {data['nombre']}",
                callback_data=f"signo_{signo}"
            )
            for signo, data in signos_ordenados[i:i+3]
        ]
        botones.append(fila)
    
    # Botones inferiores en columna única
    botones.append([InlineKeyboardButton("📊 Estadísticas", callback_data="estadisticas")])
    botones.append([InlineKeyboardButton("⚙️ Configuración", callback_data="configuracion")])
    botones.append([InlineKeyboardButton("ℹ️ Ayuda", callback_data="ayuda")])
    
    if VIP_ENABLED:
        botones.append([InlineKeyboardButton("🌟 Zona VIP Premium", callback_data="info_vip")])
    
    return InlineKeyboardMarkup(botones)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador del comando /start"""
    try:
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        mensaje = (
            f"✨ *Hola {user.first_name or 'amigo'}!*\n\n"
            "Soy tu *Bot de Horóscopo Diario* 🌟\n\n"
            "Selecciona tu signo para conocer tu predicción del día o "
            "configura el envío automático cada mañana.\n\n"
            "También puedes usar /horoscopo seguido de tu signo."
        )
        
        db.guardar_usuario(
            user_id=user.id,
            chat_id=chat_id,
            signo="none",
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        await update.effective_message.reply_text(
            mensaje,
            reply_markup=generar_teclado_principal(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error en start: {e}")
        await handle_error(update, context)

async def enviar_prediccion(update: Update, context: ContextTypes.DEFAULT_TYPE, signo: str):
    """Envía la predicción con opción para compartir"""
    try:
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        if signo not in SIGNOS:
            await update.effective_message.reply_text(
                "⚠️ Signo no reconocido. Usa /start para ver la lista.",
                parse_mode="Markdown"
            )
            return
        
        es_vip = db.verificar_vip(user.id)
        signo_data = SIGNOS[signo]
        
        # Mensaje de carga
        loading_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{signo_data['emoji']} Consultando las estrellas para {signo_data['nombre']}...",
            parse_mode="Markdown"
        )
        
        # Obtener predicción
        prediccion = await obtener_prediccion(signo, es_vip)
        
        if not prediccion:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=loading_msg.message_id,
                text=f"🔮 No pude conectar con las estrellas para {signo_data['nombre']}. Intenta más tarde.",
                parse_mode="Markdown"
            )
            return
        
        # Formatear mensaje final
        fecha = datetime.now().strftime("%d/%m/%Y")
        mensaje = (
            f"🔮 *Horóscopo de {signo_data['nombre']} {signo_data['emoji']}*\n"
            f"📅 *Fecha:* {fecha}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{prediccion}\n\n"
            "✨ *Que tengas un día maravilloso!*"
        )
        
        # Crear teclado con botón para compartir
        teclado = [
            [InlineKeyboardButton("🔄 Actualizar", callback_data=f"signo_{signo}"),
             InlineKeyboardButton("⬅️ Menú", callback_data="inicio")],
            [InlineKeyboardButton("📤 Compartir predicción", 
                                switch_inline_query=f"Horóscopo {signo_data['nombre']} {fecha}")]
        ]
        
        if VIP_ENABLED and not es_vip:
            teclado.append([InlineKeyboardButton("🌟 Desbloquear Zona VIP", callback_data="info_vip")])
        
        # Actualizar mensaje
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=loading_msg.message_id,
            text=mensaje,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(teclado)
        )
        
        # Registrar consulta
        db.guardar_consulta(user.id, signo)
        
    except Exception as e:
        logger.error(f"Error enviando predicción: {e}")
        await handle_error(update, context)

async def mostrar_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el mensaje de ayuda"""
    ayuda_texto = (
        "🌟 *Ayuda del Bot de Horóscopo*\n\n"
        "Puedes interactuar conmigo de estas formas:\n\n"
        "• Usa el teclado para seleccionar tu signo\n"
        "• Programa el envío automático con /configurar\n"
        "• Consulta estadísticas con /estadisticas\n\n"
        "🔮 *Comandos rápidos:*\n"
        "/horoscopo [signo] - Obtén tu predicción\n"
        "/diario [on/off] - Activa/desactiva envíos\n"
        "/cambiar_signo - Actualiza tu signo zodiacal\n\n"
        "📌 *Ejemplos:*\n"
        "/horoscopo leo\n"
        "/diario off\n"
        "/cambiar_signo acuario"
    )
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=ayuda_texto,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Volver al menú", callback_data="inicio")]
                ])
            )
        else:
            await update.effective_message.reply_text(
                text=ayuda_texto,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Volver al menú", callback_data="inicio")]
                ])
            )
    except Exception as e:
        logger.error(f"Error mostrando ayuda: {e}")
        await handle_error(update, context)

async def mostrar_configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú de configuración"""
    try:
        user = update.effective_user
        usuario = db.obtener_usuario(user.id)
        
        if not usuario:
            await start(update, context)
            return
        
        es_vip = db.verificar_vip(user.id)
        config_texto = (
            "⚙️ *Tus preferencias actuales:*\n\n"
            f"{SIGNOS.get(usuario['signo'], {}).get('emoji', '♉')} *Signo:* {SIGNOS.get(usuario['signo'], {}).get('nombre', 'No configurado')}\n"
            f"🔔 *Notificaciones:* {'Activadas' if usuario['recibir_diario'] else 'Desactivadas'}\n"
            f"⏰ *Hora de envío:* {usuario['hora_envio']}\n"
            f"🌟 *Zona VIP:* {'✅ Activada' if es_vip else '❌ No activada'}\n\n"
            "¿Qué deseas cambiar?"
        )
        
        teclado_config = [
            [InlineKeyboardButton("♉ Cambiar signo", callback_data="cambiar_signo")],
            [
                InlineKeyboardButton("⏰ Hora más temprana", callback_data="hora_7"),
                InlineKeyboardButton("⏰ Hora más tarde", callback_data="hora_9")
            ],
            [
                InlineKeyboardButton("🔔 Activar notificaciones", callback_data="notif_on"),
                InlineKeyboardButton("🔕 Desactivar", callback_data="notif_off")
            ]
        ]
        
        if VIP_ENABLED:
            if es_vip:
                teclado_config.append([InlineKeyboardButton("✅ VIP Activado", callback_data="info_vip")])
            else:
                teclado_config.append([InlineKeyboardButton("🌟 Activar VIP", callback_data="info_vip")])
        
        teclado_config.append([InlineKeyboardButton("⬅️ Volver al menú", callback_data="inicio")])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=config_texto,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(teclado_config)
            )
        else:
            await update.effective_message.reply_text(
                text=config_texto,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(teclado_config)
            )
            
    except Exception as e:
        logger.error(f"Error mostrando configuración: {e}")
        await handle_error(update, context)

async def mostrar_estadisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas de uso"""
    try:
        stats = db.obtener_estadisticas_hoy()
        fecha = datetime.now().strftime("%d/%m/%Y")
        
        if not stats:
            mensaje = f"📊 *Estadísticas del {fecha}*\n\nAún no hay consultas hoy."
        else:
            total = sum(item['total'] for item in stats)
            mensaje = f"📊 *Estadísticas del {fecha}*\n\n"
            mensaje += f"🔮 *Total de consultas:* {total}\n\n"
            mensaje += "📈 *Por signo:*\n"
            
            for item in stats:
                porcentaje = (item['total'] / total) * 100
                signo_data = SIGNOS.get(item['signo'], {'emoji': ' ', 'nombre': item['signo']})
                mensaje += (
                    f"{signo_data['emoji']} *{signo_data['nombre']}:* "
                    f"{item['total']} ({porcentaje:.1f}%)\n"
                )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=mensaje,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Actualizar", callback_data="estadisticas"),
                     InlineKeyboardButton("⬅️ Volver", callback_data="inicio")]
                ])
            )
        else:
            await update.effective_message.reply_text(
                text=mensaje,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Volver al menú", callback_data="inicio")]
                ])
            )
            
    except Exception as e:
        logger.error(f"Error mostrando estadísticas: {e}")
        await handle_error(update, context)

async def mostrar_info_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información sobre la zona VIP con opciones de pago"""
    try:
        user = update.effective_user
        es_vip = db.verificar_vip(user.id)
        
        if es_vip:
            usuario = db.obtener_usuario(user.id)
            fecha_vip = datetime.strptime(usuario['fecha_vip'], '%Y-%m-%d').strftime('%d/%m/%Y') if usuario.get('fecha_vip') else "indefinida"
            
            info_texto = (
                "🌟 *Zona VIP Premium*\n\n"
                "¡Ya eres miembro VIP! Disfruta de:\n\n"
                "• Predicciones extendidas exclusivas\n"
                "• Horóscopo semanal y mensual\n"
                "• Compatibilidad amorosa detallada\n"
                "• Consejos astrológicos personalizados\n\n"
                f"📅 *Suscripción válida hasta:* {fecha_vip}"
            )
            
            teclado = [
                [InlineKeyboardButton("⬅️ Volver", callback_data="inicio")]
            ]
        else:
            info_texto = (
                f"🌟 *Zona VIP Premium* - {PRECIO_VIP}€/año\n\n"
                "Beneficios exclusivos:\n\n"
                "• Predicciones extendidas detalladas\n"
                "• Horóscopo semanal y mensual\n"
                "• Análisis de compatibilidad amorosa\n"
                "• Consejos astrológicos personalizados\n\n"
                "Selecciona método de pago:"
            )
            
            teclado = [
                [InlineKeyboardButton("💳 Pagar con PayPal", url=METODOS_PAGO["paypal"])],
                [InlineKeyboardButton("📱 Pagar con Bizum", callback_data="pago_bizum")],
                [InlineKeyboardButton("✅ Ya he pagado", callback_data="verificar_pago")],
                [InlineKeyboardButton("⬅️ Volver", callback_data="inicio")]
            ]
        
        await update.callback_query.edit_message_text(
            text=info_texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(teclado)
        )
        
    except Exception as e:
        logger.error(f"Error mostrando info VIP: {e}")
        await handle_error(update, context)

async def manejar_pago_bizum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra instrucciones para pago con Bizum"""
    try:
        instrucciones = (
            f"📱 *Pago con Bizum* - {PRECIO_VIP}€\n\n"
            "1. Abre tu app de banca móvil\n"
            "2. Selecciona la opción Bizum\n"
            f"3. Envía {PRECIO_VIP}€ a este número: *{METODOS_PAGO['bizum']}*\n"
            "4. Incluye este código como concepto: \n"
            f"`VIP{update.effective_user.id}`\n\n"
            "Después de pagar, haz clic en '✅ Ya he pagado'"
        )
        
        await update.callback_query.edit_message_text(
            text=instrucciones,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya he pagado", callback_data="verificar_pago")],
                [InlineKeyboardButton("⬅️ Volver", callback_data="info_vip")]
            ])
        )
    except Exception as e:
        logger.error(f"Error en pago Bizum: {e}")
        await handle_error(update, context)

async def verificar_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica el pago (simulado - implementar lógica real)"""
    try:
        user_id = update.effective_user.id
        
        # EN PRODUCCIÓN: Implementar verificación real con API de pago
        # Esta es una simulación que marca como pagado
        if db.activar_vip(user_id, "bizum", PRECIO_VIP):
            mensaje = (
                "🎉 *¡Pago verificado!*\n\n"
                "Ahora tienes acceso completo a la Zona VIP Premium.\n\n"
                "Disfruta de tu contenido exclusivo durante 1 año."
            )
        else:
            mensaje = "❌ No hemos podido verificar tu pago. Por favor, inténtalo más tarde."
        
        await update.callback_query.edit_message_text(
            text=mensaje,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Volver al menú", callback_data="inicio")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error verificando pago: {e}")
        await handle_error(update, context)

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador centralizado de callbacks de botones"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("signo_"):
            signo = data[6:]
            await enviar_prediccion(update, context, signo)
            
        elif data == "estadisticas":
            await mostrar_estadisticas(update, context)
            
        elif data == "ayuda":
            await mostrar_ayuda(update, context)
            
        elif data == "configuracion":
            await mostrar_configuracion(update, context)
            
        elif data == "inicio":
            await start(update, context)
            
        elif data.startswith("hora_"):
            nueva_hora = data[5:]
            await cambiar_hora_envio(update, context, nueva_hora)
            
        elif data.startswith("notif_"):
            estado = data[6:]
            await cambiar_notificaciones(update, context, estado)
            
        elif data == "cambiar_signo":
            await mostrar_selector_signo(update, context)
            
        elif data.startswith("sel_signo_"):
            nuevo_signo = data[10:]
            await actualizar_signo_usuario(update, context, nuevo_signo)
            
        elif data == "info_vip":
            await mostrar_info_vip(update, context)
            
        elif data == "pago_bizum":
            await manejar_pago_bizum(update, context)
            
        elif data == "verificar_pago":
            await verificar_pago(update, context)
            
    except Exception as e:
        logger.error(f"Error manejando botones: {e}")
        await handle_error(update, context)

async def cambiar_hora_envio(update: Update, context: ContextTypes.DEFAULT_TYPE, hora: str):
    """Cambia la hora de envío programado"""
    try:
        user_id = update.effective_user.id
        hora_str = f"{hora}:00"
        
        with db.conn:
            db.conn.execute('''
                UPDATE usuarios SET hora_envio = ? WHERE user_id = ?
            ''', (hora_str, user_id))
        
        await update.callback_query.edit_message_text(
            text=f"⏰ Hora de envío actualizada a las {hora_str}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Volver a configuración", callback_data="configuracion")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error cambiando hora: {e}")
        await handle_error(update, context)

async def cambiar_notificaciones(update: Update, context: ContextTypes.DEFAULT_TYPE, estado: str):
    """Activa/desactiva notificaciones diarias"""
    try:
        user_id = update.effective_user.id
        nuevo_estado = estado == "on"
        estado_texto = "activadas" if nuevo_estado else "desactivadas"
        
        with db.conn:
            db.conn.execute('''
                UPDATE usuarios SET recibir_diario = ? WHERE user_id = ?
            ''', (nuevo_estado, user_id))
        
        await update.callback_query.edit_message_text(
            text=f"🔔 Notificaciones {estado_texto}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Volver a configuración", callback_data="configuracion")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error cambiando notificaciones: {e}")
        await handle_error(update, context)

async def mostrar_selector_signo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra teclado para cambiar signo zodiacal"""
    try:
        botones = []
        signos_ordenados = sorted(SIGNOS.items(), key=lambda x: x[1]['nombre'])
        
        # Agrupar signos en filas de 3
        for i in range(0, len(signos_ordenados), 3):
            fila = [
                InlineKeyboardButton(
                    f"{data['emoji']} {data['nombre']}",
                    callback_data=f"sel_signo_{signo}"
                )
                for signo, data in signos_ordenados[i:i+3]
            ]
            botones.append(fila)
        
        botones.append([InlineKeyboardButton("⬅️ Cancelar", callback_data="configuracion")])
        
        await update.callback_query.edit_message_text(
            text="♉ Selecciona tu nuevo signo zodiacal:",
            reply_markup=InlineKeyboardMarkup(botones)
        )
        
    except Exception as e:
        logger.error(f"Error mostrando selector de signo: {e}")
        await handle_error(update, context)

async def actualizar_signo_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE, nuevo_signo: str):
    """Actualiza el signo zodiacal del usuario"""
    try:
        user_id = update.effective_user.id
        
        if nuevo_signo not in SIGNOS:
            await update.callback_query.answer("⚠️ Signo no válido")
            return
            
        if db.actualizar_signo(user_id, nuevo_signo):
            signo_data = SIGNOS[nuevo_signo]
            await update.callback_query.edit_message_text(
                text=f"♉ Tu signo se ha actualizado a {signo_data['emoji']} {signo_data['nombre']}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Volver a configuración", callback_data="configuracion")]
                ])
            )
        else:
            await update.callback_query.answer("❌ Error al actualizar")
            
    except Exception as e:
        logger.error(f"Error actualizando signo: {e}")
        await handle_error(update, context)

async def enviar_horoscopos_diarios(context: ContextTypes.DEFAULT_TYPE):
    """Envía horóscopos programados a usuarios y canales"""
    try:
        logger.info("Iniciando envío diario de horóscopos")
        
        # Primero enviar a canales si está configurado
        if CANAL_ID:
            await enviar_a_canal(context)
        
        # Luego enviar a usuarios individuales
        for signo in SIGNOS:
            usuarios = db.obtener_usuarios_por_signo(signo)
            if not usuarios:
                continue
                
            for usuario in usuarios:
                try:
                    es_vip = db.verificar_vip(usuario['user_id'])
                    prediccion = await obtener_prediccion(signo, es_vip)
                    if not prediccion:
                        continue
                        
                    signo_data = SIGNOS[signo]
                    fecha = datetime.now().strftime("%d/%m/%Y")
                    
                    mensaje = (
                        f"🌟 *Horóscopo Diario {signo_data['emoji']} {signo_data['nombre']}*\n"
                        f"📅 {fecha}\n"
                        "━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{prediccion}\n\n"
                        "✨ Que tengas un día maravilloso!"
                    )
                    
                    await context.bot.send_message(
                        chat_id=usuario['chat_id'],
                        text=mensaje,
                        parse_mode="Markdown"
                    )
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.warning(f"No se pudo enviar a {usuario['user_id']}: {e}")
                    continue
        
        logger.info("Envío diario completado")
        
    except Exception as e:
        logger.error(f"Error en envío diario: {e}")

async def enviar_a_canal(context: ContextTypes.DEFAULT_TYPE):
    """Envía todos los horóscopos al canal configurado"""
    try:
        fecha = datetime.now().strftime("%d/%m/%Y")
        mensaje_cabecera = (
            f"🌟 *Horóscopos Diarios* 🌟\n"
            f"📅 *Fecha:* {fecha}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Selecciona tu signo para más detalles:"
        )
        
        # Enviar cabecera
        await context.bot.send_message(
            chat_id=CANAL_ID,
            text=mensaje_cabecera,
            parse_mode="Markdown"
        )
        
        # Enviar cada signo como mensaje separado
        for signo in SIGNOS:
            prediccion = await obtener_prediccion(signo)
            if not prediccion:
                continue
                
            signo_data = SIGNOS[signo]
            mensaje = (
                f"{signo_data['emoji']} *{signo_data['nombre']}*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{prediccion}\n\n"
                f"🔮 /horoscopo_{signo}"
            )
            
            await context.bot.send_message(
                chat_id=CANAL_ID,
                text=mensaje,
                parse_mode="Markdown"
            )
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error enviando a canal: {e}")

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador centralizado de errores"""
    error_msg = "⚠️ Ocurrió un error inesperado. Por favor, inténtalo de nuevo más tarde."
    
    try:
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
    except Exception as e:
        logger.error(f"Error al manejar error: {e}")

def main():
    """Función principal con manejo mejorado de cierre"""
    try:
        if not TOKEN:
            raise ValueError("No se ha configurado el token del bot")
        
        # Configuración de la aplicación
        application = ApplicationBuilder() \
            .token(TOKEN) \
            .read_timeout(30) \
            .write_timeout(30) \
            .build()
        
        # Registro de handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("ayuda", mostrar_ayuda))
        application.add_handler(CommandHandler("configurar", mostrar_configuracion))
        application.add_handler(CommandHandler("estadisticas", mostrar_estadisticas))
        application.add_handler(CommandHandler("horoscopo", 
            lambda u, c: enviar_prediccion(u, c, context.args[0] if context.args else None)))
        
        application.add_handler(CallbackQueryHandler(manejar_botones))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))
        
        # Programar tarea diaria
        application.job_queue.run_daily(
            enviar_horoscopos_diarios,
            time=HORA_ENVIO,
            name="envio_diario_horoscopos"
        )
        
        logger.info("Iniciando bot...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.critical(f"Error fatal: {e}")
    finally:
        db.close()
        logger.info("Bot detenido")

if __name__ == "__main__":
    main()
