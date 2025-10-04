"""
Main Flask application for Telegram Movie Bot
Handles webhook setup and routing for Render.com deployment
"""

import os
import logging
import time
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

# Environment-based initialization
IS_PRODUCTION = os.environ.get('RENDER', False) or os.environ.get('ENVIRONMENT') == 'production'

class BotStatusDashboard:
    """Centralized bot status management"""
    
    STATUS_TEMPLATES = {
        # Active States
        'running': "🟢 Bot is running normally",
        'processing': "🟡 Processing request...",
        'searching': "🔍 Searching database...",
        'fetching': "📡 Fetching external data...",
        
        # Warning States
        'rate_limited': "⚠️ Rate limited - slowing down",
        'api_down': "🌐 External API temporarily unavailable",
        'high_load': "🔥 High load - responses may be delayed",
        
        # Error States
        'error': "🔴 Error encountered",
        'maintenance': "🛠️ Maintenance mode",
        'offline': "⚫ Bot offline"
    }
    
    def __init__(self):
        self.current_status = 'running'
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.last_update = time.time()
    
    def update_status(self, new_status, message=None):
        """Update bot status with optional message"""
        if new_status in self.STATUS_TEMPLATES:
            self.current_status = new_status
            self.last_update = time.time()
            status_msg = self.STATUS_TEMPLATES[new_status]
            if message:
                status_msg += f" - {message}"
            logger.info(f"Status changed: {status_msg}")
            return status_msg
        return None
    
    def increment_request(self):
        """Increment request counter"""
        self.request_count += 1
    
    def increment_error(self):
        """Increment error counter"""
        self.error_count += 1
    
    def get_uptime(self):
        """Get bot uptime in human readable format"""
        uptime_seconds = time.time() - self.start_time
        return self._format_uptime(uptime_seconds)
    
    def _format_uptime(self, seconds):
        """Format uptime to human readable string"""
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m {seconds}s"

class UserStatusTemplates:
    """Templates for user-facing status messages"""
    
    @staticmethod
    def processing_search(query):
        return f"🔍 Searching for: *{query}*"
    
    @staticmethod
    def found_results(count, query):
        return f"✅ Found *{count}* results for: *{query}*"
    
    @staticmethod
    def no_results(query):
        return f"❌ No results found for: *{query}*"
    
    @staticmethod
    def maintenance_mode():
        return "🛠️ *Bot Maintenance*\n\nWe're currently performing maintenance. Please try again later."
    
    @staticmethod
    def rate_limited(retry_after=None):
        if retry_after:
            return f"⚠️ *Rate Limited*\n\nPlease wait {retry_after} seconds before making another request."
        return "⚠️ *Rate Limited*\n\nPlease wait a moment before making another request."
    
    @staticmethod
    def error_occurred():
        return "❌ *Error Occurred*\n\nAn unexpected error occurred. Please try again."

class AdminStatusTemplates:
    """Templates for admin/internal status messages"""
    
    @staticmethod
    def system_stats(status_dashboard):
        return (
            f"🤖 *Bot System Status*\n\n"
            f"• Status: {status_dashboard.STATUS_TEMPLATES[status_dashboard.current_status]}\n"
            f"• Uptime: {status_dashboard.get_uptime()}\n"
            f"• Total Requests: {status_dashboard.request_count}\n"
            f"• Errors: {status_dashboard.error_count}\n"
            f"• Last Update: {time.ctime(status_dashboard.last_update)}\n"
            f"• Mode: {'Production' if IS_PRODUCTION else 'Development'}"
        )
    
    @staticmethod
    def status_change(old_status, new_status):
        return f"🔄 *Status Change*\n\nFrom: {old_status}\nTo: {new_status}"

# Initialize status dashboard
status_dashboard = BotStatusDashboard()

# Start polling only in development
if not IS_PRODUCTION:
    logger.info("Starting in development mode with polling")
    try:
        bot.start_polling()
        status_dashboard.update_status('running', 'Development mode with polling')
    except Exception as e:
        logger.error(f"Failed to start polling: {str(e)}")
        status_dashboard.update_status('error', f'Polling failed: {str(e)}')
else:
    status_dashboard.update_status('running', 'Production mode with webhooks')

