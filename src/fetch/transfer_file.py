from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from src.dune_analytics import DuneAnalytics, QueryParameter
from src.fetch.period_slippage import get_period_slippage, SolverSlippage
from src.file_io import File, write_to_csv
from src.models import Network, Address
from src.utils.dataset import index_by


class TokenType(Enum):
    """
    Classifications of CSV Airdrop Transfer Types
    """
    NATIVE = 'native'
    ERC20 = 'erc20'

    # Technically the app also supports NFT transfers, but this is irrelevant here
    # NFT = 'nft'

    @classmethod
    def from_str(cls, type_str: str) -> TokenType:
        """Constructs Enum variant from string (case-insensitive)"""
        try:
            return cls[type_str.upper()]
        except KeyError as err:
            raise ValueError(f"No TransferType {type_str}!") from err

    def __str__(self):
        return self.value


@dataclass
class Transfer:
    """Total amount reimbursed for accounting period"""
    token_type: TokenType
    # Safe airdrop uses null address for native asset transfers
    token_address: Optional[Address]
    receiver: Address
    # safe-airdrop uses float amounts!
    amount: float

    @classmethod
    def from_dict(cls, obj: dict) -> Transfer:
        """Converts Dune data dict to object with types"""
        token_type = TokenType.from_str(obj['token_type'])
        token_address = obj['token_address']
        if token_type == TokenType.NATIVE and token_address is not None:
            raise ValueError("Native transfers must have null token_address")
        if token_type == TokenType.ERC20 and token_address is None:
            raise ValueError("ERC20 transfers must have valid token_address")

        return cls(
            token_type=token_type,
            token_address=Address(
                token_address) if token_type != TokenType.NATIVE else None,
            receiver=Address(obj['receiver']),
            amount=float(obj['amount'])
        )

    def add_slippage(self, slippage: Optional[SolverSlippage]):
        if slippage is None:
            return
        assert self.receiver == slippage.solver_address
        adjustment = slippage.amount_wei / 10 ** 18
        print(
            f"Adjusting {self.receiver} transfer by {adjustment:.5f} (slippage)"
        )
        self.amount += adjustment


def get_transfers(
        dune: DuneAnalytics,
        period_start: datetime,
        period_end: datetime
) -> list[Transfer]:
    reimbursements_and_rewards = dune.fetch(
        query_str=dune.open_query("./queries/period_transfers.sql"),
        network=Network.MAINNET,
        name="ETH Reimbursement & COW Rewards",
        parameters=[
            QueryParameter.date_type("StartTime", period_start),
            QueryParameter.date_type("EndTime", period_end),
        ])

    negative_slippage = get_period_slippage(
        dune, period_start, period_end, allow_positive=False
    )
    indexed_slippage = index_by(negative_slippage, 'solver_address')

    results = []
    for row in reimbursements_and_rewards:
        transfer = Transfer.from_dict(row)
        if transfer.token_type == TokenType.NATIVE:
            transfer.add_slippage(indexed_slippage.get(transfer.receiver))
            if transfer.amount <= 0:
                print(
                    f"Slippage adjustment resulted in negative reimbursement! \n"
                    f"Excluding eth reimbursement for solver {transfer.receiver}"
                )
                continue
        results.append(transfer)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Accounting Period Totals")
    parser.add_argument(
        "--start",
        type=str,
        help="Accounting Period Start",
        required=True
    )
    parser.add_argument(
        "--end",
        type=str,
        help="Accounting Period End",
        required=True
    )
    args = parser.parse_args()

    dune_connection = DuneAnalytics.new_from_environment()

    transfers = get_transfers(
        dune=dune_connection,
        period_start=datetime.strptime(args.start, "%Y-%m-%d"),
        period_end=datetime.strptime(args.end, "%Y-%m-%d"),
    )

    outfile = File(name=f"transfers-{args.start}-to-{args.end}.csv")
    write_to_csv(
        data_list=transfers,
        outfile=File(name=f"transfers-{args.start}-to-{args.end}.csv"),
    )
