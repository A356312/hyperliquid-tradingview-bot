import os
import ccxt
import json
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class HyperliquidBot:
    def __init__(self):
        self.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', 'default_secret')
        self.use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
        
        if not self.private_key:
            raise ValueError("HYPERLIQUID_PRIVATE_KEY environment variable required")
        
        # Initialize CCXT exchange
        try:
            if self.use_testnet:
                # Testnet setup
                self.exchange = ccxt.hyperliquid({
                    'apiKey': '',  # Not needed for spot trading
                    'secret': '',  # Not needed for spot trading
                    'private_key': self.private_key,
                    'testnet': True,
                    'sandbox': True,
                })
            else:
                # Mainnet setup
                self.exchange = ccxt.hyperliquid({
                    'apiKey': '',  # Not needed for spot trading
                    'secret': '',  # Not needed for spot trading  
                    'private_key': self.private_key,
                    'testnet': False,
                    'sandbox': False,
                })
            
            # Load markets
            self.exchange.load_markets()
            logger.info("Successfully connected to Hyperliquid")
            
        except Exception as e:
            logger.error(f"Failed to initialize exchange: {e}")
            raise
    
    def get_balance(self):
        """Get account balance"""
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return None
    
    def get_eth_price(self):
        """Get current ETH price"""
        try:
            ticker = self.exchange.fetch_ticker('ETH/USDC')
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"Error fetching ETH price: {e}")
            return 0
    
    def get_positions(self):
        """Get current positions"""
        try:
            positions = self.exchange.fetch_positions(['ETH/USDC'])
            open_positions = [pos for pos in positions if float(pos['contracts']) != 0]
            return open_positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def place_market_order(self, side, amount):
        """Place market order"""
        try:
            symbol = 'ETH/USDC'
            
            logger.info(f"Placing {side} order: {amount} ETH")
            
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=side,  # 'buy' or 'sell'
                amount=amount,
                params={}
            )
            
            logger.info(f"Order placed successfully: {order}")
            return {
                'status': 'success',
                'order': order,
                'side': side,
                'amount': amount
            }
            
        except Exception as e:
            logger.error(f"Error placing {side} order: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'side': side,
                'amount': amount
            }
    
    def close_all_positions(self):
        """Close all open positions"""
        try:
            positions = self.get_positions()
            
            if not positions:
                return {
                    'status': 'success',
                    'message': 'No positions to close',
                    'closed_positions': []
                }
            
            closed_results = []
            
            for position in positions:
                try:
                    size = abs(float(position['contracts']))
                    side = 'sell' if float(position['contracts']) > 0 else 'buy'
                    
                    result = self.place_market_order(side, size)
                    closed_results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error closing position: {e}")
                    closed_results.append({
                        'status': 'error',
                        'message': str(e)
                    })
            
            return {
                'status': 'success',
                'message': f'Closed {len(closed_results)} positions',
                'closed_positions': closed_results
            }
            
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def calculate_position_size(self, balance_usd, eth_price):
        """Calculate position size based on balance"""
        try:
            if balance_usd <= 0 or eth_price <= 0:
                return 0
            
            # Use 95% of available balance
            usable_balance = balance_usd * 0.95
            position_size = usable_balance / eth_price
            
            # Round to 4 decimal places
            position_size = round(position_size, 4)
            
            logger.info(f"Position size: {position_size} ETH (${usable_balance} / ${eth_price})")
            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    def process_signal(self, action):
        """Process trading signal"""
        try:
            logger.info(f"Processing signal: {action}")
            
            if action == 'close':
                return self.close_all_positions()
            
            # Get current balance and price
            balance = self.get_balance()
            if not balance:
                return {'status': 'error', 'message': 'Could not fetch balance'}
            
            usdc_balance = float(balance.get('USDC', {}).get('free', 0))
            
            if usdc_balance < 10:  # Minimum $10
                return {
                    'status': 'error', 
                    'message': f'Insufficient balance: ${usdc_balance}'
                }
            
            eth_price = self.get_eth_price()
            if eth_price <= 0:
                return {'status': 'error', 'message': f'Invalid ETH price: {eth_price}'}
            
            # Calculate position size
            position_size = self.calculate_position_size(usdc_balance, eth_price)
            if position_size <= 0:
                return {
                    'status': 'error', 
                    'message': f'Invalid position size: {position_size}'
                }
            
            # Place order
            side = 'buy' if action == 'buy' else 'sell'
            result = self.place_market_order(side, position_size)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def process_webhook(self, data):
        """Process TradingView webhook"""
        try:
            # Validate required fields
            if 'action' not in data:
                return {'status': 'error', 'message': 'Missing action field'}
            
            if 'passphrase' not in data:
                return {'status': 'error', 'message': 'Missing passphrase field'}
            
            # Check passphrase
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

# Initialize bot
try:
    bot = HyperliquidBot()
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    bot = None

@app.route('/', methods=['GET'])
def status():
    """Bot status endpoint"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 500
        
        balance = bot.get_balance()
        eth_price = bot.get_eth_price()
        positions = bot.get_positions()
        
        return jsonify({
            'bot': 'Hyperliquid ETH Trading Bot (CCXT)',
            'status': 'operational',
            'symbol': 'ETH/USDC',
            'testnet': bot.use_testnet,
            'balance': balance.get('USDC', {}).get('free', 0) if balance else 0,
            'positions': len(positions),
            'eth_price': eth_price,
            'timestamp': datetime.utcnow().isoformat(),
            'version': 'CCXT-1.0'
        })
        
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView webhook endpoint"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 500
        
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
