from web3 import Web3


BUSD = Web3.toChecksumAddress('0xe9e7cea3dedca5984780bafc599bd69add087d56')
BNB = Web3.toChecksumAddress('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')
USDT = Web3.toChecksumAddress('0x55d398326f99059ff775485246999027b3197955')
ROUTER = Web3.toChecksumAddress('0x10ED43C718714eb63d5aA57B78B54704E256024E')



coins = {
    'BUSD': BUSD,
    'BNB': BNB,
    'USDT': USDT
}