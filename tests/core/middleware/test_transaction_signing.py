import pytest

from eth_account import (
    Account,
)
from eth_account.signers.local import (
    LocalAccount,
)
import eth_keys
from eth_tester.exceptions import (
    ValidationError,
)
from eth_utils import (
    to_bytes,
    to_hex,
)
from eth_utils.toolz import (
    assoc,
    dissoc,
    identity,
    merge,
    valfilter,
)
from hexbytes import (
    HexBytes,
)

from web3 import Web3
from web3.exceptions import (
    InvalidAddress,
)
from web3.middleware import (
    construct_result_generator_middleware,
    construct_sign_and_send_raw_middleware,
)
from web3.middleware.signing import (
    gen_normalized_accounts,
)
from web3.providers import (
    BaseProvider,
)
from web3.providers.eth_tester import (
    EthereumTesterProvider,
)

PRIVATE_KEY_1 = to_bytes(
    hexstr='0x6a8b4de52b288e111c14e1c4b868bc125d325d40331d86d875a3467dd44bf829')

ADDRESS_1 = '0x634743b15C948820069a43f6B361D03EfbBBE5a8'

PRIVATE_KEY_2 = to_bytes(
    hexstr='0xbf963e13b164c2100795f53e5590010f76b7a91b5a78de8e2b97239c8cfca8e8')

ADDRESS_2 = '0x91eD14b5956DBcc1310E65DC4d7E82f02B95BA46'

KEY_FUNCS = (
    eth_keys.keys.PrivateKey,
    Account.from_key,
    HexBytes,
    to_hex,
    identity,
)


SAME_KEY_MIXED_TYPE = tuple(key_func(PRIVATE_KEY_1) for key_func in KEY_FUNCS)

MIXED_KEY_MIXED_TYPE = tuple(
    key_func(key) for key in [PRIVATE_KEY_1, PRIVATE_KEY_2] for key_func in KEY_FUNCS
)

SAME_KEY_SAME_TYPE = (
    eth_keys.keys.PrivateKey(PRIVATE_KEY_1),
    eth_keys.keys.PrivateKey(PRIVATE_KEY_1)
)

MIXED_KEY_SAME_TYPE = (
    eth_keys.keys.PrivateKey(PRIVATE_KEY_1), eth_keys.keys.PrivateKey(PRIVATE_KEY_2)
)


class DummyProvider(BaseProvider):
    def make_request(self, method, params):
        raise NotImplementedError("Cannot make request for {0}:{1}".format(
            method,
            params,
        ))


@pytest.fixture()
def result_generator_middleware():
    return construct_result_generator_middleware({
        'eth_sendRawTransaction': lambda *args: args,
        'net_version': lambda *_: 1,
        'eth_chainId': lambda *_: "0x02",
    })


@pytest.fixture()
def w3_base():
    return Web3(provider=DummyProvider(), middlewares=[])


@pytest.fixture()
def w3_dummy(w3_base, result_generator_middleware):
    w3_base.middleware_onion.add(result_generator_middleware)
    return w3_base


def hex_to_bytes(s):
    return to_bytes(hexstr=s)


@pytest.mark.parametrize(
    'method,key_object,from_,expected',
    (
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE, ADDRESS_2, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE, ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', MIXED_KEY_MIXED_TYPE, ADDRESS_2, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', MIXED_KEY_MIXED_TYPE, ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_SAME_TYPE, ADDRESS_2, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_SAME_TYPE, ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', MIXED_KEY_SAME_TYPE, ADDRESS_2, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', MIXED_KEY_SAME_TYPE, ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[0], ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[1], ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[2], ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[3], ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[4], ADDRESS_1, 'eth_sendRawTransaction'),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[0], ADDRESS_2, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[1], ADDRESS_2, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[2], ADDRESS_2, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[3], ADDRESS_2, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_MIXED_TYPE[4], ADDRESS_2, NotImplementedError),
        ('eth_call', MIXED_KEY_MIXED_TYPE, ADDRESS_1, NotImplementedError),
        ('eth_sendTransaction', SAME_KEY_SAME_TYPE, hex_to_bytes(ADDRESS_1),
         'eth_sendRawTransaction'),
    )
)
def test_sign_and_send_raw_middleware(
        w3_dummy,
        method,
        from_,
        expected,
        key_object):
    w3_dummy.middleware_onion.add(
        construct_sign_and_send_raw_middleware(key_object))

    legacy_transaction = {
        'to': '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf',
        'from': from_,
        'gas': 21000,
        'gasPrice': 0,
        'value': 1,
        'nonce': 0
    }
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            w3_dummy.manager.request_blocking(method, [legacy_transaction])
    else:
        # assert with legacy txn params
        actual = w3_dummy.manager.request_blocking(method, [legacy_transaction])
        assert_method_and_txn_signed(actual, expected)

        # assert with 1559 transaction params and explicit type
        transaction_1559 = dissoc(legacy_transaction, 'gasPrice')
        transaction_1559 = assoc(transaction_1559, 'maxFeePerGas', 2000000000)
        transaction_1559 = assoc(transaction_1559, 'maxPriorityFeePerGas', 1000000000)
        transaction_1559 = assoc(transaction_1559, 'type', '0x2')

        actual_1559 = w3_dummy.manager.request_blocking(method, [transaction_1559])
        assert_method_and_txn_signed(actual_1559, expected)

        # assert with 1559 transaction params and no explicit type
        transaction_1559_no_type = dissoc(transaction_1559, 'type')

        actual_1559_no_type = w3_dummy.manager.request_blocking(method, [transaction_1559_no_type])
        assert_method_and_txn_signed(actual_1559_no_type, expected)


