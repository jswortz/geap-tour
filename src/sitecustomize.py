import sys
import logging

# Workaround for Vertex AI Agent Engine Python 3.13 SSL context mutation crash (b/330372060).
# By preventing urllib3 from importing and using PyOpenSSL, we force it to use Python's
# native ssl module, which correctly supports SSL context reuse without throwing
# "Context has already been used to create a Connection".
from types import ModuleType

import os

try:
    # Disable mutual TLS (mTLS) checks in google-auth requests transport.
    # Since we mock urllib3.contrib.pyopenssl to force standard ssl, google-auth's
    # mTLS adapter (which relies on PyOpenSSL contexts) would fail with AttributeError.
    # Disabling mTLS bypasses the mTLS adapter and uses standard TLS.
    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
    
    import urllib3.contrib
    # Create mock module for urllib3.contrib.pyopenssl to bypass monkey patching
    mock_pyopenssl = ModuleType('urllib3.contrib.pyopenssl')
    mock_pyopenssl.inject_into_urllib3 = lambda: None
    mock_pyopenssl.extract_from_urllib3 = lambda: None

    sys.modules['urllib3.contrib.pyopenssl'] = mock_pyopenssl
    urllib3.contrib.pyopenssl = mock_pyopenssl
    print("--- [sitecustomize.py] Mocked urllib3.contrib.pyopenssl and disabled mTLS ---")
except ImportError:
    pass
