# bittrex-cli-python

Have fun :)

You need to set the following env vars:

```
export API_KEY=something
export PRIVATE_KEY=whatever
```

## Usage

Some rough examples.

Buying something:

```
$ python src/main.py create --pair USDT-EUR --direction buy --spend 11.38540001 --confirm
Going to buy 13.473846165680474 USDT at 0.845 EUR, spending 11.38540001 EUR
> status: CLOSED // updated: 2021-09-02T19:11:05.69Z // fee: 0.00000000 // filled: 13.47384616
```

Viewing orders:

```
$ python src/main.py orders
STATUS     DIRECTION  SYMBOL     TYPE       PRICE           QUANTITY             FILLED               FEES                 UPDATED                        CLOSED
CLOSED     BUY        USDT-EUR   LIMIT      0.84500000      13.47384616          13.47384616          0.00000000                                          2021-09-02T19:11:05.69Z
```

Viewing the balances:

```
$ python src/main.py balances
    SYMBOL           TOTAL            AVAILABLE                        UPDATED
      USDT     13.47384622          13.47384622        2021-09-02T19:11:05.69Z
```

## Execute feature

Execute a simple strategy requires `allocations.conf` with something like the following:

```
version = "1.0"
trigger = {
    symbol = EUR
    value = 20
}
allocations = [
  {
    pair = USDT-EUR
    perc = 50
  }
  {
    pair = XLM-EUR
    perc = 50
  }
]
withdrawals = [
  {
    symbol = XLM
    wallet = xxx
    memo = xxx
  }
]
```
