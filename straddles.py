import configparser
import requests
import hmac
import hashlib
import json
import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

# Reading configuration from config.ini
config = configparser.ConfigParser()
config.read('config.ini')

# API Configuration
API_KEY = config['API']['key']
API_SECRET = config['API']['secret']
BASE_URL = config['API']['base_url']

# Strategy Configuration
SELL_TIME = config['Strategy']['sell_time']
QUANTITY = int(config['Strategy']['quantity'])
STOP_LOSS_FACTOR = float(config['Strategy']['stop_loss_factor'])
STOP_PRICE_FACTOR = float(config['Strategy']['stop_price_factor'])

# ETHUSDT Configuration
SYMBOL = config['ETHUSDT']['symbol']

def get_time_stamp():
    return str(int(datetime.datetime.utcnow().timestamp()) + 19800)

def generate_signature(method, endpoint, payload):
    timestamp = get_time_stamp()
    signature_data = method + timestamp + endpoint + payload
    message = bytes(signature_data, 'utf-8')
    secret = bytes(API_SECRET, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha256)
    return hash.hexdigest(), timestamp

def get_product_id(symbol):
    headers = {'Accept': 'application/json'}
    url = f"{BASE_URL}/v2/products/{symbol}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data["success"]:
            return data["result"]["id"]
        else:
            raise Exception("Failed to get product ID")
    else:
        raise Exception("Failed to fetch product details")

def get_atm_strike_price():
    # Fetch the current price of ETHUSDT and determine the closest ATM strike
    # This is a placeholder function and needs to be implemented based on the API documentation
    return 2000  # Example strike price

def place_bracket_order(side, qty, product_id, stop_loss):
    method = 'POST'
    endpoint = "/v2/orders"
    url = BASE_URL + endpoint

    params = {
        "order_type": "market_order",
        "size": qty,
        "side": side,
        "product_id": product_id,
        "bracket_stop_loss_price": stop_loss,
        "bracket_stop_loss_limit_price": stop_loss*STOP_PRICE_FACTOR
    }

    payload = json.dumps(params).replace(' ', '')
    signature, timestamp = generate_signature(method, endpoint, payload)

    headers = {
        'api-key': API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'rest-client',
        'Content-Type': 'application/json'
    }

    response = requests.post(url, data=payload, headers=headers)
    return response.json()

def get_eth_price():
    headers = {
        'Accept': 'application/json',
        'api-key': API_KEY,
        'signature': generate_signature('GET', '/v2/tickers', '')[0],
        'timestamp': get_time_stamp()
    }
    response = requests.get(f'{BASE_URL}/v2/tickers', headers=headers)
    response_data = response.json()
    try:
        eth_price_data = [i for i in response_data['result'] if i['symbol'] == 'ETHUSDT'][0]
        return eth_price_data['close']
    except (IndexError, KeyError):
        raise Exception("Error fetching ETH price")

def get_atm_option_ids():
    eth_price = get_eth_price()
    call_options = requests.get(f'{BASE_URL}/v2/products?contract_types=call_options&states=live&page_size=10000').json()['result']
    put_options = requests.get(f'{BASE_URL}/v2/products?contract_types=put_options&states=live&page_size=10000').json()['result']

    eth_calls = [opt for opt in call_options if 'ETH' in opt['description']]
    eth_puts = [opt for opt in put_options if 'ETH' in opt['description']]

    atm_call = min(eth_calls, key=lambda x: abs(float(x['strike_price']) - eth_price))
    atm_put = min(eth_puts, key=lambda x: abs(float(x['strike_price']) - eth_price))
    print('ETH Price: ', eth_price)
    print('ATM CAll: ', atm_call['symbol'])
    print('ATM Put: ', atm_put['symbol'])

    return atm_call['id'], atm_put['id']


def get_ticker(symbol):
    headers = {'Accept': 'application/json'}
    response = requests.get(f'{BASE_URL}/v2/tickers/{symbol}', headers=headers)
    if response.status_code == 200:
        return response.json()['result']
    else:
        raise Exception("Failed to fetch ticker data")

def get_best_bid_ask(symbol):
    ticker_data = get_ticker(symbol)
    best_bid = float(ticker_data['quotes']['best_bid'])
    best_ask = float(ticker_data['quotes']['best_ask'])
    return best_bid, best_ask

def execute_strategy():
    atm_call_id, atm_put_id = get_atm_option_ids()

    # Fetch best bid and ask for ATM call and put
    call_bid, call_ask = get_best_bid_ask(atm_call_id)
    put_bid, put_ask = get_best_bid_ask(atm_put_id)

    # Calculate stop loss prices
    call_stop_loss = call_bid * STOP_LOSS_FACTOR
    put_stop_loss = put_bid * STOP_LOSS_FACTOR

    # Place a sell call
    call_response = place_bracket_order(side = "sell", qty = QUANTITY, product_id = atm_call_id, stop_loss = call_stop_loss)
    print("Call option order response:", call_response)

    # Place a sell put
    put_response = place_bracket_order("sell", QUANTITY, atm_put_id, put_stop_loss)
    print("Put option order response:", put_response)

# Scheduler to run the strategy at a specified time
print('Waiting for the scheduled time to execute the strategy')
scheduler = BlockingScheduler()
scheduler.add_job(execute_strategy, 'cron', hour=SELL_TIME.split(':')[0], minute=SELL_TIME.split(':')[1])
# #
# # # Start the scheduler
scheduler.start()
# execute_strategy()