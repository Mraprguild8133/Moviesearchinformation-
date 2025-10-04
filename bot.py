"""
Telegram Bot implementation for Movie and TV Show recommendations
Handles all bot commands and user interactions
"""

import os
import json
import logging
import requests
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from api_services import TMDBService, OMDBService, YouTubeService
from user_manager import UserManager
from recommendation_engine import RecommendationEngine
from config import Config

logger = logging.getLogger(__name__)

class MovieTVBot:
    def __init__(self):
        self.config = Config()
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.bot_username = None
        self.last_update_id = 0
        self.polling = False
        self.polling_thread = None
        
        # Initialize services
        self.tmdb = TMDBService()
        self.omdb = OMDBService()
        self.youtube = YouTubeService()
        self.user_manager = UserManager()
        self.recommendation_engine = RecommendationEngine(self.tmdb, self.user_manager)
        
        # Get bot info
        self._get_bot_info()
        
        # Command handlers
        self.commands = {
            '/start': self.handle_start,
            '/help': self.handle_help,
            '/movie': self.handle_movie_search,
            '/tv': self.handle_tv_search,
            '/recommend': self.handle_recommendations,
            '/popular': self.handle_popular,
            '/trending': self.handle_trending,
            '/myprofile': self.handle_profile
        }
        
    def _get_bot_info(self):
        """Get bot information"""
        try:
            response = requests.get(f"https://api.telegram.org/bot{self.bot_token}/getMe")
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    self.bot_username = data['result']['username']
                    logger.info(f"Bot initialized: @{self.bot_username}")
                    logger.info(f"Bot ID: {data['result']['id']}")
                    logger.info(f"Bot can join groups: {data['result'].get('can_join_groups', False)}")
                else:
                    logger.error(f"Failed to get bot info: {data.get('description', 'Unknown error')}")
            else:
                logger.error(f"HTTP error getting bot info: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to get bot info: {str(e)}")

    def handle_update(self, update_data: Dict[str, Any]):
        """Process incoming Telegram update"""
        try:
            if 'message' in update_data:
                self._handle_message(update_data['message'])
            elif 'callback_query' in update_data:
                self._handle_callback_query(update_data['callback_query'])
        except Exception as e:
            logger.error(f"Error handling update: {str(e)}")

    def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming text messages"""
        try:
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            text = message.get('text', '')
            
            # Register/update user
            self.user_manager.update_user_activity(
                user_id, 
                message['from'].get('username', ''),
                message['from'].get('first_name', '')
            )
            
            # Check for commands
            if text.startswith('/'):
                command_parts = text.split(' ', 1)
                command = command_parts[0].split('@')[0]  # Remove bot username if present
                query = command_parts[1] if len(command_parts) > 1 else ''
                
                if command in self.commands:
                    self.commands[command](chat_id, user_id, query)
                else:
                    self.send_message(chat_id, "Unknown command. Use /help to see available commands.")
            else:
                # Handle non-command messages as search queries
                self._handle_general_search(chat_id, user_id, text)
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")

    def _handle_callback_query(self, callback_query: Dict[str, Any]):
        """Handle inline keyboard callbacks"""
        try:
            chat_id = callback_query['message']['chat']['id']
            user_id = callback_query['from']['id']
            data = callback_query['data']
            
            # Parse callback data
            action, *params = data.split(':')
            
            if action == 'movie_details':
                movie_id = int(params[0])
                self._show_movie_details(chat_id, user_id, movie_id)
            elif action == 'tv_details':
                tv_id = int(params[0])
                self._show_tv_details(chat_id, user_id, tv_id)
            elif action == 'get_trailer':
                content_type = params[0]
                content_id = int(params[1])
                self._get_trailer(chat_id, content_type, content_id)
            elif action == 'recommend_similar':
                content_type = params[0]
                content_id = int(params[1])
                self._recommend_similar(chat_id, user_id, content_type, content_id)
                
            # Answer the callback query
            self._answer_callback_query(callback_query['id'])
            
        except Exception as e:
            logger.error(f"Error handling callback query: {str(e)}")

    def handle_start(self, chat_id: int, user_id: int, query: str = ''):
        """Handle /start command"""
        welcome_message = """
