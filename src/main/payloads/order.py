from pydantic import BaseModel

# "symbol" : "MESU23",
# "class": "future",
# "name": "Signal, 10, v.5",
# "ticker" : "EURUSD",
# "exchange" : "OANDA",
# "time_bar": "2023-06-29T21:24:00Z",
# "quantity": "2",
# "action" : "sell",
# "price" : "1.08658",
# "position": "-1",
# "comment": "ChBrkSE v5"


class Order(BaseModel):
    conid: int
    position: int
    price: float | None
