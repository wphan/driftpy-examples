from solana.publickey import PublicKey
from anchorpy import Program, Idl
import requests
from anchorpy import Provider, Wallet
from solana.keypair import Keypair
from solana.rpc.async_api import AsyncClient
import json
import os
from driftpy.constants.config import configs
from driftpy.clearing_house import ClearingHouse
from driftpy.accounts import *
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address


async def main(keypath,
               env,
               url,
               name,
               action,
               delegate,
               management_fee,
               profit_share,
               redeem_period,
               max_tokens,
               min_deposit_amount,
               permissioned,
               ):
    with open(os.path.expanduser(keypath), 'r') as f:
        secret = json.load(f)
    kp = Keypair.from_secret_key(bytes(secret))
    print('using public key:', kp.public_key)
    wallet = Wallet(kp)
    connection = AsyncClient(url)
    provider = Provider(connection, wallet)

    url = 'https://raw.githubusercontent.com/drift-labs/drift-vaults/master/ts/sdk/src/idl/drift_vaults.json'
    response = requests.get(url)
    data = response.json()
    idl = data
    pid = 'vAuLTsyrvSfZRuRB3XgvkPwNGgYSs9YRYymVebLKoxR'
    vault_program = Program(
        Idl.from_json(idl),
        PublicKey(pid),
        provider,
    )
    config = configs[env]
    drift_client = ClearingHouse.from_config(config, provider)

    print(f"vault name: {name}")

    # Initialize an empty list to store the character number array
    char_number_array = [0] * 32

    # Iterate through each character in the string and get its Unicode code point
    for i in range(32):
        if i < len(name):
            char_number_array[i] = ord(name[i])

    vault_pubkey = PublicKey.find_program_address(
        [b"vault", bytes(char_number_array)], PublicKey(pid)
    )[0]

    print(f"vault pubkey : {vault_pubkey}")

    vault_user = get_user_account_public_key(drift_client.program_id, vault_pubkey)

    print(f"vault user : {vault_user}")

    vault_user_stats = get_user_stats_account_public_key(drift_client.program_id, vault_pubkey)

    spot_market_index = 0

    spot_market = await get_spot_market_account(
        drift_client.program, spot_market_index
    )

    print(f"action {action}")

    if action == 'init-vault':
        params = {
            'name': char_number_array,
            'spot_market_index': spot_market_index,  # USDC spot market index
            'redeem_period': redeem_period,  # 30 days
            'max_tokens': max_tokens,
            'min_deposit_amount': min_deposit_amount,
            'management_fee': management_fee,
            'profit_share': profit_share,
            'hurdle_rate': 0,  # no supported atm
            'permissioned': permissioned,
        }

        # vault_ata = get_associated_token_address(drift_client.authority, spot_market.mint)
        ata = PublicKey.find_program_address(
            [b"vault_token_account", bytes(vault_pubkey)], vault_program.program_id
        )[0]

        instruction = vault_program.instruction['initialize_vault'](
            params,
            ctx=Context(
                accounts={
                    'drift_spot_market': spot_market.pubkey,
                    'drift_spot_market_mint': spot_market.mint,
                    'drift_user_stats': vault_user_stats,
                    'drift_user': vault_user,
                    'drift_state': drift_client.get_state_public_key(),
                    'vault': vault_pubkey,
                    'token_account': ata,
                    'token_program': TOKEN_PROGRAM_ID,
                    'drift_program': drift_client.program_id,
                    'manager': drift_client.signer.public_key,
                    'payer': drift_client.signer.public_key,
                    "rent": SYSVAR_RENT_PUBKEY,
                    "system_program": SYS_PROGRAM_ID,
                }),
        )

        tx = Transaction()
        tx.add(instruction)
        txSig = await vault_program.provider.send(tx)
        print(f"tx sig {txSig}")
    if action == 'update-vault':
        params = {
            'redeem_period': redeem_period,  # 30 days
            'max_tokens': max_tokens,
            'min_deposit_amount': min_deposit_amount,
            'management_fee': management_fee,
            'profit_share': profit_share,
            'hurdle_rate': None,  # no supported atm
            'permissioned': permissioned,
        }
        instruction = vault_program.instruction['update_vault'](
            params,
            ctx=Context(
                accounts={
                    'vault': vault_pubkey,
                    'manager': drift_client.signer.public_key,
                }),
        )

        tx = Transaction()
        tx.add(instruction)
        txSig = await vault_program.provider.send(tx)
        print(f"tx sig {txSig}")
    elif action == 'update-delegate':
        instruction = vault_program.instruction['update_delegate'](
            PublicKey(delegate),
            ctx=Context(
                accounts={
                    'drift_user': vault_user,
                    'vault': vault_pubkey,
                    'drift_program': drift_client.program_id,
                    'manager': drift_client.signer.public_key,
                }),
        )

        tx = Transaction()
        tx.add(instruction)
        txSig = await vault_program.provider.send(tx)
        print(f"tx sig {txSig}")

    vault_account = await vault_program.account.get('Vault').fetch(vault_pubkey, "processed")
    print("vault account", vault_account)


