from web3 import Web3
import time
from os import system
from telethon.sync import TelegramClient, events
from telethon import functions, types, utils
#from pyrogram import Client
from datetime import datetime
import asyncio


import secret
import config
import address
import abis


session = 'anon'
telegram = TelegramClient(session, api_id=secret.api_id, api_hash=secret.api_hash)
ADDRESS = 3
LIQUIDITY = 4
BUY_FEE = 7
SELL_FEE = 8
PLATFORM = 10
CMC_ID = -1001519789792
pts = None



print("Inicializando...")



def approve(conexao, contrato):
    allowed = contrato.functions.allowance(
        config.WALLET,
        address.ROUTER
    ).call()
    if not allowed:
        tx = contrato.functions.approve(
            address.ROUTER,
            0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
        ).buildTransaction(
            {
                'from': config.WALLET,
                'gasPrice': 5*10**9,
                'nonce': conexao.eth.get_transaction_count(config.WALLET)
            }
        )
        tx_hash = conexao.eth.send_raw_transaction(
            conexao.eth.account.sign_transaction(
                tx,
                secret.private_key
            ).rawTransaction
        )
        status = conexao.eth.wait_for_transaction_receipt(tx_hash)['status'] == 1
        return {
            'status': status,
            'tx_hash': tx_hash.hex()
        }
    else:
        return {
            'status': True,
            'tx_hash': '',
        }


async def filter_message(msg:str):
    #just for debugging
    print(f"\n{'*'*35} msg {'*'*35}\n{msg}\n{'*'*75}\n")
    if not msg:
        print("eh bait, tem mensagem nao")
        return None
    if msg[0] == '🔴':
        splitted = msg.replace('`', '', msg.count('`')).split('\n')
        endereco = splitted[ADDRESS][-42:]
        quantidade, coin = splitted[LIQUIDITY][14:].strip().split(' ')
        quantidade = float(quantidade.replace(',', '', quantidade.count(',')))
        buy_fee = float(splitted[BUY_FEE].strip().split(' ')[0][:-1])
        sell_fee = float(splitted[SELL_FEE].strip().split(' ')[0][:-1])
        platform = splitted[PLATFORM][13:].strip()
        if platform == 'BSC':
            return (endereco, quantidade, coin, buy_fee, sell_fee)
        print('plataforma: {platform}  nao eh a BSC' )
    return None


def sell(router_contract, conexao, balance, path):
    gwei_venda = 5*10**9
    tx = swapExactTokensForTokens(router_contract, conexao, config.WALLET, balance, path, gwei_venda)
    if tx['status']:
        print("Sucesso na venda")
    else:
        print("Fail na venda")
        print("Tentando novamente!")
        tx = swapExactTokensForTokens(router_contract, conexao, config.WALLET, balance, path, gwei_venda)
        if tx['status']:
            print("Sucesso!")
        else:
            print("Fail")






async def handle_buy(tk_address, liq_amount, pair, buy_fee, sell_fee):
    handle_buy_called_time = datetime.now().strftime("%H:%M:%S") + '\n'
    print(f"Tempo que foi chamado: {handle_buy_called_time}")
    conexao = Web3(
        Web3.WebsocketProvider(
            secret.moralis_ws
        )
    )
    router_contract = conexao.eth.contract(
        address=address.ROUTER,
        abi=abis.ROUTER
    )
    token = Web3.toChecksumAddress(tk_address)
    tk_contract = conexao.eth.contract(
        address=token,
        abi=abis.TOKEN
    )
    if pair != 'BUSD':
        path = [address.BUSD, address.coins[pair], token]
    else:
        path = [address.BUSD, token]
    tx = swapExactTokensForTokens(
        router_contract,
        conexao,
        config.WALLET,
        int(config.AMOUNT*10**18),
        path,
        int(config.GWEI*10**9)
    )

    if tx['status']:
        print('Sucesso')
        print(tx['tx_hash'])
        time.sleep(4)
        decimals = tk_contract.functions.decimals().call()
        balance = tk_contract.functions.balanceOf(config.WALLET).call()
        preco_comprado = config.AMOUNT/(balance*10**-decimals)
        comprado = f"Preco comprado: {preco_comprado:.14f}\n"
        target_reached = False
        print(comprado)
        print("Tentando aprovar o token para venda")
        tx = approve(conexao, tk_contract)
        if tx['status']:
            print("Sucesso!")
        else:
            print("Fail!")
            print("Tentando novamente")
            tx = approve(conexao, tk_contract)
            if tx['status']:
                print("Sucesso!")
            else:
                print("Fail")
                exit()
        target = (preco_comprado * config.TARGET)/((100-sell_fee)/100)
        target_str = f"Target: {target:.14f}\n"
        path.reverse()
        balance_normalized = balance * 10**-decimals
        start = time.perf_counter()
        while not target_reached:
            time.sleep(1)
            time_passed = time.perf_counter() - start
            preco_atual = get_price(router_contract, token, address.coins[pair], decimals)
            atual = f"Preco atual: {preco_atual:.14f}\n"
            balanca_atual = preco_atual * balance_normalized
            balanca_atual_str = f"Total atual: {balanca_atual:.14f}\n"
            system('clear')
            print(handle_buy_called_time+comprado+atual+target_str+balanca_atual_str)
            if preco_atual >= target:
                if time_passed < 20:
                    print("Target reached too fast, waiting for more profit")
                else:
                    print("Target reached!!")
                    sell(router_contract, conexao, balance, path)
                    target_reached = True
            elif balanca_atual*((100-sell_fee)/100) <= config.AMOUNT * .9:
                if time_passed > 50:
                    #se perdeu 10% doq investiu
                    #se passou mais de 1 minuto
                    #entao vende
                    print("Stop loss reached!.. triste")
                    sell(router_contract, conexao, balance, path)
                    target_reached = True
            elif time_passed > 600:
                print("Passed 10 minutes, and target not reached")
                sell(router_contract, conexao, balance, path)
                target_reached = True
    else:
        print('Deu ruim')
        print(tx['tx_hash'])


