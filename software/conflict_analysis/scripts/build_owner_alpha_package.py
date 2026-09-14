#!/usr/bin/env python3
"""Build immutable G10 artifacts; all downloads are already frozen below."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from verify_owner_alpha_package import (
    CONTROL, GateError, MANIFEST_NAME, PACKAGE_VERSION, PAYLOAD_NAMES, PROFILE_NAMES,
    SCHEMA, WINDOWS_FILES, WRAPPERS, canonical, expected_sums, identity, require,
    rootfs_inventory, safe_member, sha256_file, source_identity, verify_zip,
)

PINS = json.loads(r'''{"schema":"G10_AUTHORING_INPUT_PINS_V1","python":"3.12.14","postgresql":"18.4","oci":{"python":"docker.io/library/python@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79","postgres":"docker.io/library/postgres@sha256:4cc13dede823cab4e05290c7fb3350fb4e599ecabd9b07e6706b5d5e8f5bc929"},"wheels":[{"name":"asgiref","version":"3.12.1","filename":"asgiref-3.12.1-py3-none-any.whl","bytes":25478,"sha256":"fe386d1c2bff7259ea95929266d12a8cf9a8b5a1c2598402967d8792e7a7c094","url":"https://files.pythonhosted.org/packages/c0/1b/54f4ad77cd8a584fa70746c47df988e002cf1ee1eba43364d46f87803647/asgiref-3.12.1-py3-none-any.whl","requires":["typing_extensions>=4; python_version < \"3.11\"","pytest; extra == \"tests\"","pytest-asyncio; extra == \"tests\"","mypy>=1.14.0; extra == \"mypy\""]},{"name":"attrs","version":"26.1.0","filename":"attrs-26.1.0-py3-none-any.whl","bytes":67548,"sha256":"c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309","url":"https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl","requires":[]},{"name":"build","version":"1.3.0","filename":"build-1.3.0-py3-none-any.whl","bytes":23382,"sha256":"7145f0b5061ba90a1500d60bd1b13ca0a8a4cebdd0cc16ed8adf1c0e739f43b4","url":"https://files.pythonhosted.org/packages/cb/8c/2b30c12155ad8de0cf641d76a8b396a16d2c36bc6d50b621a62b7c4567c1/build-1.3.0-py3-none-any.whl","requires":["packaging >= 19.1","pyproject_hooks","colorama; os_name == \"nt\"","importlib-metadata >= 4.6; python_full_version < \"3.10.2\"","tomli >= 1.1.0; python_version < \"3.11\"","uv >= 0.1.18 ; extra == \"uv\"","virtualenv >= 20.11 ; extra == \"virtualenv\" and ( python_version < '3.10')","virtualenv >= 20.17 ; extra == \"virtualenv\" and ( python_version >= '3.10' and python_version < '3.14')","virtualenv >= 20.31 ; extra == \"virtualenv\" and ( python_version >= '3.14')"]},{"name":"colorama","version":"0.4.6","filename":"colorama-0.4.6-py2.py3-none-any.whl","bytes":25335,"sha256":"4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6","url":"https://files.pythonhosted.org/packages/d1/d6/3965ed04c63042e047cb6a3e6ed1a63a35087b6a609aa3a15ed8ac56c221/colorama-0.4.6-py2.py3-none-any.whl","requires":[]},{"name":"Django","version":"5.2.17","filename":"django-5.2.17-py3-none-any.whl","bytes":8315563,"sha256":"f04fb3b36ee119e1af4fa1d397d5fd6cf12700f49321e84d4f4c642c5b1973db","url":"https://files.pythonhosted.org/packages/df/f8/ce120525ca78f12b07daf65786679c5d0b54a75285a8958d3ae55e39da35/django-5.2.17-py3-none-any.whl","requires":["asgiref>=3.8.1","sqlparse>=0.3.1","tzdata; sys_platform == \"win32\"","argon2-cffi>=19.1.0; extra == \"argon2\"","bcrypt; extra == \"bcrypt\""]},{"name":"djangorestframework","version":"3.16.1","filename":"djangorestframework-3.16.1-py3-none-any.whl","bytes":1080442,"sha256":"33a59f47fb9c85ede792cbf88bde71893bcda0667bc573f784649521f1102cec","url":"https://files.pythonhosted.org/packages/b0/ce/bf8b9d3f415be4ac5588545b5fcdbbb841977db1c1d923f7568eeabe1689/djangorestframework-3.16.1-py3-none-any.whl","requires":["django>=4.2"]},{"name":"gunicorn","version":"23.0.0","filename":"gunicorn-23.0.0-py3-none-any.whl","bytes":85029,"sha256":"ec400d38950de4dfd418cff8328b2c8faed0edb0d517d3394e457c317908ca4d","url":"https://files.pythonhosted.org/packages/cb/7d/6dac2a6e1eba33ee43f318edbed4ff29151a49b5d37f080aad1e6469bca4/gunicorn-23.0.0-py3-none-any.whl","requires":["packaging","importlib-metadata ; python_version < \"3.8\"","eventlet !=0.36.0,>=0.24.1 ; extra == 'eventlet'","gevent >=1.4.0 ; extra == 'gevent'","setproctitle ; extra == 'setproctitle'","gevent ; extra == 'testing'","eventlet ; extra == 'testing'","coverage ; extra == 'testing'","pytest ; extra == 'testing'","pytest-cov ; extra == 'testing'","tornado >=0.2 ; extra == 'tornado'"]},{"name":"iniconfig","version":"2.3.0","filename":"iniconfig-2.3.0-py3-none-any.whl","bytes":7484,"sha256":"f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12","url":"https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl","requires":[]},{"name":"jsonschema","version":"4.26.0","filename":"jsonschema-4.26.0-py3-none-any.whl","bytes":90630,"sha256":"d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce","url":"https://files.pythonhosted.org/packages/69/90/f63fb5873511e014207a475e2bb4e8b2e570d655b00ac19a9a0ca0a385ee/jsonschema-4.26.0-py3-none-any.whl","requires":["attrs>=22.2.0","jsonschema-specifications>=2023.03.6","referencing>=0.28.4","rpds-py>=0.25.0","fqdn; extra == 'format'","idna; extra == 'format'","isoduration; extra == 'format'","jsonpointer>1.13; extra == 'format'","rfc3339-validator; extra == 'format'","rfc3987; extra == 'format'","uri-template; extra == 'format'","webcolors>=1.11; extra == 'format'","fqdn; extra == 'format-nongpl'","idna; extra == 'format-nongpl'","isoduration; extra == 'format-nongpl'","jsonpointer>1.13; extra == 'format-nongpl'","rfc3339-validator; extra == 'format-nongpl'","rfc3986-validator>0.1.0; extra == 'format-nongpl'","rfc3987-syntax>=1.1.0; extra == 'format-nongpl'","uri-template; extra == 'format-nongpl'","webcolors>=24.6.0; extra == 'format-nongpl'"]},{"name":"jsonschema-specifications","version":"2025.9.1","filename":"jsonschema_specifications-2025.9.1-py3-none-any.whl","bytes":18437,"sha256":"98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe","url":"https://files.pythonhosted.org/packages/41/45/1a4ed80516f02155c51f51e8cedb3c1902296743db0bbc66608a0db2814f/jsonschema_specifications-2025.9.1-py3-none-any.whl","requires":["referencing>=0.31.0"]},{"name":"packaging","version":"26.3","filename":"packaging-26.3-py3-none-any.whl","bytes":129956,"sha256":"d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c","url":"https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl","requires":[]},{"name":"pluggy","version":"1.6.0","filename":"pluggy-1.6.0-py3-none-any.whl","bytes":20538,"sha256":"e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746","url":"https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl","requires":["pre-commit; extra == \"dev\"","tox; extra == \"dev\"","pytest; extra == \"testing\"","pytest-benchmark; extra == \"testing\"","coverage; extra == \"testing\""]},{"name":"psycopg","version":"3.3.5","filename":"psycopg-3.3.5-py3-none-any.whl","bytes":213598,"sha256":"ce5aa5cdb4f9379f00f487590e5890bfa7df9a164648c969ffa628505e21af4e","url":"https://files.pythonhosted.org/packages/3d/2e/d0a645bcaadde68bd6d93c43f02f14b0191bdda367ce3f7722abe3da744a/psycopg-3.3.5-py3-none-any.whl","requires":["typing-extensions>=4.6; python_version < \"3.13\"","tzdata; sys_platform == \"win32\"","psycopg-c==3.3.5; implementation_name != \"pypy\" and extra == \"c\"","psycopg-binary==3.3.5; implementation_name != \"pypy\" and extra == \"binary\"","psycopg-pool; extra == \"pool\"","anyio>=4.0; extra == \"test\"","mypy>=2.1.0; implementation_name != \"pypy\" and extra == \"test\"","pproxy>=2.7; extra == \"test\"","pytest>=6.2.5; extra == \"test\"","pytest-cov>=3.0; extra == \"test\"","pytest-randomly>=3.5; extra == \"test\"","ast-comments>=1.1.2; extra == \"dev\"","black>=26.1.0; extra == \"dev\"","codespell>=2.2; extra == \"dev\"","cython-lint>=0.21; extra == \"dev\"","dnspython>=2.1; extra == \"dev\"","flake8>=4.0; extra == \"dev\"","isort[colors]<9.0,>=6.0; extra == \"dev\"","isort-psycopg; extra == \"dev\"","mypy>=2.1.0; extra == \"dev\"","pre-commit>=4.0.1; extra == \"dev\"","types-setuptools>=57.4; extra == \"dev\"","types-shapely>=2.0; extra == \"dev\"","wheel>=0.37; extra == \"dev\"","Sphinx>=9.1; extra == \"docs\"","furo==2025.12.19; extra == \"docs\"","sphinx-autobuild>=2025.8.25; extra == \"docs\"","sphinx-autodoc-typehints>=3.10.2; extra == \"docs\""]},{"name":"psycopg-binary","version":"3.3.5","filename":"psycopg_binary-3.3.5-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl","bytes":5227752,"sha256":"682a17a57415c3ca1731eec018ed031f012ffcb81ba74806eb219cb396065672","url":"https://files.pythonhosted.org/packages/21/d1/0f244dfef389e52e9dc3056f2a9033d1f6901e97d24d9a9c8b836e32ab6b/psycopg_binary-3.3.5-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl","requires":[]},{"name":"Pygments","version":"2.21.0","filename":"pygments-2.21.0-py3-none-any.whl","bytes":1250147,"sha256":"2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9","url":"https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl","requires":["colorama>=0.4.6; extra == 'windows-terminal'"]},{"name":"pyproject_hooks","version":"1.2.0","filename":"pyproject_hooks-1.2.0-py3-none-any.whl","bytes":10216,"sha256":"9e5c6bfa8dcc30091c74b0cf803c81fdd29d94f01992a7707bc97babb1141913","url":"https://files.pythonhosted.org/packages/bd/24/12818598c362d7f300f18e74db45963dbcb85150324092410c8b49405e42/pyproject_hooks-1.2.0-py3-none-any.whl","requires":[]},{"name":"pytest","version":"8.4.2","filename":"pytest-8.4.2-py3-none-any.whl","bytes":365750,"sha256":"872f880de3fc3a5bdc88a11b39c9710c3497a547cfa9320bc3c5e62fbf272e79","url":"https://files.pythonhosted.org/packages/a8/a4/20da314d277121d6534b3a980b29035dcd51e6744bd79075a6ce8fa4eb8d/pytest-8.4.2-py3-none-any.whl","requires":["colorama>=0.4; sys_platform == \"win32\"","exceptiongroup>=1; python_version < \"3.11\"","iniconfig>=1","packaging>=20","pluggy<2,>=1.5","pygments>=2.7.2","tomli>=1; python_version < \"3.11\"","argcomplete; extra == \"dev\"","attrs>=19.2; extra == \"dev\"","hypothesis>=3.56; extra == \"dev\"","mock; extra == \"dev\"","requests; extra == \"dev\"","setuptools; extra == \"dev\"","xmlschema; extra == \"dev\""]},{"name":"pytest-django","version":"4.11.1","filename":"pytest_django-4.11.1-py3-none-any.whl","bytes":25281,"sha256":"1b63773f648aa3d8541000c26929c1ea63934be1cfa674c76436966d73fe6a10","url":"https://files.pythonhosted.org/packages/be/ac/bd0608d229ec808e51a21044f3f2f27b9a37e7a0ebaca7247882e67876af/pytest_django-4.11.1-py3-none-any.whl","requires":["pytest>=7.0.0","sphinx; extra == \"docs\"","sphinx_rtd_theme; extra == \"docs\"","Django; extra == \"testing\"","django-configurations>=2.0; extra == \"testing\""]},{"name":"referencing","version":"0.37.0","filename":"referencing-0.37.0-py3-none-any.whl","bytes":26766,"sha256":"381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231","url":"https://files.pythonhosted.org/packages/2c/58/ca301544e1fa93ed4f80d724bf5b194f6e4b945841c5bfd555878eea9fcb/referencing-0.37.0-py3-none-any.whl","requires":["attrs>=22.2.0","rpds-py>=0.7.0","typing-extensions>=4.4.0; python_version < '3.13'"]},{"name":"rpds-py","version":"2026.6.3","filename":"rpds_py-2026.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl","bytes":366189,"sha256":"ecabd69db66de867690f9797f2f8fa27ba501bbc24540cbdbdc649cd15888ba6","url":"https://files.pythonhosted.org/packages/04/8f/d2f3f532616be4d06c316ef119683e832bd3d41e112bf3a88f4151c95b17/rpds_py-2026.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl","requires":[]},{"name":"setuptools","version":"80.9.0","filename":"setuptools-80.9.0-py3-none-any.whl","bytes":1201486,"sha256":"062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922","url":"https://files.pythonhosted.org/packages/a3/dc/17031897dae0efacfea57dfd3a82fdd2a2aeb58e0ff71b77b87e44edc772/setuptools-80.9.0-py3-none-any.whl","requires":["pytest!=8.1.*,>=6; extra == \"test\"","virtualenv>=13.0.0; extra == \"test\"","wheel>=0.44.0; extra == \"test\"","pip>=19.1; extra == \"test\"","packaging>=24.2; extra == \"test\"","jaraco.envs>=2.2; extra == \"test\"","pytest-xdist>=3; extra == \"test\"","jaraco.path>=3.7.2; extra == \"test\"","build[virtualenv]>=1.0.3; extra == \"test\"","filelock>=3.4.0; extra == \"test\"","ini2toml[lite]>=0.14; extra == \"test\"","tomli-w>=1.0.0; extra == \"test\"","pytest-timeout; extra == \"test\"","pytest-perf; sys_platform != \"cygwin\" and extra == \"test\"","jaraco.develop>=7.21; (python_version >= \"3.9\" and sys_platform != \"cygwin\") and extra == \"test\"","pytest-home>=0.5; extra == \"test\"","pytest-subprocess; extra == \"test\"","pyproject-hooks!=1.1; extra == \"test\"","jaraco.test>=5.5; extra == \"test\"","sphinx>=3.5; extra == \"doc\"","jaraco.packaging>=9.3; extra == \"doc\"","rst.linker>=1.9; extra == \"doc\"","furo; extra == \"doc\"","sphinx-lint; extra == \"doc\"","jaraco.tidelift>=1.4; extra == \"doc\"","pygments-github-lexers==0.0.5; extra == \"doc\"","sphinx-favicon; extra == \"doc\"","sphinx-inline-tabs; extra == \"doc\"","sphinx-reredirects; extra == \"doc\"","sphinxcontrib-towncrier; extra == \"doc\"","sphinx-notfound-page<2,>=1; extra == \"doc\"","pyproject-hooks!=1.1; extra == \"doc\"","towncrier<24.7; extra == \"doc\"","packaging>=24.2; extra == \"core\"","more_itertools>=8.8; extra == \"core\"","jaraco.text>=3.7; extra == \"core\"","importlib_metadata>=6; python_version < \"3.10\" and extra == \"core\"","tomli>=2.0.1; python_version < \"3.11\" and extra == \"core\"","wheel>=0.43.0; extra == \"core\"","platformdirs>=4.2.2; extra == \"core\"","jaraco.functools>=4; extra == \"core\"","more_itertools; extra == \"core\"","pytest-checkdocs>=2.4; extra == \"check\"","pytest-ruff>=0.2.1; sys_platform != \"cygwin\" and extra == \"check\"","ruff>=0.8.0; sys_platform != \"cygwin\" and extra == \"check\"","pytest-cov; extra == \"cover\"","pytest-enabler>=2.2; extra == \"enabler\"","pytest-mypy; extra == \"type\"","mypy==1.14.*; extra == \"type\"","importlib_metadata>=7.0.2; python_version < \"3.10\" and extra == \"type\"","jaraco.develop>=7.21; sys_platform != \"cygwin\" and extra == \"type\""]},{"name":"sqlparse","version":"0.6.0","filename":"sqlparse-0.6.0-py3-none-any.whl","bytes":50070,"sha256":"b861c0288ce2fa56209a9a6412d2e066ac664b3873b89c26c9d8415e8e32996f","url":"https://files.pythonhosted.org/packages/d9/50/f00935da0ec7cbf325f8dc4f772ae46fbc7b672dd62876e73f0a94adda57/sqlparse-0.6.0-py3-none-any.whl","requires":["build; extra == 'dev'","furo; extra == 'doc'","sphinx; extra == 'doc'"]},{"name":"typing_extensions","version":"4.16.0","filename":"typing_extensions-4.16.0-py3-none-any.whl","bytes":45571,"sha256":"481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8","url":"https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl","requires":[]},{"name":"tzdata","version":"2026.4","filename":"tzdata-2026.4-py2.py3-none-any.whl","bytes":347494,"sha256":"c2169a8b0a7a5e9674da5a135ccdfb2b3e671b333ed9fed17b41f73c34476e81","url":"https://files.pythonhosted.org/packages/f9/bc/8737e8d54cf51106118039b83f485a4783112fab49ea9d044b234978a46e/tzdata-2026.4-py2.py3-none-any.whl","requires":[]},{"name":"wheel","version":"0.45.1","filename":"wheel-0.45.1-py3-none-any.whl","bytes":72494,"sha256":"708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248","url":"https://files.pythonhosted.org/packages/0b/2c/87f3254fd8ffd29e4c02732eee68a83a1d3c346ae39bc6822dcbcb697f2b/wheel-0.45.1-py3-none-any.whl","requires":["pytest >= 6.0.0 ; extra == \"test\"","setuptools >= 65 ; extra == \"test\""]}],"debs":[{"name":"nginx","version":"1.26.3-3+deb13u8","architecture":"amd64","filename":"nginx_1.26.3-3+deb13u8_amd64.deb","url":"https://snapshot.debian.org/file/9d0ec6df1198961d5890cea423bf168ee56cf982","bytes":612736,"sha256":"4c9b5f9b78874298e057a32b3854c21eef3cf2b6c6855b028b6f28c1774c9b3b","snapshot_sha1":"9d0ec6df1198961d5890cea423bf168ee56cf982","control":"Package: nginx\nVersion: 1.26.3-3+deb13u8\nArchitecture: amd64\nMaintainer: Debian Nginx Maintainers <pkg-nginx-maintainers@alioth-lists.debian.net>\nInstalled-Size: 1556\nDepends: libc6 (>= 2.34), libcrypt1 (>= 1:4.1.0), libpcre2-8-0 (>= 10.22), libssl3t64 (>= 3.0.0), zlib1g (>= 1:1.1.4), iproute2, nginx-common (= 1.26.3-3+deb13u8)\nBreaks: nginx-core (<< 1.22.1-6~), nginx-extras (<< 1.22.1-6~), nginx-light (<< 1.22.1-6~)\nReplaces: nginx-core (<< 1.22.1-6~), nginx-extras (<< 1.22.1-6~), nginx-light (<< 1.22.1-6~)\nProvides: httpd, httpd-cgi, nginx-abi-1.26.3-1\nSection: httpd\nPriority: optional\nHomepage: https://nginx.org\nDescription: small, powerful, scalable web/proxy server\n Nginx (\"engine X\") is a high-performance web and reverse proxy server\n created by Igor Sysoev. It can be used both as a standalone web server\n and as a proxy to reduce the load on back-end HTTP or mail servers.\n"},{"name":"nginx-common","version":"1.26.3-3+deb13u8","architecture":"all","filename":"nginx-common_1.26.3-3+deb13u8_all.deb","url":"https://snapshot.debian.org/file/73ec9b3e4bbaacb7e452c14e6e81467575d3e75e","bytes":111428,"sha256":"4947615078bbc9457995a2a077da94c60c326e95503da83f55b2d197ec471250","snapshot_sha1":"73ec9b3e4bbaacb7e452c14e6e81467575d3e75e","control":"Package: nginx-common\nSource: nginx\nVersion: 1.26.3-3+deb13u8\nArchitecture: all\nMaintainer: Debian Nginx Maintainers <pkg-nginx-maintainers@alioth-lists.debian.net>\nInstalled-Size: 305\nDepends: debconf (>= 0.5) | debconf-2.0\nSuggests: fcgiwrap, nginx-doc, ssl-cert\nBreaks: nginx (<< 1.22.1-8)\nReplaces: nginx (<< 1.22.1-8)\nSection: httpd\nPriority: optional\nMulti-Arch: foreign\nHomepage: https://nginx.org\nDescription: small, powerful, scalable web/proxy server - common files\n Nginx (\"engine X\") is a high-performance web and reverse proxy server\n created by Igor Sysoev. It can be used both as a standalone web server\n and as a proxy to reduce the load on back-end HTTP or mail servers.\n .\n This package contains base configuration files used by all versions of\n nginx.\n"}]}''')
ROOTFS_NAME = "conflict-analysis-functional-alpha-rootfs.tar"
ZIP_NAME = "conflict-analysis-functional-alpha-0.1.0-alpha.1-windows11-wsl2-x64.zip"
BUILD_TOOLS = {"build", "setuptools", "wheel", "pyproject-hooks", "pytest",
               "pytest-django", "pluggy", "iniconfig", "pygments", "colorama"}
def normalized_name(name):
    return name.lower().replace("_", "-").replace(".", "-")

def run(args, *, cwd=None, env=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=False)
    require(result.returncode == 0, "BLOCKED_G10_NONDETERMINISTIC_BUILD",
            "build command failed: " + str(args[0]))

def download(pin, directory):
    target = directory / pin["filename"]
    directory.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(pin["url"], timeout=180) as response:
            with target.open("xb") as output:
                shutil.copyfileobj(response, output)
    require(identity(target) == {k: pin[k] for k in ("filename", "bytes", "sha256")},
            "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "frozen dependency bytes")
    return target

def lock_text(pins):
    return "".join(f'{p["name"]}=={p["version"]} --hash=sha256:{p["sha256"]}\n'
                   for p in sorted(pins, key=lambda p: normalized_name(p["name"])))

def validate_closure():
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.version import Version
    by_name = {normalized_name(p["name"]): p for p in PINS["wheels"]}
    env = default_environment()
    env.update(python_version="3.12", python_full_version="3.12.14",
               sys_platform="linux", platform_system="Linux", platform_machine="x86_64",
               implementation_name="cpython", os_name="posix", extra="")
    for pin in by_name.values():
        for text in pin["requires"]:
            requirement = Requirement(text)
            extras = ("", "binary") if normalized_name(pin["name"]) == "psycopg" else ("",)
            if requirement.marker and not any(requirement.marker.evaluate({**env, "extra": e})
                                               for e in extras):
                continue
            dependency = by_name.get(normalized_name(requirement.name))
            require(dependency is not None and Version(dependency["version"]) in requirement.specifier,
                    "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "incomplete frozen wheel closure")
    return True

def cmd_wrapper(script, arguments):
    # Inline -Command is the external admission boundary: no packaged PS bytes
    # execute until effective policy + zone + signature/trust checks have passed.
    # Neither process policy nor host policy is changed.
    check = (
        "$ErrorActionPreference='Stop';"
        "$p=Get-ExecutionPolicy;"
        "if($p -notin @('RemoteSigned','AllSigned','Unrestricted')){throw 'POLICY_DENIED'};"
        "$root=[IO.Path]::GetFullPath($env:G10_PACKAGE_ROOT);"
        "Get-ChildItem -LiteralPath (Join-Path $root 'windows') -File | "
        "Where-Object Extension -in '.ps1','.psm1' | ForEach-Object {"
        "$z=Get-Content -LiteralPath $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue;"
        "$s=Get-AuthenticodeSignature -LiteralPath $_.FullName;"
        "$marked=($z -match 'ZoneId=[3-4]');"
        "if(($p -eq 'AllSigned' -or $marked) -and $s.Status -ne 'Valid'){throw 'SIGNATURE_DENIED'};"
        "if($p -eq 'AllSigned' -or $marked){"
        "$cert=$s.SignerCertificate;"
        "$trusted=@(Get-ChildItem Cert:\\CurrentUser\\TrustedPublisher,Cert:\\LocalMachine\\TrustedPublisher);"
        "if(-not $cert -or $cert.Thumbprint -notin $trusted.Thumbprint){throw 'PUBLISHER_DENIED'}}};"
        "$port=if($env:G10_PORT){[int]$env:G10_PORT}else{8765};"
        f"& (Join-Path $root 'windows/{script}') -StateRoot $env:G10_STATE_ROOT -Port $port {arguments}"
    )
    return ("@echo off\r\nsetlocal\r\n"
            'set "G10_PACKAGE_ROOT=%~dp0"\r\n'
            'set "G10_SHELL=%ProgramFiles%\\PowerShell\\7\\pwsh.exe"\r\n'
            'if not exist "%G10_SHELL%" goto blocked\r\n'
            f'"%G10_SHELL%" -NoLogo -NoProfile -Command "{check}"\r\n'
            "if errorlevel 1 goto blocked\r\nexit /b 0\r\n:blocked\r\n"
            "echo G10: zapusk zablokirovan. Sm. START_HERE_RU.txt.\r\npause\r\nexit /b 1\r\n").encode("utf-8")

def normalize_rootfs(source, target):
    # Normalize a Docker export without extraction or following untrusted links.
    ignored = {"etc/hostname", "etc/hosts", "etc/resolv.conf", ".dockerenv"}
    fixed = {"etc/hostname": b"owner-alpha\n", "etc/hosts": b"127.0.0.1 localhost\n::1 localhost\n", "etc/resolv.conf": b""}
    with tarfile.open(source) as incoming, tarfile.open(target, "w", format=tarfile.GNU_FORMAT) as out:
        members = {}
        for member in incoming:
            name = member.name.removeprefix("./").rstrip("/")
            if not name or name in ignored or member.isdev() or member.isfifo():
                continue
            require(safe_member(name) and name not in members,
                    "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "export path")
            members[name] = member
        for name in sorted(set(members) | set(fixed)):
            if name in fixed:
                member = tarfile.TarInfo(name)
                member.mode = 0o644
                member.size = len(fixed[name])
                out.addfile(member, io.BytesIO(fixed[name]))
                continue
            original = members[name]
            member = copy.copy(original)
            member.name, member.mtime = name, 0
            member.uname, member.gname, member.pax_headers = "", "", {}
            member.mode &= 0o1777  # no setuid/setgid executables
            out.addfile(member, incoming.extractfile(original) if original.isfile() else None)
    return rootfs_inventory(target)

def write_zip(target, members):
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as out:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            with out.open(info, "w", force_zip64=True) as dst:
                value = members[name]
                if isinstance(value, Path):
                    with value.open("rb") as src:
                        shutil.copyfileobj(src, dst)
                else:
                    dst.write(value)

def metadata(value):
    return {"bytes": value.stat().st_size, "sha256": sha256_file(value)} if isinstance(value, Path) else {
        "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}

def package_members(package, rootfs, source, wheel, runtime_report, inventory):
    runtime = {**PINS, "offline_install": True}
    evidence = {"schema": "G10_BUILD_EVIDENCE_V1", "source": source, "wheel": wheel,
                "rootfs": identity(rootfs), "rootfs_inventory_sha256": inventory["sha256"],
                "runtime_report": runtime_report, "final_windows_acceptance": False}
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "components": [
                {"type": "library", "name": p["name"], "version": p["version"],
                 "hashes": [{"alg": "SHA-256", "content": p["sha256"]}]}
                for p in PINS["wheels"] + PINS["debs"]
            ], "properties": [{"name": "g10:source-tree", "value": source["tree"]}],
            "metadata": {"component": {"type": "application", "name": "conflict-analysis",
                                       "version": "0.1.0",
                                       "hashes": [{"alg": "SHA-256", "content": wheel["sha256"]}]}}}
    members = {name: (package / name).read_bytes() for name in
               ("START_HERE_RU.txt", "manifest.schema.json")}
    members.update({"windows/" + name: (package / "windows" / name).read_bytes()
                    for name in WINDOWS_FILES})
    members.update({name: cmd_wrapper(*value) for name, value in WRAPPERS.items()})
    members.update({"rootfs/" + ROOTFS_NAME: rootfs, "SBOM.cdx.json": canonical(sbom),
                    "THIRD_PARTY_NOTICES.txt": runtime_report["notices"].encode("utf-8"),
                    "evidence/package-build-evidence.json": canonical(evidence)})
    require(set(members) == PAYLOAD_NAMES, "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "payload")
    manifest = {"schema": SCHEMA, "package_version": PACKAGE_VERSION, "source": source,
                "migration": {"path": CONTROL["migration"], "blob": CONTROL["migration_blob"]},
                "wheel": wheel, "runtime": runtime, "profiles": list(PROFILE_NAMES),
                "test_registry": CONTROL["tests"], "payload": {k: metadata(v) for k, v in members.items()},
                "artifact_order": ["P", "M", "S", "Z", "E", "acceptance_index"],
                "nonclaims": {"production_ready": False, "owner_test_authorized": False,
                              "release": False, "final_windows_acceptance": False,
                              "sqlite_runtime": False, "native_windows_server": False}}
    manifest_raw = canonical(manifest)
    members[MANIFEST_NAME] = manifest_raw
    members["SHA256SUMS"] = expected_sums(manifest, manifest_raw)
    return members

def build(repository, output):
    source = source_identity(repository)
    validate_closure()
    require(not output.exists(), "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "new output directory required")
    require(not output.resolve().is_relative_to(repository.resolve()),
            "BLOCKED_G10_SCOPE_EXPANSION", "artifacts must be outside checkout")
    output.mkdir(parents=True)
    package = repository / "software/conflict_analysis/owner_alpha_package"
    with tempfile.TemporaryDirectory(prefix="g10-build-") as temporary:
        context = Path(temporary)
        for pin in PINS["wheels"]:
            download(pin, context / "wheels")
        for pin in PINS["debs"]:
            download(pin, context / "debs")
        shutil.copytree(package / "linux", context / "linux")
        (context / "runtime.lock").write_text(lock_text([p for p in PINS["wheels"]
                       if normalized_name(p["name"]) not in BUILD_TOOLS]), encoding="utf-8")
        (context / "build.lock").write_text(lock_text(PINS["wheels"]), encoding="utf-8")
        (context / "pins.json").write_bytes(canonical(PINS))
        (context / "source.json").write_bytes(canonical(source))
        archive = subprocess.run(["git", "-C", str(repository), "archive", source["head"] + ":software/conflict_analysis"],
                                 check=True, capture_output=True).stdout
        (context / "application.tar").write_bytes(archive)
        with tarfile.open(fileobj=io.BytesIO(archive)) as app_tar:
            help_member = app_tar.extractfile("domain/content/studio_help_ru_v1.json")
            require(help_member is not None, "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "Studio Help sidecar")
            (context / "studio_help_ru_v1.json").write_bytes(help_member.read())
        tag = "g10-wheel-" + source["head"]
        common = ["docker", "build", "--platform", "linux/amd64", "--network=none",
                  "--build-arg", "SOURCE_DATE_EPOCH=" + str(source["source_date_epoch"]),
                  "-f", context / "linux/Containerfile"]
        run([*common, "--target", "wheel", "-t", tag, context])
        container = subprocess.check_output(["docker", "create", tag], text=True).strip()
        try:
            run(["docker", "cp", container + ":/wheel/.", output])
        finally:
            run(["docker", "rm", container])
        wheels = list(output.glob("*.whl"))
        require(len(wheels) == 1, "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "one application wheel")
        wheel = identity(wheels[0])
        shutil.copy(wheels[0], context / wheel["filename"])
        (context / "wheel.json").write_bytes(canonical(wheel))
        (context / "application.lock").write_text(
            "./" + wheel["filename"] + " --hash=sha256:" + wheel["sha256"] + "\n", encoding="utf-8")
        reports = []
        for attempt in (1, 2):
            run([*common, "--no-cache", "--target", "runtime", "-t", tag + "-runtime", context])
            container = subprocess.check_output(["docker", "create", tag + "-runtime"], text=True).strip()
            try:
                raw = context / ("export-" + str(attempt) + ".tar")
                run(["docker", "export", "--output", raw, container])
                report_file = output / ("runtime-report-" + str(attempt) + ".json")
                run(["docker", "cp", container + ":/opt/owner-alpha/runtime-report.json", report_file])
                reports.append(json.loads(report_file.read_bytes()))
            finally:
                run(["docker", "rm", container])
            rootfs = output / (ROOTFS_NAME if attempt == 1 else "repeat-" + ROOTFS_NAME)
            inventory = normalize_rootfs(raw, rootfs)
        require(sha256_file(output / ROOTFS_NAME) == sha256_file(output / ("repeat-" + ROOTFS_NAME))
                and reports[0] == reports[1], "BLOCKED_G10_NONDETERMINISTIC_BUILD", "rootfs repeat")
        members = package_members(package, output / ROOTFS_NAME, source, wheel, reports[0], inventory)
        for prefix in ("", "repeat-"):
            write_zip(output / (prefix + ZIP_NAME), members)
        require(sha256_file(output / ZIP_NAME) == sha256_file(output / ("repeat-" + ZIP_NAME)),
                "BLOCKED_G10_NONDETERMINISTIC_BUILD", "ZIP repeat")
        verify_zip(output / ZIP_NAME)
        for name in (MANIFEST_NAME, "SHA256SUMS", "SBOM.cdx.json", "THIRD_PARTY_NOTICES.txt"):
            (output / name).write_bytes(members[name])
        (output / "artifact-identities.json").write_bytes(canonical({
            "schema": "G10_EXTERNAL_BUILD_IDENTITIES_V1", "source": source,
            "artifacts": [identity(p) for p in sorted(output.iterdir()) if p.is_file()],
            "windows_e2e": "NOT_EXECUTED", "ready_for_main_review": False}))
    return identity(output / ZIP_NAME)

def regressions(repository, output):
    """Replay accepted matrices on this exact head and the one already built wheel."""
    import xml.etree.ElementTree as ET
    import sys
    source = source_identity(repository)
    package = verify_zip(output / ZIP_NAME)
    require(package["manifest"]["source"] == source, "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "regression source")
    wheel = output / package["manifest"]["wheel"]["filename"]
    require(identity(wheel) == package["manifest"]["wheel"], "BLOCKED_G10_ARTIFACT_IDENTITY_GAP", "one wheel")
    app = repository / "software/conflict_analysis"
    env = os.environ.copy()
    env.update(STUDIO_C0_WHEEL=str(wheel), PYTHONDONTWRITEBYTECODE="1")
    product = [
        "production_studio/tests/test_browser_contract.py",
        "production_studio/tests/test_claim_boundaries.py",
        "production_studio/tests/test_read_only_http.py",
        "production_studio/tests/test_read_only_static_contracts.py",
        "production_studio/tests/test_audited_authoring.py::ProductionStudioAuditedAuthoringContractTests",
        "production_studio/tests/test_lifecycle_publication.py::ProductionStudioLifecyclePublicationTests",
        "production_player/tests/test_player_g7.py::ProductionPlayerG7Tests",
        "production_player/tests/test_player_g8.py::ProductionPlayerG8Tests",
        "production_player/tests/test_player_g9_evidence.py::ProductionPlayerG9EvidenceTests",
    ]
    browsers = [
        "production_studio/tests/test_audited_authoring.py::ProductionStudioAuditedAuthoringBrowserTests::test_authenticated_edit_save_reload_is_bounded_foundation_only_and_receipted",
        "production_studio/tests/test_lifecycle_publication.py::ProductionStudioLifecyclePublicationBrowserTests",
        "production_player/tests/test_player_g7.py::ProductionPlayerG7ChromiumTests",
        "production_player/tests/test_player_g8.py::ProductionPlayerG8ChromiumTests",
        "production_player/tests/test_player_g9_evidence.py::ProductionPlayerG9ChromiumTests",
    ]
    reports = {}
    def suite(label, nodes, expected_pass, expected_skip, environment):
        report = output / (label + ".xml")
        run([sys.executable, "-m", "pytest", *nodes, "-p", "no:cacheprovider", "--junitxml=" + str(report)],
            cwd=app, env=environment)
        tree = ET.parse(report)
        cases = tree.findall(".//testcase")
        skipped = [n.attrib["classname"] + "::" + n.attrib["name"] for n in cases if n.find("skipped") is not None]
        require(not tree.findall(".//failure") and not tree.findall(".//error")
                and len(cases) - len(skipped) == expected_pass and len(skipped) == expected_skip,
                "BLOCKED_G10_PARENT_REGRESSION", label + " exact totals")
        reports[label] = {"passed": expected_pass, "skipped": skipped, "junit": identity(report)}
    for vendor, passed, skipped in (("postgresql", 350, 0), ("sqlite", 322, 28)):
        environment = {**env, "USE_SQLITE": "true" if vendor == "sqlite" else "false",
                       "SQLITE_PATH": str(output / ("synthetic-" + vendor + ".sqlite3"))}
        suite("foundation-" + vendor, ["domain/tests"], passed, skipped, environment)
        suite("product-" + vendor, product, 68, 0, environment)
        run([sys.executable, "-m", "django", "migrate", "--noinput"], cwd=app, env=environment)
        run([sys.executable, "-m", "django", "makemigrations", "--check", "--dry-run"], cwd=app, env=environment)
    chrome = output / "chrome-linux64.zip"
    with urllib.request.urlopen("https://storage.googleapis.com/chrome-for-testing-public/152.0.7977.64/linux64/chrome-linux64.zip", timeout=180) as response:
        with chrome.open("xb") as stream: shutil.copyfileobj(response, stream)
    require(sha256_file(chrome) == "8b592f066af71f054aab2cc80fc26f73c775c6d44ebb99d16ade924b24756c2e",
            "BLOCKED_G10_RUNTIME_IDENTITY_DRIFT", "accepted Chromium archive")
    chrome_root = output / "chromium-test-only"
    with zipfile.ZipFile(chrome) as archive:
        for member in archive.infolist():
            require(safe_member(member.filename.rstrip("/")), "BLOCKED_G10_PACKAGE_MEMBER_DRIFT", "Chromium path")
        archive.extractall(chrome_root)
    chrome_bin = chrome_root / "chrome-linux64/chrome"
    for executable in ("chrome", "chrome_crashpad_handler", "chrome_sandbox"):
        (chrome_bin.parent / executable).chmod(0o755)
    suite("chromium", browsers, 10, 0, {**env, "USE_SQLITE": "false", "STUDIO_CHROME_BIN": str(chrome_bin)})
    suite("g10-portable", ["owner_alpha_package/tests/test_manifest.py",
                         "owner_alpha_package/tests/test_linux_contract.py"], 10, 0,
          {**env, "G10_ARTIFACT_DIR": str(output)})
    # Only public synthetic test results are indexed, never a database or backup.
    (output / "regression-evidence.json").write_bytes(canonical({
        "schema": "G10_PARENT_REGRESSION_EVIDENCE_V1", "source": source,
        "wheel": identity(wheel), "zip": identity(output / ZIP_NAME), "matrices": reports,
        "real_windows_e2e": "NOT_EXECUTED",
    }))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--regressions", action="store_true")
    args = parser.parse_args()
    if args.regressions:
        regressions(args.repository.resolve(), args.output.resolve())
    else:
        print(canonical(build(args.repository.resolve(), args.output.resolve())).decode(), end="")

if __name__ == "__main__":
    main()
