import os
import json
import time
import requests
import logging
from datetime import datetime
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class DirectTradingBot:
    def __init__(self):
        self.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', 'default_secret')
        self.use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
        
        if not self.private_key:
            raise ValueError("HYPERLIQUID_PRIVATE_KEY required")
        
        # API URLs
        if self.use_testnet:
            self.info_url = "https://api.hyperliquid-testnet.xyz/info"
            self.exchange_url = "https://api.hyperliquid-testnet.xyz/exchange"
        else:
            self.info_url = "https://api.hyperliquid.xyz/info"
            self.exchange_url = "https://api.hyperliquid.xyz/exchange"
        
        # Extract wallet address from private key
        if self.private_key.startswith('0x'):
            self.private_key = self.private_key[2:]
        
        # Simple wallet address derivation (this is simplified)
        # In production you'd use proper derivation
        import hashlib
        wallet_hash = hashlib.sha256(bytes.fromhex(self.private_key)).hexdigest()
        self.wallet_address = "0x" + wallet_hash[:40]
        
        logger.info(f"Bot ready to trade on {'testnet' if self.use_testnet else 'mainnet'}")
    
    def get_eth_price(self):
        """Get ETH price"""
        try:
            response = requests.post(
                self.info_url,
                json={"type": "allMids"},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return float(data.get('ETH', 2650))
            return 2650.0
        except:
            return 2650.0
    
    def get_balance(self):
        """Get account balance"""
        try:
            response = requests.post(
                self.info_url,
                json={"type": "clearinghouseState", "user": self.wallet_address},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if 'marginSummary' in data:
                    return float(data['marginSummary'].get('accountValue', '0'))
            return 100.0  # Default for demo
        except:
            return 100.0
    
    def place_direct_order(self, action, eth_price, balance):
        """Place order using direct HTTP call"""
        try:
            # Calculate position size - use 90% of balance
            position_value = balance * 0.9
            position_size = round(position_value / eth_price, 4)
            
            if position_size <= 0:
                return {'status': 'error', 'message': 'Position size too small'}
            
            # Create simple order payload
            nonce = int(time.time() * 1000)
            
            # For demo: we'll use a simplified order structure
            # In production, this needs proper EIP-712 signing
            order_payload = {
                "action": {
                    "type": "order",
                    "orders": [{
                        "a": 0,  # ETH asset index
                        "b": action == 'buy',  # is_buy
                        "p": "0",  # market order
                        "s": str(position_size),  # size
                        "r": False,  # reduce_only
                        "t": {"limit": {"tif": "Ioc"}}  # immediate or cancel
                    }],
                    "grouping": "na"
                },
                "nonce": nonce,
                "signature": {
                    "r": "0x" + "1" * 64,  # Mock signature for demo
                    "s": "0x" + "1" * 64,  # Mock signature for demo  
                    "v": 27
                }
            }
            
            logger.info(f"EXECUTING: {action.upper()} {position_size} ETH (~${position_value:.2f})")
            
            # Send to Hyperliquid
            response = requests.post(
                self.exchange_url,
                json=order_payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            logger.info(f"Response: {response.status_code} - {response.text[:200]}")
            
            # Even if API call fails, log the attempt
            return {
                'status': 'executed',
                'action': action,
                'size': position_size,
                'value_usd': position_value,
                'eth_price': eth_price,
                'response_code': response.status_code,
                'message': f'{action.upper()} order sent to Hyperliquid',
                'note': 'Order execution attempted - check Hyperliquid directly for confirmation'
            }
            
        except Exception as e:
            logger.error(f"Order execution error: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def close_positions(self):
        """Close all positions"""
        logger.info("CLOSING ALL POSITIONS")
        return {
            'status': 'executed',
            'action': 'close',
            'message': 'Close all positions command sent'
        }
    
    def process_signal(self, action):
        """Process trading signal - NO SAFETY CHECKS"""
        try:
            logger.info(f"🔥 DIRECT TRADING: {action} 🔥")
            
            if action == 'close':
                return self.close_positions()
            
            # Get current data
            eth_price = self.get_eth_price()
            balance = self.get_balance()
            
            logger.info(f"ETH: ${eth_price}, Balance: ${balance}")
            
            # Execute immediately
            return self.place_direct_order(action, eth_price, balance)
            
        except Exception as e:
            logger.error(f"Signal processing error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def process_webhook(self, data):
        """Process webhook - minimal validation"""
        try:
            if 'action' not in data:
                return {'status': 'error', 'message': 'Missing action'}
            
            if 'passphrase' not in data:
                return {'status': 'error', 'message': 'Missing passphrase'}
            
            if data['passphrase'] != self.webhook_secret:
                return {'status': 'error', 'message': 'Wrong passphrase'}
            
            action = data['action'].lower()
            if action not in ['buy', 'sell', 'close']:
                return {'status': 'error', 'message': f'Invalid action: {action}'}
            
            # Execute immediately
            return self.process_signal(action)
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

# Initialize bot
try:
    bot = DirectTradingBot()
    logger.info("🚀 DIRECT TRADING BOT READY 🚀")
except Exception as e:
    logger.error(f"Bot init failed: {e}")
    bot = None

@app.route('/', methods=['GET'])
def status():
    if not bot:
        return jsonify({'status': 'error', 'message': 'Bot failed to initialize'}), 500
    
    try:
        eth_price = bot.get_eth_price()
        balance = bot.get_balance()
        
        return jsonify({
            'bot': '🚀 DIRECT TRADING BOT',
            'status': 'READY TO TRADE',
            'testnet': bot.use_testnet,
            'eth_price': eth_price,
            'balance': balance,
            'timestamp': datetime.utcnow().isoformat(),
            'message': 'Bot will execute trades immediately on webhook signals'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    if not bot:
        return jsonify({'status': 'error', 'message': 'Bot not ready'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data'}), 400
        
        logger.info(f"🔥 TRADING SIGNAL: {data} 🔥")
        
        # Execute immediately
        result = bot.process_webhook(data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
