import click
import hashlib
import hmac
import json
import os
import requests
import sys
import time

from pyhocon import ConfigFactory


api_key = os.getenv('API_KEY')
api_private_key = os.getenv('PRIVATE_KEY')


def _call_x(method, endpoint, payload):
    base_url = 'https://api.bittrex.com/v3'
    url = f'{base_url}{endpoint}'
    timestamp = str(int(time.time()*1000))

    if (isinstance(payload, dict)):
        content_hash = hashlib.sha512(bytes(json.dumps(payload), "utf-8")).hexdigest()
    else:
        content_hash = hashlib.sha512(payload.encode()).hexdigest()

    presign = timestamp + url + method + content_hash
    signature = hmac.new(api_private_key.encode(), presign.encode(), hashlib.sha512).hexdigest()

    headers = {
          'Api-Key': api_key,
          'Api-Timestamp': timestamp,
          'Api-Content-Hash': content_hash,
          'Api-Signature': signature
    }

    if method == 'GET':
      return requests.get(url, headers=headers).json()
    if method == 'POST':
      return requests.post(url, headers=headers, json=payload).json()
    if method == 'DELETE':
      return requests.delete(url, headers=headers).json()


@click.group()
def cli():
    """ Simple Bittrex cli, have fun """


def _get_balance(symbol):
    specific = '/'+symbol if symbol else ''
    balance = _call_x('GET', '/balances' + specific, '')

    if 'code' in balance:
        reason = balance['code']
        return {'error': f'could not fetch balance: {reason}'}

    if isinstance(balance, list):
        r = balance
    else:
        r = []
        r.append(balance)
    return r


@cli.command('balances')
@click.option('--symbol', help='Symbol to list')
def get_balances(symbol):
    """ List all or specific balances """
    r = _get_balance(symbol)

    if 'error' in r:
        reason = r['error']
        click.secho(f'could not fetch balance: {reason}', fg='red')
        return

    cols = "{:>10} {:>15} {:>20} {:>30}"
    click.secho(cols.format('SYMBOL', 'TOTAL', 'AVAILABLE', 'UPDATED'), fg='green')

    # TODO: map().reduce().filter() ?
    for a in r:
        if float(a['total']) > 0.0005:
            click.secho(cols.format(a['currencySymbol'], a['total'], a['available'], a['updatedAt']))


@cli.command('orders')
@click.option('--direction', help='Only list open or closed orders')
def get_orders(direction):
    """ List all open and closed orders """
    cols = "{:<8} {:<10} {:<10} {:<8} {:<15} {:<15} {:<15} {:<15} {:<25} {:<25} {:<40}"
    click.secho(cols.format("STATUS", "DIRECTION", "SYMBOL", "TYPE", "PRICE", "QUANTITY", "FILLED", "FEES", "UPDATED", "CLOSED", "ID"), fg='green')

    if direction:
        directions = [direction]
    else:
        directions = ['open', 'closed']

    for direction in directions:
        query = '?pageSize=10' if direction == 'closed' else ''
        r = _call_x('GET', '/orders/' + direction + query, '')
        for o in r:
            updated = '' if 'closedAt' in o else o['updatedAt']
            closed = o['closedAt'] if 'closedAt' in o else ''
            price = o['limit'] if 'limit' in o else '' # TODO
            click.secho(cols.format(o['status'], o['direction'], o['marketSymbol'], o['type'], price, o['quantity'], o['fillQuantity'], o['commission'], updated, closed, o['id']))


@cli.command('delete')
@click.option('--order', required=True, help='Order to delete')
def delete_order(order):
    r = _call_x('DELETE', f'/orders/{order}', '')
    if 'code' in r:
        reason = r['code']
        click.secho(f'failed to delete order: {reason}', fg='red')
    else:
        status = r['status']
        click.secho(f'status changed: {status}', fg='red')


def _get_ticker_data(symbol):
    r = _call_x('GET', f'/markets/{symbol}/ticker', '')
    if 'code' in r:
        reason = r['code']
        click.secho(f'Error fetching ticker data: {reason}', fg='red')
        sys.exit()
    return r


@cli.command('ticker')
@click.option('--symbol', required=True, help='Symbol to view (example: ADA-EUR)')
def get_ticket(symbol):
    """ Get information about a ticker """
    cols = '{:<10} {:<20} {:<20} {:<20} {:<20}'
    click.secho(cols.format('SYMBOL', 'LASTTRADERATE', 'BIDRATE', 'ASKRATE', 'SPREAD'), fg='green')

    r = _get_ticker_data(symbol)
    spread = int((float(r['askRate']) - float(r['bidRate'])) * 10000) / 10000
    click.secho(cols.format(r['symbol'], r['lastTradeRate'], r['bidRate'], r['askRate'], spread))


def _create_order(pair, direction, quantity=None, spend=None, confirm=False, price=None):
    market = _get_ticker_data(pair)
    if price:
        limit = price
    else:
        limit = float(market['askRate'])

    if spend:
        quantity = spend / limit

    if direction.upper() == 'BUY':
        target, base = pair.split('-')
    else:
        base, target = pair.split('-')

    spend = limit * quantity
    payload = {
      "marketSymbol": pair,
      "direction": direction,
      "type": "LIMIT",
      "quantity": quantity,
      "limit": limit,
      "timeInForce": "GOOD_TIL_CANCELLED",
      "useAwards": "true"
    }
    res = {}
    res['msg'] = f'Going to buy {quantity} {target} at {limit} {base}, spending {spend} {base}'

    if confirm:
        r = _call_x('POST', '/orders', payload)
        if 'code' in r:
            res['error'] = r['code']
        else:
            res['success'] = f"> status: {r['status']} // updated: {r['updatedAt']} // fee: {r['commission']} // filled: {r['fillQuantity']}"
            res['order_id'] = r['id']
    else:
        res['error'] = 'missing confirmation'
    return res


