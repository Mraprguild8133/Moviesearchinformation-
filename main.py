"""
Main Flask application for Telegram Movie Bot
Handles webhook setup and routing for Render.com deployment
"""

import os
import logging
from flask import Flask, request, jsonify
from bot import MovieTVBot
from config import Config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize bot
bot = MovieTVBot()

# Determine if we should use polling or webhook based on environment
USE_POLLING = os.environ.get('USE_POLLING', 'False').lower() == 'true'

@app.route('/', methods=['GET'])
def index():
    """Health check endpoint"""
    return jsonify({
        'status': 'active',
        'message': 'Movie & TV Telegram Bot is running',
        'bot_username': bot.bot_username if hasattr(bot, 'bot_username') else 'N/A',
        'mode': 'polling' if USE_POLLING else 'webhook'
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram webhook updates"""
    try:
        update_data = request.get_json()
        if update_data:
            logger.info(f"Received webhook update: {update_data.get('update_id', 'N/A')}")
            bot.handle_update(update_data)
            return jsonify({'status': 'ok'})
        else:
            logger.warning("Received empty webhook data")
            return jsonify({'error': 'No data received'}), 400
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    """Set webhook URL for the bot"""
    try:
        webhook_url = request.json.get('url') if request.json else None
        if not webhook_url:
            return jsonify({'error': 'URL is required'}), 400
        
        success = bot.set_webhook(webhook_url)
        if success:
            return jsonify({'status': 'Webhook set successfully'})
        else:
            return jsonify({'error': 'Failed to set webhook'}), 500
    except Exception as e:
        logger.error(f"Set webhook error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/remove_webhook', methods=['POST'])
def remove_webhook():
    """Remove webhook and switch to polling"""
    try:
        success = bot.remove_webhook()
        if success:
            return jsonify({'status': 'Webhook removed successfully'})
        else:
            return jsonify({'error': 'Failed to remove webhook'}), 500
    except Exception as e:
        logger.error(f"Remove webhook error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/stats', methods=['GET'])
def stats():
    """Get bot statistics"""
    try:
        stats = bot.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        return jsonify({'error': 'Failed to get stats'}), 500

def setup_webhook():
    """Setup webhook URL automatically if in production"""
    if not USE_POLLING:
        webhook_url = os.environ.get('WEBHOOK_URL')
        if webhook_url:
            logger.info(f"Setting up webhook: {webhook_url}")
            success = bot.set_webhook(webhook_url)
            if success:
                logger.info("Webhook set successfully")
            else:
                logger.error("Failed to set webhook")
        else:
            logger.warning("WEBHOOK_URL environment variable not set")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Setup webhook if not using polling
    if not USE_POLLING:
        setup_webhook()
    else:
        logger.info("Starting in polling mode")
        bot.start_polling()
    
    logger.info(f"Starting Flask app on port {port}")
    logger.info(f"Bot @{bot.bot_username} is ready to receive messages")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if USE_POLLING:
            bot.stop_polling()
