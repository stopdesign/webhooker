import hashlib
import requests
import hmac
import json
from datetime import datetime
from secrets import token_hex, randbits
from urllib.parse import quote_plus
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Signature import pkcs1_15
from base64 import b64encode, b64decode
from cryptography.hazmat.primitives.serialization import load_pem_parameters


class IbkrOAuth:
    """
    https://www.interactivebrokers.com/webtradingapi/oauth.pdf
    """

    domain = "api.ibkr.com"
    endpoint = "/oauth/live_session_token"

    def __init__(
        self,
        consumer_key: str,
        oauth_token: str,
        token_secret: str,
        dh_params: str,
        signature_key: str,
        encryption_key: str,
    ) -> None:
        self.last_request_result = None

        self.consumer_key = consumer_key
        self.oauth_token = oauth_token
        self.signature_key = signature_key
        self.encryption_key = encryption_key

        dh = load_pem_parameters(dh_params.encode())
        self.dh_prime = dh.parameter_numbers().p
        self.dh_generator = dh.parameter_numbers().g

        self.token_secret_bytes = self.rsa_decrypt(token_secret)

    @property
    def url(self):
        return f"https://{self.domain}/v1/api{self.endpoint}"

    def rsa_decrypt(self, token_secret: str):
        key = PKCS1_v1_5.new(RSA.import_key(self.encryption_key))
        return key.decrypt(b64decode(token_secret), bytes(0))

    def sign_oauth(self, auth_params: str):
        key = pkcs1_15.new(RSA.import_key(self.signature_key))
        digest = SHA256.new(auth_params.encode("utf-8"))
        signature = key.sign(digest)
        return b64encode(signature).decode("utf-8")

    def combine_params(self, method: str, url: str, data: dict) -> str:
        auth_params_str = ""
        auth_url = quote_plus(url)
        for k, v in data.items():
            auth_params_str += f"{k}={v}&"
        auth_params_str = quote_plus(auth_params_str.strip("&"))
        return f"{method}&{auth_url}&{auth_params_str}"

    def obtain_live_session_token(self):
        """
        Весь процесс получения нового токена.
        """
        self.last_request_result = None

        secret_int = randbits(200)

        try:
            resp = self.request_lst(secret_int)
        except:
            raise ValueError

        try:
            token, token_exp, signature = self.decrypt_lst(resp, secret_int)
        except:
            raise ValueError

        if self.validate_token(token, signature):
            return token, token_exp
        else:
            raise ValueError

    def request_lst(self, secret_int):
        """
        Запрос live_session_token.
        """

        nonce = token_hex(10)
        timestamp = str(int(datetime.now().timestamp()))

        dh_challenge = pow(self.dh_generator, secret_int, self.dh_prime)

        data = {
            "diffie_hellman_challenge": f"{dh_challenge:0x}",
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": nonce,
            "oauth_signature": "",
            "oauth_signature_method": "RSA-SHA256",
            "oauth_timestamp": timestamp,
            "oauth_token": self.oauth_token,
            "realm": "limited_poa",
        }

        auth_params = self.token_secret_bytes.hex()

        data_copy = dict(data)
        del data_copy["realm"]
        del data_copy["oauth_signature"]

        auth_params += self.combine_params("POST", self.url, data_copy)

        data["oauth_signature"] = quote_plus(self.sign_oauth(auth_params))

        auth_header = "OAuth"
        for k, v in data.items():
            auth_header += f' {k}="{v}",'
        auth_header = auth_header.strip(",")

        # print(f"Secret Integer: {secret_int}\n")
        # print(f"Authorization: {auth_header}\n")

        headers = {"Authorization": auth_header}

        print("REQUEST LIVE SESSION TOKEN")

        self.last_request_result = None
        r = requests.post(self.url, headers=headers, timeout=5)
        self.last_request_result = r

        # print("Response:", r.status_code, r.text)

        return r.json()

    def decrypt_lst(self, response, secret_integer):
        """
        Расшифровка live_session_token.
        """

        B = response["diffie_hellman_response"]
        signature = response["live_session_token_signature"]
        token_exp = response["live_session_token_expiration"]

        token_exp_dt = datetime.utcfromtimestamp(int(token_exp) // 1000)

        K = pow(int(B, 16), secret_integer, self.dh_prime)
        K_len = (8 + (K + (K < 0)).bit_length()) // 8
        K_big = K.to_bytes(K_len, signed=True)

        sig = hmac.new(K_big, self.token_secret_bytes, hashlib.sha1)
        token = b64encode(sig.digest()).decode()

        return token, token_exp_dt, signature

    def validate_token(self, token, signature):
        """
        Проверка live_session_token по token_signature.
        """

        msg = self.consumer_key.encode()
        sig_bytes = b64decode(token.encode())

        control_sig = hmac.new(sig_bytes, msg, hashlib.sha1)
        control_str = control_sig.hexdigest()

        return control_str and control_str == signature


def main():
    base_path = "../../../ib_oauth/paper"

    token_conf_path = f"{base_path}/token.json"
    dh_params_path = f"{base_path}/dhparam.pem"
    signature_key_path = f"{base_path}/private_signature.pem"
    encryption_key_path = f"{base_path}/private_encryption.pem"

    dh_params = open(dh_params_path).read()
    signature_key = open(signature_key_path).read()
    encryption_key = open(encryption_key_path).read()
    token_conf = json.load(open(token_conf_path))

    oauth_token = token_conf["token"]
    token_secret = token_conf["tokenSecret"]
    consumer_key = token_conf["consumerKey"]

    ibanina = IbkrOAuth(
        consumer_key,
        oauth_token,
        token_secret,
        dh_params,
        signature_key,
        encryption_key,
    )
    token, token_exp = ibanina.obtain_live_session_token()

    print(token, token_exp)

    print("DONE")


if __name__ == "__main__":
    main()
