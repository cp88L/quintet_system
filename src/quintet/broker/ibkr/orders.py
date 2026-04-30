"""Build IBKR orders from broker-neutral execution intents."""

from __future__ import annotations

from dataclasses import dataclass

from ibapi.contract import Contract
from ibapi.order import Order

from quintet.broker.models import BrokerOrder
from quintet.config import VOICE_MAP
from quintet.execution.models import ModifyOrderIntent, PlaceBracketIntent


@dataclass(frozen=True)
class IbkrOrderRequest:
    """One IBKR `placeOrder` request."""

    order_id: int
    contract: Contract
    order: Order


def build_bracket_order_requests(
    intent: PlaceBracketIntent,
    *,
    entry_order_id: int,
    stop_order_id: int,
) -> list[IbkrOrderRequest]:
    """Build parent entry and child protective stop requests."""
    contract = build_futures_contract(intent)
    order_ref = VOICE_MAP[intent.key[1]]
    return [
        IbkrOrderRequest(
            order_id=entry_order_id,
            contract=contract,
            order=build_entry_order(intent, order_ref=order_ref),
        ),
        IbkrOrderRequest(
            order_id=stop_order_id,
            contract=contract,
            order=build_protective_stop_order(
                intent,
                parent_id=entry_order_id,
                order_ref=order_ref,
            ),
        ),
    ]


def build_futures_contract(intent: PlaceBracketIntent) -> Contract:
    """Build the IBKR futures contract for a bracket intent."""
    contract = Contract()
    contract.conId = intent.key[0]
    contract.symbol = intent.symbol
    contract.secType = "FUT"
    contract.exchange = intent.exchange
    contract.currency = intent.currency
    contract.localSymbol = intent.local_symbol
    return contract


def build_modify_order_request(
    original: BrokerOrder,
    intent: ModifyOrderIntent,
) -> IbkrOrderRequest:
    """Build a same-order-id modification request from current broker state."""
    contract = build_futures_contract_from_order(original)
    order = build_modified_order(original, intent)
    return IbkrOrderRequest(
        order_id=original.order_id,
        contract=contract,
        order=order,
    )


def build_futures_contract_from_order(order: BrokerOrder) -> Contract:
    """Build the IBKR futures contract for an existing broker order."""
    contract = Contract()
    contract.conId = order.con_id
    contract.symbol = order.symbol
    contract.secType = "FUT"
    contract.exchange = order.exchange
    contract.currency = order.currency
    contract.localSymbol = order.local_symbol
    return contract


def build_modified_order(original: BrokerOrder, intent: ModifyOrderIntent) -> Order:
    """Rebuild an existing order with only requested mutable fields changed."""
    order = Order()
    order.action = str(original.action)
    order.orderType = str(original.order_type)
    order.totalQuantity = original.quantity
    order.auxPrice = (
        intent.aux_price if intent.aux_price is not None else original.aux_price
    )
    if order.orderType == "STP LMT":
        order.lmtPrice = (
            intent.limit_price
            if intent.limit_price is not None
            else original.limit_price
        )
        if order.lmtPrice is None:
            raise ValueError("STP LMT order modification requires a limit price")
    elif intent.limit_price is not None:
        order.lmtPrice = intent.limit_price
    if order.orderType in {"STP", "STP LMT"} and order.auxPrice is None:
        raise ValueError(f"{order.orderType} order modification requires a stop price")
    order.parentId = original.parent_id or 0
    order.transmit = original.transmit if original.transmit is not None else True
    if original.tif:
        order.tif = original.tif
    if original.outside_rth is not None:
        order.outsideRth = original.outside_rth
    if original.order_ref:
        order.orderRef = original.order_ref
    return order


def build_entry_order(intent: PlaceBracketIntent, *, order_ref: str) -> Order:
    """Build the parent entry order."""
    order = Order()
    order.action = intent.entry_action
    order.orderType = intent.entry_order_type
    order.totalQuantity = intent.quantity
    _set_stop_limit_prices(
        order,
        stop_price=intent.entry_stop_price,
        limit_price=intent.entry_limit_price,
    )
    order.transmit = False
    order.tif = "GTC"
    order.outsideRth = True
    order.orderRef = order_ref
    return order


def build_protective_stop_order(
    intent: PlaceBracketIntent,
    *,
    parent_id: int,
    order_ref: str,
) -> Order:
    """Build the child protective stop order."""
    order = Order()
    order.action = intent.protective_action
    order.orderType = intent.protective_order_type
    order.totalQuantity = intent.quantity
    _set_stop_limit_prices(
        order,
        stop_price=intent.protective_stop_price,
        limit_price=intent.protective_limit_price,
    )
    order.parentId = parent_id
    order.transmit = True
    order.tif = "GTC"
    order.outsideRth = True
    order.orderRef = order_ref
    return order


def _set_stop_limit_prices(
    order: Order,
    *,
    stop_price: float,
    limit_price: float | None,
) -> None:
    order.auxPrice = stop_price
    if order.orderType == "STP LMT":
        if limit_price is None:
            raise ValueError("STP LMT orders require a limit price")
        order.lmtPrice = limit_price