🎬 Welcome to Movie & TV Bot! 🎬

I can help you discover movies and TV shows with:
• Search for movies and TV shows
• Get detailed information and ratings
• Find trailers on YouTube
• Get personalized recommendations
• View trending and popular content

Use these commands:
/movie [title] - Search for movies
/tv [title] - Search for TV shows
/recommend - Get personalized recommendations
/popular - View popular content
/trending - View trending content
/help - Show this help message

Just type a movie or TV show name to start searching! 🍿
        """
        self.send_message(chat_id, welcome_message)

    def handle_help(self, chat_id: int, user_id: int, query: str = ''):
        """Handle /help command"""
        help_message = """
🎬 Movie & TV Bot Commands:

/movie [title] - Search for movies
Example: /movie Inception

/tv [title] - Search for TV shows  
Example: /tv Breaking Bad

/recommend - Get personalized recommendations based on your viewing history

/popular - View currently popular movies and TV shows

/trending - View trending content today

/myprofile - View your watching profile and statistics

You can also just type any movie or TV show name without a command!

💡 Tips:
• Use specific titles for better results
• Check out the inline buttons for trailers and similar content
• The more you search, the better your recommendations become!
        """
        self.send_message(chat_id, help_message)

    def handle_movie_search(self, chat_id: int, user_id: int, query: str):
        """Handle /movie command"""
        if not query.strip():
            self.send_message(chat_id, "Please provide a movie title. Example: /movie Inception")
            return
            
        self._search_content(chat_id, user_id, query, 'movie')

    def handle_tv_search(self, chat_id: int, user_id: int, query: str):
        """Handle /tv command"""
        if not query.strip():
            self.send_message(chat_id, "Please provide a TV show title. Example: /tv Breaking Bad")
            return
            
        self._search_content(chat_id, user_id, query, 'tv')

    def handle_recommendations(self, chat_id: int, user_id: int, query: str = ''):
        """Handle /recommend command"""
        try:
            recommendations = self.recommendation_engine.get_user_recommendations(user_id)
            
            if not recommendations:
                message = """
🤔 I don't have enough data to make personalized recommendations yet.

Try searching for some movies or TV shows first:
/movie <title>
/tv <title>

