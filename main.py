"""
Main Flask application for Telegram Movie Bot
Handles webhook setup and routing for Render.com deployment
"""

import os
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from bot import MovieTVBot
from config import Config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize bot and track start time
bot = MovieTVBot()
start_time = datetime.now()

@app.route('/', methods=['GET'])
def index():
    """Serve dashboard page"""
    bot_username = getattr(bot, 'bot_username', 'movie_tv_bot')
    return render_template('index.html', bot_username=bot_username)

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API endpoint for bot statistics"""
    try:
        # Get basic bot stats
        basic_stats = bot.get_stats() if hasattr(bot, 'get_stats') else {}
        
        # Enhanced stats with runtime information
        stats = {
            'status': 'online',
            'bot_name': getattr(bot, 'bot_name', 'Movie & TV Bot'),
            'bot_username': getattr(bot, 'bot_username', 'N/A'),
            'api_connected': True,  # You can implement actual API health check
            'api_key_status': 'Connected',  # Implement TMDB API health check
            'start_time': start_time.isoformat(),
            'operating_mode': 'webhook',
            'total_users': basic_stats.get('total_users', 0),
            'active_today': basic_stats.get('active_today', 0),
            'movies_searched': basic_stats.get('movies_searched', 0),
            'tv_shows_searched': basic_stats.get('tv_shows_searched', 0),
            'environment': 'Production' if not app.debug else 'Development',
            'webhook_active': True,
            'last_update': datetime.now().isoformat(),
            'server_time': datetime.now().isoformat()
        }
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        return jsonify({'error': 'Failed to get stats'}), 500

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

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime': str(datetime.now() - start_time),
        'version': '1.0.0'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask app on port {port}")
    logger.info(f"Bot @{getattr(bot, 'bot_username', 'N/A')} is ready to receive messages")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if hasattr(bot, 'stop_polling'):
            bot.stop_polling()