@cli.command('create')
@click.option('--pair', required=True, help='Trade pair (ticker)')
@click.option('--direction', default='BUY', show_default=True, help='Buy or sell.')
@click.option('--quantity', help='Quantity to buy or sell', type=float)
@click.option('--spend', help='Spend this amount', type=float)
@click.option('--price', default=0, help='Limit price', type=float)
@click.option('--confirm', default=False, help='If not set, do not execute', is_flag=True)
def create_order(pair, direction, quantity, spend, confirm, price):
    """ Create a new order """
    if not spend and not quantity:
        click.secho('need one of --quantity or --spend', fg='red')
        return

    r = _create_order(pair, direction, quantity, spend, confirm, price)
    click.secho(r['msg'], fg='green')
    if 'error' in r:
        reason = r['error']
        click.secho(f'Failed with reason: {reason}', fg='red')
    else:
        click.secho(r['success'], fg='green')


@cli.command('withdraw')
@click.option('--quantity', required=True, help='Quantity to withdraw')
@click.option('--wallet', required=True, help='Destination wallet address')
@click.option('--tag', required=False, help='Tag or memo, if required by the network')
@click.option('--symbol', required=True, help='Symbol to withdraw')
@click.option('--confirm', default=False, help='If not set, do not execute', is_flag=True)
def withdraw(quantity, wallet, tag, symbol, confirm):
    """ Withdraw XLM funds to wallet address """
    if not symbol == 'XLM':
        click.secho('currently only XLM withdrawals are supported', fg='red')
        return

    tagline = f'using tag {tag}' if tag else ''
    click.secho(f'Going to withdraw {quantity} {symbol} to wallet at {wallet} {tagline}', fg='green')

    payload = {
      "currencySymbol": symbol,
      "quantity": quantity,
      "cryptoAddress": wallet,
      "cryptoAddressTag": tag
    }

    if confirm:
        r = _call_x('POST', '/withdrawals', payload)
        click.secho(str(r), fg='red')
    else:
        click.secho('no action taken, use --confirm to withdraw', fg='red')


@cli.command('withdrawals')
def get_withdrawals():
    """ List all withdrawals """
    # available fields: txCost, id
    cols = '{:<10} {:<25} {:<25} {:<10} {:<20} {:<10} {}'
    click.secho(cols.format('STATUS', 'CREATED', 'COMPLETED', 'SYMBOL', 'QUANTITY', 'TARGET', 'WALLET'), fg='green')
    for d in ['open', 'closed']:
        data = _call_x('GET', '/withdrawals/' + d, '')
        for line in data:
            completed = line['completedAt'] if 'completedAt' in line else ''
            click.secho(cols.format(line['status'], line['createdAt'], completed, line['currencySymbol'], line['quantity'], line['target'], line['cryptoAddress']))


@cli.command('execute')
@click.option('--confirm', default=False, help='If not set, do not execute', is_flag=True)
def execute(confirm):
    """ Execute some fancy stuff """
    try:
        conf = ConfigFactory.parse_file('allocations.conf')
    except Exception as e:
        click.secho(f'Failed to load config: {e}', fg='red')
        return

    trigger_symbol = conf['trigger']['symbol']
    trigger_value = 0 #float(conf['trigger']['value'])
    r = _get_balance(trigger_symbol)[0]
    avail = float(r['available'])

    if avail >= trigger_value:
        click.secho(f'Found {avail} EUR in balance, time to invest', fg='green')

        allocations = conf['allocations']
        for alloc in allocations:
            pair = alloc['pair']
            percentage = alloc['perc']
            base = pair.split('-')[1]
            r = _get_balance(base)[0]
            avail = float(r['available'])

            spend = avail * float(percentage/100)
            click.secho(f'Getting {percentage}% in {pair}, spending {spend} {base}', fg='green')

            r = _create_order(pair, 'buy', spend=spend, confirm=confirm)
            click.secho(r['msg'], fg='green')
            if 'error' in r:
                reason = r['error']
                click.secho(f'Failed with reason: {reason}', fg='red')
            else:
                click.secho(r['success'], fg='green')
                order_id = r['order_id']

                n = 0
                while n < 60:
                    r = _call_x('GET', '/orders/' + order_id, '')
                    if r['status'] == 'CLOSED':
                        click.secho('Order closed', fg='green')
                        break
                    time.sleep(1)
                    n += 1

        if 'withdrawals' in conf:
            withdrawals = conf['withdrawals']
            for w in withdrawals:
                symbol = w['symbol']
                wallet = w['wallet']
                memo = w['memo']
                r = _get_balance(symbol)[0]
                avail = float(r['available'])
                click.secho(f'Withdraw {avail} {symbol} to external wallet {wallet} using memo {memo}', fg='green')
                # r = _withdraw()

    else:
        click.secho(f'Insufficient funds, found {avail} of {trigger_symbol} but need {trigger_value}', fg='red')


if __name__ == '__main__':
    cli()