Or check out what's popular:
/popular
/trending
                """
                self.send_message(chat_id, message)
                return
            
            message = "🎯 Your Personalized Recommendations:\n\n"
            for i, item in enumerate(recommendations[:5], 1):
                content_type = 'movie' if item.get('media_type') == 'movie' else 'tv'
                title = item.get('title', item.get('name', 'Unknown'))
                year = item.get('release_date', item.get('first_air_date', ''))[:4] if item.get('release_date') or item.get('first_air_date') else 'N/A'
                rating = item.get('vote_average', 0)
                
                message += f"{i}. {title} ({year}) ⭐ {rating:.1f}/10\n"
                
            keyboard = self._create_recommendations_keyboard(recommendations[:5])
            self.send_message(chat_id, message, keyboard)
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get recommendations right now. Please try again later.")

    def handle_popular(self, chat_id: int, user_id: int, query: str = ''):
        """Handle /popular command"""
        try:
            movies = self.tmdb.get_popular_movies()
            tv_shows = self.tmdb.get_popular_tv()
            
            message = "🔥 Popular This Week:\n\n📽️ Movies:\n"
            for i, movie in enumerate(movies[:3], 1):
                year = movie.get('release_date', '')[:4] if movie.get('release_date') else 'N/A'
                rating = movie.get('vote_average', 0)
                message += f"{i}. {movie['title']} ({year}) ⭐ {rating:.1f}/10\n"
                
            message += "\n📺 TV Shows:\n"
            for i, tv in enumerate(tv_shows[:3], 1):
                year = tv.get('first_air_date', '')[:4] if tv.get('first_air_date') else 'N/A'
                rating = tv.get('vote_average', 0)
                message += f"{i}. {tv['name']} ({year}) ⭐ {rating:.1f}/10\n"
            
            keyboard = self._create_popular_keyboard(movies[:3], tv_shows[:3])
            self.send_message(chat_id, message, keyboard)
            
        except Exception as e:
            logger.error(f"Error getting popular content: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get popular content right now. Please try again later.")

    def handle_trending(self, chat_id: int, user_id: int, query: str = ''):
        """Handle /trending command"""
        try:
            trending = self.tmdb.get_trending()
            
            if not trending:
                self.send_message(chat_id, "Sorry, I couldn't get trending content right now.")
                return
                
            message = "📈 Trending Today:\n\n"
            for i, item in enumerate(trending[:5], 1):
                title = item.get('title', item.get('name', 'Unknown'))
                content_type = '📽️' if item.get('media_type') == 'movie' else '📺'
                year = item.get('release_date', item.get('first_air_date', ''))[:4] if item.get('release_date') or item.get('first_air_date') else 'N/A'
                rating = item.get('vote_average', 0)
                
                message += f"{i}. {content_type} {title} ({year}) ⭐ {rating:.1f}/10\n"
            
            keyboard = self._create_trending_keyboard(trending[:5])
            self.send_message(chat_id, message, keyboard)
            
        except Exception as e:
            logger.error(f"Error getting trending content: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get trending content right now. Please try again later.")

    def handle_profile(self, chat_id: int, user_id: int, query: str = ''):
        """Handle /myprofile command"""
        try:
            user_data = self.user_manager.get_user_data(user_id)
            if not user_data:
                self.send_message(chat_id, "You haven't searched for any content yet. Start exploring! 🎬")
                return
                
            search_count = len(user_data.get('search_history', []))
            preferences = user_data.get('preferences', {})
            favorite_genres = list(preferences.get('genres', {}).keys())[:3]
            
            message = f"""
👤 Your Profile:

🔍 Total Searches: {search_count}
📊 Favorite Genres: {', '.join(favorite_genres) if favorite_genres else 'Still learning your taste!'}
📅 Member Since: {user_data.get('first_seen', 'Recently')}

