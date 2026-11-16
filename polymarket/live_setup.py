"""One-time setup for real orders. Run this on your own computer, never on the server.

It creates a *session key* for your Polymarket account: a separate signer that may place and cancel
orders for the account wallet for 180 days, and cannot withdraw. The worker uses only that key.
Your account's own private key is typed here once, is not shown, and is not saved anywhere.

Before running:
  1. polymarket.com -> Settings -> API Keys -> Relayer API Keys -> Create New. Keep the key shown.
  2. Copy your account wallet address from the profile menu.

Run:   pip install polymarket-client==0.18.0
       python live_setup.py

It prints the two values to put in the host's environment (POLY_SESSION_KEY, POLY_WALLET).
To cancel the session key later: python live_setup.py --revoke <session key address>
"""
import asyncio
import getpass
import sys

from eth_account import Account
from polymarket import AsyncSecureClient, RelayerApiKey, SessionKeyKnownScope


async def main():
    wallet = input("Account wallet address (profile menu): ").strip()
    owner_key = getpass.getpass("Account private key (hidden, not saved): ").strip()
    relayer_key = getpass.getpass("Relayer API key (hidden, not saved): ").strip()
    owner = Account.from_key(owner_key).address
    async with await AsyncSecureClient.create(private_key=owner_key, wallet=wallet,
                                              api_key=RelayerApiKey(key=relayer_key, address=owner)) as client:
        print(f"Connected. Signer {owner}, wallet {client.wallet}, type {client.wallet_type}")
        if client.wallet_type != "DEPOSIT_WALLET":
            sys.exit("This account is not a Deposit Wallet, so session keys are not available for it.")
        if len(sys.argv) == 3 and sys.argv[1] == "--revoke":
            await client.revoke_session_key(address=sys.argv[2])
            print("Revoked", sys.argv[2])
            return
        session = Account.create()
        result = await client.authorize_session_key(address=session.address, scopes=(SessionKeyKnownScope.CLOB,))
        print(f"\nSession key authorized until {result.session_key.valid_until:%d %b %Y}. Address: {session.address}")
        print("\nPut these in the worker's environment on the host. Do not paste them anywhere else:\n")
        print("POLY_SESSION_KEY=0x" + session.key.hex().removeprefix("0x"))
        print("POLY_WALLET=" + str(client.wallet))
        print("\nThen set POLY_LIVE=1 when you want real orders to start.")


if __name__ == "__main__":
    asyncio.run(main())
