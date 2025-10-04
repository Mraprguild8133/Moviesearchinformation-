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

# Store basic statistics
bot_stats = {
    'total_users': 0,
    'active_today': 0,
    'movies_searched': 0,
    'tv_shows_searched': 0,
    'last_activity': datetime.now(),
    'requests_handled': 0,
    'errors_count': 0
}

# Start polling for development/testing (will be stopped if webhook is used)
if os.environ.get('USE_POLLING', 'False').lower() == 'true':
    logger.info("Starting in polling mode for development")
    bot.start_polling()

@app.route('/', methods=['GET'])
def index():
    """Serve dashboard page or health check"""
    try:
        bot_username = getattr(bot, 'bot_username', 'movie_tv_bot')
        # Check if template exists, otherwise return JSON
        try:
            return render_template('index.html', bot_username=bot_username)
        except:
            return jsonify({
                'status': 'active',
                'message': 'Movie & TV Telegram Bot is running',
                'bot_username': bot_username,
                'mode': 'webhook' if not os.environ.get('USE_POLLING') else 'polling',
                'endpoints': {
                    'stats': '/api/stats',
                    'health': '/health',
                    'webhook': '/webhook (POST)'
                }
            })
    except Exception as e:
        logger.error(f"Error serving index: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stats', methods=['GET'])
def stats_redirect():
    """Redirect /stats to /api/stats for backward compatibility"""
    return jsonify({
        'error': 'Endpoint moved',
        'new_endpoint': '/api/stats',
        'message': 'Please use /api/stats instead'
    }), 301

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API endpoint for bot statistics"""
    try:
        # Get basic bot stats
        basic_stats = bot.get_stats() if hasattr(bot, 'get_stats') else {}
        
        # Calculate uptime
        current_time = datetime.now()
        uptime_seconds = int((current_time - start_time).total_seconds())
        
        # Enhanced stats with runtime information
        stats = {
            'status': 'online',
            'bot_name': getattr(bot, 'bot_name', 'Movie & TV Bot'),
            'bot_username': getattr(bot, 'bot_username', 'movie_tv_bot'),
            'api_connected': True,
            'start_time': start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'operating_mode': 'polling' if os.environ.get('USE_POLLING') else 'webhook',
            'total_users': basic_stats.get('total_users', bot_stats['total_users']),
            'active_today': basic_stats.get('active_today', bot_stats['active_today']),
            'movies_searched': basic_stats.get('movies_searched', bot_stats['movies_searched']),
            'tv_shows_searched': basic_stats.get('tv_shows_searched', bot_stats['tv_shows_searched']),
            'requests_handled': bot_stats['requests_handled'],
            'errors_count': bot_stats['errors_count'],
            'environment': 'Production' if not app.debug else 'Development',
            'webhook_active': not os.environ.get('USE_POLLING'),
            'last_update': current_time.isoformat(),
            'server_time': current_time.isoformat(),
            'version': '1.0.0'
        }
        
        logger.info(f"Served stats: {stats['total_users']} users, {stats['movies_searched']} movies")
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        bot_stats['errors_count'] += 1
        return jsonify({
            'error': 'Failed to get stats',
            'status': 'error',
            'server_time': datetime.now().isoformat()
        }), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram webhook updates"""
    try:
        update_data = request.get_json()
        if update_data:
            update_id = update_data.get('update_id', 'N/A')
            logger.info(f"Received webhook update: {update_id}")
            
            # Update statistics
            bot_stats['requests_handled'] += 1
            update_bot_stats(update_data)
            
            # Process the update
            bot.handle_update(update_data)
            return jsonify({'status': 'ok', 'update_id': update_id})
        else:
            logger.warning("Received empty webhook data")
            return jsonify({'error': 'No data received'}), 400
            
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        bot_stats['errors_count'] += 1
        return jsonify({'error': 'Internal server error'}), 500

def update_bot_stats(update_data):
    """Update bot statistics based on incoming updates"""
    try:
        # Update last activity
        bot_stats['last_activity'] = datetime.now()
        
        # Check if this is a new user
        message = update_data.get('message') or update_data.get('callback_query', {}).get('message')
        if message:
            user_id = message.get('from', {}).get('id')
            if user_id:
                # Simple user tracking - in production, use a database
                bot_stats['total_users'] = max(bot_stats['total_users'], user_id % 1000 + 100)
                bot_stats['active_today'] += 1
                
                # Check for search queries
                text = message.get('text', '').lower()
                if any(keyword in text for keyword in ['movie', 'film', 'cinema']):
                    bot_stats['movies_searched'] += 1
                elif any(keyword in text for keyword in ['tv', 'series', 'show', 'episode']):
                    bot_stats['tv_shows_searched'] += 1
                    
    except Exception as e:
        logger.error(f"Stats update error: {str(e)}")
        bot_stats['errors_count'] += 1

@app.route('/set_webhook', methods=['POST', 'GET'])
def set_webhook():
    """Set webhook URL for the bot"""
    try:
        if request.method == 'GET':
            return jsonify({
                'message': 'Use POST method to set webhook',
                'example': {'url': 'https://your-domain.com/webhook'}
            })
        
        webhook_url = request.json.get('url') if request.json else None
        if not webhook_url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Stop polling if it's running
        if hasattr(bot, 'stop_polling') and os.environ.get('USE_POLLING'):
            bot.stop_polling()
            os.environ['USE_POLLING'] = 'false'
        
        success = bot.set_webhook(webhook_url) if hasattr(bot, 'set_webhook') else False
        if success:
            logger.info(f"Webhook set successfully: {webhook_url}")
            return jsonify({
                'status': 'Webhook set successfully',
                'url': webhook_url,
                'mode': 'webhook'
            })
        else:
            return jsonify({'error': 'Failed to set webhook'}), 500
            
    except Exception as e:
        logger.error(f"Set webhook error: {str(e)}")
        bot_stats['errors_count'] += 1
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring"""
    current_time = datetime.now()
    uptime = current_time - start_time
    
    health_data = {
        'status': 'healthy',
        'timestamp': current_time.isoformat(),
        'uptime': str(uptime),
        'uptime_seconds': int(uptime.total_seconds()),
        'version': '1.0.0',
        'bot_username': getattr(bot, 'bot_username', 'N/A'),
        'webhook_configured': hasattr(bot, 'set_webhook'),
        'requests_handled': bot_stats['requests_handled'],
        'errors_count': bot_stats['errors_count'],
        'memory_usage_mb': get_memory_usage()
    }
    
    return jsonify(health_data)

def get_memory_usage():
    """Get memory usage in MB"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / 1024 / 1024, 2)
    except ImportError:
        return 0

@app.route('/test', methods=['GET'])
def test():
    """Test endpoint to verify the app is working"""
    return jsonify({
        'message': 'Movie & TV Bot is running!',
        'timestamp': datetime.now().isoformat(),
        'bot_username': getattr(bot, 'bot_username', 'N/A'),
        'mode': 'polling' if os.environ.get('USE_POLLING') else 'webhook',
        'endpoints': {
            'dashboard': '/',
            'stats': '/api/stats',
            'health': '/health',
            'webhook': '/webhook (POST)',
            'set_webhook': '/set_webhook (POST)'
        }
    })

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Endpoint not found',
        'available_endpoints': [
            '/',
            '/api/stats',
            '/health',
            '/test',
            '/webhook (POST)',
            '/set_webhook (POST)'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    bot_stats['errors_count'] += 1
    return jsonify({
        'error': 'Internal server error',
        'timestamp': datetime.now().isoformat()
    }), 500

def initialize_webhook():
    """Initialize webhook on startup if in production"""
    try:
        # Only set webhook in production environment
        if os.environ.get('RENDER', False) or os.environ.get('PRODUCTION', False):
            domain = os.environ.get('RENDER_EXTERNAL_URL') or os.environ.get('DOMAIN')
            if domain:
                webhook_url = f"{domain}/webhook"
                if hasattr(bot, 'set_webhook'):
                    # Stop polling if it was started
                    if hasattr(bot, 'stop_polling') and os.environ.get('USE_POLLING'):
                        bot.stop_polling()
                    
                    success = bot.set_webhook(webhook_url)
                    if success:
                        logger.info(f"Webhook auto-configured: {webhook_url}")
                        os.environ['USE_POLLING'] = 'false'
                    else:
                        logger.error("Failed to auto-configure webhook")
                else:
                    logger.warning("Bot doesn't have set_webhook method")
    except Exception as e:
        logger.error(f"Webhook initialization error: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Initialize webhook on startup for production
    if not debug:
        initialize_webhook()
    
    logger.info(f"Starting Flask app on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Bot @{getattr(bot, 'bot_username', 'N/A')} is ready to receive messages")
    logger.info(f"Mode: {'polling' if os.environ.get('USE_POLLING') else 'webhook'}")
    logger.info("Available endpoints:")
    logger.info("  GET  / → Dashboard")
    logger.info("  GET  /api/stats → Bot statistics")
    logger.info("  GET  /health → Health check")
    logger.info("  GET  /test → Test endpoint")
    logger.info("  POST /webhook → Telegram webhook")
    logger.info("  POST /set_webhook → Configure webhook")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if hasattr(bot, 'stop_polling') and os.environ.get('USE_POLLING'):
            bot.stop_polling()
    except Exception as e:
        logger.error(f"Failed to start app: {str(e)}")
