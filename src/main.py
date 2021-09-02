import click
import hashlib
import hmac
import json
import os
import requests
import sys
import time


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


@click.group()
def cli():
    """ Simple Bittrex cli, have fun """


@cli.command('balances')
def get_balances():
    """ List all balances """
    r = _call_x('GET', '/balances', '')

    cols = "{:>10} {:>15} {:>20} {:>30}"
    click.secho(cols.format('SYMBOL', 'TOTAL', 'AVAILABLE', 'UPDATED'), fg='green')

    # TODO: map().reduce().filter() ?
    for a in r:
        if float(a['total']) > 0.0005:
            click.secho(cols.format(a['currencySymbol'], a['total'], a['available'], a['updatedAt']))


@cli.command('orders')
def get_orders():
    """ List all open and closed orders """
    cols = "{:<10} {:<10} {:<10} {:<10} {:<15} {:<20} {:<20} {:<20} {:<30} {:<30}"
    click.secho(cols.format("STATUS", "DIRECTION", "SYMBOL", "TYPE", "PRICE", "QUANTITY", "FILLED", "FEES", "UPDATED", "CLOSED"), fg='green')
    for direction in ['open', 'closed']:
        query = '?pageSize=10' if direction == 'closed' else ''
        r = _call_x('GET', '/orders/' + direction + query, '')
        for o in r:
            updated = '' if 'closedAt' in o else o['updatedAt']
            closed = o['closedAt'] if 'closedAt' in o else ''
            price = o['limit'] if 'limit' in o else '' # TODO
            click.secho(cols.format(o['status'], o['direction'], o['marketSymbol'], o['type'], price, o['quantity'], o['fillQuantity'], o['commission'], updated, closed))


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
    cols = '{:<10} {:<20} {:<20} {:<20}'
    click.secho(cols.format('SYMBOL', 'LASTTRADERATE', 'BIDRATE', 'ASKRATE'), fg='green')

    r = _get_ticker_data(symbol)
    click.secho(cols.format(r['symbol'], r['lastTradeRate'], r['bidRate'], r['askRate']))


@cli.command('create')
@click.option('--pair', required=True, help='Trade pair (ticker)')
@click.option('--direction', default='BUY', show_default=True, help='Buy or sell.')
@click.option('--quantity', help='Quantity to buy or sell', type=float)
@click.option('--spend', help='Spend this amount', type=float)
@click.option('--confirm', default=False, help='If not set, do not execute', is_flag=True)
def create_order(pair, direction, quantity, spend, confirm):
    """ Create a new order """
    market = _get_ticker_data(pair)
    limit = float(market['askRate'])

    if not spend and not quantity:
        click.secho('need one of --quantity or --spend', fg='red')
        return

    if spend:
        quantity = spend / limit

    if direction.upper() == 'BUY':
        target, base = pair.split('-')
    else:
        base, target = pair.split('-')

    spend = limit * quantity
    click.secho(f'Going to buy {quantity} {target} at {limit} {base}, spending {spend} {base}', fg='green')
    payload = {
      "marketSymbol": pair,
      "direction": direction,
      "type": "LIMIT",
      "quantity": quantity,
      "limit": limit,
      "timeInForce": "GOOD_TIL_CANCELLED",
      "useAwards": "true"
    }
    #click.echo(payload)
    if confirm:
        r = _call_x('POST', '/orders', payload)
        if 'code' in r:
            reason = r['code']
            click.secho(f'Failed with reason: {reason}', fg='red')
        else:
            result = f"> status: {r['status']} // updated: {r['updatedAt']} // fee: {r['commission']} // filled: {r['fillQuantity']}"
            click.secho(result, fg='red')
    else:
        click.secho('no action taken, use --confirm to create this order', fg='red')


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


if __name__ == '__main__':
    cli()
