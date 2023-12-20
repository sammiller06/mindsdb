from cryptography.fernet import Fernet
import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--unencrypted_frappe_credentials_path')
parser.add_argument('--rocketchat_username', required=True)
parser.add_argument('--key')
parser.add_argument('--encrypted_token_save_path', default='agent_tokens/')
args = parser.parse_args()

if args.key is None:
    key = Fernet.generate_key()
    print("No key provided. Generated a new key: ", key.decode())
else:
    key = args.key.encode()

with open(args.unencrypted_frappe_credentials_path, 'rt') as f:
    unencrypted_frappe_credentials = f.read().encode()        
    fernet = Fernet(key)
    encrypted = fernet.encrypt(unencrypted_frappe_credentials)

encrypted_token_save_path = os.path.join(args.encrypted_token_save_path, args.rocketchat_username)
if not os.path.exists(encrypted_token_save_path):
    os.makedirs(encrypted_token_save_path)

with open(os.path.join(encrypted_token_save_path, "frappe_token.encrypted"), 'wb') as f:
    f.write(encrypted)
    print("Encrypted token saved to ", os.path.join(encrypted_token_save_path, "frappe_token.encrypted"))
