# app.py (updated)
import os
import logging
import time
from flask import Flask, request, jsonify
from bot import MovieTVBot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize bot with error handling
try:
    bot = MovieTVBot()
    logger.info("Bot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize bot: {str(e)}")
    bot = None

IS_PRODUCTION = os.environ.get('RENDER', False)

@app.route('/', methods=['GET'])
def index():
    if not bot:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    return jsonify({
        'status': 'active',
        'bot_username': bot.bot.username if hasattr(bot, 'bot') else 'N/A',
        'mode': 'webhook' if IS_PRODUCTION else 'polling'
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    if not bot:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        update = request.get_json()
        bot.handle_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    if not bot:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    webhook_url = request.json.get('url')
    if not webhook_url:
        return jsonify({'error': 'URL is required'}), 400
    
    success = bot.set_webhook(webhook_url)
    return jsonify({'status': 'success' if success else 'failed'})

if __name__ == '__main__':
    if not IS_PRODUCTION and bot:
        logger.info("Starting polling in development mode")
        bot.start_polling()
    else:
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=not IS_PRODUCTION)
