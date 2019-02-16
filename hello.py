from flask import render_template
import hashlib
from hashlib import sha256
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request


class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transaction = []

        #this will hold the list of nodes
        self.nodes = set()
        self.port = None

        #Create genesis block
        self.new_block(previous_hash = 1 , proof = 100)
    
    def register_node(self,address):
        # Add a new node to the list of nodes
        # :param address: <str> Address of node. Eg. 'http://192.168.0.5:5000'
        # :return: None
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)
    
    def valid_chain(self,chain):
        #  Determine if a given blockchain is valid
        # :param chain: <list> A blockchain
        # :return: <bool> True if valid, False if not

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(last_block)
            print(block)
            print("----")

            #check that the hash of the block is correct
            if(block['previous_hash']!=self.hash(last_block)):
                return False

            #check that the proof of work is correct
            if not self.valid_proof(last_block['proof'] , block['proof']):
                return False

            last_block = block
            current_index = current_index + 1

        return True

    def resolve_conflicts(self):
        # This is our Consensus Algorithm, it resolves conflicts
        # by replacing our chain with the longest one in the network.
        # :return: <bool> True if our chain was replaced, False if not

        neigbours = self.nodes
        new_chain = None

        #We are only looking for longer chains than ours
        max_length = len(self.chain)

        #Grab and verify the chains from all nodes in network
        for node in neigbours:
            response = requests.get('http://{}/chain'.format(node))
            print(response)

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                #check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        
        #replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self , proof , previous_hash = None):
        #creates a new block
        # Create a new Block in the Blockchain
        # :param proof: <int> The proof given by the Proof of Work algorithm
        # :param previous_hash: (Optional) <str> Hash of previous Block
        # :return: <dict> New Block

        block = {
            'index' : len(self.chain) + 1 , 
            'timestamp' : time() , 
            'transaction' : self.current_transaction , 
            'proof' : proof , 
            'previous_hash' : previous_hash or self.hash(self.chain[-1]),
        }

        #resest current transaction
        self.current_transaction = []
        self.chain.append(block)
        return block
    
    def new_transaction(self , sender , recipient , amount):
        #adds new transaction to the list of transactions
        # Creates a new transaction to go into the next mined Block
        # :param sender: <str> Address of the Sender
        # :param recipient: <str> Address of the Recipient
        # :param amount: <int> Amount
        # :return: <int> The index of the Block that will hold this transaction

        self.current_transaction.append({
            'sender' :  sender,
            'recipient ' : recipient,
            'amount' : amount,

        })
        
        return self.last_block['index'] + 1

    def proof_of_work(self , last_proof):
        # Simple Proof of Work Algorithm:
        #  - Find a number p' such that hash(pp') contains leading 4 zeroes, where p is the previous p'
        #  - p is the previous proof, and p' is the new proof
        # :param last_proof: <int>
        # :return: <int>

        proof = 0
        while self.valid_proof(last_proof,proof) is False:
            proof = proof + 1

        return proof

    @staticmethod
    def valid_proof(last_proof , proof ):
        # Validates the Proof: Does hash(last_proof, proof) contain 4 leading zeroes?
        # :param last_proof: <int> Previous Proof
        # :param proof: <int> Current Proof
        # :return: <bool> True if correct, False if not.
        
        guess  = (str(str(last_proof)+str(proof))).encode()
        guess_hash = sha256(guess).hexdigest()

        return guess_hash[:4] == "0000"


    @staticmethod
    def hash(block):
        #hashes a block
        # Creates a SHA-256 hash of a Block
        # :param block: <dict> Block
        # :return: <str>

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block , sort_keys=True).encode()
        return sha256(block_string).hexdigest()

    @property
    def last_block(self):
        #returns the last block in the chain
        return self.chain[-1]

# Struture of block
# block = {
#     'index': 1,
#     'timestamp': 1506057125.900785,
#     'transactions': [
#         {
#             'sender': "8527147fe1f5426f9dd545de4b27ee00",
#             'recipient': "a77f5cdfa2934df3954a5c7c7da5df1f",
#             'amount': 5,
#         }
#     ],
#     'proof': 324984774000,
#     'previous_hash': "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
# }

#Flask Starts here

#Instance our Node
app = Flask(__name__)

#Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-','')

#Instantiate the Blockchain
blockchain = Blockchain()

@app.route('/')
def index():
    return render_template("index.html" , user_id = node_identifier , port = blockchain.port)

@app.route('/mine' , methods = ['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transaction': block['transaction'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }

    return jsonify(response), 200

@app.route('/transaction/new' , methods = ['POST'])
def new_transaction():
    values = request.get_json()

    #check that the required fields are in Post data
    # required = ['sender' , 'recipient' , 'amount']
    # if not all(k in values for k in required):
    #     return 'Missing values' , 400
    
    #create new transaction
    index = blockchain.new_transaction(node_identifier , request.form['recipient'] , request.form['amount'])

    response = {'message' : 'Transaction will be added to to Block : '+str(index)}

    return jsonify(response) , 201

@app.route('/chain' , methods = ['GET'])
def chain():
    response = {
        'chain' : blockchain.chain,
        'length' : len(blockchain.chain),
    }
    return jsonify(response) , 200

@app.route('/new')
def new():
    return render_template("new.html", user_id = node_identifier)


@app.route('/register', methods=['POST'])
def register_nodes():
    # values = request.get_json()
    nodes = []
    nodes.append(request.form['nodes'])
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200

if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    blockchain.port = port

    app.run(host='0.0.0.0', port=port , debug=True)