Keep exploring to get better recommendations! 🎯
            """
            
            self.send_message(chat_id, message)
            
        except Exception as e:
            logger.error(f"Error getting user profile: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get your profile right now. Please try again later.")

    def _handle_general_search(self, chat_id: int, user_id: int, query: str):
        """Handle general text as search query"""
        if len(query.strip()) < 2:
            return
            
        # Try both movie and TV search
        results = []
        
        # Search movies
        movies = self.tmdb.search_movies(query)
        for movie in movies[:2]:
            movie['search_type'] = 'movie'
            results.append(movie)
            
        # Search TV shows
        tv_shows = self.tmdb.search_tv(query)
        for tv in tv_shows[:2]:
            tv['search_type'] = 'tv'
            results.append(tv)
        
        if not results:
            self.send_message(chat_id, f"No results found for '{query}'. Try a different search term! 🔍")
            return
            
        message = f"🔍 Search results for '{query}':\n\n"
        for i, item in enumerate(results, 1):
            title = item.get('title', item.get('name', 'Unknown'))
            content_type = '📽️' if item['search_type'] == 'movie' else '📺'
            year = item.get('release_date', item.get('first_air_date', ''))[:4] if item.get('release_date') or item.get('first_air_date') else 'N/A'
            rating = item.get('vote_average', 0)
            
            message += f"{i}. {content_type} {title} ({year}) ⭐ {rating:.1f}/10\n"
        
        keyboard = self._create_search_results_keyboard(results)
        self.send_message(chat_id, message, keyboard)

    def _search_content(self, chat_id: int, user_id: int, query: str, content_type: str):
        """Search for movies or TV shows"""
        try:
            if content_type == 'movie':
                results = self.tmdb.search_movies(query)
            else:
                results = self.tmdb.search_tv(query)
                
            if not results:
                self.send_message(chat_id, f"No {content_type}s found for '{query}'. Try a different search! 🔍")
                return
            
            # Track user search
            self.user_manager.track_search(user_id, query, content_type)
            
            # Show top results
            message = f"🔍 {content_type.title()} search results for '{query}':\n\n"
            for i, item in enumerate(results[:5], 1):
                title = item.get('title', item.get('name', 'Unknown'))
                year = item.get('release_date', item.get('first_air_date', ''))[:4] if item.get('release_date') or item.get('first_air_date') else 'N/A'
                rating = item.get('vote_average', 0)
                
                message += f"{i}. {title} ({year}) ⭐ {rating:.1f}/10\n"
            
            # Create inline keyboard for detailed view
            keyboard = self._create_content_keyboard(results[:5], content_type)
            self.send_message(chat_id, message, keyboard)
            
        except Exception as e:
            logger.error(f"Error searching {content_type}: {str(e)}")
            self.send_message(chat_id, f"Sorry, I couldn't search for {content_type}s right now. Please try again later.")

    def _show_movie_details(self, chat_id: int, user_id: int, movie_id: int):
        """Show detailed movie information"""
        try:
            # Get movie details from TMDB
            movie = self.tmdb.get_movie_details(movie_id)
            if not movie:
                self.send_message(chat_id, "Sorry, I couldn't find details for this movie.")
                return
            
            # Get additional details from OMDB
            omdb_data = self.omdb.get_movie_by_title(movie['title']) if movie.get('title') else None
            
            # Track interaction
            self.user_manager.track_interaction(user_id, movie_id, 'movie')
            
            # Prepare message
            title = movie.get('title', 'Unknown')
            year = movie.get('release_date', '')[:4] if movie.get('release_date') else 'N/A'
            runtime = f"{movie.get('runtime', 'N/A')} min" if movie.get('runtime') else 'N/A'
            rating_tmdb = movie.get('vote_average', 0)
            overview = movie.get('overview', 'No overview available.')
            
            # Genre information
            genres = [g['name'] for g in movie.get('genres', [])]
            genres_text = ', '.join(genres) if genres else 'N/A'
            
            # Ratings from multiple sources
            ratings_text = f"⭐ TMDB: {rating_tmdb:.1f}/10"
            if omdb_data:
                imdb_rating = omdb_data.get('imdbRating')
                if imdb_rating and imdb_rating != 'N/A':
                    ratings_text += f"\n⭐ IMDb: {imdb_rating}/10"
                    
                rt_rating = omdb_data.get('Ratings')
                if rt_rating:
                    for rating in rt_rating:
                        if 'Rotten Tomatoes' in rating.get('Source', ''):
                            ratings_text += f"\n🍅 RT: {rating.get('Value', 'N/A')}"
                            break
            
            message = f"""
🎬 {title} ({year})

📊 Ratings:
{ratings_text}

⏱️ Runtime: {runtime}
🎭 Genres: {genres_text}

