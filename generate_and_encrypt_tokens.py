from cryptography.fernet import Fernet
import os
import argparse
from langchain.tools.gmail.utils import get_gmail_credentials

parser = argparse.ArgumentParser()
parser.add_argument('--unencrypted_gmail_credentials_path')
parser.add_argument('--unencrypted_frappe_credentials_path')
parser.add_argument('--rocketchat_username', required=True)
parser.add_argument('--key')
parser.add_argument('--encrypted_token_save_path', default='agent_tokens/')
args = parser.parse_args()
# must supply exactly one of unencrypted_gmail_credentials_path or unencrypted_frappe_credentials_path
assert (args.unencrypted_gmail_credentials_path is None) != (args.unencrypted_frappe_credentials_path is None), "Must supply either --unencrypted_gmail_credentials_path or --unencrypted_frappe_credentials_path"

if args.key is None:
    key = Fernet.generate_key()
    print("No key provided. Generated a new key: ", key.decode())
else:
    key = args.key.encode()

if args.unencrypted_gmail_credentials_path is not None:
    credentials = get_gmail_credentials(
        token_file="token.json",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        client_secrets_file=args.unencrypted_gmail_credentials_path,
    )
    encrypted_token_save_path = os.path.join(args.encrypted_token_save_path, args.rocketchat_username)
    with open("token.json", 'rb') as f:
        data = f.read()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(data)
        if not os.path.exists(encrypted_token_save_path):   
            os.makedirs(encrypted_token_save_path)
        with open(os.path.join(encrypted_token_save_path, "gmail_token.encrypted"), 'wb') as f:
            f.write(encrypted)
            print("Encrypted token saved to ", os.path.join(encrypted_token_save_path, "gmail_token.encrypted"))
            os.remove("token.json")
elif args.unencrypted_frappe_credentials_path is not None:
    with open(args.unencrypted_frappe_credentials_path, 'rb') as f:
        unencrypted_frappe_credentials = f.read()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(unencrypted_frappe_credentials)
    encrypted_token_save_path = os.path.join(args.encrypted_token_save_path, args.rocketchat_username)
    with open(os.path.join(encrypted_token_save_path, "frappe_token.encrypted"), 'wb') as f:
        f.write(encrypted)
        print("Encrypted token saved to ", os.path.join(encrypted_token_save_path, "frappe_token.encrypted"))