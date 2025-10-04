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
try:
    bot = MovieTVBot()
    logger.info("MovieTVBot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize bot: {str(e)}")
    bot = None

start_time = datetime.now()

def setup_webhook():
    """Set webhook URL on startup"""
    if not bot:
        logger.error("Cannot set webhook - bot not initialized")
        return False
        
    try:
        # Get the webhook URL based on environment
        if 'RENDER_EXTERNAL_URL' in os.environ:
            webhook_url = f"{os.environ['RENDER_EXTERNAL_URL']}/webhook"
        else:
            # Fallback for local development
            webhook_url = f"https://{request.host}/webhook" if request.host else None
            
        if webhook_url:
            success = bot.set_webhook(webhook_url)
            if success:
                logger.info(f"Webhook set successfully: {webhook_url}")
                return True
            else:
                logger.error("Failed to set webhook")
                return False
        else:
            logger.warning("Could not determine webhook URL")
            return False
    except Exception as e:
        logger.error(f"Webhook setup error: {str(e)}")
        return False

@app.before_request
def before_first_request():
    """Set up webhook before first request"""
    if not hasattr(app, 'webhook_configured'):
        if bot:
            setup_webhook()
        app.webhook_configured = True

@app.route('/', methods=['GET'])
def index():
    """Serve dashboard page"""
    bot_username = getattr(bot, 'bot_username', 'movie_tv_bot') if bot else 'movie_tv_bot'
    bot_status = "Online" if bot else "Offline"
    return render_template('index.html', 
                         bot_username=bot_username, 
                         bot_status=bot_status)

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API endpoint for bot statistics"""
    try:
        # Check bot connection status
        bot_connected = False
        bot_info = {}
        
        if bot:
            try:
                bot_info = bot.get_me()
                bot_connected = True if bot_info else False
            except:
                bot_connected = False

        # Get basic bot stats
        basic_stats = bot.get_stats() if bot and hasattr(bot, 'get_stats') else {}
        
        # Enhanced stats with runtime information
        stats = {
            'status': 'online' if bot_connected else 'offline',
            'bot_connected': bot_connected,
            'bot_name': getattr(bot, 'bot_name', 'Movie & TV Bot'),
            'bot_username': bot_info.get('username', 'N/A') if bot_info else 'N/A',
            'api_connected': True,  # You can implement actual API health check
            'api_key_status': 'Connected',  # Implement TMDB API health check
            'start_time': start_time.isoformat(),
            'operating_mode': 'webhook',
            'total_users': basic_stats.get('total_users', 0),
            'active_today': basic_stats.get('active_today', 0),
            'movies_searched': basic_stats.get('movies_searched', 0),
            'tv_shows_searched': basic_stats.get('tv_shows_searched', 0),
            'environment': 'Production' if not app.debug else 'Development',
            'webhook_active': bot_connected,
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
        if not bot:
            logger.error("Bot not initialized - cannot process webhook")
            return jsonify({'error': 'Bot not available'}), 503
            
        if not request.is_json:
            logger.warning("Received non-JSON webhook request")
            return jsonify({'error': 'Content-Type must be application/json'}), 400
            
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

@app.route('/set_webhook', methods=['POST', 'GET'])
def set_webhook():
    """Set webhook URL for the bot"""
    try:
        if not bot:
            return jsonify({'error': 'Bot not initialized'}), 503
            
        if request.method == 'POST':
            webhook_url = request.json.get('url') if request.json else None
        else:
            webhook_url = request.args.get('url')
            
        if not webhook_url:
            # Auto-detect URL
            if 'RENDER_EXTERNAL_URL' in os.environ:
                webhook_url = f"{os.environ['RENDER_EXTERNAL_URL']}/webhook"
            else:
                webhook_url = f"https://{request.host}/webhook"
        
        success = bot.set_webhook(webhook_url)
        if success:
            return jsonify({
                'status': 'success', 
                'message': 'Webhook set successfully',
                'webhook_url': webhook_url
            })
        else:
            return jsonify({'error': 'Failed to set webhook'}), 500
    except Exception as e:
        logger.error(f"Set webhook error: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/delete_webhook', methods=['POST', 'GET'])
def delete_webhook():
    """Delete webhook URL"""
    try:
        if not bot:
            return jsonify({'error': 'Bot not initialized'}), 503
            
        success = bot.delete_webhook()
        if success:
            return jsonify({'status': 'success', 'message': 'Webhook deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete webhook'}), 500
    except Exception as e:
        logger.error(f"Delete webhook error: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring"""
    try:
        bot_status = "connected" if bot and bot.get_me() else "disconnected"
        bot_username = bot.get_me().username if bot and bot.get_me() else "N/A"
    except Exception as e:
        bot_status = "disconnected"
        bot_username = "N/A"
    
    return jsonify({
        'status': 'healthy',
        'bot_status': bot_status,
        'bot_username': bot_username,
        'timestamp': datetime.now().isoformat(),
        'uptime': str(datetime.now() - start_time),
        'version': '1.0.0',
        'environment': 'production'
    })

@app.route('/test', methods=['GET'])
def test_bot():
    """Test bot functionality"""
    try:
        if not bot:
            return jsonify({'error': 'Bot not initialized'}), 503
            
        bot_info = bot.get_me()
        return jsonify({
            'status': 'success',
            'bot_info': {
                'id': bot_info.id,
                'username': bot_info.username,
                'first_name': bot_info.first_name
            },
            'message': 'Bot is working correctly'
        })
    except Exception as e:
        logger.error(f"Test error: {str(e)}")
        return jsonify({'error': f'Bot test failed: {str(e)}'}), 500

@app.route('/debug', methods=['GET'])
def debug_info():
    """Debug information endpoint"""
    env_vars = {
        'TELEGRAM_BOT_TOKEN_set': 'TELEGRAM_BOT_TOKEN' in os.environ,
        'TMDB_API_KEY_set': 'TMDB_API_KEY' in os.environ,
        'RENDER_EXTERNAL_URL': os.environ.get('RENDER_EXTERNAL_URL', 'Not set'),
        'PORT': os.environ.get('PORT', '5000'),
        'DEBUG': os.environ.get('DEBUG', 'False')
    }
    
    return jsonify({
        'environment_variables': env_vars,
        'bot_initialized': bot is not None,
        'flask_debug': app.debug,
        'current_time': datetime.now().isoformat()
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask app on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    # Initial webhook setup
    if bot:
        try:
            bot_info = bot.get_me()
            logger.info(f"Bot @{bot_info.username} is ready to receive messages")
            # Setup webhook on startup
            setup_webhook()
        except Exception as e:
            logger.error(f"Bot connection failed: {str(e)}")
    else:
        logger.error("Bot failed to initialize - check TELEGRAM_BOT_TOKEN environment variable")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if bot and hasattr(bot, 'stop_polling'):
            bot.stop_polling()
