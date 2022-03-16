import unittest

from src.fetch.period_slippage import SolverSlippage
from src.fetch.transfer_file import Transfer, TokenType
from src.models import Address, TransferType

ONE_ADDRESS = Address("0x1111111111111111111111111111111111111111")
TWO_ADDRESS = Address("0x2222222222222222222222222222222222222222")


class TestAddress(unittest.TestCase):
    def setUp(self) -> None:
        self.lower_case_address = '0xde1c59bc25d806ad9ddcbe246c4b5e5505645718'
        self.check_sum_address = '0xDEf1CA1fb7FBcDC777520aa7f396b4E015F497aB'
        self.invalid_address = '0x12'

    def test_invalid(self):
        with self.assertRaises(ValueError):
            Address(address=self.invalid_address)

    def test_valid(self):
        self.assertEqual(
            Address(address=self.lower_case_address).address,
            '0xdE1c59Bc25D806aD9DdCbe246c4B5e5505645718'
        )
        self.assertEqual(
            Address(address=self.check_sum_address).address,
            '0xDEf1CA1fb7FBcDC777520aa7f396b4E015F497aB'
        )


class TestTransferType(unittest.TestCase):
    def setUp(self) -> None:
        self.in_user_upper = 'IN_USER'
        self.in_amm_lower = 'in_amm'
        self.out_user_mixed = 'Out_User'
        self.invalid_type = 'invalid'

    def test_valid(self):
        self.assertEqual(
            TransferType.from_str(self.in_user_upper),
            TransferType.IN_USER
        )
        self.assertEqual(
            TransferType.from_str(self.in_amm_lower),
            TransferType.IN_AMM
        )
        self.assertEqual(
            TransferType.from_str(self.out_user_mixed),
            TransferType.OUT_USER
        )

    def test_invalid(self):
        with self.assertRaises(ValueError):
            TransferType.from_str(self.invalid_type)


class TestTransfer(unittest.TestCase):

    def test_add_slippage(self):
        solver = Address.zero()
        transfer = Transfer(
            token_type=TokenType.NATIVE,
            token_address=None,
            receiver=solver,
            amount=1.0
        )
        positive_slippage = SolverSlippage(
            solver_name="Test Solver",
            solver_address=solver,
            amount_wei=10 ** 18 // 2
        )
        negative_slippage = SolverSlippage(
            solver_name="Test Solver",
            solver_address=solver,
            amount_wei=-10 ** 18 // 2
        )
        transfer.add_slippage(positive_slippage)
        self.assertAlmostEqual(transfer.amount, 1.5, delta=0.0000000001)
        transfer.add_slippage(negative_slippage)
        self.assertAlmostEqual(transfer.amount, 1.0, delta=0.0000000001)

    def test_errors(self):
        transfer = Transfer(
            token_type=TokenType.NATIVE,
            token_address=None,
            receiver=ONE_ADDRESS,
            amount=1.0
        )
        slippage = SolverSlippage(
            solver_name="Test Solver",
            solver_address=TWO_ADDRESS,
            amount_wei=0
        )
        with self.assertRaises(AssertionError):
            transfer.add_slippage(slippage)

    def test_from_dict(self):
        self.assertEqual(
            Transfer.from_dict({
                "token_type": 'native',
                "token_address": None,
                "receiver": ONE_ADDRESS.address,
                "amount": "1.234"
            }),
            Transfer(
                token_type=TokenType.NATIVE,
                token_address=None,
                receiver=ONE_ADDRESS,
                amount=1.234
            )
        )

        with self.assertRaises(ValueError):
            Transfer.from_dict({
                "token_type": 'erc20',
                "token_address": None,
                "receiver": ONE_ADDRESS.address,
                "amount": "1.234"
            })

        with self.assertRaises(ValueError):
            Transfer.from_dict({
                "token_type": 'native',
                "token_address": ONE_ADDRESS.address,
                "receiver": ONE_ADDRESS.address,
                "amount": "1.234"
            })


if __name__ == '__main__':
    unittest.main()
