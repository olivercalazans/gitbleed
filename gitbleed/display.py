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

import sys
import requests
from check import is_html



class Display:

    HTML: str = " [\033[34mHTML\033[0m] "

    @staticmethod
    def response(response: requests.Response):
        code = response.status_code

        if   code >= 400: x = f"\033[31m{code}\033[0m"
        elif code >= 300: x = f"\033[33m{code}\033[0m"
        elif code >= 200: x = f"\033[32m{code}\033[0m"
        else:             x = f"{code}"

        z = Display.HTML if is_html(response) else ' '

        print(f"[{x}]{z}{response.url}", flush=True)


    @staticmethod
    def section(text: str):
        print(f"[###] {text}", flush=True)


    @staticmethod
    def warning(text: str):
        print(f"[\033[33m{'!!!'}\033[0m] {text}", flush=True)

    
    @staticmethod
    def fatal(text: str):
        print(f"[\033[31m{'ERR'}\033[0m] {text}", flush=True)
        sys.exit(1)


    @staticmethod
    def success(text: str):
        print(f"[\033[32m{'OK!'}\033[0m] {text}", flush=True)


    @staticmethod
    def passing(text: str):
        print(f"[---] {text}", flush=True)