📝 Overview:
{overview[:300]}{'...' if len(overview) > 300 else ''}
            """
            
            # Send poster if available
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
                self.send_photo(chat_id, poster_url, message)
            else:
                self.send_message(chat_id, message)
            
            # Create action buttons
            keyboard = self._create_detail_keyboard(movie_id, 'movie')
            self.send_message(chat_id, "What would you like to do?", keyboard)
            
        except Exception as e:
            logger.error(f"Error showing movie details: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get movie details right now.")

    def _show_tv_details(self, chat_id: int, user_id: int, tv_id: int):
        """Show detailed TV show information"""
        try:
            # Get TV details from TMDB
            tv = self.tmdb.get_tv_details(tv_id)
            if not tv:
                self.send_message(chat_id, "Sorry, I couldn't find details for this TV show.")
                return
            
            # Get additional details from OMDB
            omdb_data = self.omdb.get_movie_by_title(tv['name']) if tv.get('name') else None
            
            # Track interaction
            self.user_manager.track_interaction(user_id, tv_id, 'tv')
            
            # Prepare message
            name = tv.get('name', 'Unknown')
            first_air = tv.get('first_air_date', '')[:4] if tv.get('first_air_date') else 'N/A'
            last_air = tv.get('last_air_date', '')[:4] if tv.get('last_air_date') else 'N/A'
            seasons = tv.get('number_of_seasons', 'N/A')
            episodes = tv.get('number_of_episodes', 'N/A')
            rating_tmdb = tv.get('vote_average', 0)
            overview = tv.get('overview', 'No overview available.')
            status = tv.get('status', 'N/A')
            
            # Genre information
            genres = [g['name'] for g in tv.get('genres', [])]
            genres_text = ', '.join(genres) if genres else 'N/A'
            
            # Ratings from multiple sources
            ratings_text = f"⭐ TMDB: {rating_tmdb:.1f}/10"
            if omdb_data:
                imdb_rating = omdb_data.get('imdbRating')
                if imdb_rating and imdb_rating != 'N/A':
                    ratings_text += f"\n⭐ IMDb: {imdb_rating}/10"
            
            air_info = f"{first_air}"
            if status == "Ended" and last_air != first_air:
                air_info += f" - {last_air}"
            elif status != "Ended":
                air_info += f" - Present"
            
            message = f"""
📺 {name} ({air_info})

📊 Ratings:
{ratings_text}

📅 Status: {status}
🎭 Genres: {genres_text}
📺 Seasons: {seasons} | Episodes: {episodes}

