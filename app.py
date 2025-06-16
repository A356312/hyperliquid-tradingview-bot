import os
import json
import time
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class HyperliquidBot:
    def __init__(self):
        self.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', 'default_secret')
        self.use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
        
        if not self.private_key:
            logger.error("HYPERLIQUID_PRIVATE_KEY not found")
            raise ValueError("HYPERLIQUID_PRIVATE_KEY environment variable is required")
        
        # Set API URLs
        if self.use_testnet:
            self.info_url = "https://api.hyperliquid-testnet.xyz/info"
            self.exchange_url = "https://api.hyperliquid-testnet.xyz/exchange"
            self.chain_name = "Testnet"
        else:
            self.info_url = "https://api.hyperliquid.xyz/info"
            self.exchange_url = "https://api.hyperliquid.xyz/exchange"
            self.chain_name = "Mainnet"
        
        logger.info(f"Bot initialized for {'testnet' if self.use_testnet else 'mainnet'}")
        logger.info(f"Private key length: {len(self.private_key) if self.private_key else 0}")
    
    def test_connection(self) -> bool:
        """Test API connection"""
        try:
            response = requests.post(
                self.info_url,
                json={"type": "meta"},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("API connection successful")
                return True
            else:
                logger.error(f"API connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"API connection error: {e}")
            return False
    
    def get_eth_price(self) -> float:
        """Get current ETH price"""
        try:
            # Try allMids endpoint
            response = requests.post(
                self.info_url,
                json={"type": "allMids"},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                all_mids = response.json()
                if 'ETH' in all_mids:
                    price = float(all_mids['ETH'])
                    logger.info(f"ETH price: ${price}")
                    return price
            
            # Fallback: use a fixed price for testing
            logger.warning("Using fallback ETH price")
            return 3000.0
            
        except Exception as e:
            logger.error(f"Error getting ETH price: {e}")
            return 3000.0  # Fallback price
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get basic account info (simplified)"""
        try:
            # For now, return mock data to test the bot
            # In production, you'd implement proper account info fetching
            return {
                'balance': '100.0',
                'positions': [],
                'account_connected': True
            }
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {
                'balance': '0',
                'positions': [],
                'account_connected': False,
                'error': str(e)
            }
    
    def place_mock_order(self, action: str, size: float) -> Dict[str, Any]:
        """Place mock order for testing"""
        try:
            logger.info(f"MOCK ORDER: {action} {size} ETH")
            
            # Simulate order placement
            time.sleep(1)  # Simulate API delay
            
            return {
                'status': 'success',
                'message': f'Mock {action} order placed',
                'order_id': f'mock_{int(time.time())}',
                'size': size,
                'action': action,
                'note': 'This is a mock order - real trading disabled for safety'
            }
            
        except Exception as e:
            logger.error(f"Error in mock order: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def process_signal(self, action: str) -> Dict[str, Any]:
        """Process trading signal"""
        try:
            logger.info(f"Processing signal: {action}")
            
            if action == 'close':
                return {
                    'status': 'success',
                    'message': 'Mock close all positions',
                    'closed_positions': []
                }
            
            # Get price for position sizing
            eth_price = self.get_eth_price()
            
            # Mock position size calculation
            mock_balance = 100.0  # $100 mock balance
            position_size = round((mock_balance * 0.95) / eth_price, 4)
            
            # Place mock order
            result = self.place_mock_order(action, position_size)
            return result
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def process_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process TradingView webhook"""
        try:
            # Validate webhook
            if 'action' not in data:
                return {'status': 'error', 'message': 'Missing action field'}
            
            if 'passphrase' not in data:
                return {'status': 'error', 'message': 'Missing passphrase field'}
            
            if data['passphrase'] != self.webhook_secret:
                return {'status': 'error', 'message': 'Invalid passphrase'}
            
            action = data['action'].lower()
            if action not in ['buy', 'sell', 'close']:
                return {'status': 'error', 'message': f'Invalid action: {action}'}
            
            # Process the signal
            return self.process_signal(action)
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return {'status': 'error', 'message': str(e)}

# Initialize bot with better error handling
bot = None
try:
    logger.info("Initializing bot...")
    bot = HyperliquidBot()
    
    # Test connection
    if bot.test_connection():
        logger.info("Bot initialized successfully")
    else:
        logger.warning("Bot initialized but API connection failed")
        
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    # Don't crash - create a minimal bot for debugging
    class MockBot:
        def __init__(self):
            self.error = str(e)
        
        def process_webhook(self, data):
            return {'status': 'error', 'message': f'Bot init failed: {self.error}'}
    
    bot = MockBot()

@app.route('/', methods=['GET'])
def status():
    """Bot status endpoint"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot is None'}), 500
        
        if hasattr(bot, 'error'):
            return jsonify({
                'status': 'error', 
                'message': f'Bot initialization failed: {bot.error}',
                'debug': {
                    'has_private_key': bool(os.getenv('HYPERLIQUID_PRIVATE_KEY')),
                    'private_key_length': len(os.getenv('HYPERLIQUID_PRIVATE_KEY', '')),
                    'webhook_secret': bool(os.getenv('WEBHOOK_SECRET')),
                    'testnet': os.getenv('USE_TESTNET', 'false')
                }
            }), 500
        
        # Get bot info
        account_info = bot.get_account_info()
        eth_price = bot.get_eth_price()
        
        return jsonify({
            'bot': 'Hyperliquid ETH Trading Bot (HTTP Mock)',
            'status': 'operational',
            'symbol': 'ETH',
            'testnet': bot.use_testnet,
            'account_connected': account_info['account_connected'],
            'balance': account_info['balance'],
            'positions': len(account_info['positions']),
            'eth_price': eth_price,
            'timestamp': datetime.utcnow().isoformat(),
            'version': 'HTTP-Mock-1.0',
            'note': 'Mock mode active - orders are simulated for safety'
        })
        
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'debug': {
                'bot_exists': bot is not None,
                'bot_type': type(bot).__name__
            }
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView webhook endpoint"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot not available'}), 500
        
        # Parse JSON
        try:
            data = request.get_json()
            if not data:
                return jsonify({'status': 'error', 'message': 'No JSON data'}), 400
        except Exception as e:
            logger.error(f"JSON parse error: {e}")
            return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400
        
        logger.info(f"Received webhook: {data}")
        
        # Process webhook
        result = bot.process_webhook(data)
        
        # Return result
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Critical error in webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/debug', methods=['GET'])
def debug():
    """Debug endpoint"""
    return jsonify({
        'environment_variables': {
            'HYPERLIQUID_PRIVATE_KEY': 'SET' if os.getenv('HYPERLIQUID_PRIVATE_KEY') else 'NOT SET',
            'WEBHOOK_SECRET': 'SET' if os.getenv('WEBHOOK_SECRET') else 'NOT SET',
            'USE_TESTNET': os.getenv('USE_TESTNET', 'NOT SET'),
            'PORT': os.getenv('PORT', 'NOT SET')
        },
        'bot_status': {
            'initialized': bot is not None,
            'type': type(bot).__name__ if bot else None,
            'has_error': hasattr(bot, 'error') if bot else False
        }
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
