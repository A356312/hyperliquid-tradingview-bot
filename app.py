import os
import json
import time
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from eth_account import Account
from eth_account.messages import encode_structured_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class HyperliquidRealBot:
    def __init__(self):
        self.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', 'default_secret')
        self.use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
        self.max_position_usd = float(os.getenv('MAX_POSITION_USD', '50'))  # Default $50 max
        
        if not self.private_key:
            raise ValueError("HYPERLIQUID_PRIVATE_KEY environment variable is required")
        
        # Initialize account
        try:
            self.account = Account.from_key(self.private_key)
            self.wallet_address = self.account.address
            logger.info(f"Wallet address: {self.wallet_address}")
        except Exception as e:
            logger.error(f"Failed to initialize account: {e}")
            raise
        
        # Set API URLs
        if self.use_testnet:
            self.info_url = "https://api.hyperliquid-testnet.xyz/info"
            self.exchange_url = "https://api.hyperliquid-testnet.xyz/exchange"
            self.chain_name = "Testnet"
        else:
            self.info_url = "https://api.hyperliquid.xyz/info"
            self.exchange_url = "https://api.hyperliquid.xyz/exchange"
            self.chain_name = "Mainnet"
        
        # Get ETH asset info
        self.eth_asset_id = None
        self.get_asset_info()
        
        logger.info(f"Real trading bot initialized for {self.chain_name}")
        logger.info(f"Max position size: ${self.max_position_usd}")
    
    def get_asset_info(self) -> bool:
        """Get ETH asset ID"""
        try:
            response = requests.post(
                self.info_url,
                json={"type": "meta"},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get meta info: {response.status_code}")
                return False
            
            meta = response.json()
            
            # Find ETH asset
            for i, asset in enumerate(meta.get('universe', [])):
                if asset.get('name') == 'ETH':
                    self.eth_asset_id = i
                    logger.info(f"ETH asset ID: {self.eth_asset_id}")
                    return True
            
            logger.error("ETH asset not found")
            return False
            
        except Exception as e:
            logger.error(f"Error getting asset info: {e}")
            return False
    
    def get_eth_price(self) -> float:
        """Get current ETH price"""
        try:
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
            
            logger.error("Could not get ETH price")
            return 0
            
        except Exception as e:
            logger.error(f"Error getting ETH price: {e}")
            return 0
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get real account info"""
        try:
            response = requests.post(
                self.info_url,
                json={"type": "clearinghouseState", "user": self.wallet_address},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get account info: {response.status_code}")
                return {
                    'balance': '0',
                    'positions': [],
                    'account_connected': False
                }
            
            user_state = response.json()
            balance = '0'
            positions = []
            
            # Get balance
            if 'marginSummary' in user_state:
                balance = user_state['marginSummary'].get('accountValue', '0')
            
            # Get positions
            if 'assetPositions' in user_state:
                for pos in user_state['assetPositions']:
                    position = pos.get('position', {})
                    if position.get('coin') == 'ETH':
                        size = float(position.get('szi', '0'))
                        if abs(size) > 0.0001:
                            positions.append({
                                'symbol': 'ETH',
                                'size': size,
                                'side': 'long' if size > 0 else 'short'
                            })
            
            return {
                'balance': balance,
                'positions': positions,
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
    
    def sign_action(self, action: Dict[str, Any], nonce: int) -> Dict[str, str]:
        """Sign action for Hyperliquid"""
        try:
            structured_data = {
                "types": {
                    "EIP712Domain": [
                        {"name": "name", "type": "string"},
                        {"name": "version", "type": "string"},
                        {"name": "chainId", "type": "uint256"},
                        {"name": "verifyingContract", "type": "address"}
                    ],
                    "HyperliquidTransaction:Perpetuals": [
                        {"name": "signatureChainId", "type": "uint256"},
                        {"name": "hyperliquidChain", "type": "string"},
                        {"name": "nonce", "type": "uint64"},
                        {"name": "action", "type": "string"}
                    ]
                },
                "domain": {
                    "name": "HyperliquidSignTransaction",
                    "version": "1",
                    "chainId": 42161,
                    "verifyingContract": "0x0000000000000000000000000000000000000000"
                },
                "primaryType": "HyperliquidTransaction:Perpetuals",
                "message": {
                    "signatureChainId": 42161,
                    "hyperliquidChain": self.chain_name,
                    "nonce": nonce,
                    "action": json.dumps(action, separators=(',', ':'))
                }
            }
            
            encoded = encode_structured_data(structured_data)
            signature = self.account.sign_message(encoded)
            
            return {
                "r": "0x" + signature.r.to_bytes(32, 'big').hex(),
                "s": "0x" + signature.s.to_bytes(32, 'big').hex(),
                "v": signature.v
            }
            
        except Exception as e:
            logger.error(f"Error signing action: {e}")
            raise
    
    def place_market_order(self, is_buy: bool, size: float) -> Dict[str, Any]:
        """Place REAL market order"""
        try:
            if not self.eth_asset_id:
                return {'status': 'error', 'message': 'ETH asset ID not found'}
            
            nonce = int(time.time() * 1000)
            
            # Create order action
            action = {
                "type": "order",
                "orders": [{
                    "a": self.eth_asset_id,
                    "b": is_buy,
                    "p": "0",
                    "s": str(size),
                    "r": False,
                    "t": {
                        "limit": {
                            "tif": "Ioc"
                        }
                    }
                }],
                "grouping": "na"
            }
            
            # Sign the action
            signature = self.sign_action(action, nonce)
            
            # Prepare request
            payload = {
                "action": action,
                "nonce": nonce,
                "signature": signature
            }
            
            logger.info(f"Placing REAL {('BUY' if is_buy else 'SELL')} order: {size} ETH")
            
            # Send to Hyperliquid
            response = requests.post(
                self.exchange_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            logger.info(f"Order response: {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'status': 'success',
                    'message': f'REAL {"BUY" if is_buy else "SELL"} order placed',
                    'result': result,
                    'size': size,
                    'side': 'buy' if is_buy else 'sell'
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Order failed: {response.status_code} - {response.text}',
                    'size': size
                }
                
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {
                'status': 'error',
                'message': f'Order error: {str(e)}'
            }
    
    def close_all_positions(self) -> Dict[str, Any]:
        """Close all positions"""
        try:
            account_info = self.get_account_info()
            positions = account_info['positions']
            
            if not positions:
                return {
                    'status': 'success',
                    'message': 'No positions to close',
                    'closed_positions': []
                }
            
            closed_results = []
            
            for position in positions:
                size = abs(position['size'])
                is_buy = (position['side'] == 'short')  # Close long=sell, close short=buy
                
                result = self.place_market_order(is_buy, size)
                closed_results.append({
                    'position': position,
                    'close_result': result
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
                'message': f'Close error: {str(e)}'
            }
    
    def calculate_position_size(self, balance: float, eth_price: float) -> float:
        """Calculate safe position size"""
        try:
            if balance <= 0 or eth_price <= 0:
                return 0
            
            # Use smaller of: 80% balance OR max position limit
            max_from_balance = balance * 0.8
            max_position_value = min(max_from_balance, self.max_position_usd)
            
            position_size = max_position_value / eth_price
            position_size = round(position_size, 4)
            
            logger.info(f"Position size: {position_size} ETH (${max_position_value} / ${eth_price})")
            logger.info(f"Safety limits: Balance=${balance}, Max=${self.max_position_usd}")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    def process_signal(self, action: str) -> Dict[str, Any]:
        """Process REAL trading signal"""
        try:
            logger.info(f"🚨 PROCESSING REAL SIGNAL: {action} 🚨")
            
            if action == 'close':
                return self.close_all_positions()
            
            # Get current state
            eth_price = self.get_eth_price()
            if eth_price <= 0:
                return {'status': 'error', 'message': f'Invalid ETH price: {eth_price}'}
            
            account_info = self.get_account_info()
            if not account_info['account_connected']:
                return {'status': 'error', 'message': 'Account not connected'}
            
            balance = float(account_info['balance'])
            if balance < 5:  # Minimum $5
                return {'status': 'error', 'message': f'Insufficient balance: ${balance}'}
            
            # Calculate position size
            position_size = self.calculate_position_size(balance, eth_price)
            if position_size <= 0:
                return {'status': 'error', 'message': f'Invalid position size: {position_size}'}
            
            # Place REAL order
            is_buy = (action == 'buy')
            result = self.place_market_order(is_buy, position_size)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            return {'status': 'error', 'message': f'Signal error: {str(e)}'}
    
    def process_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process webhook"""
        try:
            if 'action' not in data:
                return {'status': 'error', 'message': 'Missing action field'}
            
            if 'passphrase' not in data:
                return {'status': 'error', 'message': 'Missing passphrase field'}
            
            if data['passphrase'] != self.webhook_secret:
                return {'status': 'error', 'message': 'Invalid passphrase'}
            
            action = data['action'].lower()
            if action not in ['buy', 'sell', 'close']:
                return {'status': 'error', 'message': f'Invalid action: {action}'}
            
            return self.process_signal(action)
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return {'status': 'error', 'message': f'Webhook error: {str(e)}'}

# Initialize bot
try:
    bot = HyperliquidRealBot()
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    bot = None

@app.route('/', methods=['GET'])
def status():
    """Bot status"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 500
        
        account_info = bot.get_account_info()
        eth_price = bot.get_eth_price()
        
        return jsonify({
            'bot': '🚨 REAL TRADING BOT ACTIVE 🚨',
            'status': 'operational',
            'symbol': 'ETH',
            'testnet': bot.use_testnet,
            'wallet': bot.wallet_address,
            'account_connected': account_info['account_connected'],
            'balance': account_info['balance'],
            'positions': len(account_info['positions']),
            'eth_price': eth_price,
            'max_position_usd': bot.max_position_usd,
            'timestamp': datetime.utcnow().isoformat(),
            'version': 'REAL-TRADING-1.0',
            'warning': 'REAL MONEY AT RISK'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """REAL trading webhook"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data'}), 400
        
        logger.info(f"🚨 REAL TRADING WEBHOOK: {data} 🚨")
        
        result = bot.process_webhook(data)
        
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Critical webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop - close all positions"""
    try:
        if not bot:
            return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 500
        
        result = bot.close_all_positions()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
