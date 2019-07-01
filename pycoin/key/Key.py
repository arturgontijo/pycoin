from pycoin.encoding.bytes32 import from_bytes_32, to_bytes_32
from pycoin.encoding.hash import hash160
from pycoin.encoding.hexbytes import b2h
from pycoin.encoding.sec import (
    is_sec_compressed, public_pair_to_sec, sec_to_public_pair
)
from pycoin.satoshi.der import sigencode_der, sigdecode_der


class InvalidPublicPairError(ValueError):
    pass


class InvalidSecretExponentError(ValueError):
    pass


class Key(object):

    _network = None
    _generator = None

    @classmethod
    def make_subclass(class_, network, generator):

        class Key(class_):
            _network = network
            _generator = generator

        return Key

    def __init__(self, secret_exponent=None, public_pair=None, is_compressed=True):
        """
        Include at most one of secret_exponent or public_pair.

        secret_exponent:
            a long representing the secret exponent
        public_pair:
            a tuple of long integers on the ecdsa curve
        is_compressed:
            Is this key in the compressed form? The uncompressed form is obsolete.
            Note that any function which produces output that depends on this can override
            this default value.
        """
        if [secret_exponent, public_pair].count(None) != 1:
            raise ValueError("exactly one of secret_exponent or public_pair must be passed.")
        self._secret_exponent = secret_exponent
        self._public_pair = public_pair
        self._is_compressed = is_compressed
        self._hash160_uncompressed = None
        self._hash160_compressed = None

        if self._generator is None:
            from pycoin.ecdsa.secp256k1 import secp256k1_generator
            self._generator = secp256k1_generator
        if self._network is None:
            from pycoin.networks.default import get_current_network
            self._network = get_current_network()

        if self._secret_exponent is not None:
            if self._secret_exponent < 1 \
                    or self._secret_exponent >= self._generator.order():
                raise InvalidSecretExponentError()
            public_pair = self._secret_exponent * self._generator
            self._public_pair = public_pair

        if (None in self._public_pair) or (
               not self._generator.contains_point(*self._public_pair)):
            raise InvalidPublicPairError()

    @classmethod
    def from_sec(class_, sec):
        """
        Create a key from an sec bytestream (which is an encoding of a public pair).
        """
        public_pair = sec_to_public_pair(sec, class_._generator)
        return class_(public_pair=public_pair, is_compressed=is_sec_compressed(sec))

    def is_private(self):
        return self.secret_exponent() is not None

    def secret_exponent(self):
        """
        Return an integer representing the secret exponent (or None).
        """
        return self._secret_exponent

    def wif(self, is_compressed=None):
        """
        Return the WIF representation of this key, if available.
        """
        secret_exponent = self.secret_exponent()
        if secret_exponent is None:
            return None
        if is_compressed is None:
            is_compressed = self.is_compressed()
        blob = to_bytes_32(secret_exponent)
        if is_compressed:
            blob += b'\01'
        return self._network.wif_for_blob(blob)

    def public_pair(self):
        """
        Return a pair of integers representing the public key (or None).
        """
        return self._public_pair

    def sec(self, is_compressed=None):
        """
        Return the SEC representation of this key, if available.
        """
        if is_compressed is None:
            is_compressed = self.is_compressed()
        public_pair = self.public_pair()
        if public_pair is None:
            return None
        return public_pair_to_sec(public_pair, compressed=is_compressed)

    def sec_as_hex(self, is_compressed=None):
        """
        Return the SEC representation of this key as hex text.
        """
        sec = self.sec(is_compressed=is_compressed)
        return self._network.sec_text_for_blob(sec)

    def hash160(self, is_compressed=None):
        """
        Return the hash160 representation of this key, if available.
        """
        if is_compressed is None:
            is_compressed = self.is_compressed()
        if is_compressed:
            if self._hash160_compressed is None:
                self._hash160_compressed = hash160(self.sec(is_compressed=is_compressed))
            return self._hash160_compressed

        if self._hash160_uncompressed is None:
            self._hash160_uncompressed = hash160(self.sec(is_compressed=is_compressed))
        return self._hash160_uncompressed

    def fingerprint(self, is_compressed=None):
        return self.hash160(is_compressed=is_compressed)[:4]

    def address(self, is_compressed=None):
        """
        Return the public address representation of this key, if available.
        """
        return self._network.address.for_p2pkh(self.hash160(is_compressed=is_compressed))

    def as_text(self):
        """
        Return a textual representation of this key.
        """
        if self.secret_exponent():
            return self.wif()
        sec_hex = self.sec_as_hex()
        if sec_hex:
            return sec_hex
        return self.address()

    def public_copy(self):
        if self.secret_exponent() is None:
            return self
        return self.__class__(public_pair=self.public_pair(), is_compressed=self.is_compressed())

    def subkey_for_path(self, path):
        return self

    def subkey(self, path_to_subkey):
        """
        Return the Key corresponding to the hierarchical wallet's subkey
        """
        return self

    def subkeys(self, path_to_subkeys):
        """
        Return an iterator yielding Keys corresponding to the
        hierarchical wallet's subkey path (or just this key).
        """
        yield self

    def sign(self, h):
        """
        Return a der-encoded signature for a hash h.
        Will throw a RuntimeError if this key is not a private key
        """
        if not self.is_private():
            raise RuntimeError("Key must be private to be able to sign")
        val = from_bytes_32(h)
        r, s = self._generator.sign(self.secret_exponent(), val)
        return sigencode_der(r, s)

    def verify(self, h, sig):
        """
        Return whether a signature is valid for hash h using this key.
        """
        val = from_bytes_32(h)
        pubkey = self.public_pair()
        return self._generator.verify(pubkey, val, sigdecode_der(sig))

    def is_compressed(self):
        """
        Return whether this key has been marked as compressed when it was created.
        """
        return self._is_compressed

    def __repr__(self):
        r = self.public_copy()
        if r._network:
            s = r.as_text()
        elif r.sec():
            s = b2h(r.sec())
        else:
            s = b2h(r.hash160())
        if self.is_private():
            return "private_for <%s>" % s
        return "<%s>" % s