@telegram.on(events.NewMessage(chats=config.CHAT))
async def message_handler(event):
    print(f'now: {datetime.now().strftime("%H:%M:%S")}')
    print(f'msg: {event.message.date.strftime("%H:%M:%S")}')
    filtered_message = await filter_message(event.raw_text)
    if filtered_message == None:
        return
    address, liq_amount, pair, buy_fee, sell_fee = filtered_message

    if buy_fee + sell_fee > config.MAX_TAX:
        print("Taxas muito altas!")
        return
    if pair == "BNB":
        liq_amount *= 400
    if liq_amount < config.MIN_LIQUIDITY:
        print("Liquidez muito baixa")
        return
    if liq_amount > config.MAX_LIQUIDITY:
        print("Liquidez muito alta")
        if buy_fee + sell_fee > 0:
            return
        print("Mas o token nao tem taxas")
    await handle_buy(address, liq_amount, pair, buy_fee, sell_fee)
    exit()




def swapExactTokensForTokens(router_contract, conexao, wallet, amountIn, path, gwei):
    amountOutMin = 0
    #Function: swapExactTokensForTokens(uint256 amountIn, uint256 amountOutMin, address[] path, address to, uint256 deadline)
    tx = router_contract.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
        amountIn,                   #amountIn
        amountOutMin,               #amountOutMin
        path,                       #path
        wallet,                     #to
        int(time.time()+60)         #deadline
    ).buildTransaction(
        {
            'from': wallet,
            'gas': 2000000,
            'gasPrice': gwei,
            'nonce': conexao.eth.get_transaction_count(wallet)
        }
    )
    tx_hash = conexao.eth.send_raw_transaction(
        conexao.eth.account.sign_transaction(
            tx,
            private_key=secret.private_key
        ).rawTransaction
    ).hex()
    receipt = conexao.eth.wait_for_transaction_receipt(tx_hash)
    tx_status = receipt['status'] == 1
    return {
        "status": tx_status,
        "tx_hash": tx_hash,
        "logs": receipt['logs']
    }




def get_price(router_contract, token, pair, decimals):
    value = router_contract.functions.getAmountsOut(
        10**decimals, [token, pair]
    ).call()[1]*10**-decimals
    if decimals != 18:
        value = value*10**-(18-decimals)
    if pair == address.BNB:
        value *= router_contract.functions.getAmountsOut(
            10**18, [address.BNB, address.BUSD]
        ).call()[1]*10**-18
    return value

async def get_difference():
    global pts
    await asyncio.sleep(.5)
    try:
        # Wrap the ID inside a peer to ensure we get a channel back.
        where = await telegram.get_input_entity(types.PeerChannel(CMC_ID))
    except ValueError:
        # There's a high chance that this fails, since
        # we are getting the difference to fetch entities.
        return

    if not pts:
        # First-time, can't get difference. Get pts instead.
        result = await telegram(functions.channels.GetFullChannelRequest(
            utils.get_input_channel(where)
        ))
        telegram._state_cache[CMC_ID] = result.full_chat.pts
        pts = result.full_chat.pts
        return

    result = await telegram(functions.updates.GetChannelDifferenceRequest(
        channel=where,
        filter=types.ChannelMessagesFilterEmpty(),
        pts=pts,  # just pts
        limit=100,
        force=True
    ))


async def main():
    while True:
        await get_difference()
        



print("Esperando mensagem...")

telegram.start()

telegram.loop.run_until_complete(main())