import time
import json
import signal
import threading
import traceback
from web3 import Web3
from optparse import OptionParser

def calcuteEventTopics(contract_abi):
    topics = {}
    for abi in contract_abi:
        fname = abi.get("name", None)
        ftype = abi.get("type", None)
        if not fname or not ftype or ftype != "event":
            continue

        inputs = abi.get("inputs", None)
        if inputs is None:
            continue

        args = ",".join(arg["internalType"] for arg in inputs)
        topics.update({fname: Web3.sha3(text=f"{fname}({args})").hex()})
    return topics

def increase():
    n = 0
    while 1:
        n+=1
        yield n

class ProgramStatus(object):
    def __init__(self, running=True):
        self.__running = running

    def running(self):
        return self.__running

    def setRuning(self, running:bool):
        self.__running = running

programStatus = ProgramStatus()

def sigint_handler(signum, frame):
    programStatus.setRuning(False)

signal.signal(signal.SIGINT, sigint_handler)
signal.signal(signal.SIGHUP, sigint_handler)
signal.signal(signal.SIGTERM, sigint_handler)

class SyncEventLog(threading.Thread):
    def __init__(self, eth_http, pair_address=None, from_block="latest", to_block="latest"):
        threading.Thread.__init__(self)
        self.__eth_http = eth_http

        self.__pair_abi = [{
              "anonymous": False,
              "inputs": [
                {
                  "indexed": False,
                  "internalType": "uint112",
                  "name": "reserve0",
                  "type": "uint112"
                },
                {
                  "indexed": False,
                  "internalType": "uint112",
                  "name": "reserve1",
                  "type": "uint112"
                }
              ],
              "name": "Sync",
              "type": "event"
            }]

        topics = calcuteEventTopics(self.__pair_abi)
        self.__sync_topics = topics.get("Sync", None)

        self.__filter_params = {
                "fromBlock": from_block,      # latest:最新块, pending/earliest:尚未打包的事务
                "toBlock": to_block,          # 同from_block
                "topics": self.__sync_topics,
                "address": pair_address,
                }

        self.__it = increase()

    def dealEventLog(self, event):
        print(next(self.__it), "height:", event.blockNumber, "txhash:", event.transactionHash.hex())
        print("\taddress:", event.address)
        print("\treserve0:", event.args.reserve0)
        print("\treserve1:", event.args.reserve1)

    def run(self):
        print("sync_topics:", self.__sync_topics)
        while programStatus.running():
            try:
                web3_ins = Web3(Web3.HTTPProvider(self.__eth_http))
                attached_pair_contract = web3_ins.eth.contract(abi=self.__pair_abi)
                event_filter = attached_pair_contract.events.Sync().createFilter(**self.__filter_params)
                # all_events for now
                for event in event_filter.get_all_entries():
                    self.dealEventLog(event)

                # new_events for future
                while programStatus.running() and self.__filter_params["toBlock"] in ["latest", "pending", "earliest"]:
                    for event in event_filter.get_new_entries():
                        self.dealEventLog(event)

                return
            except:
                print("exec SyncEventLog get exception:{}".format(traceback.format_exc()))
                print("reconnect ...")

if __name__ == "__main__":
    default_eth_http = "http://127.0.0.1:8545"
    default_from_block = "latest"
    default_to_block = "latest"
    default_pair_address = ""

    usage = "usage: python3 main.py [options] arg"
    parser = OptionParser(usage=usage,description="command descibe")
    parser.add_option("-H", "--eth_http", dest="eth_http", default=f"{default_eth_http}", help=f"ethereum http, default:{default_eth_http}")
    parser.add_option("-a", "--pair_address", dest="pair_address", default=default_pair_address, help=f"pair contract adress, default:{default_pair_address}")
    parser.add_option("-f", "--from_block", dest="from_block", default=f"{default_from_block}", help=f"Integer block number, or “latest”, default:{default_from_block}")
    parser.add_option("-t", "--to_block", dest="to_block", default=f"{default_to_block}", help=f"Integer block number, or “latest”, default:{default_to_block}")

    (options, args) = parser.parse_args()

    t = SyncEventLog(
            eth_http=options.eth_http,
            pair_address= Web3.toChecksumAddress(options.pair_address) if options.pair_address else "",
            from_block= options.to_block.lower() if options.from_block.lower() in ["latest", "pending", "earliest"] else int(options.from_block),
            to_block= options.to_block.lower() if options.to_block.lower() in ["latest", "pending", "earliest"] else int(options.to_block),
            )
    t.start()
    t.join()