📝 Overview:
{overview[:300]}{'...' if len(overview) > 300 else ''}
            """
            
            # Send poster if available
            if tv.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{tv['poster_path']}"
                self.send_photo(chat_id, poster_url, message)
            else:
                self.send_message(chat_id, message)
            
            # Create action buttons
            keyboard = self._create_detail_keyboard(tv_id, 'tv')
            self.send_message(chat_id, "What would you like to do?", keyboard)
            
        except Exception as e:
            logger.error(f"Error showing TV details: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get TV show details right now.")

    def _get_trailer(self, chat_id: int, content_type: str, content_id: int):
        """Find and send trailer for movie/TV show"""
        try:
            # Get content details first
            if content_type == 'movie':
                content = self.tmdb.get_movie_details(content_id)
                title = content.get('title', '') if content else ''
            else:
                content = self.tmdb.get_tv_details(content_id)
                title = content.get('name', '') if content else ''
            
            if not title:
                self.send_message(chat_id, "Sorry, I couldn't find the title to search for trailers.")
                return
            
            # Search for trailer on YouTube
            trailer_url = self.youtube.search_trailer(title, content_type)
            
            if trailer_url:
                message = f"🎬 Found trailer for {title}:\n\n{trailer_url}"
                self.send_message(chat_id, message)
            else:
                self.send_message(chat_id, f"Sorry, I couldn't find a trailer for {title} on YouTube.")
                
        except Exception as e:
            logger.error(f"Error getting trailer: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get the trailer right now.")

    def _recommend_similar(self, chat_id: int, user_id: int, content_type: str, content_id: int):
        """Get similar content recommendations"""
        try:
            if content_type == 'movie':
                similar = self.tmdb.get_similar_movies(content_id)
            else:
                similar = self.tmdb.get_similar_tv(content_id)
            
            if not similar:
                self.send_message(chat_id, "Sorry, I couldn't find similar content.")
                return
            
            message = f"🎯 Similar {content_type}s you might like:\n\n"
            for i, item in enumerate(similar[:5], 1):
                title = item.get('title', item.get('name', 'Unknown'))
                year = item.get('release_date', item.get('first_air_date', ''))[:4] if item.get('release_date') or item.get('first_air_date') else 'N/A'
                rating = item.get('vote_average', 0)
                
                message += f"{i}. {title} ({year}) ⭐ {rating:.1f}/10\n"
            
            keyboard = self._create_similar_keyboard(similar[:5], content_type)
            self.send_message(chat_id, message, keyboard)
            
        except Exception as e:
            logger.error(f"Error getting similar content: {str(e)}")
            self.send_message(chat_id, "Sorry, I couldn't get similar content right now.")

    # Keyboard creation methods
    def _create_content_keyboard(self, items: List[Dict], content_type: str) -> Dict:
        """Create inline keyboard for content list"""
        keyboard = []
        for i, item in enumerate(items):
            title = item.get('title', item.get('name', f'{content_type.title()} {i+1}'))
            callback_data = f"{content_type}_details:{item['id']}"
            keyboard.append([{'text': f"📖 {title}", 'callback_data': callback_data}])
        
        return {'inline_keyboard': keyboard}

    def _create_search_results_keyboard(self, items: List[Dict]) -> Dict:
        """Create inline keyboard for search results"""
        keyboard = []
        for i, item in enumerate(items):
            title = item.get('title', item.get('name', f'Result {i+1}'))
            content_type = item['search_type']
            callback_data = f"{content_type}_details:{item['id']}"
            icon = '📽️' if content_type == 'movie' else '📺'
            keyboard.append([{'text': f"{icon} {title}", 'callback_data': callback_data}])
        
        return {'inline_keyboard': keyboard}

    def _create_detail_keyboard(self, content_id: int, content_type: str) -> Dict:
        """Create inline keyboard for content details"""
        keyboard = [
            [{'text': '🎬 Watch Trailer', 'callback_data': f'get_trailer:{content_type}:{content_id}'}],
            [{'text': '🎯 Similar Content', 'callback_data': f'recommend_similar:{content_type}:{content_id}'}]
        ]
        return {'inline_keyboard': keyboard}

    def _create_recommendations_keyboard(self, items: List[Dict]) -> Dict:
        """Create inline keyboard for recommendations"""
        keyboard = []
        for i, item in enumerate(items):
            title = item.get('title', item.get('name', f'Recommendation {i+1}'))
            content_type = 'movie' if item.get('media_type') == 'movie' else 'tv'
            callback_data = f"{content_type}_details:{item['id']}"
            icon = '📽️' if content_type == 'movie' else '📺'
            keyboard.append([{'text': f"{icon} {title}", 'callback_data': callback_data}])
        
        return {'inline_keyboard': keyboard}

    def _create_popular_keyboard(self, movies: List[Dict], tv_shows: List[Dict]) -> Dict:
        """Create inline keyboard for popular content"""
        keyboard = []
        
        # Add movies
        for movie in movies:
            title = movie.get('title', 'Unknown Movie')
            callback_data = f"movie_details:{movie['id']}"
            keyboard.append([{'text': f"📽️ {title}", 'callback_data': callback_data}])
        
        # Add TV shows
        for tv in tv_shows:
            name = tv.get('name', 'Unknown TV Show')
            callback_data = f"tv_details:{tv['id']}"
            keyboard.append([{'text': f"📺 {name}", 'callback_data': callback_data}])
        
        return {'inline_keyboard': keyboard}

    def _create_trending_keyboard(self, items: List[Dict]) -> Dict:
        """Create inline keyboard for trending content"""
        keyboard = []
        for item in items:
            title = item.get('title', item.get('name', 'Unknown'))
            content_type = 'movie' if item.get('media_type') == 'movie' else 'tv'
            callback_data = f"{content_type}_details:{item['id']}"
            icon = '📽️' if content_type == 'movie' else '📺'
            keyboard.append([{'text': f"{icon} {title}", 'callback_data': callback_data}])
        
        return {'inline_keyboard': keyboard}

    def _create_similar_keyboard(self, items: List[Dict], content_type: str) -> Dict:
        """Create inline keyboard for similar content"""
        keyboard = []
        for item in items:
            title = item.get('title', item.get('name', 'Unknown'))
            callback_data = f"{content_type}_details:{item['id']}"
            icon = '📽️' if content_type == 'movie' else '📺'
            keyboard.append([{'text': f"{icon} {title}", 'callback_data': callback_data}])
        
        return {'inline_keyboard': keyboard}

    # Telegram API methods
    def send_message(self, chat_id: int, text: str, keyboard: Optional[Dict] = None):
        """Send message to Telegram chat"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text
            }
            
            if keyboard:
                data['reply_markup'] = json.dumps(keyboard)
            
            logger.info(f"Sending message to chat {chat_id}: {text[:50]}...")
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                logger.info(f"Message sent successfully to chat {chat_id}")
                return True
            else:
                logger.error(f"Failed to send message: {response.status_code} - {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False

    def send_photo(self, chat_id: int, photo_url: str, caption: str = ''):
        """Send photo to Telegram chat"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            data = {
                'chat_id': chat_id,
                'photo': photo_url,
                'caption': caption
            }
            
            response = requests.post(url, json=data)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error sending photo: {str(e)}")
            return False

    def _answer_callback_query(self, callback_query_id: str):
        """Answer callback query"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
            data = {'callback_query_id': callback_query_id}
            requests.post(url, json=data)
        except Exception as e:
            logger.error(f"Error answering callback query: {str(e)}")

    def set_webhook(self, webhook_url: str) -> bool:
        """Set webhook URL for the bot"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
            data = {'url': f"{webhook_url}/webhook"}
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Webhook set: {result}")
                return result.get('ok', False)
            return False
            
        except Exception as e:
            logger.error(f"Error setting webhook: {str(e)}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics"""
        try:
            total_users = len(self.user_manager.get_all_users())
            return {
                'total_users': total_users,
                'bot_username': self.bot_username,
                'status': 'active'
            }
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {'error': str(e)}

    def start_polling(self):
        """Start polling for updates"""
        if self.polling:
            return
        
        self.polling = False 
        self.polling_thread = threading.Thread(target=self._poll_updates)
        self.polling_thread.daemon = True
        self.polling_thread.start()
        logger.info("Started polling for updates")

    def stop_polling(self):
        """Stop polling for updates"""
        self.polling = False
        if self.polling_thread:
            self.polling_thread.join()
        logger.info("Stopped polling")

    def _poll_updates(self):
        """Poll for updates from Telegram"""
        logger.info("Starting polling loop...")
        while self.polling:
            try:
                updates = self._get_updates()
                if updates:
                    logger.info(f"Received {len(updates)} updates")
                    for update in updates:
                        try:
                            logger.info(f"Processing update: {update.get('update_id')}")
                            self.handle_update(update)
                            self.last_update_id = update['update_id'] + 1
                        except Exception as e:
                            logger.error(f"Error processing update {update.get('update_id')}: {str(e)}")
                else:
                    logger.debug("No new updates")
                time.sleep(1)  # Wait 1 second between polls
            except Exception as e:
                logger.error(f"Error in polling loop: {str(e)}")
                time.sleep(5)  # Wait 5 seconds on error

    def _get_updates(self) -> List[Dict]:
        """Get updates from Telegram API"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                'offset': self.last_update_id,
                'timeout': 10,
                'limit': 100
            }
            
            logger.debug(f"Polling with offset: {self.last_update_id}")
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    result = data.get('result', [])
                    if result:
                        logger.info(f"Got {len(result)} updates from Telegram")
                    return result
                else:
                    logger.error(f"Telegram API error: {data.get('description', 'Unknown error')}")
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
            return []
        except Exception as e:
            logger.error(f"Error getting updates: {str(e)}")
            return []