def get_fee_param(fee, param_name):
    if fee > 1 or fee < 0:
        raise ValueError(f"{param_name} must be between 0 and 1")
    return int(fee * 1e6)

def get_token_amount_param(amount, param_name):
    if amount < 0:
        raise ValueError(f"{param_name} must be greater than 0")
    return int(amount * 1e6)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--keypath', type=str, required=False, default=os.environ.get('ANCHOR_WALLET'))
    parser.add_argument('--name', type=str, required=True, default='devnet')
    parser.add_argument('--env', type=str, default='devnet')
    parser.add_argument('--action', choices=['init-vault', 'update-delegate', 'update-vault'], required=True)
    parser.add_argument('--management-fee', type=float, required=False, default=None)
    parser.add_argument('--profit-share', type=float, required=False, default=None)
    parser.add_argument('--redeem-period', type=int, required=False, default=None)
    parser.add_argument('--max-tokens', type=int, required=False, default=None)
    parser.add_argument('--min-deposit-amount', type=int, required=False, default=None)
    parser.add_argument('--permissioned', type=int, required=False, default=None)
    parser.add_argument('--delegate', type=str, default=None)
    args = parser.parse_args()

    if args.keypath is None:
        if os.environ['ANCHOR_WALLET'] is None:
            raise ValueError("need to provide keypath or set ANCHOR_WALLET")
        else:
            args.keypath = os.environ['ANCHOR_WALLET']

    action = args.action

    management_fee = args.management_fee
    profit_share = args.profit_share
    redeem_period = args.redeem_period
    max_tokens = args.max_tokens
    min_deposit_amount = args.min_deposit_amount
    permissioned = args.permissioned

    if action == 'init-vault':
        if management_fee is None:
            management_fee = .2

        if profit_share is None:
            profit_share = .02

        if redeem_period is None:
            redeem_period = int(60 * 60 * 24 * 30)

        if max_tokens is None:
            max_tokens = int(1_000_000)

        if min_deposit_amount is None:
            min_deposit_amount = int(100)

        if permissioned is None:
            permissioned = False

    # handle some santization/formatting
    if action == 'init-vault' or action == 'update-vault':
        if management_fee is not None:
            management_fee = get_fee_param(management_fee, 'management fee')

        if profit_share is not None:
            profit_share = get_fee_param(profit_share, 'profit share')

        if max_tokens is not None:
            max_tokens = get_token_amount_param(max_tokens, 'max tokens')

        if min_deposit_amount is not None:
            min_deposit_amount = get_token_amount_param(min_deposit_amount, 'min deposit amount')

    if args.action == 'update-delegate':
        if args.delegate is None:
            raise ValueError('update-delegate requires that you pass a delegate')

    if args.env == 'devnet':
        url = 'https://api.devnet.solana.com'
    elif args.env == 'mainnet':
        url = 'https://api.mainnet-beta.solana.com'
    else:
        raise NotImplementedError('only devnet/mainnet env supported')

    import asyncio

    asyncio.run(main(
        args.keypath,
        args.env,
        url,
        args.name,
        args.action,
        args.delegate,
        management_fee,
        profit_share,
        redeem_period,
        max_tokens,
        min_deposit_amount,
        permissioned,
    ))