def assert_method_and_txn_signed(actual, expected):
    raw_txn = actual[1][0]
    actual_method = actual[0]
    assert actual_method == expected
    assert isinstance(raw_txn, bytes)


@pytest.fixture()
def w3():
    return Web3(EthereumTesterProvider())


@pytest.mark.parametrize(
    'key_object',
    (
        (SAME_KEY_MIXED_TYPE),
        (MIXED_KEY_MIXED_TYPE),
        (SAME_KEY_SAME_TYPE),
        (MIXED_KEY_SAME_TYPE),
        (SAME_KEY_MIXED_TYPE[0]),
        (SAME_KEY_MIXED_TYPE[1]),
        (SAME_KEY_MIXED_TYPE[2]),
        (SAME_KEY_MIXED_TYPE[3]),
        (SAME_KEY_MIXED_TYPE[4]),
    )
)
def test_gen_normalized_accounts(key_object):
    accounts = gen_normalized_accounts(key_object)
    assert all(isinstance(account, LocalAccount) for account in accounts.values())


def test_gen_normalized_accounts_type_error(w3):
    with pytest.raises(TypeError):
        gen_normalized_accounts(1234567890)


@pytest.fixture()
def fund_account(w3):
    # fund local account
    tx_value = w3.toWei(10, 'ether')
    for address in (ADDRESS_1, ADDRESS_2):
        w3.eth.send_transaction({
            'to': address,
            'from': w3.eth.accounts[0],
            'gas': 21000,
            'value': tx_value})
        assert w3.eth.get_balance(address) == tx_value


@pytest.mark.parametrize(
    'transaction,expected,key_object,from_',
    (
        (
            {
                'gas': 21000,
                'gasPrice': 0,
                'value': 1
            },
            -1,
            MIXED_KEY_MIXED_TYPE,
            ADDRESS_1,
        ),
        (
            {
                'value': 1
            },
            -1,
            MIXED_KEY_MIXED_TYPE,
            ADDRESS_1,
        ),
        # expect validation error + unmanaged account
        (
            {
                'gas': 21000,
                'value': 10
            },
            ValidationError,
            SAME_KEY_MIXED_TYPE,
            ADDRESS_2,
        ),
        (
            {
                'gas': 21000,
                'value': 10
            },
            InvalidAddress,
            SAME_KEY_MIXED_TYPE,
            '0x0000',
        ),
        (
            # TODO: Once eth-tester supports 1559 params, this test should fail and we will need to
            #  update this to appropriately test 'maxFeePerGas' and 'maxPriorityFeePerGas' as
            #  well as the transaction 'type'
            {
                'type': '0x2',
                'value': 22,
                'maxFeePerGas': 2000000000,
                'maxPriorityFeePerGas': 1000000000,
            },
            ValidationError,
            SAME_KEY_MIXED_TYPE,
            ADDRESS_2,
        ),
        (
            # TODO: eth-tester support for 1559 message above applies to this test as well.
            # type should default to '0x2` and send successfully based on 1559 fields being present
            {
                'value': 22,
                'maxFeePerGas': 2000000000,
                'maxPriorityFeePerGas': 1000000000,
            },
            ValidationError,
            SAME_KEY_MIXED_TYPE,
            ADDRESS_2,
        )
    ),
    ids=[
        'with set gas',
        'with no set gas',
        'with mismatched sender',
        'with invalid sender',
        'with txn type and 1559 fees',
        'with 1559 fees and no type',
    ]
)
def test_signed_transaction(
        w3,
        fund_account,
        transaction,
        expected,
        key_object,
        from_):
    w3.middleware_onion.add(construct_sign_and_send_raw_middleware(key_object))

    # Drop any falsy addresses
    to_from = valfilter(bool, {'to': w3.eth.accounts[0], 'from': from_})

    _transaction = merge(transaction, to_from)

    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            w3.eth.send_transaction(_transaction)
    else:
        start_balance = w3.eth.get_balance(_transaction.get('from', w3.eth.accounts[0]))
        w3.eth.send_transaction(_transaction)
        assert w3.eth.get_balance(_transaction.get('from')) <= start_balance + expected


@pytest.mark.parametrize(
    'from_converter,to_converter',
    (
        (identity, identity),
        (hex_to_bytes, identity),
        (identity, hex_to_bytes),
        (hex_to_bytes, hex_to_bytes),
    )
)
def test_sign_and_send_raw_middleware_with_byte_addresses(
        w3_dummy,
        from_converter,
        to_converter):
    private_key = PRIVATE_KEY_1
    from_ = from_converter(ADDRESS_1)
    to_ = to_converter(ADDRESS_2)

    w3_dummy.middleware_onion.add(
        construct_sign_and_send_raw_middleware(private_key))

    actual = w3_dummy.manager.request_blocking(
        'eth_sendTransaction',
        [{
            'to': to_,
            'from': from_,
            'gas': 21000,
            'gasPrice': 0,
            'value': 1,
            'nonce': 0
        }])
    raw_txn = actual[1][0]
    actual_method = actual[0]
    assert actual_method == 'eth_sendRawTransaction'
    assert isinstance(raw_txn, bytes)
