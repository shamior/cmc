from web3 import Web3
import time
from os import system
from telethon import TelegramClient, events


import secret
import config
import address
import abis


session = 'anon'
telegram = TelegramClient(session, secret.api_id, secret.api_hash)
ADDRESS = 3
LIQUIDITY = 4
BUY_FEE = 7
SELL_FEE = 8
PLATFORM = 10



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
    print(f"{'*'*30}msg{'*'*30}\n{msg}")
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
    tx = swapExactTokensForTokens(router_contract, conexao, config.WALLET, balance, path)
    if tx['status']:
        print("Sucesso na venda")
    else:
        print("Fail na venda")
        print("Tentando novamente!")
        tx = swapExactTokensForTokens(router_contract, conexao, config.WALLET, balance, path)
        if tx['status']:
            print("Sucesso!")
        else:
            print("Fail")






async def handle_buy(tk_address, liq_amount, pair, buy_fee, sell_fee):
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
        path = [address.busd, address.coins[pair], token]
    else:
        path = [address.busd, token]
    tx = swapExactTokensForTokens(
        router_contract,
        conexao,
        config.WALLET,
        int(config.amount*10**18),
        path
    )

    if tx['status']:
        print('Sucesso')
        print(tx['tx_hash'])
        time.sleep(4)
        decimals = tk_contract.functions.decimals().call()
        balance = tk_contract.functions.balanceOf(config.WALLET).call()
        preco_comprado = config.AMOUNT/(balance*10**-decimals)
        comprado = f"Preco comprado: {preco_comprado:.10f}\n"
        target_reached = False
        print(comprado)
        print("Tentando aprovar o token para venda")
        tx = approve(tk_contract)
        if tx['status']:
            print("Sucesso!")
        else:
            print("Fail!")
            print("Tentando novamente")
            tx = approve(tk_contract)
            if tx['status']:
                print("Sucesso!")
            else:
                print("Fail")
                exit()
        target = (preco_comprado * config.target)/((100-sell_fee)/100)
        target_str = f"Target: {target:.10f}\n"
        path.reverse()
        balance_normalized = balance * 10**-decimals
        start = time.perf_counter()
        while not target_reached:
            time.sleep(1)
            time_passed = time.perf_counter() - start
            preco_atual = get_price(router_contract, token, address.coins[pair], decimals)
            atual = f"Preco atual: {preco_atual:.10f}\n"
            system('clear')
            print(comprado+atual+target_str)
            if preco_atual >= target:
                if time_passed < 20:
                    print("Target reached too fast, waiting for more profit")
                else:
                    print("Target reached!!")
                    sell(router_contract, conexao, balance, path)
                    target_reached = True
            elif preco_atual*balance_normalized*((100-sell_fee)/100) <= config.AMOUNT * .9:
                if time_passed > 60:
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
    print(event.raw_text)
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





def swapExactTokensForTokens(router_contract, conexao, wallet, amountIn, path):
    amountOutMin = int(0.0000001e18)
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
            'gasPrice': int(config.gwei*10**9),
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
    if pair == address.bnb:
        value *= router_contract.functions.getAmountsOut(
            10**18, [address.bnb, address.busd]
        ).call()[1]*10**-18
    return value


print("Esperando mensagem...")

telegram.start()
telegram.run_until_disconnected()