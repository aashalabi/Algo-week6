from helper import *
from algosdk.future import transaction
from algosdk import account, mnemonic
from algosdk.v2client import algod, indexer
from keys import funding_acct, funding_acct_mnemonic, user_mnemonic

import unittest

algod_address = "https://testnet-api.algonode.cloud"
indexer_address = "https://testnet-idx.algonode.cloud"
# user declared account mnemonics
funding_acct_mnemonic = funding_acct_mnemonic.replace(', ', ' ')

unittest.TestLoader.sortTestMethodsUsing = None

class TestContract(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.algod_client = algod.AlgodClient("", algod_address)
        cls.algod_indexer = indexer.IndexerClient("", indexer_address)
        cls.funding_acct = funding_acct
        cls.funding_acct_mnemonic = funding_acct_mnemonic
        cls.new_acct_priv_key, cls.new_acct_addr = account.generate_account()
        cls.new_acct_mnemonic = mnemonic.from_private_key(cls.new_acct_priv_key)

        #cls.new_acct_addr = account.address_from_private_key(cls.new_acct_priv_key)
        print("Generated new account: "+cls.new_acct_addr)
        cls.app_index = 0
        cls.regBegin = 0
        cls.regEnd = 0
        cls.voteBegin = 0
        cls.voteEnd = 0
        cls.creator_private_key = ''
        cls.user_private_key = get_private_key_from_mnemonic(user_mnemonic)
        
    
    #Methods for test cases must start with test
    def test_deploy_app(self):
        amt = 3000000
        fund_new_acct(TestContract.algod_client, TestContract.new_acct_addr, amt, TestContract.funding_acct_mnemonic)    

        print("Funded {amt} to new account for the purpose of deploying contract".format(amt = amt))

        creator_private_key = get_private_key_from_mnemonic(TestContract.new_acct_mnemonic)

        # declare application state storage (immutable)
        local_ints = 0
        local_bytes = 1
        global_ints = (
            24  # 4 for setup + 20 for choices. Use a larger number for more choices.
        )
        global_bytes = 1
        global_schema = transaction.StateSchema(global_ints, global_bytes)
        local_schema = transaction.StateSchema(local_ints, local_bytes)

        # get PyTeal approval program
        approval_program_ast = approval_program()
        # compile program to TEAL assembly
        approval_program_teal = compileTeal(
            approval_program_ast, mode=Mode.Application, version=6
        )
        # compile program to binary
        approval_program_compiled = compile_program(TestContract.algod_client, approval_program_teal)

        # get PyTeal clear state program
        clear_state_program_ast = clear_state_program()
        # compile program to TEAL assembly
        clear_state_program_teal = compileTeal(
            clear_state_program_ast, mode=Mode.Application, version=6
        )
        # compile program to binary
        clear_state_program_compiled = compile_program(
            TestContract.algod_client, clear_state_program_teal
        )

        # configure registration and voting period
        status = TestContract.algod_client.status()
        regBegin = status["last-round"] + 10
        regEnd = regBegin + 10
        voteBegin = regEnd + 1
        voteEnd = voteBegin + 10

        print(f"Registration rounds: {regBegin} to {regEnd}")
        print(f"Vote rounds: {voteBegin} to {voteEnd}")

        # create list of bytes for app args
        app_args = [
            intToBytes(regBegin),
            intToBytes(regEnd),
            intToBytes(voteBegin),
            intToBytes(voteEnd),
        ]
        
        # create new application
        TestContract.app_index = create_app(
            TestContract.algod_client,
            creator_private_key,
            approval_program_compiled,
            clear_state_program_compiled,
            global_schema,
            local_schema,
            app_args,
        )

        TestContract.regBegin = regBegin
        TestContract.regEnd = regEnd
        TestContract.voteBegin = voteBegin
        TestContract.voteEnd = voteEnd
        TestContract.creator_private_key = TestContract.new_acct_priv_key
        
        print("Deployed new app with APP ID: "+str(TestContract.app_index))

        global_state = read_global_state(
                TestContract.algod_client, account.address_from_private_key(creator_private_key), TestContract.app_index
            )
        print('Global state',global_state)
        print('Vote B', TestContract.voteBegin)
        print('Vote E', TestContract.voteEnd)
        print('Reg  B', TestContract.regBegin)
        print('Reg  E',  TestContract.regEnd)

        self.assertEqual(global_state['VoteBegin'], TestContract.voteBegin)
        self.assertEqual(global_state['VoteEnd'], TestContract.voteEnd)
        self.assertEqual(global_state['RegBegin'], TestContract.regBegin)
        self.assertEqual(global_state['RegEnd'], TestContract.regEnd)
        # wait for registration period to start
        wait_for_round(TestContract.algod_client, TestContract.regBegin)



  
        # opt-in to application
        print('start user opt in\n')
        opt_in_app(TestContract.algod_client, TestContract.user_private_key, TestContract.app_index)

        wait_for_round(TestContract.algod_client, TestContract.voteBegin)

        # call application without arguments
        call_app(TestContract.algod_client, TestContract.user_private_key, TestContract.app_index, [b"vote", b"choiceA"])

        # read local state of application from user account
        print(
            "Local state:",
            read_local_state(
                TestContract.algod_client, account.address_from_private_key(TestContract.user_private_key), TestContract.app_index
            ),
        )
    
        # wait for registration period to start
        wait_for_round(TestContract.algod_client, TestContract.voteEnd)

        # read global state of application
        global_state = read_global_state(
            TestContract.algod_client, account.address_from_private_key(TestContract.creator_private_key), 
            TestContract.app_index
        )
        print("Global state:", global_state)

        max_votes = 0
        max_votes_choice = None
        for key, value in global_state.items():
            if key not in (
                "RegBegin",
                "RegEnd",
                "VoteBegin",
                "VoteEnd",
                "Creator",
            ) and isinstance(value, int):
                if value > max_votes:
                    max_votes = value
                    max_votes_choice = key

        print("The winner is:", max_votes_choice)
        
        print(
            "Local state:",
            read_local_state(
                TestContract.algod_client, account.address_from_private_key(TestContract.user_private_key), TestContract.app_index
            ),
        )
        global_state = read_global_state(
            TestContract.algod_client, account.address_from_private_key(TestContract.creator_private_key), 
            TestContract.app_index
        )
        print("Global state:", global_state)
        assert(len(global_state) != 0)
        print('.....App delete.......')
        # delete application
        delete_app(TestContract.algod_client, TestContract.creator_private_key, TestContract.app_index)
        local_state = read_local_state(
                TestContract.algod_client, account.address_from_private_key(TestContract.user_private_key), TestContract.app_index
            )
        print(
            "Local state:",
            local_state,
        )
        assert(len(local_state) != 0)

        global_state = read_global_state(
            TestContract.algod_client, account.address_from_private_key(TestContract.creator_private_key), 
            TestContract.app_index
        )
        print("Global state:", global_state)
        assert(len(global_state) == 0)   
        
        # clear application from user account
        print('..... Clear app .......')
        clear_app(TestContract.algod_client, TestContract.user_private_key, TestContract.app_index)
        local_state = read_local_state(
                TestContract.algod_client, account.address_from_private_key(TestContract.user_private_key), TestContract.app_index
            )
        print(
            "Local state:",
            local_state,
        )
        assert(len(local_state) == 0)
            
def tearDownClass(self) -> None:
    return super().tearDown()

if __name__ == '__main__':
    unittest.main()