@app.route('/', methods=['GET'])
def index():
    """Health check endpoint"""
    status_dashboard.increment_request()
    
    return jsonify({
        'status': 'active',
        'message': 'Movie & TV Telegram Bot is running',
        'bot_username': bot.bot_username if hasattr(bot, 'bot_username') else 'N/A',
        'mode': 'webhook' if IS_PRODUCTION else 'polling',
        'system_status': status_dashboard.current_status,
        'status_message': status_dashboard.STATUS_TEMPLATES[status_dashboard.current_status],
        'uptime': status_dashboard.get_uptime()
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram webhook updates"""
    status_dashboard.increment_request()
    
    try:
        # Verify this is a legitimate Telegram request (optional but recommended)
        webhook_secret = os.environ.get('WEBHOOK_SECRET')
        if IS_PRODUCTION and webhook_secret:
            if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != webhook_secret:
                logger.warning("Unauthorized webhook access attempt")
                status_dashboard.increment_error()
                return jsonify({'error': 'Unauthorized'}), 401
            
        update_data = request.get_json()
        if update_data:
            logger.info(f"Received webhook update: {update_data.get('update_id', 'N/A')}")
            bot.handle_update(update_data)
            return jsonify({'status': 'ok'})
        else:
            logger.warning("Received empty webhook data")
            status_dashboard.increment_error()
            return jsonify({'error': 'No data received'}), 400
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        status_dashboard.increment_error()
        status_dashboard.update_status('error', f'Webhook error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    """Set webhook URL for the bot"""
    status_dashboard.increment_request()
    
    try:
        webhook_url = request.json.get('url') if request.json else None
        secret_token = os.environ.get('WEBHOOK_SECRET', 'your-secret-token-here')
        
        if not webhook_url:
            return jsonify({'error': 'URL is required'}), 400
        
        success = bot.set_webhook(webhook_url, secret_token=secret_token)
        if success:
            status_dashboard.update_status('running', 'Webhook set successfully')
            return jsonify({
                'status': 'Webhook set successfully',
                'url': webhook_url,
                'mode': 'webhook'
            })
        else:
            status_dashboard.update_status('error', 'Failed to set webhook')
            return jsonify({'error': 'Failed to set webhook'}), 500
    except Exception as e:
        logger.error(f"Set webhook error: {str(e)}")
        status_dashboard.increment_error()
        status_dashboard.update_status('error', f'Set webhook failed: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/stats', methods=['GET'])
def stats():
    """Get bot statistics"""
    status_dashboard.increment_request()
    
    try:
        bot_stats = bot.get_stats() if hasattr(bot, 'get_stats') else {}
        
        stats_data = {
            'system': {
                'status': status_dashboard.current_status,
                'status_message': status_dashboard.STATUS_TEMPLATES[status_dashboard.current_status],
                'uptime': status_dashboard.get_uptime(),
                'start_time': status_dashboard.start_time,
                'last_update': status_dashboard.last_update,
                'mode': 'webhook' if IS_PRODUCTION else 'polling'
            },
            'requests': {
                'total_requests': status_dashboard.request_count,
                'error_count': status_dashboard.error_count,
                'success_rate': f"{((status_dashboard.request_count - status_dashboard.error_count) / status_dashboard.request_count * 100):.1f}%" if status_dashboard.request_count > 0 else "0%"
            },
            'bot': bot_stats
        }
        
        return jsonify(stats_data)
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        status_dashboard.increment_error()
        return jsonify({'error': 'Failed to get stats'}), 500

@app.route('/status', methods=['GET', 'POST'])
def manage_status():
    """Get or update bot status"""
    status_dashboard.increment_request()
    
    if request.method == 'GET':
        return jsonify({
            'current_status': status_dashboard.current_status,
            'status_message': status_dashboard.STATUS_TEMPLATES[status_dashboard.current_status],
            'available_statuses': list(status_dashboard.STATUS_TEMPLATES.keys()),
            'last_updated': status_dashboard.last_update
        })
    
    elif request.method == 'POST':
        try:
            new_status = request.json.get('status')
            message = request.json.get('message')
            
            if new_status not in status_dashboard.STATUS_TEMPLATES:
                return jsonify({
                    'error': 'Invalid status',
                    'available_statuses': list(status_dashboard.STATUS_TEMPLATES.keys())
                }), 400
            
            old_status = status_dashboard.current_status
            status_message = status_dashboard.update_status(new_status, message)
            
            logger.info(f"Status changed manually: {old_status} -> {new_status}")
            
            return jsonify({
                'old_status': old_status,
                'new_status': new_status,
                'status_message': status_message,
                'timestamp': status_dashboard.last_update
            })
            
        except Exception as e:
            logger.error(f"Status update error: {str(e)}")
            status_dashboard.increment_error()
            return jsonify({'error': 'Failed to update status'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    status_dashboard.increment_request()
    
    health_data = {
        'status': 'healthy',
        'timestamp': time.time(),
        'services': {
            'bot': 'operational',
            'web_server': 'operational',
            'database': 'unknown',  # Would be updated based on your actual DB checks
            'external_apis': 'unknown'  # Would be updated based on your API checks
        },
        'system': {
            'status': status_dashboard.current_status,
            'uptime': status_dashboard.get_uptime(),
            'memory_usage': 'N/A',  # You can add psutil for system metrics
            'load': 'N/A'
        }
    }
    
    return jsonify(health_data)

@app.route('/maintenance', methods=['POST'])
def maintenance_mode():
    """Enable/disable maintenance mode"""
    status_dashboard.increment_request()
    
    try:
        enable = request.json.get('enable', True)
        message = request.json.get('message', 'Scheduled maintenance')
        
        if enable:
            status_dashboard.update_status('maintenance', message)
            return jsonify({
                'status': 'maintenance_enabled',
                'message': message
            })
        else:
            status_dashboard.update_status('running', 'Maintenance completed')
            return jsonify({
                'status': 'maintenance_disabled',
                'message': 'Back to normal operation'
            })
            
    except Exception as e:
        logger.error(f"Maintenance mode error: {str(e)}")
        status_dashboard.increment_error()
        return jsonify({'error': 'Failed to update maintenance mode'}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(error):
    status_dashboard.increment_error()
    status_dashboard.update_status('error', 'Internal server error')
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask app on port {port}")
    logger.info(f"Bot mode: {'Production' if IS_PRODUCTION else 'Development'}")
    logger.info(f"Current status: {status_dashboard.STATUS_TEMPLATES[status_dashboard.current_status]}")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        status_dashboard.update_status('offline', 'Manual shutdown')
        if not IS_PRODUCTION:
            bot.stop_polling()
    except Exception as e:
        logger.error(f"Failed to start Flask app: {str(e)}")
        status_dashboard.update_status('error', f'Startup failed: {str(e)}')
