# Copyright 2026 Oliver R. Calazans Jeronimo
# Modified from the original project git-dumper (Copyright (c) 2017 Maxime Arthaud)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import urllib
import os
import re
from dataclasses import dataclass
from pathlib     import Path



@dataclass(slots=True)
class Arguments:
    cert_p12_pwd : str
    cert_p12     : str
    url          : str
    directory    : str
    proxy        : str
    jobs         : int
    retry        : int
    timeout      : int
    http_headers : dict[str, str]
    branches     : list[str]
    delay        : float



class Parser:

    __slots__ = ('_args', '_parser')

    def __init__(self):
        self._args   : argparse.Namespace      = None
        self._parser : argparse.ArgumentParser = None



    def parse(self):
        self._create_args()
        self._args = self._parser.parse_args()
        self._valid_jobs()
        self._valid_retry()
        self._valid_timeout()
        self._valid_proxy()
        self._valid_certificate()
        self._valid_delay()
        self._create_dir()



    def _create_args(self):
        self._parser = argparse.ArgumentParser(
            usage="gitbleed --url example.com <ARGS>",
            description="Dump a git repository from a website.",
            formatter_class=lambda prog: argparse.HelpFormatter(
                prog,
                max_help_position=40,
                width=100,
            ),
        )
        self._parser.add_argument(
            "--url", type=str, required=True,
            help="(REQUIRED) URL of the git repository to dump"
        )
        self._parser.add_argument(
            "-o", "--output", type=str, required=True,
            help="(REQUIRED) Directory where the repository will be saved",
        )
        self._parser.add_argument("--proxy", help="Proxy URL, e.g. `socks5://127.0.0.1:9050`")
        self._parser.add_argument("--cert-p12", help="Client certificate in PKCS#12")
        self._parser.add_argument("--cert-p12-pwd", help="Password for the client certificate")
        self._parser.add_argument(
            "-d", "--delay", type=float, default=0,
            help="Delay in seconds between requests"
        )
        self._parser.add_argument(
            "-j", "--jobs", type=int, default=10,
            help="Number of simultaneous requests",
        )
        self._parser.add_argument(
            "-r", "--retry", type=int, default=3,
            help="Number of request attempts before giving up",
        )
        self._parser.add_argument(
            "-t", "--timeout", type=int, default=3,
            help="Maximum time in seconds per request",
        )
        self._parser.add_argument(
            "-u", "--user-agent", type=str,
            default="Mozilla/5.0 (Windows NT 10.0; rv:78.0) Gecko/20100101 Firefox/78.0",
            help="User-agent to use for requests",
        )
        self._parser.add_argument(
            "-H", "--header", type=str, action="append",
            help="Additional http headers, e.g `NAME=VALUE`",
        )
        self._parser.add_argument(
            "-b", "--branch", dest="branches", action="append",
            help=(
                "Additional branch names to check for, e.g. `-b dev -b prod`. "
                "The default branches (`main`, `master`, `staging`, `production`, "
                "`development`) are always checked."
            ),
        )

    
    def _valid_jobs(self):
        if self._args.jobs < 1:
            self._parser.error(f"Invalid number of jobs, got {self._args.jobs}")

    
    def _valid_retry(self):
        if self._args.retry < 1:
            self._parser.error(f"Invalid number of retries, got {self._args.retry}")

    
    def _valid_timeout(self):
        if self._args.timeout < 1:
            self._parser.error(f"Invalid timeout, got {self._args.timeout}")

    
    def _valid_delay(self):
        if self._args.delay < 0:
            self._parser.error(f"Delay value cannot be negative. Got {self._args.delay}")

    
    def _valid_proxy(self):
        if not self._args.proxy:
            return

        raw = self._args.proxy
        if "://" not in raw:
            raw = "socks5://" + raw

        try:
            parsed = urllib.parse.urlparse(raw)
        except ValueError as e:
            self._parser.error(f"Invalid proxy, got {self._args.proxy}: {e}")

        if parsed.scheme not in ("socks5", "socks5h", "socks4", "socks4a", "http", "https"):
            self._parser.error(
                f"Unsupported proxy scheme '{parsed.scheme}' in {self._args.proxy}"
            )

        if not parsed.hostname or not parsed.port:
            self._parser.error(f"Invalid proxy, got {self._args.proxy}")

        self._args.proxy = f"{parsed.scheme}://{parsed.netloc}"

    
    
    def _create_dir(self):
        if self._args.output == "":
            self._args.output = Path(__file__).resolve().parent

        if not os.path.isdir(self._args.output):
            self._parser.error(f"{self._args.output} is not a directory")

        url = re.sub(r"^https?://", "", self._args.url)
        self._args.output = os.path.join(self._args.output, url)

        if not os.path.exists(self._args.output):
            os.makedirs(self._args.output)

    
    
    def _valid_certificate(self):
        if not self._args.cert_p12:
            return

        if not os.path.exists(self._args.cert_p12):
            self._parser.error(
                f"Client certificate {self._args.cert_p12} does not exist"
            )

        if not os.path.isfile(self._args.cert_p12):
            self._parser.error(
                f"Client certificate {self._args.cert_p12} is not a file"
            )

        if not self._args.cert_p12_pwd:
            self._parser.error("Client certificate password is required")

    
    
    def _valid_headers(self) -> dict:
        http_headers = {
            "User-Agent": self._args.user_agent,
            "Accept": "*/*",
        }

        if not self._args.header:
            return http_headers

        for header in self._args.header:
            tokens: list[str] = header.split("=", maxsplit=1)

            if len(tokens) != 2:
                self._parser.error(
                    f"HTTP header must have the form NAME=VALUE, got {header}"
                )

            name, value = tokens
            http_headers[name.strip()] = value.strip()

        return http_headers

    
    
    def get_args(self) -> Arguments:
        return Arguments(
            cert_p12_pwd = self._args.cert_p12_pwd,
            cert_p12     = self._args.cert_p12,
            directory    = self._args.output,
            proxy        = self._args.proxy,
            url          = self._args.url,
            jobs         = self._args.jobs,
            retry        = self._args.retry,
            timeout      = self._args.timeout,
            http_headers = self._valid_headers(),
            branches     = self._args.branches,
            delay        = self._args.delay,
        )